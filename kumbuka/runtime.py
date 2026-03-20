"""Shared runtime helpers for executable discovery."""

import shutil
import sys
from pathlib import Path


def find_python() -> str:
    """Find python that has kumbuka installed.

    Checks uv tool python first, then falls back to system python.
    Uses absolute paths for LaunchAgent compatibility.
    """
    uv_python = Path.home() / ".local/share/uv/tools/kumbuka/bin/python"
    if uv_python.exists():
        return str(uv_python)

    # sys.executable is the most reliable for the running environment
    if sys.executable:
        return sys.executable

    python = shutil.which("python3") or shutil.which("python")
    return python or "/usr/bin/python3"
