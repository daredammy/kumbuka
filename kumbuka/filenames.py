"""Shared filename helpers."""

import re


def sanitize_filename(name: str) -> str | None:
    """Sanitize a string into a filesystem-safe filename."""
    name = re.sub(r"[^a-z0-9-]", "-", name.lower())
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:60] if name else None
