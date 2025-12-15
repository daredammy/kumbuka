#!/usr/bin/env python3
"""
Kumbuka Calendar Monitor

Watches for upcoming meetings and prompts to record.
"""

import subprocess
import json
import os
from datetime import datetime
from pathlib import Path

# How many minutes before meeting to prompt
PROMPT_MINUTES_BEFORE = int(os.getenv("KUMBUKA_PROMPT_MINUTES", "2"))

# Calendars to monitor (empty = all, or comma-separated names)
CALENDARS = os.getenv("KUMBUKA_CALENDARS", "").strip()

# Track which meetings we've already prompted for
PROMPTED_FILE = Path("/tmp/kumbuka/prompted_meetings.json")
LOG_FILE = Path("/tmp/kumbuka/monitor.log")


def log(msg: str):
    """Write to log file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()}: {msg}\n")


def get_upcoming_events(minutes_ahead: int = 5) -> list[dict]:
    """Get calendar events starting in the next N minutes."""
    
    # Build calendar filter
    if CALENDARS:
        cal_names = [c.strip() for c in CALENDARS.split(",")]
        cal_loop = "\n".join([f'        set end of calList to calendar "{name}"' for name in cal_names])
        cal_setup = f'''
    set calList to {{}}
    try
{cal_loop}
    end try
'''
    else:
        cal_setup = "    set calList to every calendar"
    
    script = f'''
set now to current date
set soonEnd to now + ({minutes_ahead} * 60)
set output to ""

tell application "Calendar"
{cal_setup}
    repeat with cal in calList
        try
            set calEvents to (every event of cal whose start date >= now and start date <= soonEnd)
            repeat with evt in calEvents
                set evtTitle to summary of evt
                set evtId to uid of evt
                set output to output & evtId & "|||" & evtTitle & linefeed
            end repeat
        end try
    end repeat
end tell

return output
'''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            events = []
            for line in result.stdout.strip().split("\n"):
                if "|||" in line:
                    parts = line.split("|||", 1)
                    events.append({"id": parts[0], "title": parts[1] if len(parts) > 1 else "Meeting"})
            return events
    except subprocess.TimeoutExpired:
        log("AppleScript timeout - try setting KUMBUKA_CALENDARS to specific calendar names")
    except Exception as e:
        log(f"Error getting events: {e}")
    
    return []


def load_prompted() -> set:
    """Load set of already-prompted meeting IDs."""
    if PROMPTED_FILE.exists():
        try:
            data = json.loads(PROMPTED_FILE.read_text())
            cutoff = datetime.now().timestamp() - 86400
            return {k for k, v in data.items() if v > cutoff}
        except:
            pass
    return set()


def save_prompted(prompted: set):
    """Save prompted meeting IDs with timestamps."""
    PROMPTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {mid: datetime.now().timestamp() for mid in prompted}
    PROMPTED_FILE.write_text(json.dumps(data))


def show_record_dialog(title: str) -> bool:
    """Show dialog asking if user wants to record."""
    safe_title = title.replace('"', '\\"').replace("'", "'")
    
    script = f'''
tell application "System Events"
    activate
    set dialogResult to display dialog "Meeting starting soon:" & return & return & "{safe_title}" & return & return & "Would you like to record?" buttons {{"Skip", "Record"}} default button "Record" with title "Kumbuka" giving up after 30
    
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
            timeout=35
        )
        return result.stdout.strip() == "yes"
    except:
        return False


def start_recording():
    """Launch kumbuka in a new Terminal window."""
    script = '''
tell application "Terminal"
    activate
    do script "kumbuka"
end tell
'''
    subprocess.run(["osascript", "-e", script])


def check_meetings():
    """Main check - called periodically."""
    events = get_upcoming_events(PROMPT_MINUTES_BEFORE)
    log(f"Checked - found {len(events)} upcoming events")
    
    if not events:
        return
    
    prompted = load_prompted()
    
    for event in events:
        event_id = event.get("id", "")
        title = event.get("title", "Untitled Meeting")
        
        if event_id in prompted:
            continue
        
        prompted.add(event_id)
        save_prompted(prompted)
        
        log(f"Prompting for: {title}")
        
        if show_record_dialog(title):
            start_recording()
            break


def main():
    """Entry point for daemon."""
    check_meetings()


if __name__ == "__main__":
    main()
