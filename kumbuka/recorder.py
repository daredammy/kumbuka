"""Audio recording functionality."""

import io
import signal
import wave
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

from .config import SAMPLE_RATE, CHANNELS, MAX_DURATION, TEMP_DIR


# Module state
_recording = True
_chunks = []


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
    global _recording
    _recording = False


def record() -> tuple[bytes | None, str | None]:
    """
    Record audio from microphone until Ctrl+C or max duration.
    
    Returns:
        tuple: (wav_bytes, session_id) or (None, None) if no audio
    """
    global _recording, _chunks
    _recording = True
    _chunks = []
    
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    session = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    signal.signal(signal.SIGINT, _on_signal)
    
    def callback(indata, frames, time, status):
        if _recording:
            _chunks.append(indata.copy())
    
    play_start_tone()
    print(f"\n🎙️  RECORDING STARTED")
    print(f"   Press Ctrl+C to stop\n")
    
    with sd.InputStream(
        samplerate=SAMPLE_RATE, 
        channels=CHANNELS, 
        dtype=np.int16, 
        callback=callback
    ):
        start = datetime.now()
        while _recording:
            sd.sleep(500)  # Update every 0.5s
            elapsed = (datetime.now() - start).seconds
            if elapsed >= MAX_DURATION:
                print(f"\r   ⏱️  Max duration reached        ")
                break
            m, s = divmod(elapsed, 60)
            dot = "🔴" if int(datetime.now().timestamp() * 2) % 2 == 0 else "⚫"
            print(f"\r   {dot} {m:02d}:{s:02d}", end="", flush=True)
    
    play_stop_tone()
    print(f"\r   🛑 Recording stopped             ")
    
    if not _chunks:
        print("❌ No audio recorded")
        return None, None
    
    # Combine chunks and convert to WAV
    audio = np.concatenate(_chunks)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    buf.seek(0)
    wav = buf.read()
    
    # Save backup
    audio_path = TEMP_DIR / f"{session}.wav"
    audio_path.write_bytes(wav)
    
    dur = len(wav) / (SAMPLE_RATE * 2)
    m, s = divmod(int(dur), 60)
    print(f"💾 Saved: {audio_path} ({m}m {s}s)")
    
    return wav, session
