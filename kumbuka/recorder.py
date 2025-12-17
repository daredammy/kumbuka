"""Audio recording functionality with resilient incremental saving."""

import io
import signal
import time
import wave
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

from .config import SAMPLE_RATE, CHANNELS, MAX_DURATION, TEMP_DIR


# Module state
_stop_event = threading.Event()
_chunks = []
_chunks_lock = threading.Lock()

# Incremental save settings
SAVE_INTERVAL_SECS = 10  # Save to disk every 10 seconds


def _tone(freq=880, dur=0.15, vol=0.3):
    """Play a simple tone."""
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


def _on_signal(sig, frame):
    """Handle Ctrl+C."""
    _stop_event.set()


def _chunks_to_wav(chunks: list) -> bytes:
    """Convert audio chunks to WAV bytes."""
    if not chunks:
        return b""
    audio = np.concatenate(chunks)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    buf.seek(0)
    return buf.read()


def _save_incremental(session: str, final: bool = False):
    """Save current audio to disk incrementally.

    Uses a .partial extension while recording, renamed on final save.
    """
    with _chunks_lock:
        if not _chunks:
            return
        chunks_copy = _chunks.copy()
    
    wav_bytes = _chunks_to_wav(chunks_copy)
    if not wav_bytes:
        return
    
    partial_path = TEMP_DIR / f"{session}.partial.wav"
    final_path = TEMP_DIR / f"{session}.wav"
    
    # Write to partial file
    partial_path.write_bytes(wav_bytes)

    if final:
        # Rename to final
        partial_path.rename(final_path)
        # Duration: bytes / (sample_rate * bytes_per_sample * channels)
        dur = len(wav_bytes) / (SAMPLE_RATE * 2 * CHANNELS)
        m, s = divmod(int(dur), 60)
        print(f"💾 Saved: {final_path} ({m}m {s}s)")


def recover_partial(session: str = None) -> tuple[bytes | None, str | None]:
    """Recover audio from a partial recording.
    
    Args:
        session: Specific session ID to recover, or None to find latest partial
        
    Returns:
        tuple: (wav_bytes, session_id) or (None, None) if no partial found
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    if session:
        partial_path = TEMP_DIR / f"{session}.partial.wav"
        if partial_path.exists():
            wav_bytes = partial_path.read_bytes()
            # Rename to final
            final_path = TEMP_DIR / f"{session}.wav"
            partial_path.rename(final_path)
            print(f"🔄 Recovered: {final_path}")
            return wav_bytes, session
        return None, None
    
    # Find most recent partial
    partials = sorted(TEMP_DIR.glob("*.partial.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not partials:
        print("ℹ️  No partial recordings found")
        return None, None
    
    partial_path = partials[0]
    session = partial_path.stem.replace(".partial", "")
    wav_bytes = partial_path.read_bytes()
    
    # Rename to final
    final_path = TEMP_DIR / f"{session}.wav"
    partial_path.rename(final_path)
    
    # Duration: bytes / (sample_rate * bytes_per_sample * channels)
    dur = len(wav_bytes) / (SAMPLE_RATE * 2 * CHANNELS)
    m, s = divmod(int(dur), 60)
    print(f"🔄 Recovered: {final_path} ({m}m {s}s)")
    
    return wav_bytes, session


def record() -> tuple[bytes | None, str | None]:
    """
    Record audio from microphone until Ctrl+C or max duration.
    
    Audio is saved incrementally to disk every few seconds, so even if
    the process is killed, you won't lose more than a few seconds of audio.
    
    Returns:
        tuple: (wav_bytes, session_id) or (None, None) if no audio
    """
    global _chunks

    _stop_event.clear()
    with _chunks_lock:
        _chunks = []
    
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    session = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Set up signal handler
    old_handler = signal.signal(signal.SIGINT, _on_signal)
    
    def callback(indata, frames, time_info, status):
        if not _stop_event.is_set():
            with _chunks_lock:
                _chunks.append(indata.copy())
    
    play_start_tone()
    print(f"\n🎙️  RECORDING STARTED")
    print(f"   Press Ctrl+C to stop\n")
    
    last_save_time = time.time()
    
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, 
            channels=CHANNELS, 
            dtype=np.int16, 
            callback=callback
        ):
            start = datetime.now()
            while not _stop_event.is_set():
                # Use time.sleep instead of sd.sleep - responds to signals on macOS
                time.sleep(0.1)
                
                elapsed = (datetime.now() - start).seconds
                
                # Incremental save every SAVE_INTERVAL_SECS
                if time.time() - last_save_time >= SAVE_INTERVAL_SECS:
                    _save_incremental(session)
                    last_save_time = time.time()
                
                if elapsed >= MAX_DURATION:
                    print(f"\r   ⏱️  Max duration reached        ")
                    break
                    
                m, s = divmod(elapsed, 60)
                dot = "🔴" if int(time.time() * 2) % 2 == 0 else "⚫"
                print(f"\r   {dot} {m:02d}:{s:02d}", end="", flush=True)
    
    finally:
        # Restore old signal handler
        signal.signal(signal.SIGINT, old_handler)
    
    play_stop_tone()
    print(f"\r   🛑 Recording stopped             ")
    
    with _chunks_lock:
        if not _chunks:
            print("❌ No audio recorded")
            # Clean up any partial file
            partial = TEMP_DIR / f"{session}.partial.wav"
            if partial.exists():
                partial.unlink()
            return None, None
        
        chunks_copy = _chunks.copy()
    
    # Final save
    wav = _chunks_to_wav(chunks_copy)
    
    # Save final file (removes .partial)
    _save_incremental(session, final=True)
    
    return wav, session
