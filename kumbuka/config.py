"""Kumbuka configuration."""

import os
import sys
import warnings
from pathlib import Path

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional fallback for minimal test envs
    _DOTENV_AVAILABLE = False

    def load_dotenv(*_args, **_kwargs):
        return False

from .notes import resolve_destination

# Load config from ~/.kumbuka/kumbuka.env
CONFIG_DIR = Path.home() / ".kumbuka"
ENV_FILE = CONFIG_DIR / "kumbuka.env"
if (
    not _DOTENV_AVAILABLE
    and ENV_FILE.exists()
    and "pytest" not in sys.modules
):  # pragma: no cover - import-time fallback
    warnings.warn(
        f"python-dotenv is not installed; {ENV_FILE} will not be loaded",
        RuntimeWarning,
        stacklevel=2,
    )
load_dotenv(ENV_FILE, override=True)

# Paths
PACKAGE_DIR = Path(__file__).parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"
OUTPUT_DIR = Path(os.getenv("KUMBUKA_OUTPUT_DIR", Path.home() / ".kumbuka" / "recordings"))
LOG_DIR = Path(os.getenv("KUMBUKA_LOG_DIR", Path.home() / "Documents" / "kumbuka" / "logs"))

# FluidAudio
FLUIDAUDIO_REPO = os.getenv("KUMBUKA_FLUIDAUDIO_REPO", os.path.expanduser("~/FluidAudio"))
FLUIDAUDIO_BIN = Path(FLUIDAUDIO_REPO) / ".build/release/fluidaudio"

# Notes destination (optional)
_configured_notes_destination = os.getenv("KUMBUKA_NOTES_DESTINATION", "")

# Notion (optional)
NOTION_URL = os.getenv("KUMBUKA_NOTION_URL", "")

# Notion integration mode: "token" (API token) or "mcp" (Claude MCP integration)
# Falls back to "mcp" automatically if NOTION_TOKEN is not set
_configured_mode = os.getenv("KUMBUKA_NOTION_MODE", "token")
NOTION_MODE = _configured_mode if (_configured_mode == "mcp" or os.getenv("NOTION_TOKEN")) else "mcp"

# Obsidian (optional)
OBSIDIAN_VAULT = os.getenv("KUMBUKA_OBSIDIAN_VAULT", "")
OBSIDIAN_FOLDER = os.getenv("KUMBUKA_OBSIDIAN_FOLDER", "")

try:
    NOTES_DESTINATION = resolve_destination(
        _configured_notes_destination,
        notion_url=NOTION_URL,
        obsidian_vault=OBSIDIAN_VAULT,
    )
except RuntimeError as exc:  # pragma: no cover - import-time fallback
    warnings.warn(
        f"{exc}. Falling back to terminal output only.",
        RuntimeWarning,
        stacklevel=2,
    )
    NOTES_DESTINATION = "terminal"

# Recording
MAX_DURATION = int(os.getenv("KUMBUKA_MAX_RECORDING_SECONDS", "7200"))  # 2 hours
SAMPLE_RATE = 16000
CHANNELS = 1

# Audio device: "auto" (detect BlackHole), "mic", "system", or a device name/index
AUDIO_DEVICE = os.getenv("KUMBUKA_AUDIO_DEVICE", "auto")

# Calendar monitoring - minutes before meeting to prompt
PROMPT_MINUTES = int(os.getenv("KUMBUKA_PROMPT_MINUTES", "2"))

# Auto-record mode (True = auto-record without dialog; False = show dialog prompt)
AUTO_RECORD = os.getenv("KUMBUKA_AUTO_RECORD", "true").lower() in ("true", "1", "yes")

# Buffer minutes added after meeting end
BUFFER_MINUTES = int(os.getenv("KUMBUKA_BUFFER_MINUTES", "10"))

# User identification (for personalized feedback)
USER_NAME = os.getenv("KUMBUKA_USER_NAME", "Me")
