# Kumbuka

macOS meeting recorder that transcribes locally with **FluidAudio (Parakeet TDT v3)** and generates notes with Claude.

## Why

Notion's built-in meeting recording requires an Enterprise subscription. Kumbuka gives you the same workflow—record, transcribe, and save to Notion—without the enterprise price tag. Everything runs locally on your Mac.

It uses **FluidAudio** (wrapping NVIDIA's Parakeet TDT model) for transcription, which is **50x faster than real-time** and optimized for Apple Silicon (Neural Engine), freeing up your CPU.

## Features

- **Blazing Fast Transcription**: ~10s to transcribe a 1-hour meeting
- **Local & Private**: No audio leaves your machine (FluidAudio runs offline)
- **Auto-generated Notes**: Summary, decisions, and action items via Claude
- **Notion Export**: Saves formatted notes directly to your Notion workspace
- **Auto-Record**: Detects meetings from Google Calendar and records automatically
- **Smart Filtering**: Skips personal time, focus blocks, and holidays — records real meetings

## Requirements

> **macOS 14+ (Apple Silicon) Only.**
> FluidAudio relies on the Apple Neural Engine and Swift/CoreML optimizations.

- **macOS 14+**
- **Apple Silicon** (M1/M2/M3/M4)
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) - Python package manager
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) - CLI access to Claude
- Google Chrome with Google Calendar signed in (for auto-record)
- Notion account (optional, for auto-saving)

## macOS Permissions

Kumbuka requires these permissions in **System Settings → Privacy & Security**:

| Permission                | Why                              | When prompted                     |
| ------------------------- | -------------------------------- | --------------------------------- |
| **Microphone**            | Record audio                     | First time you run `kumbuka`      |
| **Automation → Terminal** | Open Terminal to start recording | When you click "Record" on prompt |

Additionally, enable in Chrome:

| Setting                                    | Why                          |
| ------------------------------------------ | ---------------------------- |
| **View → Developer → Allow JavaScript from Apple Events** | Calendar event scraping |

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

### 3. Setup FluidAudio

Clone the FluidAudio repository. Kumbuka will automatically compile the binary on first run.

```bash
git clone https://github.com/FluidInference/FluidAudio.git ~/FluidAudio
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

3. **Configure Environment**:
   Add the following to `~/.kumbuka/kumbuka.env`:
   ```bash
   KUMBUKA_NOTION_URL="https://www.notion.so/Your-Meetings-Page-abc123"
   KUMBUKA_NOTION_MODE="mcp"
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

3. **Configure Environment**:
   Add the following to `~/.kumbuka/kumbuka.env`:
   ```bash
   NOTION_TOKEN="ntn_YOUR_TOKEN_HERE"
   KUMBUKA_NOTION_URL="https://www.notion.so/Your-Meetings-Page-abc123"
   KUMBUKA_NOTION_MODE="token"  # This is the default
   ```

#### After configuration

**If using calendar monitor**, re-enable to pick up new settings:

```bash
kumbuka monitor disable
kumbuka monitor enable
```

Without these variables, notes are displayed in the terminal only.

## Usage

```bash
kumbuka                              # Start recording (Ctrl+C to stop)
kumbuka record-only --duration 3600  # Record for exactly 1 hour, then exit
kumbuka -h                           # Show all commands
kumbuka recover                      # Recover interrupted recording
```

Audio is saved incrementally every 10 seconds, so if the process is interrupted, you can recover with `kumbuka recover`.

### First Run Note

The first time you run `kumbuka`, it will build the FluidAudio binary. This takes about a minute. Subsequent runs are instant.

## Auto-Record Calendar Meetings

Kumbuka watches Google Calendar in Chrome and automatically records meetings.

### How it works

1. `kumbuka calendar setup` checks Chrome and Calendar access
2. `kumbuka monitor enable` installs a **LaunchAgent** (`~/Library/LaunchAgents/com.kumbuka.monitor.plist`)
3. macOS runs this agent every 60 seconds, even after restarts
4. It scrapes Google Calendar events from Chrome's DOM via AppleScript
5. Smart filtering decides what to record: skips personal time, records real meetings
6. When a recordable meeting starts, headless recording begins automatically
7. Recording stops after `meeting_end + 10 minutes` (configurable)

### Meeting Filter

Events are classified using deterministic rules, with Claude (Haiku) as fallback for ambiguous cases:

| Always Record | Always Skip | Claude Decides |
| --- | --- | --- |
| 1:1s, syncs, standups | All-day events | Ambiguous titles |
| Interviews, reviews | Lunch, gym, focus time | No participants listed |
| Meetings with participants | Holidays, OOO, travel | Everything else |
| Demos, retrospectives | Busy blocks, DND | |

### Setup

```bash
# 1. Enable JavaScript from Apple Events in Chrome
#    Chrome → View → Developer → Allow JavaScript from Apple Events

# 2. Make sure you're logged into Google Calendar in Chrome

# 3. Check setup
kumbuka calendar setup

# 4. Test that it works
kumbuka calendar test

# 5. Enable calendar monitoring (survives restarts)
kumbuka monitor enable

# Check status
kumbuka monitor status

# Disable
kumbuka monitor disable
```

No Google Cloud project, no OAuth credentials, no API keys.

## Configuration

Kumbuka prioritizes configuration from `~/.kumbuka/kumbuka.env`.

**Example `~/.kumbuka/kumbuka.env`:**

```bash
KUMBUKA_NOTION_URL="https://www.notion.so/My-Meetings-abc123"
NOTION_TOKEN="ntn_..."
KUMBUKA_PROMPT_MINUTES="5"
KUMBUKA_AUTO_RECORD="true"
KUMBUKA_BUFFER_MINUTES="10"
```

| Environment Variable            | Default        | Description                                                             |
| ------------------------------- | -------------- | ----------------------------------------------------------------------- |
| `NOTION_TOKEN`                  | (none)         | Notion integration token (starts with `ntn_`) - required for token mode |
| `KUMBUKA_NOTION_URL`            | (none)         | Notion page URL for meeting notes                                       |
| `KUMBUKA_NOTION_MODE`           | `token`        | Notion integration: `mcp` or `token`                                    |
| `KUMBUKA_FLUIDAUDIO_REPO`       | `~/FluidAudio` | Path to FluidAudio repository                                          |
| `KUMBUKA_MAX_RECORDING_SECONDS` | `7200`         | Max recording time (seconds)                                            |
| `KUMBUKA_PROMPT_MINUTES`        | `2`            | Minutes before meeting to detect                                        |
| `KUMBUKA_AUTO_RECORD`           | `true`         | Auto-record meetings (`true`) or show dialog prompt (`false`)           |
| `KUMBUKA_BUFFER_MINUTES`        | `10`           | Minutes to keep recording after meeting ends                            |
| `KUMBUKA_USER_NAME`             | `Me`           | Your name (for transcript attribution and feedback)                     |

## Project Structure

```
kumbuka/
├── kumbuka/
│   ├── __main__.py         # CLI entry point
│   ├── config.py           # Configuration
│   ├── recorder.py         # Audio recording
│   ├── transcriber.py      # FluidAudio integration
│   ├── processor.py        # Claude integration
│   ├── calendar_scraper.py # Google Calendar scraping via Chrome
│   ├── meeting_filter.py   # Smart meeting classification
│   ├── runtime.py          # Executable discovery helpers
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

**"Chrome is not running"**

Start Google Chrome and make sure you're logged into Google Calendar.

**"Not authenticated"**

Log into Google Calendar at `calendar.google.com` in Chrome, then run:

```bash
kumbuka calendar setup
```

**"FluidAudio repo not found"**

```bash
git clone https://github.com/FluidInference/FluidAudio.git ~/FluidAudio
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

**Calendar monitor not prompting / not auto-recording**

1. Check it's running: `kumbuka monitor status`
2. Check logs: `cat ~/.kumbuka/recordings/monitor.log`
3. Verify Chrome has Calendar open: `kumbuka calendar test`
4. Verify Chrome JS permissions: View → Developer → Allow JavaScript from Apple Events

**Calendar monitor stopped after restart**

The LaunchAgent should survive restarts automatically. If it doesn't:

- Re-enable: `kumbuka monitor enable`
- Check LaunchAgent: `launchctl list | grep kumbuka`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
