"""Tests for notes destination resolution and dispatch."""

import importlib
import sys
import warnings
from unittest.mock import patch

from kumbuka.notes import resolve_destination, save_meeting_notes


def test_resolve_destination_prefers_explicit_value():
    result = resolve_destination(
        "obsidian",
        notion_url="https://www.notion.so/page",
        obsidian_vault="/tmp/vault",
    )
    assert result == "obsidian"


def test_resolve_destination_defaults_to_notion():
    result = resolve_destination(
        "",
        notion_url="https://www.notion.so/page",
        obsidian_vault="/tmp/vault",
    )
    assert result == "notion"


def test_resolve_destination_defaults_to_obsidian():
    result = resolve_destination("", obsidian_vault="/tmp/vault")
    assert result == "obsidian"


def test_resolve_destination_defaults_to_terminal():
    assert resolve_destination("") == "terminal"


def test_save_meeting_notes_saves_to_notion():
    notion = importlib.import_module("kumbuka.notion")

    with patch.object(notion, "create_page", return_value={"url": "https://www.notion.so/page"}):
        saved = save_meeting_notes(
            {"title": "Weekly Sync", "summary": "", "participants": [], "transcript": ""},
            destination="notion",
            notion_url="https://www.notion.so/parent",
            notion_mode="token",
        )

    assert saved == ("notion", "https://www.notion.so/page")


def test_save_meeting_notes_skips_notion_mcp_export():
    saved = save_meeting_notes(
        {"title": "Weekly Sync", "summary": "", "participants": [], "transcript": ""},
        destination="notion",
        notion_url="https://www.notion.so/parent",
        notion_mode="mcp",
    )

    assert saved == ("notion", "mcp-handled")


def test_config_invalid_destination_warns_and_falls_back(monkeypatch):
    monkeypatch.setenv("KUMBUKA_NOTES_DESTINATION", "bad-value")
    monkeypatch.delenv("KUMBUKA_NOTION_URL", raising=False)
    monkeypatch.delenv("KUMBUKA_OBSIDIAN_VAULT", raising=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = sys.modules.get("kumbuka.config")
        if config is None:
            config = importlib.import_module("kumbuka.config")
        else:
            config = importlib.reload(config)

    assert config.NOTES_DESTINATION == "terminal"
    assert any("Falling back to terminal output only" in str(w.message) for w in caught)
