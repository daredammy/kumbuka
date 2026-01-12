"""Whisper transcription functionality."""

import re
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path

import httpx

from .config import WHISPER_URL, TEMP_DIR, WHISPER_CMD

# Chunk long audio into 10-minute segments to avoid Whisper hallucinations
CHUNK_DURATION_SECS = 600  # 10 minutes


def _is_hallucination(text: str) -> bool:
    """
    Detect if Whisper output is a hallucination (stuck in a loop).

    Common patterns:
    - Repeated bracketed phrases: "[ sign unzipping ] [ sign unzipping ]..."
    - Repeated short phrases: "Thank you. Thank you. Thank you..."
    - Repeated parenthetical phrases: "(bell dings) (bell dings)..."

    This happens when the Whisper model gets into a degenerate state,
    often after running for extended periods without restart.
    """
    if not text or len(text) < 100:
        return False

    # Check for repeated lines
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if len(lines) < 5:
        return False

    # If >80% of lines are identical, it's likely a hallucination
    counts = Counter(lines)
    most_common_count = counts.most_common(1)[0][1]
    if most_common_count / len(lines) > 0.8:
        return True

    # Check for bracketed hallucination pattern: [ something ] repeated
    bracket_pattern = r'\[\s*[^\]]{1,40}\s*\]'
    brackets = re.findall(bracket_pattern, text)
    if len(brackets) >= 5:
        bracket_counts = Counter(brackets)
        most_common_bracket = bracket_counts.most_common(1)[0]
        # If same bracket appears 5+ times and is >50% of all brackets
        if most_common_bracket[1] >= 5 and most_common_bracket[1] / len(brackets) > 0.5:
            return True

    # Check for parenthetical hallucination pattern: (something) repeated
    paren_pattern = r'\(\s*[^\)]{1,40}\s*\)'
    parens = re.findall(paren_pattern, text)
    if len(parens) >= 5:
        paren_counts = Counter(parens)
        most_common_paren = paren_counts.most_common(1)[0]
        if most_common_paren[1] >= 5 and most_common_paren[1] / len(parens) > 0.5:
            return True

    return False


def _restart_whisper() -> bool:
    """
    Restart the Whisper server to clear corrupted state.

    Returns:
        True if restart successful, False otherwise
    """
    if not WHISPER_CMD:
        print("⚠️  KUMBUKA_WHISPER_CMD not set, cannot restart Whisper")
        return False

    print("🔄 Restarting Whisper server...")

    # Find and kill existing whisper-server process
    try:
        subprocess.run(
            ["pkill", "-f", "whisper-server"],
            capture_output=True,
            check=False
        )
    except Exception:
        pass

    time.sleep(2)

    # Start new instance
    try:
        subprocess.Popen(
            WHISPER_CMD,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"❌ Failed to start Whisper: {e}")
        return False

    # Wait for server to be ready
    for _ in range(10):
        time.sleep(1)
        if check_whisper():
            print("✅ Whisper server restarted")
            return True

    print("❌ Whisper server failed to start")
    return False


def _get_audio_duration(wav_path: Path) -> float | None:
    """Get duration of audio file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(wav_path)
            ],
            capture_output=True,
            text=True,
            check=True
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def _chunk_audio(wav_path: Path, chunk_dir: Path) -> list[Path]:
    """
    Split audio file into chunks using ffmpeg.

    Args:
        wav_path: Path to the input WAV file
        chunk_dir: Directory to store chunks

    Returns:
        List of paths to chunk files
    """
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_pattern = chunk_dir / "chunk_%03d.wav"

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(wav_path),
            "-f", "segment", "-segment_time", str(CHUNK_DURATION_SECS),
            "-c", "copy", str(chunk_pattern)
        ],
        capture_output=True,
        check=True
    )

    # Return sorted list of chunk files
    return sorted(chunk_dir.glob("chunk_*.wav"))


def _transcribe_single(wav_data: bytes, timeout: int = 600) -> str:
    """
    Transcribe a single audio segment.

    Args:
        wav_data: WAV audio bytes
        timeout: Request timeout in seconds

    Returns:
        Transcript text
    """
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            WHISPER_URL,
            files={"file": ("audio.wav", wav_data, "audio/wav")},
            data={"model": "whisper-1", "response_format": "json"}
        )
        resp.raise_for_status()
        return resp.json().get("text", "")


def transcribe(wav: bytes, session: str, retry_on_hallucination: bool = True) -> str | None:
    """
    Send audio to Whisper for transcription.

    For long audio (>15 minutes), automatically chunks into smaller segments
    to prevent Whisper hallucinations.

    Args:
        wav: WAV audio bytes
        session: Session ID for saving transcript
        retry_on_hallucination: If True, restart Whisper and retry on hallucination

    Returns:
        Transcript text or None if failed
    """
    print("\n📝 Transcribing with Whisper...")

    # Write to temp file to check duration
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav)
        tmp_path = Path(tmp.name)

    try:
        duration = _get_audio_duration(tmp_path)

        # For long audio, use chunked transcription
        if duration and duration > CHUNK_DURATION_SECS * 1.5:  # >15 minutes
            print(
                f"📊 Long audio detected ({duration/60:.1f} min), chunking for reliability...")
            return _transcribe_chunked(tmp_path, session, retry_on_hallucination)

        # Short audio: transcribe directly
        text = _transcribe_single(wav)

        # Check for hallucination
        if _is_hallucination(text):
            print("⚠️  Detected Whisper hallucination (model stuck in loop)")

            if retry_on_hallucination:
                if _restart_whisper():
                    print("🔁 Retrying transcription...")
                    return transcribe(wav, session, retry_on_hallucination=False)
                else:
                    print(
                        "❌ Could not restart Whisper. Set KUMBUKA_WHISPER_CMD to enable auto-restart.")
                    print(
                        "   Example: export KUMBUKA_WHISPER_CMD='/path/to/whisper-server --port 2022 ...'")
            return None

        if text:
            path = TEMP_DIR / f"{session}.txt"
            path.write_text(text)
            print(f"💾 Saved: {path} ({len(text)} chars)")

        return text
    finally:
        tmp_path.unlink(missing_ok=True)


def _transcribe_chunked(wav_path: Path, session: str, retry_on_hallucination: bool = True) -> str | None:
    """
    Transcribe long audio by splitting into chunks.

    Args:
        wav_path: Path to the WAV file
        session: Session ID for saving transcript
        retry_on_hallucination: If True, restart Whisper and retry failed chunks

    Returns:
        Combined transcript text or None if failed
    """
    chunk_dir = TEMP_DIR / f"{session}_chunks"

    try:
        # Split audio into chunks
        chunks = _chunk_audio(wav_path, chunk_dir)
        print(f"📦 Split into {len(chunks)} chunks")

        transcripts = []
        failed_chunks = []

        for i, chunk_path in enumerate(chunks):
            print(f"📝 Transcribing chunk {i+1}/{len(chunks)}...")

            chunk_data = chunk_path.read_bytes()
            text = _transcribe_single(chunk_data)

            if _is_hallucination(text):
                print(f"⚠️  Hallucination detected in chunk {i+1}")
                failed_chunks.append((i, chunk_path))
                transcripts.append(None)
            else:
                transcripts.append(text)

        # Retry failed chunks after restart
        if failed_chunks and retry_on_hallucination:
            if _restart_whisper():
                print(f"🔁 Retrying {len(failed_chunks)} failed chunk(s)...")
                for i, chunk_path in failed_chunks:
                    chunk_data = chunk_path.read_bytes()
                    text = _transcribe_single(chunk_data)

                    if _is_hallucination(text):
                        print(
                            f"❌ Chunk {i+1} still hallucinating after restart")
                        transcripts[i] = "[TRANSCRIPTION FAILED - AUDIO SEGMENT UNCLEAR]"
                    else:
                        print(f"✅ Chunk {i+1} recovered")
                        transcripts[i] = text

        # Combine transcripts
        combined = "\n\n".join(t for t in transcripts if t)

        if combined:
            path = TEMP_DIR / f"{session}.txt"
            path.write_text(combined)
            print(f"💾 Saved: {path} ({len(combined)} chars)")

        return combined if combined else None

    finally:
        # Cleanup chunk files
        if chunk_dir.exists():
            for f in chunk_dir.glob("*"):
                f.unlink(missing_ok=True)
            chunk_dir.rmdir()


def check_whisper() -> bool:
    """Check if Whisper server is running."""
    try:
        health_url = WHISPER_URL.replace("/v1/audio/transcriptions", "/health")
        resp = httpx.get(health_url, timeout=2)
        return resp.status_code == 200
    # pylint: disable=broad-exception-caught
    except Exception:
        return False
