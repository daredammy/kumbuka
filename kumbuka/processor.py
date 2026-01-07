"""Claude processing functionality."""

import shutil
import subprocess
from pathlib import Path

from .config import PROMPTS_DIR, NOTION_URL


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
        notion_instructions = f"""

6. **CREATE A NEW NOTION SUBPAGE** for this meeting in the Meetings database:
   {NOTION_URL}

   IMPORTANT: Each meeting must have its own separate subpage. Do NOT update or
   modify any existing pages - always create a fresh new subpage for this meeting.

   Use the generated title as the page title. Include participants, summary,
   then the cleaned transcript."""

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
