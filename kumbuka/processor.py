"""Claude processing functionality."""

import shutil
import subprocess
from pathlib import Path

from .config import PROMPTS_DIR, NOTION_URL, NOTION_MODE


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


def process_with_claude(
    transcript: str,
    duration: str,
    timestamp: str,
    prompt_name: str = "meeting"
) -> None:
    """
    Send transcript to Claude for processing.

    Args:
        transcript: Raw transcript text
        duration: Recording duration string
        timestamp: Recording timestamp string
        prompt_name: Which prompt template to use
    """
    print("\n🤖 Sending to Claude...")

    # Load and format prompt
    template = load_prompt(prompt_name)

    # Build Notion instructions only if URL is configured
    notion_instructions = ""
    if NOTION_URL:
        if NOTION_MODE == "mcp":
            # MCP mode: Use Claude Code's Notion MCP integration
            notion_instructions = f"""

7. **CREATE A NEW NOTION SUBPAGE** for this meeting:
   Parent page: {NOTION_URL}

   Use the Notion MCP tools to create a new subpage under the parent page.

   Steps:
   a) Use notion-fetch to get the parent page ID from the URL
   b) Use notion-create-pages to create a new subpage with:
      - Title: the generated meeting title
      - Content: participants, summary, then the cleaned transcript
      - Format with markdown: ## for headers, - for bullets, --- for dividers

   Each meeting must have its own separate subpage."""
        else:
            # Token mode: Use the kumbuka.notion CLI with NOTION_TOKEN
            notion_instructions = f"""

7. **CREATE A NEW NOTION SUBPAGE** for this meeting:
   Parent page: {NOTION_URL}

   Use the Bash command below to create the page (requires NOTION_TOKEN env var).

   Steps:
   a) First, write the meeting notes to a temporary file /tmp/meeting_notes.md
      Format with markdown: ## for headers, - for bullets, --- for dividers
   b) Run this exact command via Bash:
      ~/.local/share/uv/tools/kumbuka/bin/python -m kumbuka.notion create "{NOTION_URL}" "<meeting_title>" /tmp/meeting_notes.md
   c) The command outputs the new page URL - include it in your response

   Each meeting must have its own separate subpage. Use the generated title as
   the page title. Include participants, summary, then the cleaned transcript."""

    prompt = template.format(
        transcript=transcript,
        duration=duration,
        timestamp=timestamp,
        notion_instructions=notion_instructions
    )

    # Run Claude
    claude = find_claude()
    if not claude:
        raise RuntimeError("Claude CLI not found")

    subprocess.run([claude, "-p", prompt], check=True)
