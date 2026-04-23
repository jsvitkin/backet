from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

from backet.cli import app
from backet.indexing import _parse_markdown_chunks, inspect_index_state, open_index_connection
from backet.retrieval import build_fts_query


def test_parse_markdown_chunks_is_heading_aware() -> None:
    title, chunks = _parse_markdown_chunks(
        "sample-note",
        """
# Sample Note

Intro paragraph.

## Court Politics

Sabine controls feeding permits.

## Street Hunger

Blood doll rumors spread through Zizkov.
""".strip(),
    )

    assert title == "Sample Note"
    assert len(chunks) == 3
    assert chunks[1].heading_path == "Sample Note > Court Politics"
    assert chunks[2].heading_path == "Sample Note > Street Hunger"


def test_build_fts_query_tokenizes_text() -> None:
    query = build_fts_query("Sabine's blood-doll rumors!!!")

    assert query == '"sabine\'s" OR "blood" OR "doll" OR "rumors"'


def test_index_command_builds_sqlite_state_and_ignores_non_markdown(
    runner, retrieval_vault: Path
) -> None:
    (retrieval_vault / "notes.txt").write_text("ignored", encoding="utf-8")

    result = runner.invoke(app, ["--json", "index", str(retrieval_vault)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert (retrieval_vault / ".backet" / "state" / "vault-index.sqlite3").exists()

    state = inspect_index_state(retrieval_vault)
    assert state.has_index is True
    assert state.needs_refresh is False
    assert state.total_notes == 6

    with closing(open_index_connection(retrieval_vault)) as connection:
        indexed_notes = connection.execute("SELECT COUNT(*) AS count FROM notes").fetchone()["count"]
        indexed_chunks = connection.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()["count"]

    assert indexed_notes == 6
    assert indexed_chunks >= 6


def test_index_state_reports_missing_index_before_first_build(retrieval_vault: Path) -> None:
    state = inspect_index_state(retrieval_vault)

    assert state.has_index is False
    assert state.needs_refresh is True
    assert state.total_notes == 6


def test_index_command_reports_up_to_date_and_supports_full_reindex(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])

    up_to_date = runner.invoke(app, ["--json", "index", str(retrieval_vault)])
    full_reindex = runner.invoke(app, ["--json", "index", str(retrieval_vault), "--full"])

    assert up_to_date.exit_code == 0
    up_to_date_payload = json.loads(up_to_date.stdout)
    assert up_to_date_payload["message"] == "Vault index is already up to date"

    assert full_reindex.exit_code == 0
    full_payload = json.loads(full_reindex.stdout)
    assert full_payload["data"]["full_reindex"] is True
