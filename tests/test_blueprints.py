from __future__ import annotations

import json
from pathlib import Path

from backet.blueprints import read_note_frontmatter
from backet.cli import app


def test_blueprint_apply_creates_default_notes_and_state(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)

    result = runner.invoke(app, ["--json", "blueprint", "apply", str(vault), "city-by-night-v1"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["blueprint_id"] == "city-by-night-v1"
    assert payload["data"]["custom_slot_ids"] == []

    state_path = vault / ".backet" / "state" / "blueprints" / "city-by-night-v1.json"
    note_path = vault / "1. City Identity & Thematic Structure" / "1.1 Aesthetic & Mood.md"
    assert state_path.exists()
    assert note_path.exists()

    frontmatter = read_note_frontmatter(note_path)
    assert frontmatter == {
        "backet": {
            "blueprint": "city-by-night-v1",
            "workflow": "city-foundation",
            "slot": "aesthetic-mood",
        }
    }


def test_blueprint_apply_supports_partial_custom_mapping_and_status_reports_sources(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)

    apply_result = runner.invoke(
        app,
        [
            "--json",
            "blueprint",
            "apply",
            str(vault),
            "city-by-night-v1",
            "--slot-path",
            "aesthetic-mood=Setting/City Tone",
        ],
    )
    assert apply_result.exit_code == 0

    custom_note = vault / "Setting" / "City Tone.md"
    default_note = vault / "1. City Identity & Thematic Structure" / "1.1 Aesthetic & Mood.md"
    other_default = vault / "1. City Identity & Thematic Structure" / "1.2 Historical Trauma & Memory.md"
    assert custom_note.exists()
    assert not default_note.exists()
    assert other_default.exists()

    status_result = runner.invoke(app, ["--json", "blueprint", "status", str(vault), "city-by-night-v1"])
    assert status_result.exit_code == 0
    status_payload = json.loads(status_result.stdout)
    slots = {slot["slot_id"]: slot for slot in status_payload["data"]["slots"]}

    assert slots["aesthetic-mood"]["mapping_source"] == "custom"
    assert slots["aesthetic-mood"]["resolved_path"] == "Setting/City Tone.md"
    assert slots["historical-trauma-memory"]["mapping_source"] == "default"
    assert status_payload["data"]["missing_slots"] == []


def test_blueprint_apply_is_non_destructive_on_reapply(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    initial = runner.invoke(app, ["blueprint", "apply", str(vault), "city-by-night-v1"])
    assert initial.exit_code == 0

    note_path = vault / "1. City Identity & Thematic Structure" / "1.3 Kindred Reputation (Global Perception).md"
    original_text = note_path.read_text(encoding="utf-8")
    custom_text = original_text + "\nThis canon was edited by the user.\n"
    note_path.write_text(custom_text, encoding="utf-8")

    reapply = runner.invoke(app, ["blueprint", "apply", str(vault), "city-by-night-v1"])

    assert reapply.exit_code == 0
    assert note_path.read_text(encoding="utf-8") == custom_text


def test_blueprint_status_recovers_custom_mapping_from_committed_state_on_new_machine(
    runner,
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    result = runner.invoke(
        app,
        [
            "--json",
            "blueprint",
            "apply",
            str(vault),
            "city-by-night-v1",
            "--slot-path",
            "present-night-pressure=Setting/Pressure Ledger.md",
        ],
    )
    assert result.exit_code == 0

    monkeypatch.setenv("BACKET_CONFIG_HOME", str(tmp_path / "other-machine-config"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "other-codex-home"))

    status = runner.invoke(app, ["--json", "blueprint", "status", str(vault), "city-by-night-v1"])
    assert status.exit_code == 0
    payload = json.loads(status.stdout)
    slots = {slot["slot_id"]: slot for slot in payload["data"]["slots"]}
    assert slots["present-night-pressure"]["resolved_path"] == "Setting/Pressure Ledger.md"
    assert slots["present-night-pressure"]["mapping_source"] == "custom"


def _make_bootstrapped_vault(runner, tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    result = runner.invoke(app, ["init", str(vault)])
    assert result.exit_code == 0
    return vault
