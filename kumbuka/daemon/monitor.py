#!/usr/bin/env python3
"""
Kumbuka Meeting Monitor

Detects meetings via Google Calendar and prompts to record.
Prompts when a meeting is about to start or currently in progress.
"""

import subprocess
import json
from datetime import datetime
from pathlib import Path

from kumbuka.config import TEMP_DIR, PROMPT_MINUTES

LOG_FILE = Path("/tmp/kumbuka/monitor.log")
PROMPTED_FILE = Path("/tmp/kumbuka/prompted_meetings.json")


def log(msg: str):
    """Write to log file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()}: {msg}\n")


def is_recording_in_progress() -> bool:
    """Check if kumbuka is currently recording (has a .partial.wav file)."""
    if not TEMP_DIR.exists():
        return False
    return any(TEMP_DIR.glob("*.partial.wav"))


def load_prompted() -> set:
    """Load set of already-prompted meeting IDs."""
    if PROMPTED_FILE.exists():
        try:
            data = json.loads(PROMPTED_FILE.read_text(encoding="utf-8"))
            cutoff = datetime.now().timestamp() - 86400  # 24 hours
            return {k for k, v in data.items() if v > cutoff}
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    return set()


def save_prompted(prompted: set):
    """Save prompted meeting IDs with timestamps."""
    PROMPTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {mid: datetime.now().timestamp() for mid in prompted}
    PROMPTED_FILE.write_text(json.dumps(data), encoding="utf-8")


def show_record_dialog(title: str) -> bool:
    """Show dialog asking if user wants to record."""
    safe_title = title.replace('"', '\\"').replace("'", "'")

    script = f'''
tell application "System Events"
    activate
    set msg to "Meeting: {safe_title}" & return & return
    set msg to msg & "Would you like to record?"

    set dialogResult to display dialog msg buttons {{"Skip", "Record"}} ¬
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
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def start_recording():
    """Launch kumbuka in a new Terminal window."""
    script = '''
tell application "Terminal"
    activate
    do script "kumbuka"
end tell
'''
    subprocess.run(["osascript", "-e", script], check=False)


def check_calendar():
    """Check Google Calendar for upcoming/current meetings."""
    try:
        from kumbuka.calendar import (
            is_authenticated,
            get_upcoming_events,
            get_current_meetings,
        )

        if not is_authenticated():
            log("Not authenticated with Google Calendar")
            return False

        prompted = load_prompted()

        # Check for meetings starting soon
        upcoming = get_upcoming_events(PROMPT_MINUTES)
        for event in upcoming:
            if event.id in prompted:
                continue

            prompted.add(event.id)
            save_prompted(prompted)

            log(f"Meeting starting soon: {event.title}")
            if show_record_dialog(f"{event.title} (starting soon)"):
                start_recording()
                return True

        # Check for meetings currently in progress
        current = get_current_meetings()
        for event in current:
            if event.id in prompted:
                continue

            prompted.add(event.id)
            save_prompted(prompted)

            log(f"Meeting in progress: {event.title}")
            if show_record_dialog(f"{event.title} (in progress)"):
                start_recording()
                return True

        event_count = len(upcoming) + len(current)
        if event_count > 0:
            log(f"Checked - {event_count} events, all already prompted")
        else:
            log("Checked - no meetings")

        return False

    except Exception as e:  # pylint: disable=broad-exception-caught
        log(f"Calendar check error: {e}")
        return False


def main():
    """Entry point for daemon - checks Google Calendar."""
    if is_recording_in_progress():
        log("Recording in progress - skipping")
        return

    check_calendar()


if __name__ == "__main__":
    main()
