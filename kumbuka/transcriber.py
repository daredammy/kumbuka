"""Whisper transcription functionality."""

import re
import subprocess
import time
from collections import Counter

import httpx

from .config import WHISPER_URL, TEMP_DIR, WHISPER_CMD


def _is_hallucination(text: str) -> bool:
    """
    Detect if Whisper output is a hallucination (stuck in a loop).
    
    Common patterns:
    - Repeated bracketed phrases: "[ sign unzipping ] [ sign unzipping ]..."
    - Repeated short phrases: "Thank you. Thank you. Thank you..."
    
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
        result = subprocess.run(
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


def transcribe(wav: bytes, session: str, retry_on_hallucination: bool = True) -> str | None:
    """
    Send audio to Whisper for transcription.

    Args:
        wav: WAV audio bytes
        session: Session ID for saving transcript
        retry_on_hallucination: If True, restart Whisper and retry on hallucination

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

    # Check for hallucination
    if _is_hallucination(text):
        print("⚠️  Detected Whisper hallucination (model stuck in loop)")
        
        if retry_on_hallucination:
            if _restart_whisper():
                print("🔁 Retrying transcription...")
                return transcribe(wav, session, retry_on_hallucination=False)
            else:
                print("❌ Could not restart Whisper. Set KUMBUKA_WHISPER_CMD to enable auto-restart.")
                print("   Example: export KUMBUKA_WHISPER_CMD='/path/to/whisper-server --port 2022 ...'")
        return None

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
