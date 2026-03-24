"""Kumbuka CLI entry point."""

from typing import Optional
import sys
import subprocess
from datetime import datetime
from pathlib import Path

from .config import (
    SAMPLE_RATE, CHANNELS, PACKAGE_DIR, PROMPT_MINUTES, OUTPUT_DIR, LOG_DIR, ENV_FILE, CONFIG_DIR,
    NOTES_DESTINATION, NOTION_URL, NOTION_MODE, OBSIDIAN_VAULT, OBSIDIAN_FOLDER, AUTO_RECORD, BUFFER_MINUTES
)
from .filenames import sanitize_filename
from .recorder import record, recover_partial
from .transcriber import transcribe, check_fluidaudio
from .processor import process_with_claude, find_claude
from .notes import save_meeting_notes


# Valid config keys and their env var names
CONFIG_KEYS = {
    "output_dir": "KUMBUKA_OUTPUT_DIR",
    "fluidaudio_repo": "KUMBUKA_FLUIDAUDIO_REPO",
    "notes_destination": "KUMBUKA_NOTES_DESTINATION",
    "notion_url": "KUMBUKA_NOTION_URL",
    "notion_mode": "KUMBUKA_NOTION_MODE",
    "notion_token": "NOTION_TOKEN",
    "obsidian_vault": "KUMBUKA_OBSIDIAN_VAULT",
    "obsidian_folder": "KUMBUKA_OBSIDIAN_FOLDER",
    "max_recording_seconds": "KUMBUKA_MAX_RECORDING_SECONDS",
    "prompt_minutes": "KUMBUKA_PROMPT_MINUTES",
    "user_name": "KUMBUKA_USER_NAME",
    "auto_record": "KUMBUKA_AUTO_RECORD",
    "buffer_minutes": "KUMBUKA_BUFFER_MINUTES",
    "log_dir": "KUMBUKA_LOG_DIR",
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


def _run_with_retry(label: str, fn, *args, **kwargs):
    """Run a function with retry-on-failure prompt.

    On failure, asks user to [r]etry, [s]kip, or [q]uit.
    Returns the function result, or None if skipped.
    """
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"\n⚠️  {label} failed: {e}")
            while True:
                choice = input("   [r]etry / [s]kip / [q]uit? ").strip().lower()
                if choice in ("r", "retry"):
                    print(f"🔄 Retrying {label}...")
                    break
                if choice in ("s", "skip"):
                    return None
                if choice in ("q", "quit"):
                    sys.exit(1)


def _rename_session_files(session: str, filename: str | None):
    """Rename session .wav and .txt files to a descriptive name."""
    if not filename:
        return

    for ext in (".wav", ".txt"):
        old = OUTPUT_DIR / f"{session}{ext}"
        new = OUTPUT_DIR / f"{filename}{ext}"
        if old.exists():
            # Avoid overwriting existing files by appending the date
            if new.exists():
                new = OUTPUT_DIR / f"{filename}_{session}{ext}"
            old.rename(new)
            print(f"📁 Renamed: {old.name} → {new.name}")


def _save_notes(result: dict) -> tuple[str, str] | None:
    """Persist meeting notes to the configured destination."""
    saved = save_meeting_notes(
        result,
        destination=NOTES_DESTINATION,
        notion_url=NOTION_URL,
        notion_mode=NOTION_MODE,
        obsidian_vault=OBSIDIAN_VAULT,
        obsidian_folder=OBSIDIAN_FOLDER,
    )
    if not saved:
        return None

    destination, location = saved
    if destination == "notion" and location == "mcp-handled":
        print("📝 Notion page handled via Claude MCP during processing")
    elif destination == "notion":
        print(f"📝 Notion page: {location}")
    elif destination == "obsidian":
        print(f"📝 Obsidian note: {location}")
    return saved


def do_record():
    """Main recording flow."""
    if not check_requirements():
        sys.exit(1)

    # Record
    wav, session = record()
    if not wav or not session:
        sys.exit(1)
    assert session is not None  # narrowing for type checker

    # Transcribe
    wav_path = OUTPUT_DIR / f"{session}.wav"
    transcript = transcribe(wav_path)
    if not transcript:
        print("❌ Transcription failed")
        sys.exit(1)

    # Process with Claude
    # Duration: bytes / (sample_rate * bytes_per_sample * channels)
    duration_secs = len(wav) / (SAMPLE_RATE * 2 * CHANNELS)
    m, s = divmod(int(duration_secs), 60)

    result = _run_with_retry(
        "Claude processing",
        process_with_claude,
        transcript=transcript,
        duration=f"{m}m {s}s",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    if result:
        filename = sanitize_filename(result.get("filename", ""))
        _rename_session_files(session, filename)
        _run_with_retry("notes export", _save_notes, result)

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
    wav_path = OUTPUT_DIR / f"{recovered_session}.wav"
    transcript = transcribe(wav_path)
    if not transcript:
        print("❌ Transcription failed")
        sys.exit(1)

    # Process with Claude
    # Duration: bytes / (sample_rate * bytes_per_sample * channels)
    duration_secs = len(wav) / (SAMPLE_RATE * 2 * CHANNELS)
    m, s = divmod(int(duration_secs), 60)

    result = _run_with_retry(
        "Claude processing",
        process_with_claude,
        transcript=transcript,
        duration=f"{m}m {s}s",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    if result:
        filename = sanitize_filename(result.get("filename", ""))
        _rename_session_files(recovered_session, filename)
        _run_with_retry("notes export", _save_notes, result)

    print("\n✅ Recovery complete!")


def monitor_enable():
    """Enable meeting monitor daemon."""
    from .runtime import find_python

    python_path = find_python()
    prompt_minutes = str(PROMPT_MINUTES)
    auto_record = "true" if AUTO_RECORD else "false"
    buffer_minutes = str(BUFFER_MINUTES)

    plist_content = PLIST_SRC.read_text()
    plist_content = plist_content.replace("__PYTHON_PATH__", python_path)
    plist_content = plist_content.replace("__PROMPT_MINUTES__", prompt_minutes)
    plist_content = plist_content.replace("__OUTPUT_DIR__", str(OUTPUT_DIR))
    plist_content = plist_content.replace("__LOG_DIR__", str(LOG_DIR))
    plist_content = plist_content.replace("__AUTO_RECORD__", auto_record)
    plist_content = plist_content.replace("__BUFFER_MINUTES__", buffer_minutes)

    PLIST_DST.parent.mkdir(parents=True, exist_ok=True)
    PLIST_DST.write_text(plist_content)

    subprocess.run(["launchctl", "unload", str(PLIST_DST)],
                   capture_output=True, check=False)
    result = subprocess.run(["launchctl", "load", str(
        PLIST_DST)], capture_output=True, check=False)

    if result.returncode == 0:
        mode = "auto-record" if AUTO_RECORD else "prompt"
        print(f"✅ Meeting monitor enabled ({mode} mode)")
        print(f"   Prompt: {prompt_minutes} min before meetings")
        if AUTO_RECORD:
            print(f"   Buffer: {buffer_minutes} min after meeting end")
        print(f"   Logs: {LOG_DIR}")
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
        log = LOG_DIR / "monitor.log"
        if log.exists():
            print(f"   Log: {log}")
    else:
        print("❌ Meeting monitor is not running")
        print("   Enable with: kumbuka monitor enable")


def calendar_setup():
    """Check Chrome JS permissions and open Calendar for authentication."""
    import subprocess as _sp
    from .calendar_scraper import ensure_kumbuka_calendar_tab, is_authenticated, _run_js_in_tab

    print("Checking Chrome setup for calendar integration...")

    tab = ensure_kumbuka_calendar_tab()
    if tab is None:
        print("❌ Google Chrome is not running")
        print("   Start Chrome and try again")
        sys.exit(1)

    print("✅ Chrome is running and Calendar tab is ready")

    # Test JS execution permission
    wid, tidx = tab
    try:
        _run_js_in_tab("document.title", wid, tidx)
        print("✅ JavaScript from Apple Events is enabled")
    except _sp.CalledProcessError:
        print("❌ JavaScript from Apple Events is NOT enabled")
        print("   Enable: Chrome → View → Developer → Allow JavaScript from Apple Events")
        sys.exit(1)

    if is_authenticated():
        print("✅ Authenticated with Google Calendar")
    else:
        print("⚠️  Not logged into Google Calendar in Chrome")
        print("   Log in at calendar.google.com, then re-run this command")

    print("\n✅ Setup complete! Test with: kumbuka calendar test")


def calendar_test():
    """Test calendar by showing upcoming events from Chrome."""
    from .calendar_scraper import get_upcoming_events, get_current_meetings, is_authenticated

    if not is_authenticated():
        print("❌ Not authenticated. Run: kumbuka calendar setup")
        sys.exit(1)

    print("Current meetings:")
    current = get_current_meetings()
    if current:
        for event in current:
            parts = f" ({', '.join(event.participants)})" if event.participants else ""
            print(f"  🔴 {event.title}{parts}")
    else:
        print("  (none)")

    print("\nUpcoming meetings (next 60 min):")
    upcoming = get_upcoming_events(60)
    if upcoming:
        for event in upcoming:
            parts = f" ({', '.join(event.participants)})" if event.participants else ""
            print(f"  📅 {event.title} @ {event.start.strftime('%H:%M')}{parts}")
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


_MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB


def _auto_log(msg: str):
    """Append a timestamped line to the auto-record log."""
    log_file = LOG_DIR / "auto_record.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        if log_file.exists() and log_file.stat().st_size > _MAX_LOG_BYTES:
            backup = log_file.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            log_file.rename(backup)
    except OSError:
        pass
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()}: {msg}\n")


def do_record_only(duration: int):
    """Record for a fixed duration, then transcribe and process non-interactively.

    Unlike do_record(), this never prompts for input — errors are logged and
    the pipeline continues best-effort.  Designed to run headless from the
    monitor daemon.
    """
    _auto_log(f"Recording started (duration={duration}s)")

    wav, session = record(duration_secs=duration)
    if not wav or not session:
        _auto_log("Recording failed — no audio captured")
        sys.exit(1)
    assert session is not None
    _auto_log(f"Recording saved: {session}")

    # Transcribe
    wav_path = OUTPUT_DIR / f"{session}.wav"
    try:
        transcript = transcribe(wav_path)
    except Exception as e:
        _auto_log(f"Transcription failed: {e}")
        return
    if not transcript:
        _auto_log(f"Transcription returned empty for {session}")
        return
    _auto_log(f"Transcription complete ({len(transcript)} chars)")

    # Process with Claude
    duration_secs = len(wav) / (SAMPLE_RATE * 2 * CHANNELS)
    m, s = divmod(int(duration_secs), 60)
    try:
        result = process_with_claude(
            transcript=transcript,
            duration=f"{m}m {s}s",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
    except Exception as e:
        _auto_log(f"Claude processing failed: {e}")
        return
    _auto_log(f"Claude processing complete: {result.get('title', 'untitled')}")

    if result:
        filename = sanitize_filename(result.get("filename", ""))
        _rename_session_files(session, filename)
        try:
            saved = _save_notes(result)
            if saved:
                destination, location = saved
                _auto_log(f"Saved notes to {destination}: {location}")
        except Exception as e:
            _auto_log(f"Notes export failed: {e}")

    _auto_log("Pipeline complete")


def print_usage():
    """Print usage information."""
    print("""
Kumbuka - Local-first meeting recorder

Usage:
  kumbuka                     Start recording (Ctrl+C to stop)
  kumbuka record-only --duration SECS  Record for fixed duration, then exit
  kumbuka recover             Recover last interrupted recording
  kumbuka recover <session>   Recover specific session (e.g. 2025-12-17_14-30-00)

Calendar:
  kumbuka calendar setup      Check Chrome setup for calendar integration
  kumbuka calendar test       Show current/upcoming meetings

Config:
  kumbuka config              Show all settings
  kumbuka config get <key>    Get a setting
  kumbuka config set <key> <value>  Set a setting

Monitor:
  kumbuka monitor enable      Auto-record when meetings start
  kumbuka monitor disable     Turn off auto-recording
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
            print("Usage: kumbuka calendar [setup|test]")
            sys.exit(1)

        cmd = args[1]
        if cmd == "setup":
            calendar_setup()
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
    elif args[0] == "record-only":
        duration = None
        for i, arg in enumerate(args[1:], 1):
            if arg == "--duration" and i + 1 < len(args):
                try:
                    duration = int(args[i + 1])
                except ValueError:
                    print(f"Invalid duration: {args[i + 1]}")
                    sys.exit(1)
        if duration is None:
            print("Usage: kumbuka record-only --duration SECONDS")
            sys.exit(1)
        do_record_only(duration)
    else:
        print(f"Unknown command: {args[0]}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
