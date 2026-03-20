#!/usr/bin/env python3
"""
Kumbuka Meeting Monitor

Detects meetings via Calendar scraper and auto-records or prompts to record.
"""

import subprocess
import json
from datetime import datetime

from kumbuka.config import OUTPUT_DIR, LOG_DIR, PROMPT_MINUTES, AUTO_RECORD, BUFFER_MINUTES
from kumbuka.runtime import find_python

LOG_FILE = LOG_DIR / "monitor.log"
PROMPTED_FILE = OUTPUT_DIR / "prompted_meetings.json"


def log(msg: str):
    """Write to log file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()}: {msg}\n")


def is_recording_in_progress() -> bool:
    """Check if kumbuka is currently recording (has a .partial.wav file)."""
    if not OUTPUT_DIR.exists():
        return False
    return any(OUTPUT_DIR.glob("*.partial.wav"))


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

    python_path = find_python()
    auto_log = LOG_DIR / "auto_record.log"
    auto_log.parent.mkdir(parents=True, exist_ok=True)

    log(f"Starting auto-record: {event.title} (duration={duration}s)")
    subprocess.Popen(
        [python_path, "-m", "kumbuka", "record-only", "--duration", str(duration)],
        stdout=open(auto_log, "a"),
        stderr=subprocess.STDOUT,
    )


def check_calendar():
    """Check calendar and auto-record or prompt if meeting found."""
    try:
        from kumbuka.calendar_scraper import get_upcoming_events, get_current_meetings
        from kumbuka.meeting_filter import should_record

        prompted = load_prompted()

        events = get_upcoming_events(PROMPT_MINUTES) + get_current_meetings()

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
