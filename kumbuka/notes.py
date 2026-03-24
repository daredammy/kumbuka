"""Note destination selection and save helpers."""

from typing import Optional

VALID_DESTINATIONS = {"terminal", "notion", "obsidian"}


def resolve_destination(
    configured: str | None,
    *,
    notion_url: str = "",
    obsidian_vault: str = "",
) -> str:
    """Resolve the configured notes destination with backward-compatible fallbacks."""
    destination = (configured or "").strip().lower()
    if destination:
        if destination not in VALID_DESTINATIONS:
            raise RuntimeError(
                "Unsupported KUMBUKA_NOTES_DESTINATION. "
                "Expected one of: terminal, notion, obsidian"
            )
        return destination

    if notion_url:
        return "notion"
    if obsidian_vault:
        return "obsidian"
    return "terminal"


def save_meeting_notes(
    result: dict,
    *,
    destination: str,
    notion_url: str = "",
    notion_mode: str = "token",
    obsidian_vault: str = "",
    obsidian_folder: str = "",
) -> Optional[tuple[str, str]]:
    """Persist meeting notes to the configured destination."""
    if destination not in VALID_DESTINATIONS:
        raise RuntimeError(
            "Unsupported notes destination. "
            "Expected one of: terminal, notion, obsidian"
        )
    if destination == "terminal":
        return None

    from .render import format_notes

    title = result.get("title", "Untitled Meeting")
    content = format_notes(result)

    if destination == "notion":
        if notion_mode != "token":
            return "notion", "mcp-handled"
        if not notion_url:
            raise RuntimeError(
                "KUMBUKA_NOTION_URL is required when KUMBUKA_NOTES_DESTINATION is notion"
            )

        from .notion import create_page

        page = create_page(notion_url, title, content)
        return "notion", page["url"]

    if not obsidian_vault:
        raise RuntimeError(
            "KUMBUKA_OBSIDIAN_VAULT is required when KUMBUKA_NOTES_DESTINATION is obsidian"
        )

    from .obsidian import save_note

    note_path = save_note(
        obsidian_vault,
        title=title,
        content=content,
        filename=result.get("filename"),
        folder=obsidian_folder,
    )
    return "obsidian", str(note_path)
