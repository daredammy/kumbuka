"""Kumbuka configuration."""

import os
from pathlib import Path

# Paths
PACKAGE_DIR = Path(__file__).parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"
TEMP_DIR = Path("/tmp/kumbuka")

# Whisper
WHISPER_URL = os.getenv(
    "KUMBUKA_WHISPER_URL",
    "http://127.0.0.1:2022/v1/audio/transcriptions"
)

# Whisper server command for auto-restart on hallucination
# Example: "/path/to/whisper-server --host 0.0.0.0 --port 2022 --model /path/to/model.bin"
WHISPER_CMD = os.getenv("KUMBUKA_WHISPER_CMD", "")

# Notion (optional) - if set, notes are saved to Notion
NOTION_URL = os.getenv("KUMBUKA_NOTION_URL", "")

# Notion integration mode: "mcp" (Claude Code MCP) or "token" (API token)
# MCP requires Notion MCP to be connected in Claude Code
# Token requires NOTION_TOKEN environment variable
NOTION_MODE = os.getenv("KUMBUKA_NOTION_MODE", "token")

# Recording
MAX_DURATION = int(os.getenv("KUMBUKA_MAX_DURATION", "7200"))  # 2 hours
SAMPLE_RATE = 16000
CHANNELS = 1
