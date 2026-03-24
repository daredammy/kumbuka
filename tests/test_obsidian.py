"""Tests for Obsidian vault note writing."""

import pytest

from kumbuka.obsidian import save_note


def test_save_note_writes_markdown_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    note_path = save_note(
        str(vault),
        title="Weekly Sync",
        content="# Weekly Sync",
        filename="weekly-sync",
        folder="Meetings/Team",
    )

    assert note_path == (vault / "Meetings" / "Team" / "weekly-sync.md").resolve()
    assert note_path.read_text(encoding="utf-8") == "# Weekly Sync\n"


def test_save_note_avoids_overwriting_existing_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    existing = vault / "weekly-sync.md"
    existing.write_text("old\n", encoding="utf-8")

    note_path = save_note(
        str(vault),
        title="Weekly Sync",
        content="# Weekly Sync",
        filename="weekly-sync",
    )

    assert note_path == (vault / "weekly-sync-2.md").resolve()
    assert note_path.read_text(encoding="utf-8") == "# Weekly Sync\n"


def test_save_note_rejects_folder_escape(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    with pytest.raises(RuntimeError, match="within the vault"):
        save_note(
            str(vault),
            title="Weekly Sync",
            content="# Weekly Sync",
            folder="../outside",
        )
