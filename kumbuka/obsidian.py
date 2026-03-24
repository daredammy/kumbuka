"""Obsidian vault writer."""

from pathlib import Path
from .filenames import sanitize_filename


def _resolve_target_dir(vault_path: str, folder: str = "") -> Path:
    """Resolve and validate the target directory inside the vault."""
    vault_root = Path(vault_path).expanduser().resolve()
    if not vault_root.exists():
        raise RuntimeError(f"Obsidian vault does not exist: {vault_root}")
    if not vault_root.is_dir():
        raise RuntimeError(f"Obsidian vault is not a directory: {vault_root}")

    subdir = Path(folder.strip("/")) if folder else Path()
    target_dir = (vault_root / subdir).resolve()
    try:
        target_dir.relative_to(vault_root)
    except ValueError as exc:
        raise RuntimeError("KUMBUKA_OBSIDIAN_FOLDER must stay within the vault") from exc

    return target_dir


def _next_available_path(path: Path) -> Path:
    """Return a non-conflicting path by adding a numeric suffix when needed."""
    if not path.exists():
        return path

    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def save_note(
    vault_path: str,
    *,
    title: str,
    content: str,
    filename: str | None = None,
    folder: str = "",
) -> Path:
    """Write a markdown note into an Obsidian vault."""
    target_dir = _resolve_target_dir(vault_path, folder)
    target_dir.mkdir(parents=True, exist_ok=True)

    note_name = (filename or "").strip()
    if note_name.lower().endswith(".md"):
        note_name = note_name[:-3]
    note_name = sanitize_filename(note_name) or sanitize_filename(title) or "meeting-notes"

    note_path = _next_available_path(target_dir / f"{note_name}.md")
    note_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return note_path
