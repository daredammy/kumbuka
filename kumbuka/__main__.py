"""Kumbuka CLI entry point."""

from typing import Optional
import os
import sys
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

from .config import (
    WHISPER_URL, SAMPLE_RATE, CHANNELS, PACKAGE_DIR, PROMPT_MINUTES
)
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

    wav, recovered_session = recover_partial(session)
    if not wav or not recovered_session:
        print("❌ No partial recording to recover")
        sys.exit(1)

    # Transcribe
    transcript = transcribe(wav, recovered_session)
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
    """Enable meeting monitor daemon (Google Calendar)."""
    from .calendar import is_authenticated

    if not is_authenticated():
        print("❌ Not authenticated with Google Calendar")
        print("   Run: kumbuka calendar auth")
        sys.exit(1)

    # Create plist with correct paths and env vars
    python_path = find_python()
    prompt_minutes = str(PROMPT_MINUTES)
    notion_token = os.getenv("NOTION_TOKEN", "")

    plist_content = PLIST_SRC.read_text()
    plist_content = plist_content.replace("__PYTHON_PATH__", python_path)
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
        print("✅ Meeting monitor enabled")
        print(f"   Prompt: {prompt_minutes} min before meetings")
        print("   Logs: /tmp/kumbuka/monitor.log")
    else:
        print(f"❌ Failed to enable monitor: {result.stderr.decode()}")
        sys.exit(1)


def monitor_disable():
    """Disable meeting monitor daemon."""
    if PLIST_DST.exists():
        subprocess.run(["launchctl", "unload", str(PLIST_DST)],
                       capture_output=True, check=False)
        PLIST_DST.unlink()
        print("✅ Meeting monitor disabled")
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
        print("✅ Meeting monitor is running")
        log = Path("/tmp/kumbuka/monitor.log")
        if log.exists():
            print(f"   Log: {log}")
    else:
        print("❌ Meeting monitor is not running")
        print("   Enable with: kumbuka monitor enable")


def calendar_auth():
    """Authenticate with Google Calendar."""
    from .calendar import authenticate, CREDENTIALS_FILE

    if not CREDENTIALS_FILE.exists():
        print(f"❌ Credentials file not found at {CREDENTIALS_FILE}")
        print("   Download OAuth credentials from Google Cloud Console.")
        sys.exit(1)

    print("Opening browser for Google Calendar authentication...")
    try:
        authenticate()
        print("✅ Successfully authenticated with Google Calendar!")
        print("   You can now use: kumbuka calendar list")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"❌ Authentication failed: {e}")
        sys.exit(1)


def calendar_list():
    """List available calendars."""
    from .calendar import is_authenticated, list_calendars

    if not is_authenticated():
        print("❌ Not authenticated. Run: kumbuka calendar auth")
        sys.exit(1)

    print("Your calendars:")
    for cal in list_calendars():
        print(f"  - {cal['name']}")
        print(f"    ID: {cal['id']}")


def calendar_test():
    """Test calendar by showing upcoming events."""
    from .calendar import is_authenticated, get_upcoming_events, get_current_meetings

    if not is_authenticated():
        print("❌ Not authenticated. Run: kumbuka calendar auth")
        sys.exit(1)

    print("Current meetings:")
    current = get_current_meetings()
    if current:
        for event in current:
            print(f"  🔴 {event.title} ({event.calendar_name})")
    else:
        print("  (none)")

    print("\nUpcoming meetings (next 60 min):")
    upcoming = get_upcoming_events(60)
    if upcoming:
        for event in upcoming:
            print(f"  📅 {event.title} @ {event.start.strftime('%H:%M')} ({event.calendar_name})")
    else:
        print("  (none)")


def print_usage():
    """Print usage information."""
    print("""
Kumbuka - Local-first meeting recorder

Usage:
  kumbuka                     Start recording (Ctrl+C to stop)
  kumbuka recover             Recover last interrupted recording
  kumbuka recover <session>   Recover specific session (e.g. 2025-12-17_14-30-00)

Calendar:
  kumbuka calendar auth       Authenticate with Google Calendar
  kumbuka calendar list       List your calendars
  kumbuka calendar test       Show current/upcoming meetings

Monitor:
  kumbuka monitor enable      Auto-prompt when meetings start
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
    elif args[0] == "calendar":
        if len(args) < 2:
            print("Usage: kumbuka calendar [auth|list|test]")
            sys.exit(1)

        cmd = args[1]
        if cmd == "auth":
            calendar_auth()
        elif cmd == "list":
            calendar_list()
        elif cmd == "test":
            calendar_test()
        else:
            print(f"Unknown calendar command: {cmd}")
            sys.exit(1)
    elif args[0] == "monitor":
        if len(args) < 2:
            print("Usage: kumbuka monitor [enable|disable|status]")
            sys.exit(1)

        cmd = args[1]
        if cmd == "enable":
            monitor_enable()
        elif cmd == "disable":
            monitor_disable()
        elif cmd == "status":
            monitor_status()
        else:
            print(f"Unknown monitor command: {cmd}")
            sys.exit(1)
    else:
        print(f"Unknown command: {args[0]}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
