"""Notion API wrapper for creating meeting pages."""

import os
import re
import httpx
from typing import Optional

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def get_token() -> str:
    """Get Notion API token from environment."""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise RuntimeError(
            "NOTION_TOKEN environment variable not set. "
            "Get your token from https://www.notion.so/profile/integrations"
        )
    return token


def extract_page_id(url_or_id: str) -> str:
    """
    Extract and format page ID from a Notion URL or raw ID.

    Handles:
    - Full URLs: https://www.notion.so/Page-Name-abc123...
    - Raw IDs with or without dashes
    """
    # If it's a URL, extract the ID from the end
    if "notion.so" in url_or_id:
        # Get the last segment after the last dash in the path
        match = re.search(r"([a-f0-9]{32})$", url_or_id.replace("-", ""))
        if match:
            raw_id = match.group(1)
        else:
            raise ValueError(f"Could not extract page ID from URL: {url_or_id}")
    else:
        # Remove any existing dashes
        raw_id = url_or_id.replace("-", "")

    # Validate length
    if len(raw_id) != 32:
        raise ValueError(f"Invalid page ID length: {raw_id}")

    # Format as UUID: 8-4-4-4-12
    return f"{raw_id[:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"


def create_page(
    parent_id: str,
    title: str,
    content: Optional[str] = None,
    token: Optional[str] = None
) -> dict:
    """
    Create a new page under a parent page.

    Args:
        parent_id: Parent page ID or URL
        title: Page title
        content: Optional markdown-ish content (paragraphs separated by newlines)
        token: Optional API token (defaults to NOTION_TOKEN env var)

    Returns:
        Created page object with 'id' and 'url' keys
    """
    token = token or get_token()
    parent_uuid = extract_page_id(parent_id)

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    # Build the page payload
    payload = {
        "parent": {"page_id": parent_uuid},
        "properties": {
            "title": [{"text": {"content": title}}]
        }
    }

    # Add content blocks if provided
    if content:
        payload["children"] = _text_to_blocks(content)

    response = httpx.post(
        f"{NOTION_API_URL}/pages",
        headers=headers,
        json=payload,
        timeout=30.0
    )

    if response.status_code != 200:
        raise RuntimeError(f"Notion API error: {response.status_code} - {response.text}")

    return response.json()


def append_blocks(
    page_id: str,
    content: str,
    token: Optional[str] = None
) -> dict:
    """
    Append content blocks to an existing page.

    Args:
        page_id: Page ID or URL to append to
        content: Markdown-ish content (paragraphs separated by double newlines)
        token: Optional API token

    Returns:
        API response
    """
    token = token or get_token()
    page_uuid = extract_page_id(page_id)

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    payload = {
        "children": _text_to_blocks(content)
    }

    response = httpx.patch(
        f"{NOTION_API_URL}/blocks/{page_uuid}/children",
        headers=headers,
        json=payload,
        timeout=30.0
    )

    if response.status_code != 200:
        raise RuntimeError(f"Notion API error: {response.status_code} - {response.text}")

    return response.json()


def _text_to_blocks(content: str) -> list:
    """
    Convert text content to Notion block objects.

    Handles:
    - Paragraphs (double newline separated)
    - Headers (lines starting with #, ##, ###)
    - Bullet points (lines starting with - or *)
    - Dividers (lines that are just ---)
    """
    blocks = []
    lines = content.split("\n")
    current_paragraph = []

    def flush_paragraph():
        if current_paragraph:
            text = " ".join(current_paragraph).strip()
            if text:
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": text}}]
                    }
                })
            current_paragraph.clear()

    for line in lines:
        stripped = line.strip()

        # Empty line - flush paragraph
        if not stripped:
            flush_paragraph()
            continue

        # Divider
        if stripped == "---":
            flush_paragraph()
            blocks.append({"type": "divider", "divider": {}})
            continue

        # Headers
        if stripped.startswith("### "):
            flush_paragraph()
            blocks.append({
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[4:]}}]
                }
            })
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            blocks.append({
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[3:]}}]
                }
            })
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            blocks.append({
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]
                }
            })
            continue

        # Bullet points
        if stripped.startswith("- ") or stripped.startswith("* "):
            flush_paragraph()
            blocks.append({
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]
                }
            })
            continue

        # Checkbox items
        if stripped.startswith("- [ ] "):
            flush_paragraph()
            blocks.append({
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[6:]}}],
                    "checked": False
                }
            })
            continue

        if stripped.startswith("- [x] ") or stripped.startswith("- [X] "):
            flush_paragraph()
            blocks.append({
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[6:]}}],
                    "checked": True
                }
            })
            continue

        # Regular text - accumulate for paragraph
        current_paragraph.append(stripped)

    # Flush any remaining paragraph
    flush_paragraph()

    return blocks


# CLI interface
if __name__ == "__main__":
    import sys
    import json

    usage = """
Usage: python -m kumbuka.notion <command> [args]

Commands:
    create <parent_id> <title> [content_file]
        Create a new page under parent_id with the given title.
        If content_file is provided, read content from that file.

    append <page_id> <content_file>
        Append content from file to an existing page.

Environment:
    NOTION_TOKEN - Your Notion integration token (required)

Examples:
    python -m kumbuka.notion create "https://notion.so/Meetings-abc123" "New Meeting"
    python -m kumbuka.notion create abc123 "Meeting Title" /tmp/notes.md
    python -m kumbuka.notion append abc123 /tmp/more_notes.md
"""

    if len(sys.argv) < 2:
        print(usage)
        sys.exit(1)

    command = sys.argv[1]

    if command == "create":
        if len(sys.argv) < 4:
            print("Error: create requires parent_id and title")
            print(usage)
            sys.exit(1)

        parent_id = sys.argv[2]
        title = sys.argv[3]
        content = None

        if len(sys.argv) > 4:
            with open(sys.argv[4], "r") as f:
                content = f.read()

        result = create_page(parent_id, title, content)
        print(json.dumps({"id": result["id"], "url": result["url"]}, indent=2))

    elif command == "append":
        if len(sys.argv) < 4:
            print("Error: append requires page_id and content_file")
            print(usage)
            sys.exit(1)

        page_id = sys.argv[2]
        with open(sys.argv[3], "r") as f:
            content = f.read()

        result = append_blocks(page_id, content)
        print("Content appended successfully")

    else:
        print(f"Unknown command: {command}")
        print(usage)
        sys.exit(1)
