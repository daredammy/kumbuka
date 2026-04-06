"""Audio device detection and configuration for BlackHole system audio capture."""

from dataclasses import dataclass

try:
    import sounddevice as sd
except ModuleNotFoundError:  # pragma: no cover
    sd = None


BLACKHOLE_PREFERRED = "BlackHole 2ch"
BLACKHOLE_FALLBACK = "BlackHole 16ch"


@dataclass
class RecordingConfig:
    """Describes how Kumbuka should record audio."""

    mode: str  # "single" | "dual"
    primary_device: int | None  # device index (None = system default)
    primary_channels: int
    secondary_device: int | None  # device index for second stream (dual mode only)
    secondary_channels: int
    description: str  # human-readable summary, e.g. "MacBook Pro Microphone + BlackHole 2ch"


def _require_sd():
    global sd  # pylint: disable=global-statement
    if sd is None:
        import sounddevice as _sd
        sd = _sd


def query_input_devices() -> list[dict]:
    """Return all audio devices capable of recording."""
    _require_sd()
    devices = sd.query_devices()
    return [
        {"index": i, "name": d["name"], "max_input_channels": d["max_input_channels"]}
        for i, d in enumerate(devices)
        if d["max_input_channels"] > 0
    ]


def find_blackhole() -> dict | None:
    """Find BlackHole virtual audio device. Prefers 2ch over 16ch."""
    devices = query_input_devices()
    by_name = {d["name"]: d for d in devices}

    if BLACKHOLE_PREFERRED in by_name:
        return by_name[BLACKHOLE_PREFERRED]
    if BLACKHOLE_FALLBACK in by_name:
        return by_name[BLACKHOLE_FALLBACK]

    # Fuzzy match — catch renamed or custom BlackHole installs
    for d in devices:
        if "blackhole" in d["name"].lower():
            return d
    return None


def find_default_mic() -> dict | None:
    """Find the system default input device, excluding BlackHole."""
    _require_sd()
    try:
        default = sd.query_devices(kind="input")
    except sd.PortAudioError:
        return None

    if default is None:
        return None

    name = default["name"]
    if "blackhole" in name.lower():
        # BlackHole is somehow the default input — fall back to first non-BlackHole input
        for d in query_input_devices():
            if "blackhole" not in d["name"].lower():
                return d
        return None

    # Find the index (query_devices(kind=) doesn't include it directly)
    idx = sd.default.device[0]
    return {"index": idx, "name": name, "max_input_channels": default["max_input_channels"]}


def resolve_recording_config(audio_device_setting: str) -> RecordingConfig:
    """Decide how to record based on the KUMBUKA_AUDIO_DEVICE setting.

    Values:
        "auto"     — detect BlackHole; dual-stream if found, mic-only otherwise
        "mic"      — force mic-only (current behavior)
        "system"   — force BlackHole-only (no mic)
        <name>     — use a specific device by name
        <number>   — use a specific device by index
    """
    _require_sd()
    setting = audio_device_setting.strip().lower()

    if setting in ("", "auto"):
        return _resolve_auto()
    if setting in ("mic", "mic-only"):
        return _resolve_mic_only()
    if setting in ("system", "blackhole"):
        return _resolve_system_only()
    return _resolve_explicit(audio_device_setting.strip())


def _resolve_auto() -> RecordingConfig:
    mic = find_default_mic()
    bh = find_blackhole()

    if mic and bh:
        return RecordingConfig(
            mode="dual",
            primary_device=mic["index"],
            primary_channels=1,
            secondary_device=bh["index"],
            secondary_channels=min(bh["max_input_channels"], 2),
            description=f"{mic['name']} + {bh['name']}",
        )
    if mic:
        return RecordingConfig(
            mode="single",
            primary_device=mic["index"],
            primary_channels=1,
            secondary_device=None,
            secondary_channels=0,
            description=mic["name"],
        )
    if bh:
        return RecordingConfig(
            mode="single",
            primary_device=bh["index"],
            primary_channels=min(bh["max_input_channels"], 2),
            secondary_device=None,
            secondary_channels=0,
            description=f"{bh['name']} (system audio only)",
        )
    # No devices found — fall back to system default
    return RecordingConfig(
        mode="single",
        primary_device=None,
        primary_channels=1,
        secondary_device=None,
        secondary_channels=0,
        description="default input device",
    )


def _resolve_mic_only() -> RecordingConfig:
    mic = find_default_mic()
    name = mic["name"] if mic else "default input device"
    idx = mic["index"] if mic else None
    return RecordingConfig(
        mode="single",
        primary_device=idx,
        primary_channels=1,
        secondary_device=None,
        secondary_channels=0,
        description=name,
    )


def _resolve_system_only() -> RecordingConfig:
    bh = find_blackhole()
    if not bh:
        raise RuntimeError(
            "BlackHole is not installed. Install with: brew install blackhole-2ch"
        )
    return RecordingConfig(
        mode="single",
        primary_device=bh["index"],
        primary_channels=min(bh["max_input_channels"], 2),
        secondary_device=None,
        secondary_channels=0,
        description=f"{bh['name']} (system audio only)",
    )


def _resolve_explicit(device: str) -> RecordingConfig:
    """Resolve a device by name or numeric index."""
    # Try numeric index first
    try:
        idx = int(device)
        info = sd.query_devices(idx)
        if info["max_input_channels"] <= 0:
            raise RuntimeError(f"Device {idx} ({info['name']}) has no input channels")
        return RecordingConfig(
            mode="single",
            primary_device=idx,
            primary_channels=min(info["max_input_channels"], 2),
            secondary_device=None,
            secondary_channels=0,
            description=info["name"],
        )
    except (ValueError, sd.PortAudioError):
        pass  # Not a number or invalid index — fall through to name search

    # Search by name (case-insensitive substring match)
    device_lower = device.lower()
    for d in query_input_devices():
        if device_lower in d["name"].lower():
            return RecordingConfig(
                mode="single",
                primary_device=d["index"],
                primary_channels=min(d["max_input_channels"], 2),
                secondary_device=None,
                secondary_channels=0,
                description=d["name"],
            )

    raise RuntimeError(
        f"Audio device '{device}' not found. "
        f"Run 'kumbuka audio devices' to list available devices."
    )
