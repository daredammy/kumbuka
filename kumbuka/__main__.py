"""Kumbuka CLI entry point."""

import sys
from datetime import datetime

from .config import WHISPER_URL, NOTION_URL, SAMPLE_RATE
from .recorder import record
from .transcriber import transcribe, check_whisper
from .processor import process_with_claude, find_claude


def check_requirements() -> bool:
    """Verify all requirements are met."""
    errors = []
    
    if not check_whisper():
        errors.append(
            f"❌ Whisper not running at {WHISPER_URL}\n"
            f"   Start it with: voicemode start-service whisper"
        )
    
    if not find_claude():
        errors.append(
            "❌ Claude CLI not found\n"
            "   Install with: npm install -g @anthropic-ai/claude-code"
        )
    
    if not NOTION_URL:
        errors.append(
            "❌ Notion database URL not set\n"
            "   Set KUMBUKA_NOTION_URL environment variable"
        )
    
    if errors:
        print("\n⚠️  Setup incomplete:\n")
        for e in errors:
            print(f"   {e}\n")
        print("See README.md for setup instructions.")
        return False
    
    return True


def main():
    """Main entry point."""
    if not check_requirements():
        sys.exit(1)
    
    # Record
    wav, session = record()
    if not wav:
        sys.exit(1)
    
    # Transcribe
    transcript = transcribe(wav, session)
    if not transcript:
        print("❌ Transcription failed")
        sys.exit(1)
    
    # Process with Claude
    duration_secs = len(wav) / (SAMPLE_RATE * 2)
    m, s = divmod(int(duration_secs), 60)
    
    process_with_claude(
        transcript=transcript,
        duration=f"{m}m {s}s",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
