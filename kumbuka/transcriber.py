"""Whisper transcription functionality."""

import httpx

from .config import WHISPER_URL, TEMP_DIR


def transcribe(wav: bytes, session: str) -> str | None:
    """
    Send audio to Whisper for transcription.

    Args:
        wav: WAV audio bytes
        session: Session ID for saving transcript

    Returns:
        Transcript text or None if failed
    """
    print("\n📝 Transcribing with Whisper...")

    with httpx.Client(timeout=600) as client:
        resp = client.post(
            WHISPER_URL,
            files={"file": ("audio.wav", wav, "audio/wav")},
            data={"model": "whisper-1", "response_format": "json"}
        )
        resp.raise_for_status()
        text = resp.json().get("text", "")

    if text:
        path = TEMP_DIR / f"{session}.txt"
        path.write_text(text)
        print(f"💾 Saved: {path} ({len(text)} chars)")

    return text


def check_whisper() -> bool:
    """Check if Whisper server is running."""
    try:
        health_url = WHISPER_URL.replace("/v1/audio/transcriptions", "/health")
        resp = httpx.get(health_url, timeout=2)
        return resp.status_code == 200
    # pylint: disable=broad-exception-caught
    except Exception:
        return False
