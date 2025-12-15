# Kumbuka

> *Swahili: "to remember"*

**macOS-only** local-first meeting recorder with AI-powered transcription and smart summaries. Records audio, transcribes with Whisper, and uses Claude to generate intelligent meeting notes.

**Zero subscription fees. Your data stays local.**

## How it works

```
kumbuka                   # Start recording
                          # 🔴 See live progress
Ctrl+C                    # Stop when done
                          # → Transcribes locally (Whisper)
                          # → Claude generates title, identifies participants
                          # → Creates structured Notion page
```

## What you get

- **Auto-generated title** based on content (not "Meeting - Dec 15")
- **Participant identification** with roles inferred from context
- **Smart summary** adapted to your meeting type
- **Decisions & Action Items** extracted automatically
- **Cleaned transcript** with speaker attribution

## Requirements

- **macOS 12+** (Apple Silicon recommended)
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) - Python package manager
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) - CLI access to Claude
- Local Whisper server
- Notion account (optional, for auto-saving)

## macOS Permissions

Kumbuka requires these permissions in **System Settings → Privacy & Security**:

| Permission | Why | When prompted |
|------------|-----|---------------|
| **Microphone** | Record audio | First time you run `kumbuka` |
| **Automation → Calendar** | Read upcoming meetings | First time calendar monitor runs |
| **Automation → Terminal** | Open Terminal to start recording | When you click "Record" on prompt |

If prompts don't appear, manually add Terminal (or your terminal app) in System Settings.

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
# Install from GitHub
uv tool install git+https://github.com/hypebridge/kumbuka

# Set your Notion database URL
export KUMBUKA_NOTION_URL="https://www.notion.so/YOUR-DATABASE-URL"

# Add to shell profile
echo 'export KUMBUKA_NOTION_URL="https://www.notion.so/YOUR-DATABASE-URL"' >> ~/.zshrc
```

## Usage

```bash
kumbuka
# That's it. Ctrl+C to stop.
```

## Auto-Record Calendar Meetings

Kumbuka can watch your calendar and prompt you when meetings are about to start.

### How it works

1. `kumbuka monitor enable` installs a **LaunchAgent** (`~/Library/LaunchAgents/com.kumbuka.monitor.plist`)
2. macOS runs this agent every 60 seconds, even after restarts
3. It queries Calendar.app via AppleScript (works with Google Calendar, Outlook, iCloud - any calendar synced to macOS)
4. When a meeting starts in 2 minutes, you see a dialog prompt
5. Click "Record" → opens Terminal and starts recording

### Setup

```bash
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

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `KUMBUKA_NOTION_URL` | (required) | Your Notion database URL |
| `KUMBUKA_WHISPER_URL` | `http://127.0.0.1:2022/v1/audio/transcriptions` | Whisper endpoint |
| `KUMBUKA_MAX_DURATION` | `7200` | Max recording time (seconds) |
| `KUMBUKA_CALENDARS` | (all) | Calendars to monitor (comma-separated) |
| `KUMBUKA_PROMPT_MINUTES` | `2` | Minutes before meeting to prompt |

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

**Want to customize how meetings are processed?** Edit `kumbuka/prompts/meeting.txt` - it's just a text file with placeholders.

## Comparison

| Feature | Kumbuka | Otter.ai | Fireflies |
|---------|---------|----------|-----------|
| Cost | Free | $16/mo | $19/mo |
| Data location | 100% local | Cloud | Cloud |
| Transcription | Local Whisper | Cloud | Cloud |
| Customizable | Fully | No | No |
| Open source | ✅ | No | No |

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

**Calendar monitor not prompting**
1. Check it's running: `kumbuka monitor status`
2. Check logs: `cat /tmp/kumbuka/monitor.log`
3. Verify permissions: System Settings → Privacy & Security → Automation
   - Terminal (or iTerm) needs access to Calendar and System Events
4. Make sure your calendar is synced to Calendar.app
5. Set specific calendars: `export KUMBUKA_CALENDARS="your@email.com"`

**Calendar monitor stopped after restart**
- Re-enable: `kumbuka monitor enable`
- Check LaunchAgent: `launchctl list | grep kumbuka`

**Dialog not appearing**
- Grant Terminal access to System Events in Privacy & Security → Automation

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to:
- Improve the prompt
- Add new output formats
- Support other LLMs
- Add integrations

## Why "Kumbuka"?

Kumbuka (koom-BOO-kah) is Swahili for "to remember."

## License

MIT

## Built by

[HypeBridge](https://hypebridge.com) - AI-powered influencer discovery
