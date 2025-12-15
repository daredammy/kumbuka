# Kumbuka

> *Swahili: "to remember"*

Local-first meeting recorder with AI-powered transcription and smart summaries. Records audio, transcribes with Whisper, and uses Claude to generate intelligent meeting notes.

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

- macOS (Apple Silicon recommended) or Linux
- [uv](https://github.com/astral-sh/uv) - Python package manager
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) - CLI access to Claude
- Local Whisper server
- Notion account (optional, for auto-saving)

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
```

This starts Whisper on `http://127.0.0.1:2022`. To auto-start on boot:

```bash
# macOS - creates LaunchAgent
voicemode enable-service whisper
```

**Alternative**: Run whisper.cpp directly - see [whisper.cpp server docs](https://github.com/ggerganov/whisper.cpp/tree/master/examples/server).

### 4. Set up Notion (optional)

Add Notion MCP to Claude Code:

```bash
claude mcp add --scope user --transport http Notion https://mcp.notion.com/mcp
```

Then authenticate when prompted.

### 5. Install kumbuka

```bash
# Download
curl -o ~/.local/bin/kumbuka https://raw.githubusercontent.com/hypebridge/kumbuka/main/kumbuka
chmod +x ~/.local/bin/kumbuka

# Set your Notion database URL
export KUMBUKA_NOTION_URL="https://www.notion.so/YOUR-DATABASE-URL"

# Add to your shell profile (~/.zshrc or ~/.bashrc)
echo 'export KUMBUKA_NOTION_URL="https://www.notion.so/YOUR-DATABASE-URL"' >> ~/.zshrc
```

To find your Notion database URL: Open your Meetings database → Click `...` → Copy link.

## Usage

```bash
kumbuka
# That's it. Ctrl+C to stop.
```

### Configuration

Set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KUMBUKA_NOTION_URL` | (required) | Your Notion database URL |
| `KUMBUKA_WHISPER_URL` | `http://127.0.0.1:2022/v1/audio/transcriptions` | Whisper API endpoint |
| `KUMBUKA_MAX_DURATION` | `7200` | Max recording time in seconds |

Or edit the script directly.

## Output

Audio and transcripts are backed up to `/tmp/kumbuka/` with automatic cleanup on reboot.

Example Notion page created:

**Title:** "Q1 Roadmap Planning - API Priorities"

**Participants:**
- Dami (Engineering Lead)
- Sarah (Product)
- Mike (Design)

**Summary:**
- Overview of Q1 priorities...
- **Decisions:** Ship API v1 by January
- **Action Items:**
  - [ ] Dami: Draft API spec by Friday
  - [ ] Sarah: Update roadmap

**Transcript:**
> **Dami:** Let's start with the API discussion...

## Comparison

| Feature | Kumbuka | Otter.ai | Fireflies |
|---------|---------|----------|-----------|
| Cost | Free | $16/mo | $19/mo |
| Data location | 100% local | Cloud | Cloud |
| Transcription | Local Whisper | Cloud | Cloud |
| Customizable | Fully | No | No |
| Works offline | Yes* | No | No |

*Requires Claude API for summaries

## Troubleshooting

**"Whisper not running"**
```bash
voicemode start-service whisper
# Or check: curl http://127.0.0.1:2022/health
```

**"Claude CLI not found"**
```bash
npm install -g @anthropic-ai/claude-code
# Make sure ~/.npm-global/bin is in your PATH
```

**"Notion database URL not set"**
```bash
export KUMBUKA_NOTION_URL="https://www.notion.so/your-database-url"
```

**No audio recorded**
- Check microphone permissions in System Settings → Privacy & Security → Microphone
- Test with: `python -c "import sounddevice; print(sounddevice.query_devices())"`

## Tech stack

- **Recording**: sounddevice + numpy
- **Transcription**: Whisper.cpp (local)
- **AI Processing**: Claude via Claude Code
- **Storage**: Notion API via MCP

## Why "Kumbuka"?

Kumbuka (koom-BOO-kah) is Swahili for "to remember." Because that's what this tool does—it remembers your meetings so you don't have to.

## License

MIT

## Built by

[HypeBridge](https://hypebridge.com) - AI-powered influencer discovery
