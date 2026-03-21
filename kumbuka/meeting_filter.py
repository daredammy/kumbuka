"""Meeting classification module.

Decides whether a calendar event should be recorded. Uses deterministic
rules first, then falls back to Claude CLI classification for ambiguous events.
"""

import json
import logging
import re
import shutil
import subprocess
import time

from .calendar_scraper import CalendarEvent
from .config import OUTPUT_DIR

__all__ = ["should_record"]

log = logging.getLogger(__name__)

CACHE_FILE = OUTPUT_DIR / "meeting_classification_cache.json"
_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours

_SKIP_PATTERNS = re.compile(
    r"\b(?:lunch|gym|focus|holiday|ooo|out of office|do not disturb|dnd"
    r"|busy|block|commute|travel\s*time|personal|dentist|doctor|appointment)\b",
    re.IGNORECASE,
)
_RECORD_PATTERNS = re.compile(
    r"(?:1[:\-]1"
    r"|\bone[- ]on[- ]one\b"
    r"|\bsync\b"
    r"|\bstand-?up\b"
    r"|\binterview\b"
    r"|\breview\b"
    r"|\bretro(?:spective)?\b"
    r"|\bsprint\b"
    r"|\bplanning\b"
    r"|\bdemo\b"
    r"|\ball[- ]hands\b"
    r"|\btown\s*hall\b"
    r"|\bonboarding\b"
    r"|\btraining\b"
    r"|\bworkshop\b"
    r"|\bbrainstorm\b"
    r"|\bkick-?off\b"
    r"|\bcheck-?in\b)",
    re.IGNORECASE,
)


def _load_cache() -> dict:
    """Load cache from disk, purging entries older than 24 hours."""
    try:
        raw = json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}

    now = time.time()
    return {
        event_id: entry
        for event_id, entry in raw.items()
        if now - entry.get("timestamp", 0) < _CACHE_TTL_SECONDS
    }


def _save_cache(cache: dict) -> None:
    """Write cache to disk."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache))


def _deterministic_classify(event: CalendarEvent) -> str | None:
    """Apply deterministic rules to classify an event.

    Returns "RECORD", "SKIP", or None if ambiguous.
    """
    if event.is_all_day:
        return "SKIP"

    if _SKIP_PATTERNS.search(event.title):
        return "SKIP"

    if _RECORD_PATTERNS.search(event.title):
        return "RECORD"

    if len(event.participants) >= 1:
        return "RECORD"

    return None


def _classify_with_claude(event: CalendarEvent) -> str:
    """Use Claude CLI to classify an ambiguous event."""
    claude_path = shutil.which("claude")
    if not claude_path:
        log.warning("Claude CLI not found on PATH; defaulting to RECORD")
        return "RECORD"

    prompt = (
        f'Given this calendar event, should it be recorded as a meeting?\n'
        f'\n'
        f'Event: "{event.title}"\n'
        f'Time: {event.start.strftime("%H:%M")} - {event.end.strftime("%H:%M")}\n'
        f'All-day: {"yes" if event.is_all_day else "no"}\n'
        f'Participants: {", ".join(event.participants) if event.participants else "none listed"}\n'
        f'\n'
        f'Rules:\n'
        f'- RECORD: 1:1s, team meetings, standups, syncs, reviews, interviews, any meeting with other people\n'
        f'- SKIP: personal time, doctor, all day meetings, busy blocks, lunch, gym, focus hours, holidays, "Do not disturb", travel time\n'
        f'- When in doubt, RECORD\n'
        f'\n'
        f'Respond with exactly: RECORD or SKIP'
    )

    try:
        result = subprocess.run(
            [claude_path, "--print", "-m", "haiku", prompt],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout.strip().upper()

        if "SKIP" in output:
            return "SKIP"
        if "RECORD" in output:
            return "RECORD"

        log.warning("Unclear Claude response: %s; defaulting to RECORD", result.stdout.strip())
        return "RECORD"
    except Exception:
        log.exception("Claude classification failed; defaulting to RECORD")
        return "RECORD"


def should_record(event: CalendarEvent) -> bool:
    """Decide whether a calendar event should be recorded.

    Checks the cache first, then applies deterministic rules, and finally
    falls back to Claude CLI classification for ambiguous events.
    """
    try:
        cache = _load_cache()

        cached = cache.get(event.id)
        if cached is not None:
            log.debug("Cache hit for %s: %s", event.id, cached["result"])
            return cached["result"] == "RECORD"

        result = _deterministic_classify(event)
        if result is not None:
            log.debug("Deterministic classification for '%s': %s", event.title, result)
            cache[event.id] = {"result": result, "timestamp": time.time()}
            _save_cache(cache)
            return result == "RECORD"

        result = _classify_with_claude(event)
        log.debug("Claude classification for '%s': %s", event.title, result)
        cache[event.id] = {"result": result, "timestamp": time.time()}
        _save_cache(cache)
        return result == "RECORD"
    except Exception:
        log.exception("Classification failed for '%s'; defaulting to RECORD", event.title)
        return True
