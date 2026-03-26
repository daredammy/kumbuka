"""Tests for daemon monitor -- auto-record logic."""

import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from kumbuka.daemon.monitor import (
    load_prompted,
    save_prompted,
    start_auto_recording,
)
from kumbuka.calendar_scraper import CalendarEvent, _generate_event_id


def _make_event(
    title: str = "Test Meeting",
    minutes_from_now: int = 30,
) -> CalendarEvent:
    """Create a CalendarEvent ending N minutes from now."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=5)
    end = now + timedelta(minutes=minutes_from_now)
    event_id = _generate_event_id(title, start, end, ())
    return CalendarEvent(
        id=event_id,
        title=title,
        start=start,
        end=end,
        calendar_name="Google Calendar",
        participants=(),
        is_all_day=False,
        raw_label=f"test label for {title}",
    )


class TestPromptedPersistence:

    def test_save_and_load(self, tmp_path, monkeypatch):
        prompted_file = tmp_path / "prompted.json"
        monkeypatch.setattr("kumbuka.daemon.monitor.PROMPTED_FILE", prompted_file)

        save_prompted({"event1", "event2"})
        loaded = load_prompted()
        assert "event1" in loaded
        assert "event2" in loaded

    def test_load_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("kumbuka.daemon.monitor.PROMPTED_FILE", tmp_path / "nope.json")
        assert load_prompted() == set()

    def test_expired_entries_purged(self, tmp_path, monkeypatch):
        prompted_file = tmp_path / "prompted.json"
        monkeypatch.setattr("kumbuka.daemon.monitor.PROMPTED_FILE", prompted_file)

        old_data = {"old_event": time.time() - 90000}  # >24h ago
        prompted_file.write_text(json.dumps(old_data))

        loaded = load_prompted()
        assert "old_event" not in loaded


class TestStartAutoRecording:

    @patch("kumbuka.daemon.monitor.subprocess.Popen")
    @patch("kumbuka.daemon.monitor.find_python", return_value="/usr/bin/python3")
    @patch("kumbuka.recording_lock.get_active_recording", return_value=None)
    def test_calculates_duration(self, mock_lock, mock_python, mock_popen, tmp_path, monkeypatch):
        monkeypatch.setattr("kumbuka.daemon.monitor.OUTPUT_DIR", tmp_path)
        monkeypatch.setattr("kumbuka.daemon.monitor.BUFFER_MINUTES", 10)

        event = _make_event("Team Sync", minutes_from_now=30)
        start_auto_recording(event)

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "/usr/bin/python3"
        assert "--duration" in call_args
        duration_idx = call_args.index("--duration") + 1
        duration = int(call_args[duration_idx])
        # Should be roughly 30min + 10min buffer = 2400s, give or take execution time
        assert 2300 <= duration <= 2500

    @patch("kumbuka.daemon.monitor.subprocess.Popen")
    @patch("kumbuka.daemon.monitor.find_python", return_value="/usr/bin/python3")
    @patch("kumbuka.recording_lock.get_active_recording", return_value=None)
    def test_minimum_5_minutes(self, mock_lock, mock_python, mock_popen, tmp_path, monkeypatch):
        monkeypatch.setattr("kumbuka.daemon.monitor.OUTPUT_DIR", tmp_path)
        monkeypatch.setattr("kumbuka.daemon.monitor.BUFFER_MINUTES", 0)

        # Event ending 1 minute from now with 0 buffer
        event = _make_event("Quick Chat", minutes_from_now=1)
        start_auto_recording(event)

        call_args = mock_popen.call_args[0][0]
        duration_idx = call_args.index("--duration") + 1
        duration = int(call_args[duration_idx])
        assert duration >= 300  # minimum 5 min
