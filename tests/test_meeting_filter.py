"""Tests for meeting_filter module -- deterministic classification rules."""

import json
import time
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from kumbuka.calendar_scraper import CalendarEvent, _generate_event_id
from kumbuka.meeting_filter import (
    _deterministic_classify,
    _classify_with_claude,
    _load_cache,
    _save_cache,
    should_record,
    CACHE_FILE,
)


def _make_event(
    title: str = "Test Meeting",
    is_all_day: bool = False,
    participants: tuple[str, ...] = (),
    start: datetime | None = None,
    end: datetime | None = None,
) -> CalendarEvent:
    """Helper to create a CalendarEvent for testing."""
    start = start or datetime(2026, 3, 20, 10, 0)
    end = end or datetime(2026, 3, 20, 10, 30)
    event_id = _generate_event_id(title, start, end, participants)
    return CalendarEvent(
        id=event_id,
        title=title,
        start=start,
        end=end,
        calendar_name="Google Calendar",
        participants=participants,
        is_all_day=is_all_day,
        raw_label=f"test label for {title}",
    )


class TestDeterministicClassify:
    """Test deterministic classification rules."""

    # --- SKIP rules ---

    def test_all_day_events_skip(self):
        event = _make_event("Company All-Hands", is_all_day=True)
        assert _deterministic_classify(event) == "SKIP"

    @pytest.mark.parametrize("title", [
        "Lunch", "lunch break", "Gym", "Focus Time", "Focus Block",
        "Holiday", "OOO", "Out of Office", "Do Not Disturb",
        "DND", "Busy", "Travel Time", "Personal",
        "Dentist appointment", "Doctor", "Commute",
    ])
    def test_skip_patterns(self, title):
        event = _make_event(title)
        assert _deterministic_classify(event) == "SKIP"

    # --- RECORD rules ---

    @pytest.mark.parametrize("title", [
        "1:1 with Manager", "1-1 Alice", "One on One",
        "Team Sync", "Weekly Standup", "Stand-up",
        "Interview - Backend", "Design Review",
        "Sprint Retro", "Retrospective",
        "Sprint Planning", "Product Demo",
        "All Hands", "All-Hands", "Town Hall",
        "Onboarding Session", "Training",
        "Workshop", "Brainstorm",
        "Kickoff Meeting", "Kick-off",
        "Weekly Check-in", "Checkin",
    ])
    def test_record_patterns(self, title):
        event = _make_event(title)
        assert _deterministic_classify(event) == "RECORD"

    def test_event_with_participants_records(self):
        event = _make_event("Unclear Title", participants=("Alice Johnson",))
        assert _deterministic_classify(event) == "RECORD"

    # --- Ambiguous ---

    def test_ambiguous_returns_none(self):
        event = _make_event("Something")
        assert _deterministic_classify(event) is None

    def test_single_word_no_pattern_match_is_ambiguous(self):
        event = _make_event("Meditation")
        assert _deterministic_classify(event) is None


class TestClassifyWithClaude:
    """Test Claude CLI classification with mocked subprocess."""

    @patch("kumbuka.meeting_filter.shutil.which", return_value="/usr/local/bin/claude")
    @patch("kumbuka.meeting_filter.subprocess.run")
    def test_record_response(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(stdout="RECORD\n", returncode=0)
        event = _make_event("Unclear Meeting")
        assert _classify_with_claude(event) == "RECORD"

    @patch("kumbuka.meeting_filter.shutil.which", return_value="/usr/local/bin/claude")
    @patch("kumbuka.meeting_filter.subprocess.run")
    def test_skip_response(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(stdout="SKIP\n", returncode=0)
        event = _make_event("Unclear Meeting")
        assert _classify_with_claude(event) == "SKIP"

    @patch("kumbuka.meeting_filter.shutil.which", return_value=None)
    def test_no_claude_defaults_to_record(self, mock_which):
        event = _make_event("Unclear Meeting")
        assert _classify_with_claude(event) == "RECORD"

    @patch("kumbuka.meeting_filter.shutil.which", return_value="/usr/local/bin/claude")
    @patch("kumbuka.meeting_filter.subprocess.run", side_effect=Exception("timeout"))
    def test_exception_defaults_to_record(self, mock_run, mock_which):
        event = _make_event("Unclear Meeting")
        assert _classify_with_claude(event) == "RECORD"

    @patch("kumbuka.meeting_filter.shutil.which", return_value="/usr/local/bin/claude")
    @patch("kumbuka.meeting_filter.subprocess.run")
    def test_unclear_output_defaults_to_record(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(stdout="I'm not sure what to do\n", returncode=0)
        event = _make_event("Unclear Meeting")
        assert _classify_with_claude(event) == "RECORD"


class TestShouldRecord:
    """Test the main should_record function with cache behavior."""

    @patch("kumbuka.meeting_filter._load_cache", return_value={})
    @patch("kumbuka.meeting_filter._save_cache")
    def test_deterministic_skip_cached(self, mock_save, mock_load):
        event = _make_event("Lunch")
        result = should_record(event)
        assert result is False
        mock_save.assert_called_once()
        cache = mock_save.call_args[0][0]
        assert event.id in cache
        assert cache[event.id]["result"] == "SKIP"

    @patch("kumbuka.meeting_filter._load_cache", return_value={})
    @patch("kumbuka.meeting_filter._save_cache")
    def test_deterministic_record_cached(self, mock_save, mock_load):
        event = _make_event("1:1 with Manager")
        result = should_record(event)
        assert result is True
        mock_save.assert_called_once()

    @patch("kumbuka.meeting_filter._load_cache")
    @patch("kumbuka.meeting_filter._save_cache")
    def test_cache_hit(self, mock_save, mock_load):
        event = _make_event("Lunch")
        mock_load.return_value = {
            event.id: {"result": "RECORD", "timestamp": time.time()}
        }
        result = should_record(event)
        assert result is True  # Cache says RECORD, even though rules would say SKIP
        mock_save.assert_not_called()

    @patch("kumbuka.meeting_filter._load_cache", side_effect=Exception("disk error"))
    def test_exception_defaults_to_true(self, mock_load):
        event = _make_event("Anything")
        assert should_record(event) is True


class TestCache:
    """Test cache loading and saving."""

    def test_load_cache_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("kumbuka.meeting_filter.CACHE_FILE", tmp_path / "nonexistent.json")
        assert _load_cache() == {}

    def test_save_and_load_cache(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr("kumbuka.meeting_filter.CACHE_FILE", cache_file)

        cache = {"abc123": {"result": "RECORD", "timestamp": time.time()}}
        _save_cache(cache)

        loaded = _load_cache()
        assert "abc123" in loaded
        assert loaded["abc123"]["result"] == "RECORD"

    def test_expired_entries_purged(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr("kumbuka.meeting_filter.CACHE_FILE", cache_file)

        old_timestamp = time.time() - 90000  # >24 hours ago
        cache = {"old_event": {"result": "SKIP", "timestamp": old_timestamp}}
        _save_cache(cache)

        loaded = _load_cache()
        assert "old_event" not in loaded
