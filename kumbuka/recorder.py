"""Audio recording functionality with resilient incremental saving."""

import io
import signal
import time
import wave
import threading
from datetime import datetime

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - optional fallback for minimal test envs
    np = None

try:
    import sounddevice as sd
except ModuleNotFoundError:  # pragma: no cover - optional fallback for minimal test envs
    sd = None

from .config import SAMPLE_RATE, CHANNELS, MAX_DURATION, OUTPUT_DIR, AUDIO_DEVICE
from .audio_devices import resolve_recording_config


# Module state — primary stream (mic or single device)
_stop_event = threading.Event()
_chunks = []
_chunks_lock = threading.Lock()

# Module state — secondary stream (system audio via BlackHole)
_chunks_secondary = []
_chunks_secondary_lock = threading.Lock()

# Incremental save settings
SAVE_INTERVAL_SECS = 10  # Save to disk every 10 seconds


def _require_audio_deps():
    """Import audio dependencies lazily when recording is actually used."""
    global np, sd  # pylint: disable=global-statement

    if np is None:
        import numpy as _np
        np = _np

    if sd is None:
        import sounddevice as _sd
        sd = _sd


def _tone(freq=880, dur=0.15, vol=0.3):
    """Play a simple tone."""
    _require_audio_deps()
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), False)
    w = np.sin(freq * 2 * np.pi * t) * vol
    env = np.ones_like(w)
    fade = int(SAMPLE_RATE * 0.01)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    sd.play((w * env * 32767).astype(np.int16), SAMPLE_RATE)
    sd.wait()


def play_start_tone():
    """Play ascending tones to indicate recording started."""
    _tone(660, 0.1)
    _tone(880, 0.15)


def play_stop_tone():
    """Play descending tones to indicate recording stopped."""
    _tone(880, 0.1)
    _tone(660, 0.15)


def _on_signal(_sig, _frame):
    """Handle Ctrl+C."""
    _stop_event.set()


def _to_mono(indata):
    """Downmix multi-channel audio to mono int16."""
    if indata.shape[1] == 1:
        return indata.copy()
    # Average channels, keeping int16 range
    return indata.astype(np.int32).mean(axis=1, keepdims=True).astype(np.int16)


def _normalize(audio):
    """Normalize audio to use ~70% of int16 range. Returns float64."""
    peak = np.abs(audio).max()
    if peak == 0:
        return audio.astype(np.float64)
    # Target 70% of max range — leaves headroom for mixing
    target = 32767 * 0.7
    return audio.astype(np.float64) * (target / peak)


def _mix_streams(primary_chunks: list, secondary_chunks: list) -> list:
    """Mix two mono audio streams with per-stream normalization.

    Each stream is normalized independently before mixing so both
    sides (mic and system audio) contribute equally regardless of
    their raw volume levels. Handles clock drift between devices.
    """
    primary = np.concatenate(primary_chunks) if primary_chunks else np.array([], dtype=np.int16).reshape(0, 1)
    secondary = np.concatenate(secondary_chunks) if secondary_chunks else np.array([], dtype=np.int16).reshape(0, 1)

    if primary.size == 0:
        return [secondary] if secondary.size > 0 else []
    if secondary.size == 0:
        return [primary]

    # Pad shorter stream to match longer (clock drift compensation)
    max_len = max(len(primary), len(secondary))
    if len(primary) < max_len:
        primary = np.pad(primary, ((0, max_len - len(primary)), (0, 0)))
    if len(secondary) < max_len:
        secondary = np.pad(secondary, ((0, max_len - len(secondary)), (0, 0)))

    # Normalize each stream independently, then mix
    p_norm = _normalize(primary)
    s_norm = _normalize(secondary)

    # If secondary is silent (e.g. BlackHole not receiving audio),
    # return primary at full level instead of halving it
    secondary_silent = np.abs(secondary).max() == 0
    primary_silent = np.abs(primary).max() == 0

    if secondary_silent:
        mixed = p_norm
    elif primary_silent:
        mixed = s_norm
    else:
        mixed = (p_norm + s_norm) / 2.0

    mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
    return [mixed]


def _get_mixed_chunks() -> list:
    """Get current audio chunks, mixing dual streams if active."""
    with _chunks_lock:
        primary = _chunks.copy()
    with _chunks_secondary_lock:
        secondary = _chunks_secondary.copy()

    if not secondary:
        # Single-stream mode or no secondary audio yet
        return primary

    # Downmix each set to mono first, then mix together
    return _mix_streams(primary, secondary)


def _chunks_to_wav(chunks: list) -> bytes:
    """Convert audio chunks to WAV bytes."""
    _require_audio_deps()
    if not chunks:
        return b""
    audio = np.concatenate(chunks)
    buf = io.BytesIO()
    # pylint: disable=no-member
    with wave.open(buf, 'wb') as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    # pylint: enable=no-member
    buf.seek(0)
    return buf.read()


def _save_incremental(session: str, final: bool = False):
    """Save current audio to disk incrementally.

    Uses a .partial extension while recording, renamed on final save.
    In dual-stream mode, mixes both streams before saving.
    """
    chunks_copy = _get_mixed_chunks()
    if not chunks_copy:
        return

    wav_bytes = _chunks_to_wav(chunks_copy)
    if not wav_bytes:
        return

    partial_path = OUTPUT_DIR / f"{session}.partial.wav"
    final_path = OUTPUT_DIR / f"{session}.wav"

    # Write to partial file
    partial_path.write_bytes(wav_bytes)

    if final:
        # Rename to final
        partial_path.rename(final_path)
        # Duration: bytes / (sample_rate * bytes_per_sample * channels)
        dur = len(wav_bytes) / (SAMPLE_RATE * 2 * CHANNELS)
        m, s = divmod(int(dur), 60)
        print(f"💾 Saved: {final_path} ({m}m {s}s)")


def recover_partial(session: str | None = None) -> tuple[bytes | None, str | None]:
    """Recover audio from a partial recording.

    Args:
        session: Specific session ID to recover, or None to find latest partial

    Returns:
        tuple: (wav_bytes, session_id) or (None, None) if no partial found
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if session:
        partial_path = OUTPUT_DIR / f"{session}.partial.wav"
        if partial_path.exists():
            wav_bytes = partial_path.read_bytes()
            # Rename to final
            final_path = OUTPUT_DIR / f"{session}.wav"
            partial_path.rename(final_path)
            print(f"🔄 Recovered: {final_path}")
            return wav_bytes, session
        return None, None

    # Find most recent partial
    partials = sorted(OUTPUT_DIR.glob("*.partial.wav"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    if not partials:
        print("ℹ️  No partial recordings found")
        return None, None

    partial_path = partials[0]
    session = partial_path.stem.replace(".partial", "")
    wav_bytes = partial_path.read_bytes()

    # Rename to final
    final_path = OUTPUT_DIR / f"{session}.wav"
    partial_path.rename(final_path)

    # Duration: bytes / (sample_rate * bytes_per_sample * channels)
    dur = len(wav_bytes) / (SAMPLE_RATE * 2 * CHANNELS)
    m, s = divmod(int(dur), 60)
    print(f"🔄 Recovered: {final_path} ({m}m {s}s)")

    return wav_bytes, session


def record(duration_secs: int | None = None) -> tuple[bytes | None, str | None]:
    """
    Record audio until Ctrl+C or max duration.

    In auto mode, captures from both microphone and system audio (via BlackHole)
    when available. Falls back to mic-only if BlackHole is not installed.

    Audio is saved incrementally to disk every few seconds, so even if
    the process is killed, you won't lose more than a few seconds of audio.

    Args:
        duration_secs: Optional fixed recording duration in seconds.
                       Clamped to MAX_DURATION. Ctrl+C still stops early.

    Returns:
        tuple: (wav_bytes, session_id) or (None, None) if no audio
    """
    global _chunks, _chunks_secondary  # pylint: disable=global-statement
    _require_audio_deps()

    # Resolve audio device configuration
    try:
        rec_config = resolve_recording_config(AUDIO_DEVICE)
    except RuntimeError as e:
        print(f"❌ Audio device error: {e}")
        return None, None

    _stop_event.clear()
    with _chunks_lock:
        _chunks = []
    with _chunks_secondary_lock:
        _chunks_secondary = []

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Set up signal handler
    old_handler = signal.signal(signal.SIGINT, _on_signal)

    def callback_primary(indata, _frames, _time_info, _status):
        if not _stop_event.is_set():
            mono = _to_mono(indata) if indata.shape[1] > 1 else indata.copy()
            with _chunks_lock:
                _chunks.append(mono)

    def callback_secondary(indata, _frames, _time_info, _status):
        if not _stop_event.is_set():
            mono = _to_mono(indata) if indata.shape[1] > 1 else indata.copy()
            with _chunks_secondary_lock:
                _chunks_secondary.append(mono)

    effective_max = min(duration_secs, MAX_DURATION) if duration_secs else MAX_DURATION

    play_start_tone()
    if duration_secs:
        dm, ds = divmod(effective_max, 60)
        print(f"\n🎙️  RECORDING STARTED ({dm}m {ds}s)")
        print("   Press Ctrl+C to stop early")
    else:
        print("\n🎙️  RECORDING STARTED")
        print("   Press Ctrl+C to stop")
    print(f"   Audio: {rec_config.description}\n")

    last_save_time = time.time()

    def _recording_loop(effective_max, duration_secs, session):
        """Main recording loop shared by single and dual-stream modes."""
        nonlocal last_save_time
        start = datetime.now()
        while not _stop_event.is_set():
            time.sleep(0.1)

            elapsed = (datetime.now() - start).seconds

            # Incremental save every SAVE_INTERVAL_SECS
            if time.time() - last_save_time >= SAVE_INTERVAL_SECS:
                _save_incremental(session)
                last_save_time = time.time()

            if elapsed >= effective_max:
                if duration_secs:
                    print("\r   ⏱️  Duration reached              ")
                else:
                    print("\r   ⏱️  Max duration reached        ")
                break

            if duration_secs:
                remaining = max(0, effective_max - elapsed)
                rm, rs = divmod(remaining, 60)
                dot = "🔴" if int(time.time() * 2) % 2 == 0 else "⚫"
                print(f"\r   {dot} Recording: {rm:02d}:{rs:02d} remaining", end="", flush=True)
            else:
                m, s = divmod(elapsed, 60)
                dot = "🔴" if int(time.time() * 2) % 2 == 0 else "⚫"
                print(f"\r   {dot} {m:02d}:{s:02d}", end="", flush=True)

    try:
        if rec_config.mode == "dual":
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=rec_config.primary_channels,
                device=rec_config.primary_device,
                dtype=np.int16,
                callback=callback_primary,
            ):
                with sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=rec_config.secondary_channels,
                    device=rec_config.secondary_device,
                    dtype=np.int16,
                    callback=callback_secondary,
                ):
                    _recording_loop(effective_max, duration_secs, session)
        else:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=rec_config.primary_channels,
                device=rec_config.primary_device,
                dtype=np.int16,
                callback=callback_primary,
            ):
                _recording_loop(effective_max, duration_secs, session)

    finally:
        # Restore old signal handler
        signal.signal(signal.SIGINT, old_handler)

    play_stop_tone()
    print("\r   🛑 Recording stopped             ")

    # Get final mixed audio
    chunks_copy = _get_mixed_chunks()

    if not chunks_copy:
        print("❌ No audio recorded")
        # Clean up any partial file
        partial = OUTPUT_DIR / f"{session}.partial.wav"
        if partial.exists():
            partial.unlink()
        return None, None

    # Final save
    wav = _chunks_to_wav(chunks_copy)

    # Save final file (removes .partial)
    _save_incremental(session, final=True)

    return wav, session
