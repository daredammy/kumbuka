# Contributing to Kumbuka

Thanks for your interest in contributing! Here's how the project is structured.

## Project Structure

```
kumbuka/
├── pyproject.toml          # Package configuration
├── README.md
├── LICENSE
├── CONTRIBUTING.md
└── kumbuka/
    ├── __init__.py
    ├── __main__.py         # CLI entry point
    ├── config.py           # Configuration (env vars, paths)
    ├── recorder.py         # Audio recording
    ├── transcriber.py      # Whisper integration
    ├── processor.py        # Claude integration
    └── prompts/
        └── meeting.txt     # The prompt sent to Claude
```

## Key Areas to Contribute

### 1. Prompts (`kumbuka/prompts/`)

The prompt is the heart of how Kumbuka processes meetings. It's a plain text file with placeholders:

- `{transcript}` - Raw transcript from Whisper
- `{duration}` - Recording duration
- `{timestamp}` - When recorded
- `{notion_url}` - User's Notion database

**Ideas:**
- Improve participant detection
- Better action item extraction
- Add support for different meeting types (standup, 1:1, interview)
- Localization / non-English prompts

### 2. Recorder (`kumbuka/recorder.py`)

Audio capture using `sounddevice`.

**Ideas:**
- Voice activity detection (skip silence)
- Multiple audio input support
- Real-time audio levels display

### 3. Transcriber (`kumbuka/transcriber.py`)

Whisper integration.

**Ideas:**
- Support for other Whisper APIs (OpenAI, faster-whisper)
- Speaker diarization
- Streaming transcription

### 4. Processor (`kumbuka/processor.py`)

Claude integration.

**Ideas:**
- Support for other LLMs (GPT-4, local models)
- Different output formats (Markdown file, email)
- Other integrations (Obsidian, Google Docs, Linear)

## Development Setup

```bash
# Clone
git clone https://github.com/hypebridge/kumbuka
cd kumbuka

# Install in dev mode
uv pip install -e .

# Or run directly
uv run python -m kumbuka
```

## Testing Your Changes

```bash
# Set required env var
export KUMBUKA_NOTION_URL="https://www.notion.so/test-db"

# Run
kumbuka
```

## Submitting Changes

1. Fork the repo
2. Create a branch: `git checkout -b my-feature`
3. Make your changes
4. Test locally
5. Submit a PR with a clear description

## Code Style

- Keep it simple - this is a ~200 line tool, not a framework
- Type hints where helpful
- Docstrings for public functions

## Questions?

Open an issue or reach out to [@hypebridge](https://twitter.com/hypebridge).
