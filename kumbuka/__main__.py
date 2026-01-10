"""Kumbuka CLI entry point."""

from typing import Optional
import os
import sys
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

from .config import WHISPER_URL, SAMPLE_RATE, CHANNELS, PACKAGE_DIR
from .recorder import record, recover_partial
from .transcriber import transcribe, check_whisper
from .processor import process_with_claude, find_claude


PLIST_NAME = "com.kumbuka.monitor.plist"
PLIST_SRC = PACKAGE_DIR / "daemon" / PLIST_NAME
PLIST_DST = Path.home() / "Library/LaunchAgents" / PLIST_NAME


def check_requirements() -> bool:
    """Verify all requirements are met."""
    errors = []

    if not check_whisper():
        errors.append(
            f"❌ Whisper not running at {WHISPER_URL}\n"
            "   Start it with: voicemode start-service whisper"
        )

    if not find_claude():
        errors.append(
            "❌ Claude CLI not found\n"
            "   Install with: npm install -g @anthropic-ai/claude-code"
        )

    if errors:
        print("\n⚠️  Setup incomplete:\n")
        for e in errors:
            print(f"   {e}\n")
        print("See README.md for setup instructions.")
        return False

    return True


def do_record():
    """Main recording flow."""
    if not check_requirements():
        sys.exit(1)

    # Record
    wav, session = record()
    if not wav:
        sys.exit(1)

    # Transcribe
    transcript = transcribe(wav, session or "")
    if not transcript:
        print("❌ Transcription failed")
        sys.exit(1)

    # Process with Claude
    # Duration: bytes / (sample_rate * bytes_per_sample * channels)
    duration_secs = len(wav) / (SAMPLE_RATE * 2 * CHANNELS)
    m, s = divmod(int(duration_secs), 60)

    process_with_claude(
        transcript=transcript,
        duration=f"{m}m {s}s",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    print("\n✅ Done!")


def do_recover(session: Optional[str] = None):
    """Recover a partial recording that was interrupted."""
    if not check_requirements():
        sys.exit(1)

    wav, session = recover_partial(session)
    if not wav:
        print("❌ No partial recording to recover")
        sys.exit(1)

    # Transcribe
    transcript = transcribe(wav, session)
    if not transcript:
        print("❌ Transcription failed")
        sys.exit(1)

    # Process with Claude
    # Duration: bytes / (sample_rate * bytes_per_sample * channels)
    duration_secs = len(wav) / (SAMPLE_RATE * 2 * CHANNELS)
    m, s = divmod(int(duration_secs), 60)

    process_with_claude(
        transcript=transcript,
        duration=f"{m}m {s}s",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    print("\n✅ Recovery complete!")


def find_python() -> str:
    """Find python that has kumbuka installed."""
    # Try uv's tool python first
    uv_python = Path.home() / ".local/share/uv/tools/kumbuka/bin/python"
    if uv_python.exists():
        return str(uv_python)

    # Fall back to which python
    python = shutil.which("python3") or shutil.which("python")
    return python or "/usr/bin/python3"


def monitor_enable():
    """Enable calendar monitoring daemon."""

    # Create plist with correct paths and env vars
    python_path = find_python()
    calendars = os.getenv("KUMBUKA_CALENDARS", "")
    prompt_minutes = os.getenv("KUMBUKA_PROMPT_MINUTES", "2")
    notion_token = os.getenv("NOTION_TOKEN", "")

    plist_content = PLIST_SRC.read_text()
    plist_content = plist_content.replace("__PYTHON_PATH__", python_path)
    plist_content = plist_content.replace("__CALENDARS__", calendars)
    plist_content = plist_content.replace("__PROMPT_MINUTES__", prompt_minutes)
    plist_content = plist_content.replace("__NOTION_TOKEN__", notion_token)

    PLIST_DST.parent.mkdir(parents=True, exist_ok=True)
    PLIST_DST.write_text(plist_content)

    # Load the agent
    subprocess.run(["launchctl", "unload", str(PLIST_DST)],
                   capture_output=True, check=False)
    result = subprocess.run(["launchctl", "load", str(
        PLIST_DST)], capture_output=True, check=False)

    if result.returncode == 0:
        print("✅ Calendar monitor enabled")
        if calendars:
            print(f"   Watching: {calendars}")
        else:
            print("   Watching: all calendars")
        print(f"   Prompt: {prompt_minutes} minutes before meetings")
        print("   Logs: /tmp/kumbuka/monitor.log")
    else:
        print(f"❌ Failed to enable monitor: {result.stderr.decode()}")
        sys.exit(1)


def monitor_disable():
    """Disable calendar monitoring daemon."""
    if PLIST_DST.exists():
        subprocess.run(["launchctl", "unload", str(PLIST_DST)],
                       capture_output=True, check=False)
        PLIST_DST.unlink()
        print("✅ Calendar monitor disabled")
    else:
        print("ℹ️  Monitor was not enabled")


def monitor_status():
    """Check if monitor is running."""
    result = subprocess.run(
        ["launchctl", "list"],
        capture_output=True,
        text=True,
        check=False
    )

    if "com.kumbuka.monitor" in result.stdout:
        print("✅ Calendar monitor is running")
        # Try to get last check time from log
        log = Path("/tmp/kumbuka/monitor.log")
        if log.exists():
            print(f"   Log: {log}")
    else:
        print("❌ Calendar monitor is not running")
        print("   Enable with: kumbuka monitor enable")


def monitor_permissions():
    """Request calendar permissions using the daemon's Python executable."""
    print("Requesting calendar permissions...")
    print("A system dialog should appear asking for calendar access.\n")

    # Use the same Python that the daemon will use
    python_path = find_python()

    result = subprocess.run(
        [python_path, "-c", """
from kumbuka.daemon.monitor import request_calendar_permission
import sys
sys.exit(0 if request_calendar_permission() else 1)
"""],
        capture_output=False,
        check=False
    )

    if result.returncode == 0:
        print("\nYou can now enable the monitor with: kumbuka monitor enable")
    else:
        print("\nWithout calendar permissions, the monitor cannot detect meetings.")
        print("You can manually grant access in System Settings → Privacy & Security → Calendars")


def print_usage():
    """Print usage information."""
    print("""
Kumbuka - Local-first meeting recorder

Usage:
  kumbuka                     Start recording (Ctrl+C to stop)
  kumbuka recover             Recover last interrupted recording
  kumbuka recover <session>   Recover specific session (e.g. 2025-12-17_14-30-00)
  kumbuka monitor permissions Request calendar access (run this first!)
  kumbuka monitor enable      Auto-prompt when calendar meetings start
  kumbuka monitor disable     Turn off auto-prompts
  kumbuka monitor status      Check if monitor is running
  kumbuka help                Show this message

Audio is saved incrementally, so interrupted recordings can be recovered.
""")


def main():
    """Main entry point."""
    args = sys.argv[1:]

    if args and (args[0] == "help" or args[0] == "--help" or args[0] == "-h"):
        print_usage()
        return

    if not args:
        # Default: record
        do_record()
    elif args[0] == "recover":
        # Recover interrupted recording
        session = args[1] if len(args) > 1 else None
        do_recover(session)
    elif args[0] == "monitor":
        if len(args) < 2:
            print("Usage: kumbuka monitor [permissions|enable|disable|status]")
            sys.exit(1)

        cmd = args[1]
        if cmd == "enable":
            monitor_enable()
        elif cmd == "disable":
            monitor_disable()
        elif cmd == "status":
            monitor_status()
        elif cmd == "permissions":
            monitor_permissions()
        else:
            print(f"Unknown monitor command: {cmd}")
            sys.exit(1)
    else:
        print(f"Unknown command: {args[0]}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
