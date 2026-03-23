#!/usr/bin/env python3
"""
Kumbuka Meeting Monitor

Detects meetings via Calendar scraper and auto-records or prompts to record.
"""

import subprocess
import json
import time
from datetime import datetime

from kumbuka.config import OUTPUT_DIR, LOG_DIR, PROMPT_MINUTES, AUTO_RECORD, BUFFER_MINUTES
from kumbuka.runtime import find_python

LOG_FILE = LOG_DIR / "monitor.log"
PROMPTED_FILE = OUTPUT_DIR / "prompted_meetings.json"


MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB


def _rotate_if_needed(path):
    """Rotate log file if it exceeds MAX_LOG_BYTES. Keeps one backup."""
    try:
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            backup = path.with_suffix(path.suffix + ".1")
            if backup.exists():
                backup.unlink()
            path.rename(backup)
    except OSError:
        pass


def log(msg: str):
    """Write to log file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_needed(LOG_FILE)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()}: {msg}\n")


RECORDING_LOCK = OUTPUT_DIR / ".recording.lock"

# A .partial.wav not modified in this many seconds is considered stale
# (abandoned by a crashed recorder).
_PARTIAL_STALE_SECONDS = 120


def is_recording_in_progress() -> bool:
    """Check if kumbuka is currently recording.

    Uses both a lock file (covers the first 10s before .partial.wav exists)
    and the .partial.wav glob (covers the rest of the recording).
    Stale artifacts from crashed recordings are ignored and cleaned up.
    """
    if not OUTPUT_DIR.exists():
        return False

    now = time.time()
    for partial in OUTPUT_DIR.glob("*.partial.wav"):
        age = now - partial.stat().st_mtime
        if age < _PARTIAL_STALE_SECONDS:
            return True
        log(f"Stale partial detected ({partial.name}, {age:.0f}s old) — ignoring")

    if RECORDING_LOCK.exists():
        try:
            import os
            pid = int(RECORDING_LOCK.read_text().strip())
            os.kill(pid, 0)  # signal 0 = existence check
            return True
        except (ValueError, OSError, ProcessLookupError):
            RECORDING_LOCK.unlink(missing_ok=True)
    return False


def load_prompted() -> set:
    """Load set of already-prompted meeting IDs."""
    if PROMPTED_FILE.exists():
        try:
            data = json.loads(PROMPTED_FILE.read_text(encoding="utf-8"))
            cutoff = datetime.now().timestamp() - 86400  # 24 hours
            return {k for k, v in data.items() if v > cutoff}
        except Exception:
            pass
    return set()


def save_prompted(prompted: set):
    """Save prompted meeting IDs with timestamps."""
    PROMPTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {mid: datetime.now().timestamp() for mid in prompted}
    PROMPTED_FILE.write_text(json.dumps(data), encoding="utf-8")


def show_record_dialog(title: str) -> bool:
    """Show dialog asking if user wants to record."""
    safe_title = title.replace('"', '\\"').replace("'", "\u2019")

    script = f'''
tell application "System Events"
    activate
    set msg to "Meeting: {safe_title}" & return & return
    set msg to msg & "Would you like to record?"

    set dialogResult to display dialog msg buttons {{"Skip", "Record"}} \u00ac
        default button "Record" with title "Kumbuka" giving up after 30

    if button returned of dialogResult is "Record" then
        return "yes"
    else
        return "no"
    end if
end tell
'''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=35,
            check=False
        )
        return result.stdout.strip() == "yes"
    except Exception:
        return False


def start_recording_in_terminal():
    """Launch kumbuka in a new Terminal window (dialog mode)."""
    script = '''
tell application "Terminal"
    activate
    do script "kumbuka"
end tell
'''
    subprocess.run(["osascript", "-e", script], check=False)


def start_auto_recording(event):
    """Start headless recording for meeting duration + buffer."""
    from datetime import timezone as tz

    now = datetime.now(tz.utc)
    # Convert event.end to UTC-aware if needed
    event_end = event.end
    if event_end.tzinfo is None:
        event_end = event_end.replace(tzinfo=tz.utc)
    elif event_end.tzinfo != tz.utc:
        event_end = event_end.astimezone(tz.utc)

    remaining = (event_end - now).total_seconds()
    buffer = BUFFER_MINUTES * 60
    duration = max(int(remaining + buffer), 300)  # minimum 5 min

    # Cap at MAX_DURATION to prevent runaway recordings
    from kumbuka.config import MAX_DURATION
    duration = min(duration, MAX_DURATION)

    python_path = find_python()
    auto_log = LOG_DIR / "auto_record.log"
    auto_log.parent.mkdir(parents=True, exist_ok=True)

    log(f"Starting auto-record: {event.title} (duration={duration}s)")
    log_fh = open(auto_log, "a")
    proc = subprocess.Popen(
        [python_path, "-m", "kumbuka", "record-only", "--duration", str(duration)],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )

    # Write lock file with PID so the next monitor tick doesn't start a second recording.
    RECORDING_LOCK.parent.mkdir(parents=True, exist_ok=True)
    RECORDING_LOCK.write_text(str(proc.pid))


def check_calendar():
    """Check calendar and auto-record or prompt if meeting found."""
    try:
        from kumbuka.calendar_scraper import get_upcoming_events, get_current_meetings
        from kumbuka.meeting_filter import should_record

        prompted = load_prompted()

        # Deduplicate: same event can appear in both upcoming and current lists
        # with different IDs if the textContent varies between scrapes.
        all_events = get_upcoming_events(PROMPT_MINUTES) + get_current_meetings()
        seen_titles = set()
        events = []
        for e in all_events:
            key = (e.title, e.start.strftime("%Y-%m-%d %H:%M"))
            if key not in seen_titles:
                seen_titles.add(key)
                events.append(e)

        for event in events:
            if event.id in prompted:
                continue

            if not should_record(event):
                log(f"Skipping: {event.title}")
                prompted.add(event.id)
                save_prompted(prompted)
                continue

            prompted.add(event.id)
            save_prompted(prompted)

            if AUTO_RECORD:
                log(f"Auto-recording: {event.title}")
                start_auto_recording(event)
                return True
            else:
                log(f"Meeting detected: {event.title}")
                if show_record_dialog(f"{event.title} (starting soon)"):
                    start_recording_in_terminal()
                    return True

        event_count = len(events)
        if event_count > 0:
            log(f"Checked - {event_count} events, all already prompted or skipped")
        else:
            log("Checked - no meetings")

        return False

    except Exception as e:
        log(f"Calendar check error: {e}")
        return False


def main():
    """Entry point for daemon."""
    if is_recording_in_progress():
        log("Recording in progress - skipping")
        return

    check_calendar()


if __name__ == "__main__":
    main()
