from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import fitz

from backet.bot_runtime import BotBundle, answer_bot_query, open_index_readonly
from backet.cli import app
from backet.vault import initialize_vault


def test_bot_runtime_answers_from_access_scoped_sources(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_bot_config(vault)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs say do not ping @everyone.")
    _write(vault / "NPCs" / "Sabine.md", "storyteller", ["npc"], "# Sabine\n\nSecret ghoul stat block.")
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    player_answer = answer_bot_query(
        bundle,
        command="canon.ask",
        question="What are the court customs around pinging everyone?",
        role_ids=["player-role"],
    )
    denied = answer_bot_query(bundle, command="st.npc", question="Sabine stat block", role_ids=["player-role"])
    storyteller_answer = answer_bot_query(bundle, command="st.npc", question="Sabine stat block", role_ids=["st-role"])

    assert player_answer.denied is False
    assert player_answer.access_tier == "player"
    assert {source["relative_path"] for source in player_answer.sources} == {"Player Primer.md"}
    assert "@everyone" not in player_answer.text
    assert "@\u200beveryone" in player_answer.text
    assert denied.denied is True
    assert denied.retrieval_attempted is False
    assert denied.response_private is True
    assert storyteller_answer.access_tier == "storyteller"
    assert "NPCs/Sabine.md" in {source["relative_path"] for source in storyteller_answer.sources}
    assert "Secret ghoul stat block" in storyteller_answer.text


def test_bot_runtime_denies_player_before_storyteller_index_is_opened(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_bot_config(vault)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    _write(vault / "Plot.md", "storyteller", ["plotline"], "# Plot\n\nHidden betrayal.")
    output = _export_bundle(runner, vault, tmp_path)
    opened: list[str] = []

    def tracking_index_opener(path: Path):
        opened.append(path.name)
        return open_index_readonly(path)

    bundle = BotBundle.load(output, index_opener=tracking_index_opener)
    answer = answer_bot_query(bundle, command="st.plot", question="hidden betrayal", role_ids=["player-role"])

    assert answer.denied is True
    assert opened == []


def test_bot_runtime_opens_bundle_indexes_read_only(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    with closing(bundle.open_index("player")) as connection:
        with pytest_raises_readonly():
            connection.execute("INSERT INTO index_meta (key, value) VALUES ('mutate', 'nope')")


def test_bot_ask_cli_exercises_runtime_without_discord(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_bot_config(vault)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    output = _export_bundle(runner, vault, tmp_path)

    result = runner.invoke(
        app,
        [
            "--json",
            "bot",
            "ask",
            str(output),
            "court customs",
            "--command",
            "canon.ask",
            "--role-id",
            "player-role",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["access_tier"] == "player"
    assert payload["data"]["sources"][0]["relative_path"] == "Player Primer.md"


def test_bot_runtime_keeps_unscoped_supplement_matches_answerable(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    _ingest_book(
        runner,
        vault,
        _create_text_pdf(
            tmp_path / "camarilla-a.pdf",
            [
                _rule_page(
                    "Feeding Rights",
                    "The Camarilla forbids feeding from blood dolls without approval. Permission must be explicit and revocable by local authority.",
                )
            ],
        ),
        "camarilla-a",
        "Camarilla A",
        "supplement",
    )
    _ingest_book(
        runner,
        vault,
        _create_text_pdf(
            tmp_path / "camarilla-b.pdf",
            [
                _rule_page(
                    "Feeding Rights",
                    "The Camarilla requires formal approval before blood doll feeding. Local officers may punish unlicensed access to blood dolls.",
                )
            ],
        ),
        "camarilla-b",
        "Camarilla B",
        "supplement",
    )
    output = _export_bundle(runner, vault, tmp_path)
    bundle = BotBundle.load(output)

    answer = answer_bot_query(
        bundle,
        command="rules.ask",
        question="camarilla blood doll approval feeding",
        role_ids=["player-role"],
    )

    assert "I found permitted sources" in answer.text
    assert "Camarilla A" in answer.text
    assert "Camarilla B" in answer.text
    assert answer.sources[0]["source_type"] == "vault"


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    initialize_vault(vault, cli_version="0.1.0")
    return vault


def _export_bundle(runner, vault: Path, tmp_path: Path) -> Path:
    output = tmp_path / "bundle"
    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])
    assert result.exit_code == 0, result.stdout
    return output


def _write_bot_config(vault: Path) -> None:
    (vault / ".backet" / "state" / "bot-config.yaml").write_text(
        "schema_version: 1\n"
        "roles:\n"
        "  player:\n"
        "    - player-role\n"
        "  storyteller:\n"
        "    - st-role\n",
        encoding="utf-8",
    )


def _write(path: Path, visibility: str, topics: list[str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    topic_lines = "".join(f"    - {topic}\n" for topic in topics)
    topics_block = f"  bot_topics:\n{topic_lines}" if topics else ""
    path.write_text(f"---\nbacket:\n  visibility: {visibility}\n{topics_block}---\n\n{body}\n", encoding="utf-8")


def _ingest_book(runner, vault: Path, pdf_path: Path, book_id: str, title: str, tier: str) -> None:
    result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "ingest",
            str(vault),
            str(pdf_path),
            "--book-id",
            book_id,
            "--title",
            title,
            "--tier",
            tier,
        ],
    )
    assert result.exit_code == 0, result.stdout


def _create_text_pdf(path: Path, page_texts: list[str]) -> Path:
    document = fitz.open()
    try:
        for text in page_texts:
            page = document.new_page()
            box = fitz.Rect(36, 36, page.rect.width - 36, page.rect.height - 36)
            page.insert_textbox(box, text, fontsize=12)
        document.save(path)
    finally:
        document.close()
    return path


def _rule_page(title: str, body: str) -> str:
    return f"{title}\n{body}"


class pytest_raises_readonly:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        assert exc_type is sqlite3.OperationalError
        assert "readonly" in str(exc_value).lower()
        return True
