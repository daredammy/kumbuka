# Contributing

## Project Structure

```
kumbuka/
├── pyproject.toml
├── kumbuka/
│   ├── __main__.py         # CLI entry point
│   ├── config.py           # Configuration
│   ├── recorder.py         # Audio recording
│   ├── transcriber.py      # Whisper integration
│   ├── processor.py        # Claude integration
│   ├── prompts/
│   │   └── meeting.txt     # Prompt template
│   └── daemon/
│       └── monitor.py      # Calendar monitoring
```

## Areas

- **Prompts** (`kumbuka/prompts/`) - Template with placeholders: `{transcript}`, `{duration}`, `{timestamp}`, `{notion_instructions}`
- **Recorder** (`recorder.py`) - Audio capture via `sounddevice`
- **Transcriber** (`transcriber.py`) - Whisper API client
- **Processor** (`processor.py`) - Claude integration

## Development Setup

```bash
git clone https://github.com/daredammy/kumbuka
cd kumbuka
uv pip install -e .
```

## Testing

```bash
kumbuka
# Optionally set KUMBUKA_NOTION_URL to test Notion integration
```

## Submitting Changes

1. Fork the repo
2. Create a branch
3. Test locally
4. Submit a PR
