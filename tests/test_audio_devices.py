"""Tests for audio device detection and dual-stream mixing."""

from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from kumbuka.audio_devices import (
    find_blackhole,
    find_default_mic,
    resolve_recording_config,
    query_input_devices,
)
from kumbuka.recorder import _to_mono, _mix_streams


# --- Fixtures ---

MOCK_DEVICES = [
    {"name": "MacBook Pro Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "BlackHole 2ch", "max_input_channels": 2, "max_output_channels": 0},
    {"name": "ZoomAudioDevice", "max_input_channels": 2, "max_output_channels": 2},
    {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2},
]

MOCK_DEVICES_NO_BH = [
    {"name": "MacBook Pro Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2},
]

MOCK_DEVICES_BOTH_BH = [
    {"name": "MacBook Pro Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "BlackHole 2ch", "max_input_channels": 2, "max_output_channels": 0},
    {"name": "BlackHole 16ch", "max_input_channels": 16, "max_output_channels": 0},
]


def _patch_sd(devices, default_input_idx=0):
    """Create a mock sounddevice module with the given device list."""
    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = devices

    # Default input device
    default_dev = devices[default_input_idx]
    mock_sd.query_devices.side_effect = lambda *args, **kwargs: (
        default_dev if kwargs.get("kind") == "input"
        else devices[args[0]] if args and isinstance(args[0], int)
        else devices
    )
    mock_sd.default.device = (default_input_idx, 0)
    mock_sd.PortAudioError = Exception
    return mock_sd


# --- find_blackhole tests ---

class TestFindBlackhole:
    @patch("kumbuka.audio_devices.sd")
    def test_finds_2ch(self, mock_sd):
        mock_sd.query_devices.return_value = MOCK_DEVICES
        mock_sd.PortAudioError = Exception
        result = find_blackhole()
        assert result is not None
        assert result["name"] == "BlackHole 2ch"

    @patch("kumbuka.audio_devices.sd")
    def test_prefers_2ch_over_16ch(self, mock_sd):
        mock_sd.query_devices.return_value = MOCK_DEVICES_BOTH_BH
        mock_sd.PortAudioError = Exception
        result = find_blackhole()
        assert result["name"] == "BlackHole 2ch"

    @patch("kumbuka.audio_devices.sd")
    def test_returns_none_when_absent(self, mock_sd):
        mock_sd.query_devices.return_value = MOCK_DEVICES_NO_BH
        mock_sd.PortAudioError = Exception
        result = find_blackhole()
        assert result is None

    @patch("kumbuka.audio_devices.sd")
    def test_fuzzy_match(self, mock_sd):
        devices = [
            {"name": "Custom BlackHole Device", "max_input_channels": 2, "max_output_channels": 0},
        ]
        mock_sd.query_devices.return_value = devices
        mock_sd.PortAudioError = Exception
        result = find_blackhole()
        assert result is not None
        assert "BlackHole" in result["name"]


# --- resolve_recording_config tests ---

class TestResolveConfig:
    @patch("kumbuka.audio_devices.sd")
    def test_auto_with_blackhole_returns_dual(self, mock_sd):
        mock_sd.query_devices = _patch_sd(MOCK_DEVICES).query_devices
        mock_sd.default = _patch_sd(MOCK_DEVICES).default
        mock_sd.PortAudioError = Exception

        config = resolve_recording_config("auto")
        assert config.mode == "dual"
        assert config.secondary_device is not None
        assert "BlackHole" in config.description

    @patch("kumbuka.audio_devices.sd")
    def test_auto_without_blackhole_returns_single(self, mock_sd):
        patched = _patch_sd(MOCK_DEVICES_NO_BH)
        mock_sd.query_devices = patched.query_devices
        mock_sd.default = patched.default
        mock_sd.PortAudioError = Exception

        config = resolve_recording_config("auto")
        assert config.mode == "single"
        assert config.secondary_device is None

    @patch("kumbuka.audio_devices.sd")
    def test_mic_only_forces_single(self, mock_sd):
        mock_sd.query_devices = _patch_sd(MOCK_DEVICES).query_devices
        mock_sd.default = _patch_sd(MOCK_DEVICES).default
        mock_sd.PortAudioError = Exception

        config = resolve_recording_config("mic")
        assert config.mode == "single"
        assert config.secondary_device is None

    @patch("kumbuka.audio_devices.sd")
    def test_system_only_uses_blackhole(self, mock_sd):
        mock_sd.query_devices = _patch_sd(MOCK_DEVICES).query_devices
        mock_sd.default = _patch_sd(MOCK_DEVICES).default
        mock_sd.PortAudioError = Exception

        config = resolve_recording_config("system")
        assert config.mode == "single"
        assert "BlackHole" in config.description

    @patch("kumbuka.audio_devices.sd")
    def test_system_without_blackhole_raises(self, mock_sd):
        patched = _patch_sd(MOCK_DEVICES_NO_BH)
        mock_sd.query_devices = patched.query_devices
        mock_sd.default = patched.default
        mock_sd.PortAudioError = Exception

        with pytest.raises(RuntimeError, match="BlackHole is not installed"):
            resolve_recording_config("system")

    @patch("kumbuka.audio_devices.sd")
    def test_explicit_device_by_name(self, mock_sd):
        mock_sd.query_devices = _patch_sd(MOCK_DEVICES).query_devices
        mock_sd.default = _patch_sd(MOCK_DEVICES).default
        mock_sd.PortAudioError = Exception

        config = resolve_recording_config("ZoomAudioDevice")
        assert config.mode == "single"
        assert config.description == "ZoomAudioDevice"

    @patch("kumbuka.audio_devices.sd")
    def test_explicit_device_not_found_raises(self, mock_sd):
        mock_sd.query_devices = _patch_sd(MOCK_DEVICES).query_devices
        mock_sd.default = _patch_sd(MOCK_DEVICES).default
        mock_sd.PortAudioError = Exception

        with pytest.raises(RuntimeError, match="not found"):
            resolve_recording_config("NonExistent")


# --- Mono downmix tests ---

class TestToMono:
    def test_mono_passthrough(self):
        data = np.array([[100], [200], [300]], dtype=np.int16)
        result = _to_mono(data)
        np.testing.assert_array_equal(result, data)

    def test_stereo_to_mono(self):
        data = np.array([[100, 300], [200, 400]], dtype=np.int16)
        result = _to_mono(data)
        assert result.shape == (2, 1)
        assert result[0, 0] == 200  # (100 + 300) / 2
        assert result[1, 0] == 300  # (200 + 400) / 2


# --- Stream mixing tests ---

class TestMixStreams:
    def test_equal_length_balanced(self):
        """Two streams with equal peaks produce balanced output."""
        a = [np.array([[10000], [20000]], dtype=np.int16)]
        b = [np.array([[10000], [20000]], dtype=np.int16)]
        result = _mix_streams(a, b)
        mixed = np.concatenate(result)
        assert len(mixed) == 2
        # Both normalized equally — ratio between samples preserved
        assert mixed[1, 0] > mixed[0, 0]

    def test_different_volumes_normalized(self):
        """A quiet stream and loud stream contribute equally after normalization."""
        loud = [np.array([[30000], [0]], dtype=np.int16)]
        quiet = [np.array([[300], [0]], dtype=np.int16)]
        result = _mix_streams(loud, quiet)
        mixed = np.concatenate(result)
        # Both get normalized — so the first sample should be similar magnitude
        # (not 30000 + 300 = 30300 like naive summing)
        assert mixed[0, 0] > 0
        assert mixed[0, 0] < 25000  # well below naive sum

    def test_different_lengths_pads_shorter(self):
        a = [np.array([[10000], [20000], [30000]], dtype=np.int16)]
        b = [np.array([[5000]], dtype=np.int16)]
        result = _mix_streams(a, b)
        mixed = np.concatenate(result)
        assert len(mixed) == 3

    def test_no_overflow(self):
        """Normalized mixing should never overflow int16."""
        a = [np.array([[32767]], dtype=np.int16)]
        b = [np.array([[32767]], dtype=np.int16)]
        result = _mix_streams(a, b)
        mixed = np.concatenate(result)
        assert -32768 <= mixed[0, 0] <= 32767

    def test_empty_secondary_returns_primary(self):
        a = [np.array([[1000], [2000]], dtype=np.int16)]
        result = _mix_streams(a, [])
        mixed = np.concatenate(result)
        np.testing.assert_array_equal(mixed, np.array([[1000], [2000]], dtype=np.int16))

    def test_both_empty(self):
        result = _mix_streams([], [])
        assert result == []

    def test_silent_stream_doesnt_kill_audio(self):
        """If one stream is all zeros, the other still comes through."""
        a = [np.array([[10000], [20000]], dtype=np.int16)]
        b = [np.array([[0], [0]], dtype=np.int16)]
        result = _mix_streams(a, b)
        mixed = np.concatenate(result)
        # Primary audio should still be present (normalized then halved)
        assert mixed[0, 0] > 0
        assert mixed[1, 0] > mixed[0, 0]
