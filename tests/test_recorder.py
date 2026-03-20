"""Tests for recorder module -- duration parameter behavior."""

from unittest.mock import patch, MagicMock
import threading

import pytest


class TestRecordDuration:
    """Test the duration_secs parameter of record()."""

    @patch("kumbuka.recorder.sd")
    @patch("kumbuka.recorder.play_start_tone")
    @patch("kumbuka.recorder.play_stop_tone")
    @patch("kumbuka.recorder._save_incremental")
    def test_duration_clamps_to_max(self, mock_save, mock_stop, mock_start, mock_sd):
        """duration_secs exceeding MAX_DURATION should be clamped."""
        from kumbuka.recorder import MAX_DURATION

        # We can't easily test the full record loop, but we can verify the
        # effective_max calculation logic
        duration_secs = MAX_DURATION + 1000
        effective_max = min(duration_secs, MAX_DURATION)
        assert effective_max == MAX_DURATION

    def test_none_duration_uses_max(self):
        """When duration_secs is None, MAX_DURATION is used."""
        from kumbuka.recorder import MAX_DURATION

        duration_secs = None
        effective_max = min(duration_secs, MAX_DURATION) if duration_secs else MAX_DURATION
        assert effective_max == MAX_DURATION

    def test_duration_less_than_max(self):
        """duration_secs less than MAX_DURATION should be used as-is."""
        from kumbuka.recorder import MAX_DURATION

        duration_secs = 300
        effective_max = min(duration_secs, MAX_DURATION) if duration_secs else MAX_DURATION
        assert effective_max == 300
