from __future__ import annotations

import json
import logging
from pathlib import Path

from backet.bot_discord import DiscordRequestContext, _format_health, _format_help, build_discord_health, evaluate_discord_request
from backet.bot_runtime import BotBundle, open_index_readonly
from backet.cli import app
from backet.vault import initialize_vault


def test_discord_request_rejects_guild_mismatch_before_retrieval(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_bot_config(vault, guild_id="guild-a")
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    output = _export_bundle(runner, vault, tmp_path)
    opened: list[str] = []

    def tracking_index_opener(path: Path):
        opened.append(path.name)
        return open_index_readonly(path)

    bundle = BotBundle.load(output, index_opener=tracking_index_opener)
    answer = evaluate_discord_request(
        bundle,
        DiscordRequestContext(guild_id="guild-b", user_id="player", role_ids=["player-role"], channel_id="allowed"),
        command="canon.ask",
        question="court customs",
    )

    assert answer.denied is True
    assert answer.retrieval_attempted is False
    assert opened == []


def test_discord_request_enforces_channel_and_public_policy(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_bot_config(vault, guild_id="guild-a", restricted=True)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    wrong_channel = evaluate_discord_request(
        bundle,
        DiscordRequestContext(guild_id="guild-a", user_id="player", role_ids=["player-role"], channel_id="blocked"),
        command="canon.ask",
        question="court customs",
        private_requested=False,
    )
    allowed_channel = evaluate_discord_request(
        bundle,
        DiscordRequestContext(guild_id="guild-a", user_id="player", role_ids=["player-role"], channel_id="allowed"),
        command="canon.ask",
        question="court customs",
        private_requested=False,
    )

    assert wrong_channel.denied is True
    assert wrong_channel.retrieval_attempted is False
    assert allowed_channel.denied is False
    assert allowed_channel.response_private is True
    assert allowed_channel.sources[0]["relative_path"] == "Player Primer.md"


def test_discord_request_defaults_missing_mapping_to_player_and_denies_storyteller_command(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "Plot.md", "storyteller", ["plotline"], "# Plot\n\nHidden betrayal.")
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    answer = evaluate_discord_request(
        bundle,
        DiscordRequestContext(guild_id=None, user_id="unknown", role_ids=[], channel_id=None),
        command="st.plot",
        question="hidden betrayal",
    )

    assert answer.denied is True
    assert answer.retrieval_attempted is False


def test_discord_health_hides_sensitive_details_from_players(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_bot_config(vault, guild_id="guild-a")
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    player = build_discord_health(
        bundle,
        DiscordRequestContext(guild_id="guild-a", user_id="player", role_ids=["player-role"], channel_id="allowed"),
    )
    storyteller = build_discord_health(
        bundle,
        DiscordRequestContext(guild_id="guild-a", user_id="storyteller", role_ids=["st-role"], channel_id="allowed"),
    )

    assert player["ready"] is True
    assert "indexes" not in player
    assert "guild_id" not in player
    assert storyteller["guild_id"] == "guild-a"
    assert storyteller["indexes"]["storyteller"]["note_count"] == 1


def test_discord_health_format_is_compact_for_storytellers(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_bot_config(vault, guild_id="guild-a")
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)
    bundle.manifest["indexes"]["storyteller"]["relative_paths"] = [f"Note {index}.md" for index in range(500)]

    health = build_discord_health(
        bundle,
        DiscordRequestContext(guild_id="guild-a", user_id="storyteller", role_ids=["st-role"], channel_id="allowed"),
    )
    text = _format_health(health)

    assert len(text) < 1900
    assert "storyteller index: 1 notes" in text
    assert "Note 499.md" not in text


def test_discord_help_includes_registered_bot_help_command() -> None:
    text = _format_help()

    assert "/bot help" in text
    assert "/rules ask" in text


def test_discord_command_log_includes_answer_diagnostics(caplog, runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_bot_config(vault, guild_id="guild-a")
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    with caplog.at_level(logging.INFO, logger="backet.bot.discord"):
        evaluate_discord_request(
            bundle,
            DiscordRequestContext(guild_id="guild-a", user_id="player", role_ids=["player-role"], channel_id="allowed"),
            command="canon.ask",
            question="court customs",
        )

    message = next(record.getMessage() for record in caplog.records if "discord_bot_command" in record.getMessage())
    assert "answer_mode=template" in message
    assert "source_count=1" in message
    assert "response_chars=" in message
    assert "question_fingerprint=" in message
    assert "source_refs=[V1:vault]" in message


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    initialize_vault(vault, cli_version="0.1.0")
    return vault


def _export_bundle(runner, vault: Path, tmp_path: Path) -> Path:
    output = tmp_path / "bundle"
    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])
    assert result.exit_code == 0, result.stdout
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert "roles" in manifest["bot"]
    return output


def _write_bot_config(vault: Path, guild_id: str, restricted: bool = False) -> None:
    restricted_block = (
        "commands:\n"
        "  canon:\n"
        "    min_tier: player\n"
        "    topics:\n"
        "      - canon\n"
        "    channel_ids:\n"
        "      - allowed\n"
        "    public_allowed: false\n"
        if restricted
        else ""
    )
    (vault / ".backet" / "state" / "bot-config.yaml").write_text(
        "schema_version: 1\n"
        f"guild_id: {guild_id}\n"
        "roles:\n"
        "  player:\n"
        "    - player-role\n"
        "  storyteller:\n"
        "    - st-role\n"
        f"{restricted_block}",
        encoding="utf-8",
    )


def _write(path: Path, visibility: str, topics: list[str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    topic_lines = "".join(f"    - {topic}\n" for topic in topics)
    topics_block = f"  bot_topics:\n{topic_lines}" if topics else ""
    path.write_text(f"---\nbacket:\n  visibility: {visibility}\n{topics_block}---\n\n{body}\n", encoding="utf-8")
