from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

from backet.bot_access import read_note_frontmatter
from backet.cli import app
from backet.indexing import open_index_connection
from backet.vault import initialize_vault


def test_bot_visibility_audit_defaults_unmarked_notes_to_storyteller(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nKnown court customs.")
    _write(vault / "NPCs" / "Sabine.md", "storyteller", ["npc"], "# Sabine\n\nHidden stat block.")
    _write(vault / "Scratch.md", "excluded", [], "# Scratch\n\nNot for bot export.")
    (vault / "Legacy.md").write_text("# Legacy\n\nNo visibility metadata yet.", encoding="utf-8")

    result = runner.invoke(app, ["--json", "bot", "visibility", "audit", str(vault)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    summary = payload["data"]["summary"]
    assert summary["total_notes"] == 4
    assert summary["player_index_notes"] == 1
    assert summary["storyteller_index_notes"] == 3
    assert summary["excluded_notes"] == 1
    assert summary["unclassified_notes"] == 1

    decisions = {item["relative_path"]: item for item in payload["data"]["decisions"]}
    assert decisions["Player Primer.md"]["included_in_player"] is True
    assert decisions["NPCs/Sabine.md"]["included_in_player"] is False
    assert decisions["NPCs/Sabine.md"]["included_in_storyteller"] is True
    assert decisions["Scratch.md"]["included_in_storyteller"] is False
    assert decisions["Legacy.md"]["visibility"] == "storyteller"
    assert decisions["Legacy.md"]["metadata_source"] == "default"


def test_bot_visibility_list_filters_by_visibility_topic_and_unclassified(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nKnown court customs.")
    _write(vault / "NPCs" / "Sabine.md", "storyteller", ["npc"], "# Sabine\n\nHidden stat block.")
    (vault / "Legacy.md").write_text("# Legacy\n\nNo visibility metadata yet.", encoding="utf-8")

    player = runner.invoke(app, ["--json", "bot", "visibility", "list", str(vault), "--visibility", "player"])
    npc = runner.invoke(app, ["--json", "bot", "visibility", "list", str(vault), "--topic", "npc"])
    unclassified = runner.invoke(app, ["--json", "bot", "visibility", "list", str(vault), "--unclassified"])

    assert player.exit_code == 0
    assert [item["relative_path"] for item in json.loads(player.stdout)["data"]["decisions"]] == ["Player Primer.md"]
    assert npc.exit_code == 0
    assert [item["relative_path"] for item in json.loads(npc.stdout)["data"]["decisions"]] == ["NPCs/Sabine.md"]
    assert unclassified.exit_code == 0
    assert [item["relative_path"] for item in json.loads(unclassified.stdout)["data"]["decisions"]] == ["Legacy.md"]


def test_bot_visibility_set_updates_frontmatter_and_preserves_content(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    note = vault / "Primer.md"
    note.write_text("---\naliases:\n  - Primer\n---\n\n# Primer\n\nVisible canon.\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--json",
            "bot",
            "visibility",
            "set",
            str(vault),
            "Primer.md",
            "--visibility",
            "player",
            "--topic",
            "canon",
        ],
    )

    assert result.exit_code == 0
    frontmatter = read_note_frontmatter(note)
    assert frontmatter["aliases"] == ["Primer"]
    assert frontmatter["backet"] == {"visibility": "player", "bot_topics": ["canon"]}
    assert "# Primer\n\nVisible canon." in note.read_text(encoding="utf-8")


def test_bot_visibility_recursive_requires_confirmation_and_supports_dry_run(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    folder = vault / "Player Facing"
    folder.mkdir()
    (folder / "One.md").write_text("# One\n\nPublic.", encoding="utf-8")
    (folder / "Two.md").write_text("# Two\n\nPublic.", encoding="utf-8")

    blocked = runner.invoke(
        app,
        [
            "--json",
            "bot",
            "visibility",
            "set",
            str(vault),
            "Player Facing",
            "--visibility",
            "player",
            "--topic",
            "canon",
            "--recursive",
        ],
    )
    dry_run = runner.invoke(
        app,
        [
            "--json",
            "bot",
            "visibility",
            "set",
            str(vault),
            "Player Facing",
            "--visibility",
            "player",
            "--topic",
            "canon",
            "--recursive",
            "--dry-run",
        ],
    )
    assert blocked.exit_code == 2
    assert json.loads(blocked.stdout)["error"]["code"] == "bot_visibility_confirmation_required"
    assert dry_run.exit_code == 0
    assert read_note_frontmatter(folder / "One.md") is None

    applied = runner.invoke(
        app,
        [
            "--json",
            "bot",
            "visibility",
            "set",
            str(vault),
            "Player Facing",
            "--visibility",
            "player",
            "--topic",
            "canon",
            "--recursive",
            "--yes",
        ],
    )

    assert applied.exit_code == 0
    payload = json.loads(applied.stdout)
    assert payload["data"]["changed_count"] == 2
    assert read_note_frontmatter(folder / "One.md")["backet"]["visibility"] == "player"
    assert read_note_frontmatter(folder / "Two.md")["backet"]["bot_topics"] == ["canon"]


def test_bot_visibility_clear_preserves_unrelated_frontmatter(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    note = vault / "Primer.md"
    note.write_text(
        "---\naliases:\n  - Primer\nbacket:\n  visibility: player\n  bot_topics:\n    - canon\n---\n\n# Primer\n\nVisible canon.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--json", "bot", "visibility", "clear", str(vault), "Primer.md"])

    assert result.exit_code == 0
    frontmatter = read_note_frontmatter(note)
    assert frontmatter == {"aliases": ["Primer"]}
    assert "# Primer\n\nVisible canon." in note.read_text(encoding="utf-8")


def test_bot_visibility_rejects_invalid_values(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    (vault / "Primer.md").write_text("# Primer\n", encoding="utf-8")

    bad_visibility = runner.invoke(
        app,
        ["--json", "bot", "visibility", "set", str(vault), "Primer.md", "--visibility", "public"],
    )
    bad_topic = runner.invoke(
        app,
        [
            "--json",
            "bot",
            "visibility",
            "set",
            str(vault),
            "Primer.md",
            "--visibility",
            "player",
            "--topic",
            "secret",
        ],
    )

    assert bad_visibility.exit_code == 2
    assert json.loads(bad_visibility.stdout)["error"]["code"] == "bot_visibility_invalid"
    assert bad_topic.exit_code == 2
    assert json.loads(bad_topic.stdout)["error"]["code"] == "bot_topic_invalid"


def test_bot_visibility_without_subcommand_runs_guided_wizard(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    (vault / "Legacy.md").write_text("# Legacy\n\nNo visibility metadata yet.", encoding="utf-8")

    result = runner.invoke(app, ["bot", "visibility", "--guided", "--vault", str(vault)], input="4\n7\n")

    assert result.exit_code == 0, result.output
    assert "Bot visibility wizard" in result.output
    assert "Current visibility" in result.output
    assert "What would you like to do?" in result.output
    assert "Bot visibility list" in result.output
    assert "Legacy.md" in result.output
    assert "Action [" not in result.output
    assert "backet bot visibility set" not in result.output
    assert "decisions:" not in result.output
    assert "{'relative_path'" not in result.output


def test_bot_visibility_wizard_end_to_end_classifies_fake_vault_without_command_recipes(
    runner,
    tmp_path: Path,
) -> None:
    vault = _make_bot_vault(tmp_path)
    player_folder = vault / "Player Facing"
    player_folder.mkdir()
    (player_folder / "Primer.md").write_text("# Primer\n\nPublic court facts.", encoding="utf-8")
    (player_folder / "Laws.md").write_text("# Laws\n\nPublic domain rules.", encoding="utf-8")
    secrets = vault / "Secrets"
    secrets.mkdir()
    (secrets / "Prince.md").write_text("# Prince\n\nHidden plot material.", encoding="utf-8")

    result = runner.invoke(
        app,
        ["bot", "visibility", "--guided", "--vault", str(vault)],
        input="1\n1\n1\ny\ny\n3\n1\ny\n7\n",
    )

    assert result.exit_code == 0, result.output
    assert "What would you like to do?" in result.output
    assert "Suggested targets from this vault" in result.output
    assert "Apply this visibility update?" in result.output
    assert "Action [" not in result.output
    assert "Run `" not in result.output
    assert "backet bot visibility set" not in result.output
    assert "{'relative_path'" not in result.output
    assert read_note_frontmatter(player_folder / "Primer.md")["backet"] == {
        "visibility": "player",
        "bot_topics": ["canon"],
    }
    assert read_note_frontmatter(player_folder / "Laws.md")["backet"] == {
        "visibility": "player",
        "bot_topics": ["canon"],
    }
    assert read_note_frontmatter(secrets / "Prince.md")["backet"] == {"visibility": "excluded"}


def test_bot_without_subcommand_runs_guided_command_center(runner) -> None:
    result = runner.invoke(app, ["bot", "--guided"], input="q\n")

    assert result.exit_code == 0, result.output
    assert "Backet bot command center" in result.output
    assert "Setup or deploy" in result.output
    assert "Review or edit bot visibility" in result.output


def test_bot_visibility_guided_set_previews_and_confirms(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    note = vault / "Primer.md"
    note.write_text("# Primer\n\nVisible canon.\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "bot",
            "visibility",
            "set",
            "--guided",
            str(vault),
            "Primer.md",
            "--visibility",
            "player",
            "--topic",
            "canon",
        ],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert "Bot visibility dry run complete" in result.output
    assert "Apply this visibility update?" in result.output
    assert "Bot visibility metadata updated" in result.output
    assert read_note_frontmatter(note)["backet"] == {"visibility": "player", "bot_topics": ["canon"]}


def test_bot_policy_uses_guided_human_renderer(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nKnown court customs.")

    result = runner.invoke(app, ["bot", "policy", str(vault)])

    assert result.exit_code == 0, result.output
    assert "Bot policy" in result.output
    assert "Visibility:" in result.output
    assert "config:" not in result.output
    assert "{'schema_version'" not in result.output


def test_bot_visibility_audit_human_output_points_to_wizard_without_command_recipe(
    runner,
    tmp_path: Path,
) -> None:
    vault = _make_bot_vault(tmp_path)
    (vault / "Legacy.md").write_text("# Legacy\n\nNo visibility metadata yet.", encoding="utf-8")

    result = runner.invoke(app, ["bot", "visibility", "audit", str(vault)])

    assert result.exit_code == 0, result.output
    assert "Bot visibility audit" in result.output
    assert "Open the guided visibility editor" in result.output
    assert "Run `" not in result.output
    assert "backet bot visibility set" not in result.output


def test_bot_excluded_note_remains_available_to_normal_indexing(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    _write(vault / "Scratch.md", "excluded", [], "# Scratch\n\nThe normal index may still see this.")

    result = runner.invoke(app, ["--json", "index", str(vault)])

    assert result.exit_code == 0
    with closing(open_index_connection(vault)) as connection:
        row = connection.execute("SELECT * FROM notes WHERE relative_path = 'Scratch.md'").fetchone()
    assert row is not None


def test_bot_policy_reports_default_config_without_secrets(runner, tmp_path: Path) -> None:
    vault = _make_bot_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nKnown court customs.")

    result = runner.invoke(app, ["--json", "bot", "policy", str(vault)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["config"]["exists"] is False
    assert payload["data"]["config"]["commands"]["rules"]["min_tier"] == "player"
    assert payload["data"]["visibility_summary"]["player_index_notes"] == 1


def _make_bot_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    initialize_vault(vault, cli_version="0.1.0")
    return vault


def _write(path: Path, visibility: str, topics: list[str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    topic_lines = "".join(f"    - {topic}\n" for topic in topics)
    topics_block = f"  bot_topics:\n{topic_lines}" if topics else ""
    path.write_text(f"---\nbacket:\n  visibility: {visibility}\n{topics_block}---\n\n{body}\n", encoding="utf-8")
