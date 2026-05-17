from __future__ import annotations

import json
import logging
import shutil
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from backet.bot_discord import DiscordRequestContext, evaluate_discord_request
from backet.bot_runtime import BotBundle, answer_bot_query
from backet.cli import app
from backet.errors import AppError
from backet.indexing import open_index_database
from backet.vault import initialize_vault


def test_leakage_fixture_excludes_hidden_content_from_player_export_and_answers(runner, tmp_path: Path) -> None:
    vault = _make_leakage_vault(tmp_path)
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    with closing(open_index_database(output / "indexes" / "player-vault-index.sqlite3")) as connection:
        note_rows = connection.execute("SELECT relative_path, title, preview FROM notes").fetchall()
        chunk_rows = connection.execute("SELECT content, excerpt, heading_path FROM chunks").fetchall()

    serialized = json.dumps([dict(row) for row in [*note_rows, *chunk_rows]])
    assert "Sabine Secret Stat Block" not in serialized
    assert "regent betrayal" not in serialized
    assert "hidden haven beneath the museum" not in serialized

    player_answer = answer_bot_query(
        bundle,
        command="canon.ask",
        question="What does public canon say about Sabine and the museum?",
        role_ids=["player-role"],
    )

    assert player_answer.denied is False
    assert {source["relative_path"] for source in player_answer.sources} == {"Public Court.md"}
    assert "Sabine Secret Stat Block" not in player_answer.text
    assert "regent betrayal" not in player_answer.text


def test_storyteller_can_retrieve_hidden_sources_when_authorized(runner, tmp_path: Path) -> None:
    vault = _make_leakage_vault(tmp_path)
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    answer = answer_bot_query(bundle, command="st.npc", question="Sabine secret stat block", role_ids=["st-role"])

    assert answer.denied is False
    assert "NPCs/Sabine.md" in {source["relative_path"] for source in answer.sources}
    assert "regent betrayal" in answer.text


def test_secret_like_bot_config_fields_fail_closed_before_export(runner, tmp_path: Path) -> None:
    vault = _make_leakage_vault(tmp_path)
    (vault / ".backet" / "state" / "bot-config.yaml").write_text(
        "schema_version: 1\n"
        "guild_id: guild-a\n"
        "discord_token: never-store-this-here\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(tmp_path / "bundle")])

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "bot_config_secret_field"
    assert not (tmp_path / "bundle").exists()


def test_runtime_uses_exact_fallback_when_semantic_query_backend_is_unavailable(
    runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = _make_leakage_vault(tmp_path)
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    def fail_embedding_backend():
        raise AppError(code="embedding_backend_missing", message="no semantic backend", exit_code=2)

    monkeypatch.setattr("backet.retrieval.resolve_embedding_backend", fail_embedding_backend)
    answer = answer_bot_query(bundle, command="canon.ask", question="Sabine museum public", role_ids=["player-role"])

    assert answer.denied is False
    assert answer.sources[0]["relative_path"] == "Public Court.md"
    assert "exact" in answer.sources[0]["match_reasons"]


def test_bot_json_outputs_and_logs_do_not_include_hidden_text_or_secret_names(
    runner,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    vault = _make_leakage_vault(tmp_path)
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)
    manifest_text = (output / "manifest.json").read_text(encoding="utf-8")

    assert "DISCORD_TOKEN" not in manifest_text
    assert "ORACLE_VM_SSH_KEY" not in manifest_text

    with caplog.at_level(logging.INFO, logger="backet.bot.discord"):
        answer = evaluate_discord_request(
            bundle,
            DiscordRequestContext(guild_id="guild-a", user_id="player", role_ids=["player-role"], channel_id="allowed"),
            command="canon.ask",
            question="Sabine museum public",
        )

    assert answer.denied is False
    assert "regent betrayal" not in caplog.text
    assert "hidden haven" not in caplog.text
    assert "Public Court" not in caplog.text


def test_source_pdfs_are_not_copied_to_bot_bundle(runner, tmp_path: Path) -> None:
    vault = _make_leakage_vault(tmp_path)
    (vault / ".backet" / "rules" / "source.pdf").write_bytes(b"pdf")
    output = _export_bundle(runner, vault, tmp_path)

    assert not any(path.suffix.lower() == ".pdf" for path in output.rglob("*"))


def test_bot_cli_contracts_and_openspec_validation(runner, tmp_path: Path) -> None:
    vault = _make_leakage_vault(tmp_path)
    human = runner.invoke(app, ["bot", "export", str(vault), "--output", str(tmp_path / "bundle")])
    ask = runner.invoke(
        app,
        [
            "--json",
            "bot",
            "ask",
            str(tmp_path / "bundle"),
            "Sabine museum public",
            "--command",
            "canon.ask",
            "--role-id",
            "player-role",
        ],
    )
    assert human.exit_code == 0
    assert "Exported private bot bundle" in human.stdout
    assert ask.exit_code == 0
    assert json.loads(ask.stdout)["data"]["sources"][0]["relative_path"] == "Public Court.md"

    openspec = shutil.which("openspec")
    if openspec is None:
        pytest.skip("openspec CLI is not installed on this runner")
    validation = subprocess.run(
        [openspec, "validate", "--specs"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )
    assert validation.returncode == 0, validation.stderr


def _make_leakage_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    initialize_vault(vault, cli_version="0.1.0")
    (vault / ".backet" / "state" / "bot-config.yaml").write_text(
        "schema_version: 1\n"
        "guild_id: guild-a\n"
        "roles:\n"
        "  player:\n"
        "    - player-role\n"
        "  storyteller:\n"
        "    - st-role\n",
        encoding="utf-8",
    )
    _write(
        vault / "Public Court.md",
        "player",
        ["canon"],
        "# Public Court\n\nSabine is publicly known as a museum patron and Elysium regular.",
    )
    _write(
        vault / "NPCs" / "Sabine.md",
        "storyteller",
        ["npc", "statblock"],
        "# Sabine Secret Stat Block\n\nSabine has a regent betrayal clock and a hidden haven beneath the museum.",
    )
    _write(
        vault / "Plotlines" / "Museum Betrayal.md",
        "storyteller",
        ["plotline"],
        "# Museum Betrayal\n\nThe regent betrayal starts below the public exhibit.",
    )
    return vault


def _export_bundle(runner, vault: Path, tmp_path: Path) -> Path:
    output = tmp_path / "bundle"
    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])
    assert result.exit_code == 0, result.stdout
    return output


def _write(path: Path, visibility: str, topics: list[str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    topic_lines = "".join(f"    - {topic}\n" for topic in topics)
    topics_block = f"  bot_topics:\n{topic_lines}" if topics else ""
    path.write_text(f"---\nbacket:\n  visibility: {visibility}\n{topics_block}---\n\n{body}\n", encoding="utf-8")
