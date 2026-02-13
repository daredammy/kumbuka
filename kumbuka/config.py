"""Kumbuka configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load config from ~/.kumbuka/kumbuka.env
CONFIG_DIR = Path.home() / ".kumbuka"
ENV_FILE = CONFIG_DIR / "kumbuka.env"
load_dotenv(ENV_FILE, override=True)

# Paths
PACKAGE_DIR = Path(__file__).parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"
TEMP_DIR = Path(os.getenv("KUMBUKA_OUTPUT_DIR", "/tmp/kumbuka"))

# FluidAudio
FLUIDAUDIO_REPO = os.getenv("KUMBUKA_FLUIDAUDIO_REPO", os.path.expanduser("~/FluidAudio"))
FLUIDAUDIO_BIN = Path(FLUIDAUDIO_REPO) / ".build/release/fluidaudio"

# Notion (optional) - if set, notes are saved to Notion
NOTION_URL = os.getenv("KUMBUKA_NOTION_URL", "")

# Notion integration mode: "token" (API token) or "mcp" (Claude MCP integration)
# Falls back to "mcp" automatically if NOTION_TOKEN is not set
_configured_mode = os.getenv("KUMBUKA_NOTION_MODE", "token")
NOTION_MODE = _configured_mode if (_configured_mode == "mcp" or os.getenv("NOTION_TOKEN")) else "mcp"

# Recording
MAX_DURATION = int(os.getenv("KUMBUKA_MAX_RECORDING_SECONDS", "7200"))  # 2 hours
SAMPLE_RATE = 16000
CHANNELS = 1

# Calendar monitoring - minutes before meeting to prompt
PROMPT_MINUTES = int(os.getenv("KUMBUKA_PROMPT_MINUTES", "2"))

# User identification (for personalized feedback)
USER_NAME = os.getenv("KUMBUKA_USER_NAME", "Me")
