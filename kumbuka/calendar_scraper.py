"""AppleScript-based Google Calendar event extraction via Chrome DOM scraping.

Replaces the OAuth-based calendar.py. Extracts events by reading aria-labels
from [data-eventchip] elements in the Google Calendar Schedule view.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

__all__ = [
    "CalendarEvent",
    "ensure_kumbuka_calendar_tab",
    "get_upcoming_events",
    "get_current_meetings",
    "is_authenticated",
]

log = logging.getLogger(__name__)

CALENDAR_URL = "https://calendar.google.com/calendar/u/0/r/custom/2/d"
CALENDAR_ORIGIN = "calendar.google.com"
SEPARATOR = "\n---KUMBUKA_SEP---\n"
DEFAULT_CALENDAR_NAME = "Google Calendar"
PAGE_LOAD_TIMEOUT_S = 10
PAGE_LOAD_POLL_INTERVAL_S = 1

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
MONTH_ABBREVS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
ALL_MONTH_NAMES = MONTH_NAMES + MONTH_ABBREVS

_MONTH_LOOKUP: dict[str, int] = {}
for _i, _name in enumerate(MONTH_NAMES, 1):
    _MONTH_LOOKUP[_name] = _i
    _MONTH_LOOKUP[MONTH_ABBREVS[_i - 1]] = _i

_TIME_RANGE_RE = re.compile(
    r"^(\d{1,2}(?::\d{2})?\s*[AP]M)\s+to\s+(\d{1,2}(?::\d{2})?\s*[AP]M)$",
    re.IGNORECASE,
)

# Date patterns:
# "March 20, 2026"
_SINGLE_DATE_RE = re.compile(
    r"^(" + "|".join(ALL_MONTH_NAMES) + r")\s+(\d{1,2}),?\s+(\d{4})$"
)
# "March 16 – 20, 2026" or "March 16 - 20, 2026"
_DATE_RANGE_SAME_MONTH_RE = re.compile(
    r"^(" + "|".join(ALL_MONTH_NAMES) + r")\s+(\d{1,2})\s*[–\-]\s*(\d{1,2}),?\s+(\d{4})$"
)
# "March 28 – April 1, 2026"
_DATE_RANGE_CROSS_MONTH_RE = re.compile(
    r"^(" + "|".join(ALL_MONTH_NAMES) + r")\s+(\d{1,2})\s*[–\-]\s*"
    r"(" + "|".join(ALL_MONTH_NAMES) + r")\s+(\d{1,2}),?\s+(\d{4})$"
)

_PARTICIPANT_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$")

# Pattern to extract a date from a Google Calendar data-datekey value.
_DATEKEY_SEPARATED_RE = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
_DATEKEY_COMPACT_RE = re.compile(r"(\d{4})(\d{2})(\d{2})")

# Module-level tab reference cache.
_tab_ref: tuple[int, int] | None = None


@dataclass(frozen=True)
class CalendarEvent:
    """A calendar event scraped from the Google Calendar DOM."""

    id: str
    title: str
    start: datetime
    end: datetime
    calendar_name: str
    participants: tuple[str, ...]
    is_all_day: bool
    raw_label: str


# ---------------------------------------------------------------------------
# AppleScript helpers
# ---------------------------------------------------------------------------

OSASCRIPT_TIMEOUT_S = 10


def _run_applescript(script: str) -> str:
    """Run an AppleScript via osascript and return stdout.

    Raises subprocess.CalledProcessError on non-zero exit.
    Times out after OSASCRIPT_TIMEOUT_S to prevent process pile-up when
    Chrome is unresponsive.
    """
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=OSASCRIPT_TIMEOUT_S,
    )
    return result.stdout.strip()


def _escape_js_for_jxa(js: str) -> str:
    """Escape a JavaScript string for embedding in a JXA script string literal."""
    js = js.replace("\\", "\\\\")
    js = js.replace('"', '\\"')
    js = js.replace("\n", "\\n")
    js = js.replace("\r", "\\r")
    return js


def _run_js_in_tab(js: str, window_id: int, tab_index: int) -> str:
    """Execute JavaScript in a specific Chrome tab via JXA (JavaScript for Automation).

    Uses JXA instead of AppleScript's ``execute javascript`` because recent
    macOS versions block the AppleScript form with error -1723.
    """
    escaped = _escape_js_for_jxa(js)
    # JXA uses 0-based tab indices; our internal convention is 1-based.
    jxa_tab_idx = tab_index - 1
    jxa_script = (
        "var chrome = Application('Google Chrome');\n"
        "var wins = chrome.windows();\n"
        "var result = '';\n"
        "for (var i = 0; i < wins.length; i++) {\n"
        f"  if (wins[i].id() == {window_id}) {{\n"
        f'    result = wins[i].tabs[{jxa_tab_idx}].execute({{javascript: "{escaped}"}});\n'
        "    break;\n"
        "  }\n"
        "}\n"
        "result;"
    )
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", jxa_script],
        capture_output=True,
        text=True,
        check=True,
        timeout=OSASCRIPT_TIMEOUT_S,
    )
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Chrome tab management
# ---------------------------------------------------------------------------

def _chrome_is_running() -> bool:
    """Return True if Google Chrome is currently running."""
    try:
        result = _run_applescript(
            'tell application "System Events" to '
            '(name of processes) contains "Google Chrome"'
        )
        return result.lower() == "true"
    except subprocess.CalledProcessError:
        return False


def _tab_exists(window_id: int, tab_index: int) -> bool:
    """Return True if the given Chrome tab exists and points at Google Calendar."""
    try:
        url = _run_applescript(
            'tell application "Google Chrome"\n'
            f"    tell window id {window_id}\n"
            f"        URL of tab {tab_index}\n"
            "    end tell\n"
            "end tell"
        )
        return url.startswith(f"https://{CALENDAR_ORIGIN}")
    except subprocess.CalledProcessError:
        return False


def _find_calendar_tab() -> tuple[int, int] | None:
    """Search all Chrome windows/tabs for one on calendar.google.com.

    Prefers a tab already at CALENDAR_URL (the correct view) over any other
    calendar tab.  Returns the best match.
    """
    try:
        win_ids_raw = _run_applescript(
            'tell application "Google Chrome" to return id of every window'
        )
        if not win_ids_raw:
            return None

        best: tuple[int, int] | None = None
        for win_id_str in win_ids_raw.split(", "):
            win_id_str = win_id_str.strip()
            if not win_id_str:
                continue
            win_id = int(win_id_str)

            urls_raw = _run_applescript(
                'tell application "Google Chrome"\n'
                f"    tell window id {win_id}\n"
                "        URL of every tab\n"
                "    end tell\n"
                "end tell"
            )
            urls = [u.strip() for u in urls_raw.split(", ")]
            for idx, url in enumerate(urls, 1):
                if CALENDAR_URL in url:
                    return (win_id, idx)  # exact match — use immediately
                if f"https://{CALENDAR_ORIGIN}" in url and best is None:
                    best = (win_id, idx)

        return best
    except (subprocess.CalledProcessError, ValueError):
        return None


def _wait_for_tab_load(window_id: int, tab_index: int) -> bool:
    """Poll until the tab finishes loading or the timeout is reached."""
    deadline = time.monotonic() + PAGE_LOAD_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            loading = _run_applescript(
                'tell application "Google Chrome"\n'
                f"    tell window id {window_id}\n"
                f"        loading of tab {tab_index}\n"
                "    end tell\n"
                "end tell"
            )
            if loading.lower() == "false":
                return True
        except subprocess.CalledProcessError:
            pass
        time.sleep(PAGE_LOAD_POLL_INTERVAL_S)
    return False


def ensure_kumbuka_calendar_tab() -> tuple[int, int] | None:
    """Find or create Kumbuka's dedicated calendar tab in Chrome.

    Returns (window_id, tab_index) on success, or None if Chrome is not running.
    Caches the result in module-level _tab_ref.
    """
    global _tab_ref  # noqa: PLW0603

    if not _chrome_is_running():
        log.debug("Chrome is not running")
        return None

    # Check cached reference.
    if _tab_ref is not None:
        wid, tidx = _tab_ref
        if _tab_exists(wid, tidx):
            log.debug("Reusing cached tab ref: window %d, tab %d", wid, tidx)
            return _tab_ref

    # Search existing tabs.
    found = _find_calendar_tab()
    if found is not None:
        _tab_ref = found
        log.debug("Found existing calendar tab: window %d, tab %d", *found)
        return found

    # Create a new tab in the front window (or a new window if none exist).
    try:
        cal_url = CALENDAR_URL
        raw = _run_applescript(
            'tell application "Google Chrome"\n'
            f'    set newTab to make new tab at end of tabs of front window '
            f'with properties {{URL:"{cal_url}"}}\n'
            "    return (id of front window) & \",\" & (count of tabs of front window)\n"
            "end tell"
        )
        parts = raw.split(",")
        win_id = int(parts[0].strip())
        tab_idx = int(parts[1].strip())
    except (subprocess.CalledProcessError, ValueError, IndexError):
        # No windows open — create one.
        try:
            raw = _run_applescript(
                'tell application "Google Chrome"\n'
                "    set newWindow to make new window\n"
                f'    set URL of active tab of newWindow to "{cal_url}"\n'
                "    return (id of newWindow) & \",\" & 1\n"
                "end tell"
            )
            parts = raw.split(",")
            win_id = int(parts[0].strip())
            tab_idx = int(parts[1].strip())
        except (subprocess.CalledProcessError, ValueError, IndexError) as exc:
            log.error("Failed to create calendar tab: %s", exc)
            return None

    _wait_for_tab_load(win_id, tab_idx)
    _tab_ref = (win_id, tab_idx)
    global _last_refresh  # noqa: PLW0603
    _last_refresh = time.monotonic()  # fresh tab at CALENDAR_URL — no need to refresh again
    log.debug("Created new calendar tab: window %d, tab %d", win_id, tab_idx)
    return _tab_ref


# ---------------------------------------------------------------------------
# View & scrape helpers
# ---------------------------------------------------------------------------

_last_refresh: float = 0.0
_REFRESH_INTERVAL_S = 55  # refresh at most once per minute


def _refresh_calendar_tab(window_id: int, tab_index: int) -> None:
    """Navigate the calendar tab to today's view to flush stale DOM content.

    Google Calendar doesn't always auto-refresh a background tab, so event
    chips from a previous render can linger.  Navigating to the canonical
    URL forces a fresh render.  Skips the refresh if one happened within
    the last _REFRESH_INTERVAL_S seconds.
    """
    global _last_refresh  # noqa: PLW0603

    now = time.monotonic()
    if now - _last_refresh < _REFRESH_INTERVAL_S:
        return

    try:
        _run_js_in_tab(f'window.location.href = "{CALENDAR_URL}"', window_id, tab_index)
    except subprocess.CalledProcessError:
        log.warning("Calendar tab refresh failed; will scrape existing DOM")
        return
    if not _wait_for_tab_load(window_id, tab_index):
        log.warning("Calendar tab load timed out after refresh")
        return  # don't stamp _last_refresh — retry next call
    # Give Calendar's JS a moment to render event chips after page load.
    time.sleep(2)
    _last_refresh = time.monotonic()


def _scrape_aria_labels(window_id: int, tab_index: int) -> list[str]:
    """Extract event descriptions from [data-eventchip] elements.

    Prefers ``aria-label`` (schedule/day views) but falls back to
    ``textContent`` (week view) which embeds the same comma-separated
    description after the visible chip text.

    In multi-day views (week, custom N-day), each label may be prefixed
    with ``DATEKEY:<key>|||`` so the caller can determine the event's
    actual date instead of assuming today.
    """
    js = (
        "(function(){"
        # Identify today's numeric datekey from the column header button
        # whose aria-label contains "today" (e.g. "Tuesday, March 24, today").
        "var todayKey=null;"
        "document.querySelectorAll('button[data-datekey]').forEach(function(btn){"
        "var al=btn.getAttribute('aria-label')||'';"
        "if(al.indexOf('today')>=0||al.indexOf('Today')>=0)"
        "todayKey=parseInt(btn.dataset.datekey);"
        "});"
        # No "today" column → single-day view or non-standard layout.
        # Fall back to original behaviour (no date prefix).
        "if(todayKey===null){"
        "return Array.from(document.querySelectorAll('[data-eventchip]'))"
        ".map(function(el){"
        "var label=el.getAttribute('aria-label');"
        "if(!label){"
        "var text=el.textContent.trim();"
        "var m=text.match(/(\\d{1,2}(?::\\d{2})?\\s*[ap]m\\s+to\\s+|All day,)/i);"
        "if(m)label=text.substring(m.index);"
        "else return '';}"
        "return label;})"
        ".filter(Boolean)"
        ".join('\\n---KUMBUKA_SEP---\\n');}"
        # Build column map: for each data-datekey element, compute the
        # YYYYMMDD date string from the day-offset relative to today.
        "var td=new Date();td.setHours(0,0,0,0);"
        "var dkEls=document.querySelectorAll('[data-datekey]');"
        "var colMap=[];"
        "dkEls.forEach(function(h){"
        "var r=h.getBoundingClientRect();"
        "if(r.width>0){"
        "var dk=parseInt(h.dataset.datekey);"
        "var dt=new Date(td.getTime()+(dk-todayKey)*86400000);"
        "var ds=''+dt.getFullYear()+('0'+(dt.getMonth()+1)).slice(-2)+('0'+dt.getDate()).slice(-2);"
        "colMap.push({dk:dk,cx:(r.left+r.right)/2,ds:ds});"
        "}});"
        # Helper: walk up DOM for ancestor datekey, else position-match.
        "function findDate(el){"
        "var p=el.parentElement;"
        "while(p&&p!==document.body){"
        "if(p.dataset&&p.dataset.datekey){"
        "var dk=parseInt(p.dataset.datekey);"
        "var dt=new Date(td.getTime()+(dk-todayKey)*86400000);"
        "return ''+dt.getFullYear()+('0'+(dt.getMonth()+1)).slice(-2)+('0'+dt.getDate()).slice(-2);}"
        "p=p.parentElement;}"
        "if(colMap.length>1){"
        "var r=el.getBoundingClientRect();"
        "var cx=(r.left+r.right)/2;"
        "var best='',bd=1e9;"
        "for(var i=0;i<colMap.length;i++){"
        "var d=Math.abs(cx-colMap[i].cx);"
        "if(d<bd){bd=d;best=colMap[i].ds;}}"
        "return best;}"
        "return '';}"
        # Extract labels, prefixing with DATEKEY:YYYYMMDD||| when found.
        "return Array.from(document.querySelectorAll('[data-eventchip]'))"
        ".map(function(el){"
        "var label=el.getAttribute('aria-label');"
        "if(!label){"
        "var text=el.textContent.trim();"
        "var m=text.match(/(\\d{1,2}(?::\\d{2})?\\s*[ap]m\\s+to\\s+|All day,)/i);"
        "if(m)label=text.substring(m.index);"
        "else return '';}"
        "var dk=findDate(el);"
        "if(dk)return 'DATEKEY:'+dk+'|||'+label;"
        "return label;})"
        ".filter(Boolean)"
        ".join('\\n---KUMBUKA_SEP---\\n');"
        "})()"
    )
    try:
        raw = _run_js_in_tab(js, window_id, tab_index)
    except subprocess.CalledProcessError as exc:
        if "Access not allowed" in (exc.stderr or ""):
            log.error(
                "JavaScript execution blocked by Chrome. "
                "Enable: View → Developer → Allow JavaScript from Apple Events"
            )
        else:
            log.error("Failed to scrape aria labels: %s", exc)
        return []

    if not raw:
        return []
    return [label.strip() for label in raw.split("---KUMBUKA_SEP---") if label.strip()]


# ---------------------------------------------------------------------------
# Aria-label parsing
# ---------------------------------------------------------------------------

def _local_tz():
    """Return the local timezone."""
    return datetime.now().astimezone().tzinfo


def _parse_time(time_str: str, ref_date: datetime) -> datetime:
    """Parse a time string like '10:00 AM', '2 PM', or '5pm' into a datetime on ref_date."""
    time_str = time_str.strip()
    # Normalize compact forms: "5pm" -> "5:00 PM", "11:30am" -> "11:30 AM"
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*([APap][Mm])$", time_str)
    if m:
        hour = m.group(1)
        mins = m.group(2) or "00"
        ampm = m.group(3).upper()
        time_str = f"{hour}:{mins} {ampm}"
    elif ":" not in time_str.split()[0]:
        # "2 PM" -> "2:00 PM"
        parts = time_str.split()
        time_str = parts[0] + ":00 " + parts[1]
    parsed = datetime.strptime(time_str, "%I:%M %p")
    return ref_date.replace(
        hour=parsed.hour,
        minute=parsed.minute,
        second=0,
        microsecond=0,
    )


def _parse_datekey(datekey: str, tz) -> datetime | None:
    """Parse a Google Calendar ``data-datekey`` value into a midnight datetime.

    Handles ``YYYYMMDD``, ``YYYY-MM-DD``, and ``YYYY/MM/DD`` formats.
    """
    m = _DATEKEY_SEPARATED_RE.search(datekey)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=tz)
        except ValueError:
            pass
    m = _DATEKEY_COMPACT_RE.search(datekey)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=tz)
        except ValueError:
            pass
    return None


def _generate_event_id(title: str, start: datetime, end: datetime, participants: tuple[str, ...]) -> str:
    """Generate a stable 16-char hex hash from event content."""
    payload = f"{title}|{start.isoformat()}|{end.isoformat()}|{','.join(participants)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _parse_date_token(token: str) -> tuple[datetime, datetime | None] | None:
    """Try to parse a token as a date or date range.

    Returns (start_date, end_date) where end_date is None for single dates.
    Dates are returned as timezone-aware datetimes at midnight.
    """
    tz = _local_tz()

    m = _SINGLE_DATE_RE.match(token)
    if m:
        month = _MONTH_LOOKUP[m.group(1)]
        day = int(m.group(2))
        year = int(m.group(3))
        dt = datetime(year, month, day, tzinfo=tz)
        return (dt, None)

    m = _DATE_RANGE_SAME_MONTH_RE.match(token)
    if m:
        month = _MONTH_LOOKUP[m.group(1)]
        day_start = int(m.group(2))
        day_end = int(m.group(3))
        year = int(m.group(4))
        return (
            datetime(year, month, day_start, tzinfo=tz),
            datetime(year, month, day_end, tzinfo=tz),
        )

    m = _DATE_RANGE_CROSS_MONTH_RE.match(token)
    if m:
        month_start = _MONTH_LOOKUP[m.group(1)]
        day_start = int(m.group(2))
        month_end = _MONTH_LOOKUP[m.group(3)]
        day_end = int(m.group(4))
        year = int(m.group(5))
        return (
            datetime(year, month_start, day_start, tzinfo=tz),
            datetime(year, month_end, day_end, tzinfo=tz),
        )

    return None


def _is_full_day_time_range(start_str: str, end_str: str) -> bool:
    """Return True if a time range spans the full day (e.g. 12 AM to 11:59 PM)."""
    start_str = start_str.strip().upper()
    end_str = end_str.strip().upper()
    start_is_midnight = start_str in ("12 AM", "12:00 AM")
    end_is_late = end_str in (
        "11:59 PM", "11:30 PM", "12 AM", "12:00 AM",
        "11:59PM", "11:30PM", "12AM", "12:00AM",
    )
    return start_is_midnight and end_is_late


def _parse_aria_label(label: str, *, datekey: str | None = None) -> CalendarEvent | None:
    """Parse a Google Calendar aria-label into a CalendarEvent.

    *datekey* is an optional ``data-datekey`` value extracted from the DOM
    that indicates which day-column the event chip belongs to. It is used
    as a fallback when the aria-label itself does not contain a date token.

    Returns None if the label cannot be parsed.
    """
    tokens = [t.strip().rstrip(".") for t in label.split(", ")]
    if len(tokens) < 2:
        return None

    tz = _local_tz()
    today = datetime.now(tz=tz).replace(hour=0, minute=0, second=0, microsecond=0)

    is_all_day = False
    start_time_str: str | None = None
    end_time_str: str | None = None
    time_token_idx: int | None = None
    title: str | None = None
    event_date_start: datetime | None = None
    event_date_end: datetime | None = None
    participants: list[str] = []

    # 1. Check first token for time range.
    time_match = _TIME_RANGE_RE.match(tokens[0])
    if time_match:
        start_time_str = time_match.group(1)
        end_time_str = time_match.group(2)
        time_token_idx = 0
        if _is_full_day_time_range(start_time_str, end_time_str):
            is_all_day = True

    # 2. Scan for "All day" token.
    all_day_idx: int | None = None
    for i, tok in enumerate(tokens):
        if tok.lower() == "all day":
            is_all_day = True
            all_day_idx = i
            break

    # 3. Find date token(s) — scan from the end.
    #    Date ranges like "March 16 – 20, 2026" get split into two tokens
    #    ("March 16 – 20" and "2026"), so try joining consecutive tokens.
    date_token_idx: int | None = None
    date_token_end_idx: int | None = None  # set when 2 tokens were joined
    for i in range(len(tokens) - 1, -1, -1):
        # Try single token first.
        parsed = _parse_date_token(tokens[i])
        if parsed is not None:
            event_date_start, event_date_end = parsed
            date_token_idx = i
            break
        # Try joining with next token (e.g. "March 16 – 20" + "2026").
        if i + 1 < len(tokens):
            combined = tokens[i] + ", " + tokens[i + 1]
            parsed = _parse_date_token(combined)
            if parsed is not None:
                event_date_start, event_date_end = parsed
                date_token_idx = i
                date_token_end_idx = i + 1
                break

    # Fall back to DOM column date, then to today.
    if event_date_start is None and datekey:
        event_date_start = _parse_datekey(datekey, tz)
    if event_date_start is None:
        event_date_start = today

    # 4. Determine title: the first non-time, non-"All day", non-date token.
    title_idx: int | None = None
    for i, tok in enumerate(tokens):
        if i == time_token_idx:
            continue
        if i == all_day_idx:
            continue
        if i == date_token_idx or i == date_token_end_idx:
            continue
        title = tok
        title_idx = i
        break

    if title is None:
        return None

    # 5. Extract participants: tokens between title and date that look like person names.
    skip_indices = {time_token_idx, all_day_idx, date_token_idx, date_token_end_idx, title_idx}
    for i, tok in enumerate(tokens):
        if i in skip_indices:
            continue
        # Participant heuristic: 2+ capitalized words.
        if _PARTICIPANT_RE.match(tok):
            participants.append(tok)

    participants_tuple = tuple(participants)

    # 6. Build start/end datetimes.
    if is_all_day:
        start_dt = event_date_start.replace(hour=0, minute=0, second=0, microsecond=0)
        if event_date_end is not None:
            end_dt = event_date_end.replace(hour=23, minute=59, second=59, microsecond=0)
        else:
            end_dt = event_date_start.replace(hour=23, minute=59, second=59, microsecond=0)
    elif start_time_str and end_time_str:
        start_dt = _parse_time(start_time_str, event_date_start)
        end_dt = _parse_time(end_time_str, event_date_start)
        # Handle overnight meetings (end time before start time).
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
    elif event_date_end is not None:
        # Multi-day event without explicit time or "All day" keyword.
        is_all_day = True
        start_dt = event_date_start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = event_date_end.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        # Cannot determine times — treat as unparseable.
        return None

    event_id = _generate_event_id(title, start_dt, end_dt, participants_tuple)

    return CalendarEvent(
        id=event_id,
        title=title,
        start=start_dt,
        end=end_dt,
        calendar_name=DEFAULT_CALENDAR_NAME,
        participants=participants_tuple,
        is_all_day=is_all_day,
        raw_label=label,
    )


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

_DATEKEY_PREFIX = "DATEKEY:"
_DATEKEY_SEP = "|||"


_CONFIRM_DELAY_S = 1.5


def _parse_raw_labels(raw_labels: list[str]) -> list[CalendarEvent]:
    """Parse a list of raw aria-label strings into CalendarEvents."""
    events: list[CalendarEvent] = []
    for raw in raw_labels:
        datekey: str | None = None
        label = raw
        if raw.startswith(_DATEKEY_PREFIX):
            rest = raw[len(_DATEKEY_PREFIX):]
            sep_idx = rest.find(_DATEKEY_SEP)
            if sep_idx >= 0:
                datekey = rest[:sep_idx]
                label = rest[sep_idx + len(_DATEKEY_SEP):]

        event = _parse_aria_label(label, datekey=datekey)
        if event is not None:
            events.append(event)
        else:
            log.debug("Could not parse aria label: %s", label)
    return events


def _extract_events() -> list[CalendarEvent]:
    """Open/find the calendar tab, scrape, and parse all events.

    Performs a confirmation scrape: scrapes twice with a short delay and
    only returns events present in both scrapes.  This filters transient
    DOM artifacts (phantom events from Google Calendar's rendering pipeline).
    """
    ref = ensure_kumbuka_calendar_tab()
    if ref is None:
        return []

    window_id, tab_index = ref
    _refresh_calendar_tab(window_id, tab_index)

    first_labels = _scrape_aria_labels(window_id, tab_index)
    time.sleep(_CONFIRM_DELAY_S)
    second_labels = _scrape_aria_labels(window_id, tab_index)

    # Keep only labels present in both scrapes
    confirmed = set(first_labels) & set(second_labels)
    if len(confirmed) < len(first_labels):
        dropped = set(first_labels) - confirmed
        for d in dropped:
            log.warning("Dropped transient event chip: %s", d[:80])

    return _parse_raw_labels([l for l in first_labels if l in confirmed])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_upcoming_events(minutes_ahead: int = 5) -> list[CalendarEvent]:
    """Return events starting between now and now + minutes_ahead.

    All-day events are included only if they start within the window.
    """
    now = datetime.now(tz=_local_tz())
    cutoff = now + timedelta(minutes=minutes_ahead)

    events = _extract_events()
    upcoming = [e for e in events if now <= e.start <= cutoff]
    upcoming.sort(key=lambda e: e.start)
    return upcoming


def get_current_meetings() -> list[CalendarEvent]:
    """Return timed events that are currently in progress.

    All-day events are excluded (consistent with original calendar.py behavior).
    """
    now = datetime.now(tz=_local_tz())

    events = _extract_events()
    current = [e for e in events if not e.is_all_day and e.start <= now <= e.end]
    current.sort(key=lambda e: e.start)
    return current


def is_authenticated() -> bool:
    """Return True if the calendar tab is loaded and not on a sign-in page."""
    ref = ensure_kumbuka_calendar_tab()
    if ref is None:
        return False

    window_id, tab_index = ref
    try:
        title = _run_applescript(
            'tell application "Google Chrome"\n'
            f"    tell window id {window_id}\n"
            f"        title of tab {tab_index}\n"
            "    end tell\n"
            "end tell"
        )
        if "sign in" in title.lower():
            return False

        url = _run_applescript(
            'tell application "Google Chrome"\n'
            f"    tell window id {window_id}\n"
            f"        URL of tab {tab_index}\n"
            "    end tell\n"
            "end tell"
        )
        if "accounts.google.com" in url:
            return False

    except subprocess.CalledProcessError:
        return False

    return True
