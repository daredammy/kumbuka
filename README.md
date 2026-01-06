# Kumbuka

macOS meeting recorder that transcribes locally with Whisper and generates notes with Claude.

## Why

Notion's built-in meeting recording requires an Enterprise subscription. Kumbuka gives you the same workflow—record, transcribe, and save to Notion—without the enterprise price tag. Everything runs locally on your Mac.

## Features

- Auto-generated titles and participant identification
- Summary, decisions, and action items extraction
- Speaker-attributed transcript
- Optional Notion export

## Requirements

> **macOS only.** Windows and Linux are not supported.

- **macOS 12+** (Apple Silicon recommended)
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) - Python package manager
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) - CLI access to Claude
- Local Whisper server (e.g., [VoiceMode](https://github.com/mbailey/voicemode))
- Notion account (optional, for auto-saving)
- Claude code notion mcp setup (optional, for auto-saving) [Notion MCP](https://developers.notion.com/docs/get-started-with-mcp#streamable-http-recommended)

## macOS Permissions

Kumbuka requires these permissions in **System Settings → Privacy & Security**:

| Permission                | Why                              | When prompted                          |
| ------------------------- | -------------------------------- | -------------------------------------- |
| **Microphone**            | Record audio                     | First time you run `kumbuka`           |
| **Calendars**             | Read upcoming meetings           | When you run `kumbuka monitor permissions` |
| **Automation → Terminal** | Open Terminal to start recording | When you click "Record" on prompt      |

If prompts don't appear, manually add Python/Terminal in System Settings.

## Installation

### 1. Install uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install Claude Code

```bash
npm install -g @anthropic-ai/claude-code
claude  # Follow auth prompts
```

### 3. Set up local Whisper

The easiest way is using [VoiceMode](https://github.com/nicobrenner/voicemode):

```bash
# Install VoiceMode
uv tool install voicemode

# Download Whisper model and start server
voicemode start-service whisper

# Auto-start on boot (macOS)
voicemode enable-service whisper
```

### 4. Set up Notion MCP (optional)

```bash
claude mcp add --scope user --transport http Notion https://mcp.notion.com/mcp
```

### 5. Install Kumbuka

```bash
uv tool install git+https://github.com/daredammy/kumbuka
```

### 6. Configure Notion (optional)

To auto-save meeting notes to Notion:

```bash
export KUMBUKA_NOTION_URL="https://www.notion.so/YOUR-DATABASE-URL"

# Add to shell profile
echo 'export KUMBUKA_NOTION_URL="https://www.notion.so/YOUR-DATABASE-URL"' >> ~/.zshrc
```

Without this, notes are displayed in the terminal only.

## Usage

```bash
kumbuka           # Start recording (Ctrl+C to stop)
kumbuka -h        # Show all commands
kumbuka recover   # Recover interrupted recording
```

Audio is saved incrementally every 10 seconds, so if the process is interrupted, you can recover with `kumbuka recover`.

## Auto-Record Calendar Meetings

Kumbuka can watch your calendar and prompt you when meetings are about to start.

### How it works

1. `kumbuka monitor permissions` grants calendar access via EventKit
2. `kumbuka monitor enable` installs a **LaunchAgent** (`~/Library/LaunchAgents/com.kumbuka.monitor.plist`)
3. macOS runs this agent every 60 seconds, even after restarts
4. It queries Calendar.app via EventKit (works with Google Calendar, Outlook, iCloud - any calendar synced to macOS)
5. When a meeting starts in 2 minutes, you see a dialog prompt
6. Click "Record" → opens Terminal and starts recording

### Setup

```bash
# Grant calendar permissions (required first time)
kumbuka monitor permissions

# Enable calendar monitoring (survives restarts)
kumbuka monitor enable

# Check if running
kumbuka monitor status

# Disable
kumbuka monitor disable
```

### Dialog prompt

When a meeting is about to start:

```
┌─────────────────────────────────────┐
│ Meeting starting soon:              │
│                                     │
│ Weekly Standup                      │
│                                     │
│ Would you like to record?           │
│                                     │
│         [Skip]    [Record]          │
└─────────────────────────────────────┘
```

### Configuration

```bash
# Which calendars to watch (comma-separated)
# Find your calendar names in Calendar.app sidebar
export KUMBUKA_CALENDARS="work@company.com,personal@gmail.com"

# How many minutes before meeting to prompt (default: 2)
export KUMBUKA_PROMPT_MINUTES="5"

# Re-enable to apply changes
kumbuka monitor enable
```

## Configuration

| Environment Variable     | Default                                         | Description                            |
| ------------------------ | ----------------------------------------------- | -------------------------------------- |
| `KUMBUKA_NOTION_URL`     | (none)                                          | Notion database URL (optional)         |
| `KUMBUKA_WHISPER_URL`    | `http://127.0.0.1:2022/v1/audio/transcriptions` | Whisper endpoint                       |
| `KUMBUKA_WHISPER_CMD`    | (none)                                          | Whisper server command (for auto-restart) |
| `KUMBUKA_MAX_DURATION`   | `7200`                                          | Max recording time (seconds)           |
| `KUMBUKA_CALENDARS`      | (all)                                           | Calendars to monitor (comma-separated) |
| `KUMBUKA_PROMPT_MINUTES` | `2`                                             | Minutes before meeting to prompt       |

## Project Structure

```
kumbuka/
├── kumbuka/
│   ├── __main__.py         # CLI entry point
│   ├── config.py           # Configuration
│   ├── recorder.py         # Audio recording
│   ├── transcriber.py      # Whisper integration
│   ├── processor.py        # Claude integration
│   ├── prompts/
│   │   └── meeting.txt     # ← The prompt (easy to customize!)
│   └── daemon/
│       └── monitor.py      # Calendar monitoring
├── pyproject.toml
├── README.md
├── CONTRIBUTING.md
└── LICENSE
```

To customize meeting processing, edit `kumbuka/prompts/meeting.txt`.

## Troubleshooting

**"Whisper not running"**

```bash
voicemode start-service whisper
# Check: curl http://127.0.0.1:2022/health
```

**"Claude CLI not found"**

```bash
npm install -g @anthropic-ai/claude-code
```

**No audio recorded**

- Check microphone permissions: System Settings → Privacy & Security → Microphone

**Recording was interrupted / killed**

Audio is saved incrementally. Recover with:
```bash
kumbuka recover
```

**Whisper outputs gibberish like "[ sign unzipping ]"**

This is a known Whisper hallucination issue that occurs when the model gets into a degenerate state after running for extended periods. Kumbuka will auto-detect this and attempt to restart Whisper if `KUMBUKA_WHISPER_CMD` is set:

```bash
# Set your Whisper command for auto-restart
export KUMBUKA_WHISPER_CMD="/path/to/whisper-server --host 0.0.0.0 --port 2022 --model /path/to/model.bin"

# Or manually restart Whisper
pkill -f whisper-server
voicemode start-service whisper
```

**Calendar monitor not prompting**

1. Check it's running: `kumbuka monitor status`
2. Check logs: `cat /tmp/kumbuka/monitor.log`
3. If logs show "No calendars found", run: `kumbuka monitor permissions`
4. Verify permissions: System Settings → Privacy & Security → Calendars
5. Make sure your calendar is synced to Calendar.app
6. Set specific calendars: `export KUMBUKA_CALENDARS="your@email.com"`

**Calendar monitor stopped after restart**

The LaunchAgent should survive restarts automatically. If it doesn't:

- Re-enable: `kumbuka monitor enable`
- Check LaunchAgent: `launchctl list | grep kumbuka`

**Dialog not appearing**

- Grant Terminal access to System Events in Privacy & Security → Automation

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
