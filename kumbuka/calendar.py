"""Google Calendar integration for meeting detection."""

# pylint: skip-file

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import dataclass

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CONFIG_DIR = Path.home() / ".kumbuka"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"


@dataclass
class CalendarEvent:
    """A calendar event."""

    id: str
    title: str
    start: datetime
    end: datetime
    calendar_name: str


def get_credentials():
    """Get valid credentials, refreshing if needed."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json())

    return creds


def is_authenticated() -> bool:
    """Check if we have valid credentials."""
    creds = get_credentials()
    return creds is not None and creds.valid


def authenticate():
    """Run the OAuth flow to get credentials."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"Credentials file not found at {CREDENTIALS_FILE}\n"
            "Download OAuth credentials from Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json())

    return creds


def get_calendar_service():
    """Get the Google Calendar service."""
    # pylint: disable=import-outside-toplevel
    from googleapiclient.discovery import build

    creds = get_credentials()
    if not creds:
        raise RuntimeError("Not authenticated. Run: kumbuka calendar auth")

    return build("calendar", "v3", credentials=creds)


def list_calendars() -> list[dict]:
    """List all calendars the user has access to."""
    service = get_calendar_service()
    result = service.calendarList().list().execute()  # pylint: disable=no-member
    return [
        {"id": cal["id"], "name": cal.get("summary", "Untitled")}
        for cal in result.get("items", [])
    ]


def get_upcoming_events(minutes_ahead: int = 5) -> list[CalendarEvent]:
    """
    Get calendar events starting in the next N minutes.

    Args:
        minutes_ahead: How many minutes ahead to look for events

    Returns:
        List of CalendarEvent objects for events starting soon
    """
    if not is_authenticated():
        return []

    try:
        service = get_calendar_service()

        now = datetime.now(timezone.utc)
        time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = (now + timedelta(minutes=minutes_ahead)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Get list of calendars to check
        calendars_env = os.getenv("KUMBUKA_CALENDARS", "").strip()
        if calendars_env:
            calendar_ids = [c.strip() for c in calendars_env.split(",")]
        else:
            # Get all calendars
            # pylint: disable=no-member
            cal_list = service.calendarList().list().execute()
            calendar_ids = [cal["id"] for cal in cal_list.get("items", [])]

        events = []
        for cal_id in calendar_ids:
            try:
                # pylint: disable=no-member
                result = (
                    service.events()
                    .list(
                        calendarId=cal_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )

                cal_name = cal_id.split("@")[0] if "@" in cal_id else cal_id

                for event in result.get("items", []):
                    start = event.get("start", {})
                    end = event.get("end", {})

                    # Skip all-day events
                    if "dateTime" not in start:
                        continue

                    events.append(
                        CalendarEvent(
                            id=event.get("id", ""),
                            title=event.get("summary", "Untitled"),
                            start=datetime.fromisoformat(
                                start["dateTime"].replace("Z", "+00:00")
                            ),
                            end=datetime.fromisoformat(
                                end["dateTime"].replace("Z", "+00:00")
                            ),
                            calendar_name=cal_name,
                        )
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                continue

        return events

    except Exception:  # pylint: disable=broad-exception-caught
        return []


def get_current_meetings() -> list[CalendarEvent]:
    """
    Get meetings that are currently happening (started and not ended).

    Returns:
        List of CalendarEvent objects for meetings in progress
    """
    if not is_authenticated():
        return []

    try:
        service = get_calendar_service()

        now = datetime.now(timezone.utc)
        # Look back 2 hours and forward 1 minute to catch ongoing meetings
        time_min = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = (now + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        calendars_env = os.getenv("KUMBUKA_CALENDARS", "").strip()
        if calendars_env:
            calendar_ids = [c.strip() for c in calendars_env.split(",")]
        else:
            # pylint: disable=no-member
            cal_list = service.calendarList().list().execute()
            calendar_ids = [cal["id"] for cal in cal_list.get("items", [])]

        current_meetings = []
        now_aware = datetime.now().astimezone()

        for cal_id in calendar_ids:
            try:
                # pylint: disable=no-member
                result = (
                    service.events()
                    .list(
                        calendarId=cal_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )

                cal_name = cal_id.split("@")[0] if "@" in cal_id else cal_id

                for event in result.get("items", []):
                    start = event.get("start", {})
                    end = event.get("end", {})

                    if "dateTime" not in start:
                        continue

                    start_dt = datetime.fromisoformat(
                        start["dateTime"].replace("Z", "+00:00")
                    )
                    end_dt = datetime.fromisoformat(
                        end["dateTime"].replace("Z", "+00:00")
                    )

                    # Check if meeting is currently happening
                    if start_dt <= now_aware <= end_dt:
                        current_meetings.append(
                            CalendarEvent(
                                id=event.get("id", ""),
                                title=event.get("summary", "Untitled"),
                                start=start_dt,
                                end=end_dt,
                                calendar_name=cal_name,
                            )
                        )
            except Exception:  # pylint: disable=broad-exception-caught
                continue

        return current_meetings

    except Exception:  # pylint: disable=broad-exception-caught
        return []


if __name__ == "__main__":
    # Quick test
    if is_authenticated():
        print("Authenticated!")
        print("\nCalendars:")
        for cal in list_calendars():
            print(f"  - {cal['name']} ({cal['id']})")
        print("\nUpcoming events (next 60 min):")
        for event in get_upcoming_events(60):
            print(f"  - {event.title} ({event.calendar_name})")
    else:
        print("Not authenticated. Run: kumbuka calendar auth")
