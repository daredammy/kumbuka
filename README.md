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
- Python 3.10+
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

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `KUMBUKA_NOTION_URL` | (required) | Your Notion database URL |
| `KUMBUKA_WHISPER_URL` | `http://127.0.0.1:2022/v1/audio/transcriptions` | Whisper endpoint |
| `KUMBUKA_MAX_DURATION` | `7200` | Max recording time (seconds) |

## Project Structure

```
kumbuka/
├── kumbuka/
│   ├── __main__.py         # CLI entry point
│   ├── config.py           # Configuration
│   ├── recorder.py         # Audio recording
│   ├── transcriber.py      # Whisper integration  
│   ├── processor.py        # Claude integration
│   └── prompts/
│       └── meeting.txt     # ← The prompt (easy to customize!)
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
