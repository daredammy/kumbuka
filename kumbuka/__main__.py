"""Kumbuka CLI entry point."""

from typing import Optional
import os
import sys
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

from .config import (
    SAMPLE_RATE, CHANNELS, PACKAGE_DIR, PROMPT_MINUTES, TEMP_DIR, ENV_FILE, CONFIG_DIR,
    NOTION_URL, NOTION_MODE
)
from .recorder import record, recover_partial
from .transcriber import transcribe, check_fluidaudio
from .processor import process_with_claude, find_claude, sanitize_filename, format_notes


# Valid config keys and their env var names
CONFIG_KEYS = {
    "output_dir": "KUMBUKA_OUTPUT_DIR",
    "fluidaudio_repo": "KUMBUKA_FLUIDAUDIO_REPO",
    "notion_url": "KUMBUKA_NOTION_URL",
    "notion_mode": "KUMBUKA_NOTION_MODE",
    "notion_token": "NOTION_TOKEN",
    "max_recording_seconds": "KUMBUKA_MAX_RECORDING_SECONDS",
    "prompt_minutes": "KUMBUKA_PROMPT_MINUTES",
    "user_name": "KUMBUKA_USER_NAME",
}


PLIST_NAME = "com.kumbuka.monitor.plist"
PLIST_SRC = PACKAGE_DIR / "daemon" / PLIST_NAME
PLIST_DST = Path.home() / "Library/LaunchAgents" / PLIST_NAME


def check_requirements() -> bool:
    """Verify all requirements are met."""
    errors = []

    if not check_fluidaudio():
        errors.append(
            "❌ FluidAudio not found or Swift not installed\n"
            "   Install Swift and clone FluidAudio:\n"
            "   git clone https://github.com/FluidInference/FluidAudio.git ~/FluidAudio"
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


def _rename_session_files(session: str, filename: str | None):
    """Rename session .wav and .txt files to a descriptive name."""
    if not filename:
        return

    for ext in (".wav", ".txt"):
        old = TEMP_DIR / f"{session}{ext}"
        new = TEMP_DIR / f"{filename}{ext}"
        if old.exists():
            # Avoid overwriting existing files by appending the date
            if new.exists():
                new = TEMP_DIR / f"{filename}_{session}{ext}"
            old.rename(new)
            print(f"📁 Renamed: {old.name} → {new.name}")


def _save_to_notion(result: dict):
    """Create a Notion page from structured output (token mode only)."""
    if not NOTION_URL or NOTION_MODE != "token":
        return

    from .notion import create_page

    title = result.get("title", "Untitled Meeting")
    content = format_notes(result)

    try:
        page = create_page(NOTION_URL, title, content)
        print(f"📝 Notion page: {page['url']}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"⚠️  Notion page creation failed: {e}")


def do_record():
    """Main recording flow."""
    if not check_requirements():
        sys.exit(1)

    # Record
    wav, session = record()
    if not wav:
        sys.exit(1)

    # Transcribe
    wav_path = TEMP_DIR / f"{session}.wav"
    transcript = transcribe(wav_path)
    if not transcript:
        print("❌ Transcription failed")
        sys.exit(1)

    # Process with Claude
    # Duration: bytes / (sample_rate * bytes_per_sample * channels)
    duration_secs = len(wav) / (SAMPLE_RATE * 2 * CHANNELS)
    m, s = divmod(int(duration_secs), 60)

    result = process_with_claude(
        transcript=transcript,
        duration=f"{m}m {s}s",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    if result:
        filename = sanitize_filename(result.get("filename", ""))
        _rename_session_files(session, filename)
        _save_to_notion(result)

    print("\n✅ Done!")


def do_recover(session: Optional[str] = None):
    """Recover a partial recording that was interrupted."""
    if not check_requirements():
        sys.exit(1)

    wav, recovered_session = recover_partial(session)
    if not wav or not recovered_session:
        print("❌ No partial recording to recover")
        sys.exit(1)
    assert recovered_session is not None  # narrowing for type checker

    # Transcribe
    wav_path = TEMP_DIR / f"{recovered_session}.wav"
    transcript = transcribe(wav_path)
    if not transcript:
        print("❌ Transcription failed")
        sys.exit(1)

    # Process with Claude
    # Duration: bytes / (sample_rate * bytes_per_sample * channels)
    duration_secs = len(wav) / (SAMPLE_RATE * 2 * CHANNELS)
    m, s = divmod(int(duration_secs), 60)

    result = process_with_claude(
        transcript=transcript,
        duration=f"{m}m {s}s",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    if result:
        filename = sanitize_filename(result.get("filename", ""))
        _rename_session_files(recovered_session, filename)
        _save_to_notion(result)

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
    plist_content = plist_content.replace("__OUTPUT_DIR__", str(TEMP_DIR))

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
        print(f"   Logs: {TEMP_DIR}/monitor.log")
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
        log = TEMP_DIR / "monitor.log"
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
            print(
                f"  📅 {event.title} @ {event.start.strftime('%H:%M')} ({event.calendar_name})")
    else:
        print("  (none)")


def _read_env_file() -> dict[str, str]:
    """Read key=value pairs from the env file."""
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, val = stripped.partition("=")
                values[key.strip()] = val.strip().strip('"')
    return values


def _write_env_value(env_var: str, value: str):
    """Set a value in the env file, preserving comments and other keys."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    lines = []
    found = False
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.partition("=")[0].strip()
                if key == env_var:
                    lines.append(f'{env_var}="{value}"')
                    found = True
                    continue
            lines.append(line)

    if not found:
        lines.append(f'{env_var}="{value}"')

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def config_set(key: str, value: str):
    """Set a config value."""
    if key not in CONFIG_KEYS:
        print(f"Unknown config key: {key}")
        print(f"Valid keys: {', '.join(sorted(CONFIG_KEYS))}")
        sys.exit(1)

    env_var = CONFIG_KEYS[key]
    _write_env_value(env_var, value)
    print(f"Set {key} = {value}")


def config_get(key: str):
    """Get a config value."""
    if key not in CONFIG_KEYS:
        print(f"Unknown config key: {key}")
        print(f"Valid keys: {', '.join(sorted(CONFIG_KEYS))}")
        sys.exit(1)

    env_var = CONFIG_KEYS[key]
    values = _read_env_file()
    value = values.get(env_var)
    if value:
        print(value)
    else:
        print(f"{key} is not set")


def config_list():
    """List all config values."""
    values = _read_env_file()
    for key, env_var in sorted(CONFIG_KEYS.items()):
        value = values.get(env_var, "")
        if value:
            print(f"  {key} = {value}")
        else:
            print(f"  {key} (not set)")


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

Config:
  kumbuka config              Show all settings
  kumbuka config get <key>    Get a setting
  kumbuka config set <key> <value>  Set a setting

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
    elif args[0] == "config":
        if len(args) < 2:
            config_list()
        elif args[1] == "set":
            if len(args) < 4:
                print("Usage: kumbuka config set <key> <value>")
                sys.exit(1)
            config_set(args[2], " ".join(args[3:]))
        elif args[1] == "get":
            if len(args) < 3:
                print("Usage: kumbuka config get <key>")
                sys.exit(1)
            config_get(args[2])
        else:
            print(f"Unknown config command: {args[1]}")
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
