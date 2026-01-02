#!/usr/bin/env python3
"""
Kumbuka Calendar Monitor

Watches for upcoming meetings and prompts to record.
Uses EventKit for fast calendar access (handles large calendars).
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
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()}: {msg}\n")


def request_calendar_permission() -> bool:
    """
    Request calendar permission from the user.
    Must be run interactively (not from daemon) to show the permission dialog.
    Returns True if permission was granted.
    """
    try:
        # pylint: disable=import-outside-toplevel,no-member
        import EventKit
        import time

        store = EventKit.EKEventStore.alloc().init()

        # Check current authorization status
        status = EventKit.EKEventStore.authorizationStatusForEntityType_(
            EventKit.EKEntityTypeEvent
        )

        # EKAuthorizationStatus: 0=NotDetermined, 1=Restricted, 2=Denied, 3=Authorized, 4=FullAccess
        if status in (3, 4):  # Already authorized
            return True

        if status == 2:  # Denied
            print("❌ Calendar access was previously denied.")
            print("   Go to System Settings → Privacy & Security → Calendars")
            print("   and enable access for Python/Terminal.")
            return False

        # Request access - this triggers the permission dialog
        granted = [None]  # Use list to allow mutation in callback

        def callback(success, _error):
            granted[0] = success

        # Try the newer API first (macOS 14+), fall back to older API
        try:
            store.requestFullAccessToEventsWithCompletion_(callback)
        except AttributeError:
            # Older macOS - use legacy API
            store.requestAccessToEntityType_completion_(
                EventKit.EKEntityTypeEvent, callback
            )

        # Wait for the callback (user interaction with dialog)
        timeout = 60  # Give user time to respond to dialog
        start = time.time()
        while granted[0] is None and (time.time() - start) < timeout:
            # Process events to allow the dialog to work
            from Foundation import NSRunLoop, NSDate
            NSRunLoop.currentRunLoop().runUntilDate_(
                NSDate.dateWithTimeIntervalSinceNow_(0.1)
            )

        if granted[0]:
            print("✅ Calendar permission granted!")
            return True

        print("❌ Calendar permission denied or timed out.")
        return False

    except ImportError:
        print("❌ EventKit not available. Install with: pip install pyobjc-framework-EventKit")
        return False
    # pylint: disable=broad-exception-caught
    except Exception as e:
        print(f"❌ Error requesting permission: {e}")
        return False


def get_upcoming_events_eventkit(minutes_ahead: int = 5) -> list[dict]:
    """Get calendar events using EventKit (fast, handles large calendars)."""
    try:
        # pylint: disable=import-outside-toplevel,no-member
        import EventKit
        from Foundation import NSDate

        store = EventKit.EKEventStore.alloc().init()

        # Get calendars
        all_calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)

        if not all_calendars:
            log("EventKit: No calendars found - check Calendar permissions in System Settings")
            return []

        # Filter calendars if specified
        if CALENDARS:
            cal_names = [c.strip().lower() for c in CALENDARS.split(",")]
            calendars = [c for c in all_calendars if c.title().lower() in cal_names]
            if not calendars:
                log(f"EventKit: No matching calendars for {CALENDARS}")
                return []
        else:
            calendars = list(all_calendars)

        # Time range
        now = NSDate.date()
        end = NSDate.dateWithTimeIntervalSinceNow_(minutes_ahead * 60)

        # Create predicate and fetch events
        predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
            now, end, calendars
        )
        events = store.eventsMatchingPredicate_(predicate)

        result = []
        for evt in events:
            result.append({
                "id": evt.eventIdentifier(),
                "title": evt.title() or "Untitled"
            })

        return result

    except ImportError:
        log("EventKit not available, falling back to AppleScript")
        return get_upcoming_events_applescript(minutes_ahead)
    # pylint: disable=broad-exception-caught
    except Exception as e:
        log(f"EventKit error: {e}")
        return []


def get_upcoming_events_applescript(minutes_ahead: int = 5) -> list[dict]:
    """Fallback: Get events via AppleScript (requires Calendar.app to be running)."""
    # Ensure Calendar.app is running (launches in background if not)
    subprocess.run(
        ["osascript", "-e", 'tell application "Calendar" to launch'],
        capture_output=True,
        timeout=5,
        check=False
    )

    if CALENDARS:
        cal_names = [c.strip() for c in CALENDARS.split(",")]
        cal_loop = "\n".join(
            [f'        set end of calList to calendar "{name}"' for name in cal_names]
        )
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
            timeout=15,
            check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            events = []
            for line in result.stdout.strip().split("\n"):
                if "|||" in line:
                    parts = line.split("|||", 1)
                    events.append({
                        "id": parts[0],
                        "title": parts[1] if len(parts) > 1 else "Meeting"
                    })
            return events
    except subprocess.TimeoutExpired:
        log("AppleScript timeout - calendar has too many events. "
            "Grant EventKit permissions in System Settings")
    # pylint: disable=broad-exception-caught
    except Exception as e:
        log(f"AppleScript error: {e}")

    return []


def get_upcoming_events_osascript_direct(minutes_ahead: int = 5) -> list[dict]:
    """Get events by running osascript via /bin/sh (may have better permission inheritance)."""
    if CALENDARS:
        cal_filter = f'calendar "{CALENDARS.split(",")[0].strip()}"'
        cal_setup = f'set calList to {{{cal_filter}}}'
    else:
        cal_setup = 'set calList to every calendar'

    # Use a simpler script structure
    script = f'''
tell application "Calendar"
    set now to current date
    set soonEnd to now + ({minutes_ahead} * 60)
    {cal_setup}
    set output to ""
    repeat with cal in calList
        try
            set calEvents to (every event of cal whose start date >= now and start date <= soonEnd)
            repeat with evt in calEvents
                set output to output & (uid of evt) & "|||" & (summary of evt) & linefeed
            end repeat
        end try
    end repeat
    return output
end tell
'''
    try:
        # Run via /bin/sh to potentially inherit different permissions
        result = subprocess.run(
            ['/bin/sh', '-c', f'osascript -e {repr(script)}'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            events = []
            for line in result.stdout.strip().split("\n"):
                if "|||" in line:
                    parts = line.split("|||", 1)
                    events.append({
                        "id": parts[0],
                        "title": parts[1] if len(parts) > 1 else "Meeting"
                    })
            return events
    except subprocess.TimeoutExpired:
        log("osascript direct timeout")
    # pylint: disable=broad-exception-caught
    except Exception as e:
        log(f"osascript direct error: {e}")
    return []


def get_upcoming_events(minutes_ahead: int = 5) -> list[dict]:
    """Get upcoming events, trying EventKit first, then AppleScript."""
    # If KUMBUKA_USE_APPLESCRIPT is set, skip EventKit (useful for permission issues)
    if os.getenv("KUMBUKA_USE_APPLESCRIPT"):
        log("Using AppleScript (KUMBUKA_USE_APPLESCRIPT set)")
        return get_upcoming_events_applescript(minutes_ahead)

    events = get_upcoming_events_eventkit(minutes_ahead)
    # If EventKit returns nothing, try AppleScript, then osascript direct
    if not events:
        log("EventKit returned no events, trying AppleScript fallback")
        events = get_upcoming_events_applescript(minutes_ahead)
    if not events:
        log("AppleScript returned no events, trying osascript direct")
        events = get_upcoming_events_osascript_direct(minutes_ahead)
    return events


def load_prompted() -> set:
    """Load set of already-prompted meeting IDs."""
    if PROMPTED_FILE.exists():
        try:
            data = json.loads(PROMPTED_FILE.read_text(encoding="utf-8"))
            cutoff = datetime.now().timestamp() - 86400
            return {k for k, v in data.items() if v > cutoff}
        # pylint: disable=broad-exception-caught
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


    safe_title = title.replace('"', '\\"').replace("'", "'")





    script = f'''


tell application "System Events"


    activate


    set msg to "Meeting starting soon:" & return & return


    set msg to msg & "{safe_title}" & return & return


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


    # pylint: disable=broad-exception-caught


    except Exception:


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
