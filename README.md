# Kumbuka

macOS meeting recorder that transcribes locally with Whisper and generates notes with Claude.

## Why

Notion's built-in meeting recording requires an Enterprise subscription. Kumbuka gives you the same workflow—record, transcribe, and save to Notion—without the enterprise price tag. Everything runs locally on your Mac.

## Features

- Auto-generated titles and participant identification
- Summary, decisions, and action items extraction
- Speaker-attributed transcript
- Optional Notion export
- Google Calendar integration for automatic meeting prompts

## Requirements

> **macOS only.** Windows and Linux are not supported.

- **macOS 12+** (Apple Silicon recommended)
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) - Python package manager
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) - CLI access to Claude
- Local Whisper server (e.g., [VoiceMode](https://github.com/mbailey/voicemode))
- Notion account (optional, for auto-saving)
- Google account (optional, for calendar monitoring)

## macOS Permissions

Kumbuka requires these permissions in **System Settings → Privacy & Security**:

| Permission                | Why                              | When prompted                     |
| ------------------------- | -------------------------------- | --------------------------------- |
| **Microphone**            | Record audio                     | First time you run `kumbuka`      |
| **Automation → Terminal** | Open Terminal to start recording | When you click "Record" on prompt |

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

### 4. Install Kumbuka

```bash
uv tool install git+https://github.com/daredammy/kumbuka
```

### 5. Configure Notion (optional)

To auto-save meeting notes to Notion, choose one of two integration methods:

#### Option A: MCP Integration (recommended for Claude Code users)

If you use Claude Code with the Notion MCP server:

1. **Connect Notion MCP** in Claude Code:

   ```bash
   claude /mcp   # Follow prompts to authenticate with Notion
   ```

2. **Connect your Meetings page** to Claude Code:

   - Open your Meetings page in Notion
   - Click ••• → Connections → Add "Claude" (or your MCP integration name)

3. **Set environment variables**:
   ```bash
   # Add to your shell profile (~/.zshrc)
   export KUMBUKA_NOTION_URL="https://www.notion.so/Your-Meetings-Page-abc123"
   export KUMBUKA_NOTION_MODE="mcp"
   ```

#### Option B: Token Integration (for standalone use)

If you prefer using a Notion API token directly:

1. **Create a Notion integration** at https://www.notion.so/profile/integrations

   - Click "New integration"
   - Give it a name (e.g., "Kumbuka")
   - Copy the "Internal Integration Secret" (starts with `ntn_`)

2. **Connect your Meetings page** to the integration

   - Open your Meetings page in Notion
   - Click ••• → Connections → Add your integration

3. **Set environment variables**:
   ```bash
   # Add to your shell profile (~/.zshrc)
   export NOTION_TOKEN="ntn_YOUR_TOKEN_HERE"
   export KUMBUKA_NOTION_URL="https://www.notion.so/Your-Meetings-Page-abc123"
   export KUMBUKA_NOTION_MODE="token"  # This is the default
   ```

#### After configuration

1. **Reload your shell**:

   ```bash
   source ~/.zshrc
   ```

2. **If using calendar monitor**, re-enable to pick up new settings:
   ```bash
   kumbuka monitor disable
   kumbuka monitor enable
   ```

Without these variables, notes are displayed in the terminal only.

## Usage

```bash
kumbuka           # Start recording (Ctrl+C to stop)
kumbuka -h        # Show all commands
kumbuka recover   # Recover interrupted recording
```

Audio is saved incrementally every 10 seconds, so if the process is interrupted, you can recover with `kumbuka recover`.

## Auto-Record Calendar Meetings

Kumbuka can watch your Google Calendar and prompt you when meetings are about to start.

### How it works

1. `kumbuka calendar auth` authenticates with Google Calendar via OAuth
2. `kumbuka monitor enable` installs a **LaunchAgent** (`~/Library/LaunchAgents/com.kumbuka.monitor.plist`)
3. macOS runs this agent every 60 seconds, even after restarts
4. It queries Google Calendar directly via API
5. When a meeting starts in 2 minutes, you see a dialog prompt
6. Click "Record" → opens Terminal and starts recording

### Setup

```bash
# 1. Download OAuth credentials from Google Cloud Console
#    (Create project → Enable Calendar API → Create OAuth credentials)
#    Save as ~/.kumbuka/credentials.json

# 2. Authenticate with Google Calendar
kumbuka calendar auth

# 3. Test that it works
kumbuka calendar test

# 4. Enable calendar monitoring (survives restarts)
kumbuka monitor enable

# Check status
kumbuka monitor status

# Disable
kumbuka monitor disable
```

### Google Cloud Setup

To use Google Calendar integration:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable the **Google Calendar API**
4. Go to **Credentials** → Create **OAuth 2.0 Client ID**
   - Application type: Desktop app
   - Download the JSON file
5. Save as `~/.kumbuka/credentials.json`
6. Run `kumbuka calendar auth` to complete OAuth flow

### Dialog prompt

When a meeting is about to start:

```
┌─────────────────────────────────────┐
│ Meeting: Weekly Standup             │
│ (starting soon)                     │
│                                     │
│ Would you like to record?           │
│                                     │
│         [Skip]    [Record]          │
└─────────────────────────────────────┘
```

### Configuration

```bash
# How many minutes before meeting to prompt (default: 2)
export KUMBUKA_PROMPT_MINUTES="5"

# Re-enable to apply changes
kumbuka monitor enable
```

## Configuration

| Environment Variable     | Default                                         | Description                                                             |
| ------------------------ | ----------------------------------------------- | ----------------------------------------------------------------------- |
| `NOTION_TOKEN`           | (none)                                          | Notion integration token (starts with `ntn_`) - required for token mode |
| `KUMBUKA_NOTION_URL`     | (none)                                          | Notion page URL for meeting notes                                       |
| `KUMBUKA_NOTION_MODE`    | `token`                                         | Notion integration: `mcp` or `token`                                    |
| `KUMBUKA_WHISPER_URL`    | `http://127.0.0.1:2022/v1/audio/transcriptions` | Whisper endpoint                                                        |
| `KUMBUKA_WHISPER_CMD`    | (none)                                          | Whisper server command (for auto-restart)                               |
| `KUMBUKA_MAX_DURATION`   | `7200`                                          | Max recording time (seconds)                                            |
| `KUMBUKA_PROMPT_MINUTES` | `2`                                             | Minutes before meeting to prompt                                        |

## Project Structure

```
kumbuka/
├── kumbuka/
│   ├── __main__.py         # CLI entry point
│   ├── config.py           # Configuration
│   ├── recorder.py         # Audio recording
│   ├── transcriber.py      # Whisper integration
│   ├── processor.py        # Claude integration
│   ├── calendar.py         # Google Calendar integration
│   ├── notion.py           # Notion API wrapper
│   ├── prompts/
│   │   └── meeting.txt     # ← The prompt (easy to customize!)
│   └── daemon/
│       └── monitor.py      # Calendar monitoring daemon
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
3. Verify Google Calendar auth: `kumbuka calendar test`
4. If "Not authenticated": `kumbuka calendar auth`
5. Check credentials file exists: `ls ~/.kumbuka/credentials.json`

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
