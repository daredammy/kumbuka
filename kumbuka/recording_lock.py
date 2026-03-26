"""Recording lock to prevent overlapping recording sessions.

Both manual (``kumbuka``) and auto (``kumbuka record-only``) entry points
acquire this lock before recording.  If another session is already active
the caller gets back a :class:`RecordingInfo` describing the holder so it
can print a meaningful message instead of double-recording.
"""

import json
import os
import time
from dataclasses import dataclass

from .config import OUTPUT_DIR

LOCK_FILE = OUTPUT_DIR / "recording.lock"


@dataclass(frozen=True)
class RecordingInfo:
    """Metadata about an active recording session."""

    pid: int
    mode: str  # "manual" or "auto"
    meeting: str
    started_at: str


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it.
        return True


def get_active_recording() -> RecordingInfo | None:
    """Return info about the currently-active recording, or ``None``."""
    if not LOCK_FILE.exists():
        return None

    try:
        data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        pid = data["pid"]

        if not _is_pid_alive(pid):
            LOCK_FILE.unlink(missing_ok=True)
            return None

        return RecordingInfo(
            pid=pid,
            mode=data["mode"],
            meeting=data.get("meeting", ""),
            started_at=data.get("started_at", ""),
        )
    except (json.JSONDecodeError, KeyError):
        # Corrupted content but file owned by unknown process — leave it
        # for stale-PID cleanup on the next call rather than deleting
        # another process's lock.
        return None
    except OSError:
        return None


def acquire(mode: str, meeting: str = "") -> RecordingInfo | None:
    """Try to acquire the recording lock.

    Returns ``None`` on success (lock acquired), or a :class:`RecordingInfo`
    describing the current holder on conflict.

    Uses O_CREAT|O_EXCL for atomic creation to avoid TOCTOU races when
    multiple processes attempt to acquire simultaneously.
    """
    active = get_active_recording()
    if active is not None:
        return active

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "pid": os.getpid(),
        "mode": mode,
        "meeting": meeting,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, json.dumps(data).encode("utf-8"))
        finally:
            os.close(fd)
        return None
    except FileExistsError:
        # Another process created the lock between our check and create
        return get_active_recording()


def release():
    """Release the recording lock if held by this process."""
    try:
        if not LOCK_FILE.exists():
            return
        data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        if data.get("pid") == os.getpid():
            LOCK_FILE.unlink(missing_ok=True)
    except (json.JSONDecodeError, KeyError, OSError):
        pass
