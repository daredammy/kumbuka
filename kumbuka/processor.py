"""Claude processing functionality."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import PROMPTS_DIR, NOTION_URL, NOTION_MODE, USER_NAME

OUTPUT_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Concise, descriptive meeting title"
        },
        "filename": {
            "type": "string",
            "description": (
                "Filename-safe title: lowercase, hyphens, no special chars, "
                "max 60 chars. Example: product-roadmap-planning-q1"
            )
        },
        "participants": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Each entry is a participant with role if discernible, "
                "e.g. 'Sarah (Engineering Lead)'"
            )
        },
        "summary": {
            "type": "string",
            "description": (
                "Meeting summary in markdown. Include decisions, action items, "
                "key discussion points, and other relevant sections"
            )
        },
        "feedback": {
            "type": "string",
            "description": (
                "Communication feedback for the host. "
                "Empty string if solo session or not applicable"
            )
        },
        "transcript": {
            "type": "string",
            "description": (
                "Cleaned transcript: grammar fixed, filler words removed, "
                "speaker-attributed paragraphs"
            )
        }
    },
    "required": ["title", "filename", "participants", "summary", "transcript"]
})


def find_claude() -> str | None:
    """Find claude CLI in PATH or common locations."""
    # Check PATH first
    claude = shutil.which("claude")
    if claude:
        return claude

    # Check common locations
    locations = [
        Path.home() / ".npm-global/bin/claude",
        Path.home() / ".local/bin/claude",
        Path("/usr/local/bin/claude"),
    ]
    for loc in locations:
        if loc.exists():
            return str(loc)

    return None


def load_prompt(name: str = "meeting") -> str:
    """
    Load a prompt template from the prompts directory.

    Args:
        name: Prompt name (without .txt extension)

    Returns:
        Prompt template string
    """
    prompt_file = PROMPTS_DIR / f"{name}.txt"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_file}")
    return prompt_file.read_text()


def sanitize_filename(name: str) -> str | None:
    """Sanitize a string into a safe filename."""
    name = re.sub(r"[^a-z0-9-]", "-", name.lower())
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:60] if name else None


def _run_claude_structured(
    claude: str, prompt: str
) -> dict | None:
    """Run Claude with stream-json + json-schema, stream progress, return structured output."""
    env = {**os.environ, "CLAUDECODE": ""}  # cspell:ignore CLAUDECODE
    with subprocess.Popen(
        [
            claude, "-p", prompt,
            "--output-format", "stream-json",
            "--json-schema", OUTPUT_SCHEMA,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    ) as proc:
        structured_output = None
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Print assistant text to terminal (progress updates)
            if event.get("type") == "assistant":
                message = event.get("message", {})
                for block in message.get("content", []):
                    if block.get("type") == "text":
                        sys.stdout.write(block["text"])
                        sys.stdout.flush()

            # Capture structured output from result
            if event.get("type") == "result":
                structured_output = event.get("structured_output")

        proc.wait()
        if proc.returncode != 0:
            assert proc.stderr is not None
            stderr = proc.stderr.read()
            raise subprocess.CalledProcessError(proc.returncode, claude, stderr)

    return structured_output


def format_notes(result: dict) -> str:
    """Format structured output as readable markdown for terminal display."""
    sections = []

    title = result.get("title", "Untitled Meeting")
    sections.append(f"# {title}")

    participants = result.get("participants", [])
    if participants:
        sections.append("## Participants")
        sections.append("\n".join(f"- {p}" for p in participants))

    summary = result.get("summary", "")
    if summary:
        sections.append("## Summary")
        sections.append(summary)

    feedback = result.get("feedback", "")
    if feedback:
        sections.append("## Communication Feedback")
        sections.append(feedback)

    transcript = result.get("transcript", "")
    if transcript:
        sections.append("## Transcript")
        sections.append(transcript)

    return "\n\n".join(sections)


def process_with_claude(
    transcript: str,
    duration: str,
    timestamp: str,
    prompt_name: str = "meeting"
) -> dict | None:
    """
    Send transcript to Claude for processing.

    Args:
        transcript: Raw transcript text
        duration: Recording duration string
        timestamp: Recording timestamp string
        prompt_name: Which prompt template to use

    Returns:
        Structured output dict with title, filename, participants,
        summary, feedback, transcript — or None on failure
    """
    print("\n🤖 Sending to Claude...")

    template = load_prompt(prompt_name)

    # MCP mode: append Notion instructions so Claude creates the page via MCP tools
    notion_instructions = ""
    if NOTION_URL and NOTION_MODE == "mcp":
        notion_instructions = f"""

Also create a Notion subpage for this meeting:
- Parent page: {NOTION_URL}
- Use notion-fetch to get the parent page ID from the URL
- Use notion-create-pages to create a subpage with the meeting title
- Include participants, summary, and cleaned transcript
- Format with markdown: ## for headers, - for bullets, --- for dividers"""

    prompt = template.format(
        transcript=transcript,
        duration=duration,
        timestamp=timestamp,
        user_name=USER_NAME
    ) + notion_instructions

    claude = find_claude()
    if not claude:
        raise RuntimeError("Claude CLI not found")

    result = _run_claude_structured(claude, prompt)

    if not result:
        return None

    print(f"\n{format_notes(result)}")
    return result
