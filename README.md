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

- macOS (Apple Silicon recommended)
- [uv](https://github.com/astral-sh/uv) - Python package manager
- [Claude Code](https://claude.ai/code) - CLI access to Claude
- Local Whisper server (we recommend [VoiceMode](https://github.com/nicobrenner/voicemode))
- Notion account (optional, for auto-saving)

## Installation

```bash
# Install uv if you haven't
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Download kumbuka
curl -o ~/.local/bin/kumbuka https://raw.githubusercontent.com/hypebridge/kumbuka/main/kumbuka
chmod +x ~/.local/bin/kumbuka

# Start Whisper (if using VoiceMode)
voicemode start-service whisper
```

## Usage

```bash
kumbuka
# That's it. Ctrl+C to stop.
```

## Output

Audio and transcripts are backed up to `/tmp/kumbuka/` with automatic cleanup on reboot.

## Configuration

Edit the script to customize:
- `WHISPER_URL` - your Whisper endpoint (default: `http://127.0.0.1:2022`)
- `MAX_DURATION` - max recording time (default: 2 hours)
- Notion database URL - where pages are created

## Comparison

| Feature | Kumbuka | Otter.ai | Fireflies |
|---------|---------|----------|-----------|
| Cost | Free | $16/mo | $19/mo |
| Data location | 100% local | Cloud | Cloud |
| Transcription | Local Whisper | Cloud | Cloud |
| Customizable | Fully | No | No |
| Works offline | Yes* | No | No |

*Requires Claude API for summaries

## Tech stack

- **Recording**: sounddevice + numpy
- **Transcription**: Whisper.cpp (local)
- **AI Processing**: Claude via Claude Code
- **Storage**: Notion API (optional)

## Why "Kumbuka"?

Kumbuka (koom-BOO-kah) is Swahili for "to remember." Because that's what this tool does—it remembers your meetings so you don't have to.

## License

MIT

## Built by

[HypeBridge](https://hypebridge.com) - AI-powered influencer discovery
