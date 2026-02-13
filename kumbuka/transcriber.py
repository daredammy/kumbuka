"""FluidAudio transcription functionality."""

import subprocess
from pathlib import Path

from .config import FLUIDAUDIO_BIN, FLUIDAUDIO_REPO


def _ensure_fluidaudio() -> bool:
    """
    Ensure FluidAudio binary exists, building it if necessary.
    """
    if FLUIDAUDIO_BIN.exists():
        return True

    repo_path = Path(FLUIDAUDIO_REPO)
    if not repo_path.exists():
        print(f"❌ FluidAudio repo not found at {repo_path}")
        print("   Clone it: git clone https://github.com/FluidInference/FluidAudio.git ~/FluidAudio")
        return False

    print("🔨 Building FluidAudio (this may take a minute)...")
    try:
        subprocess.run(
            ["swift", "build", "-c", "release"],
            cwd=repo_path,
            check=True,
            capture_output=False
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to build FluidAudio: {e}")
        return False
    except FileNotFoundError:
        print("❌ Swift toolchain not found. Install Xcode or Swift.")
        return False


def transcribe(wav_path: Path) -> str | None:
    """
    Transcribe audio using FluidAudio (Parakeet TDT).

    Args:
        wav_path: Path to the WAV file

    Returns:
        Transcript text or None if failed
    """
    print("\n📝 Transcribing with FluidAudio...")

    if not _ensure_fluidaudio():
        return None

    try:
        # Run FluidAudio CLI
        # Usage: fluidaudio transcribe <file>
        result = subprocess.run(
            [str(FLUIDAUDIO_BIN), "transcribe", str(wav_path)],
            capture_output=True,
            text=True,
            check=True
        )
        
        text = result.stdout.strip()
        if text:
            # Save transcript next to audio for reference
            txt_path = wav_path.with_suffix(".txt")
            txt_path.write_text(text)
            print(f"💾 Saved: {txt_path} ({len(text)} chars)")
            return text
        
        print("⚠️  No text transcribed")
        return None

    except subprocess.CalledProcessError as e:
        print(f"❌ FluidAudio failed: {e.stderr}")
        return None
    except Exception as e:
        print(f"❌ Transcription error: {e}")
        return None


def check_fluidaudio() -> bool:
    """Check if FluidAudio requirements are met."""
    # Check Swift
    try:
        subprocess.run(["swift", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

    # Check Repo
    if not Path(FLUIDAUDIO_REPO).exists():
        return False

    return True