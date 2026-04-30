from __future__ import annotations

import json
import shutil
from contextlib import closing
from pathlib import Path

from backet.cli import app
from backet.indexing import open_index_connection
from backet.retrieval import resolve_scope_anchor


def test_scope_resolution_binds_note_and_subtree(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])
    with closing(open_index_connection(retrieval_vault)) as connection:
        note_anchor = resolve_scope_anchor(connection, "note", "Sabine")
        subtree_anchor = resolve_scope_anchor(connection, "subtree", "11. Plotlines")

    assert len(note_anchor.note_rows) == 1
    assert note_anchor.relative_paths == ["9. Named Storyteller Characters/9.1 Clan Ventrue/Sabine.md"]
    assert subtree_anchor.relative_paths == ["11. Plotlines/11.1 Blood Doll Trade/11.1.1 Premise & Summary.md"]


def test_context_exact_lookup_returns_named_canon(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])

    result = runner.invoke(
        app,
        [
            "--json",
            "context",
            str(retrieval_vault),
            "note",
            "Sabine",
            "--query",
            "Sabine Prince Prague feeding permits",
            "--limit",
            "4",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["scope"] == "note"
    assert payload["data"]["sources"][0]["title"] == "Sabine"
    assert payload["data"]["sources"][0]["relative_path"].endswith("Sabine.md")


def test_context_semantic_lookup_returns_relevant_plotline_context(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])

    result = runner.invoke(
        app,
        [
            "--json",
            "context",
            str(retrieval_vault),
            "vault",
            ".",
            "--query",
            "blood doll addiction mortal attachment hunger crisis",
            "--limit",
            "5",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    source_paths = [source["relative_path"] for source in payload["data"]["sources"]]
    assert "11. Plotlines/11.1 Blood Doll Trade/11.1.1 Premise & Summary.md" in source_paths
    assert any("semantic" in source["match_reasons"] for source in payload["data"]["sources"])


def test_context_query_does_not_return_ignored_markdown(runner, retrieval_vault: Path) -> None:
    archive = retrieval_vault / "Archive"
    archive.mkdir()
    (archive / "Forbidden Source.md").write_text(
        "# Forbidden Source\n\nThe emerald reliquary controls every ghoul ledger.",
        encoding="utf-8",
    )
    runner.invoke(app, ["index", str(retrieval_vault)])

    result = runner.invoke(
        app,
        [
            "--json",
            "context",
            str(retrieval_vault),
            "vault",
            ".",
            "--query",
            "emerald reliquary ghoul ledger",
            "--limit",
            "8",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    source_paths = [source["relative_path"] for source in payload["data"]["sources"]]
    assert "Archive/Forbidden Source.md" not in source_paths


def test_context_scope_bounded_bundle_stays_inside_subtree(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])

    result = runner.invoke(
        app,
        [
            "--json",
            "context",
            str(retrieval_vault),
            "subtree",
            "11. Plotlines",
            "--query",
            "blood doll witnesses",
            "--limit",
            "5",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["scope_note_count"] == 1
    assert all(source["relative_path"].startswith("11. Plotlines/") for source in payload["data"]["sources"])


def test_context_detects_stale_state_and_can_refresh(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])
    plotline_note = retrieval_vault / "11. Plotlines" / "11.1 Blood Doll Trade" / "11.1.1 Premise & Summary.md"
    plotline_note.write_text(plotline_note.read_text(encoding="utf-8") + "\n\n## New Lead\n\nA witness hid near the tram depot.\n", encoding="utf-8")

    stale_result = runner.invoke(
        app,
        ["--json", "context", str(retrieval_vault), "subtree", "11. Plotlines", "--query", "tram depot witness"],
    )
    assert stale_result.exit_code == 2
    stale_payload = json.loads(stale_result.stdout)
    assert stale_payload["error"]["code"] == "index_stale"

    refreshed_result = runner.invoke(
        app,
        [
            "--json",
            "context",
            str(retrieval_vault),
            "subtree",
            "11. Plotlines",
            "--query",
            "tram depot witness",
            "--refresh",
        ],
    )
    assert refreshed_result.exit_code == 0
    refreshed_payload = json.loads(refreshed_result.stdout)
    assert refreshed_payload["data"]["refresh_performed"] is True
    assert any("tram depot" in source["excerpt"].lower() for source in refreshed_payload["data"]["sources"])


def test_committed_index_portability_on_new_machine(runner, retrieval_vault: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])
    portable_vault = tmp_path / "portable-copy"
    shutil.copytree(retrieval_vault, portable_vault)

    result = runner.invoke(
        app,
        ["--json", "context", str(portable_vault), "note", "Sabine", "--query", "Prince Sabine"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["refresh_performed"] is False
    assert payload["data"]["index"]["has_index"] is True
    assert payload["data"]["sources"][0]["relative_path"].endswith("Sabine.md")


def test_context_rejects_invalid_scope_and_limit(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])

    invalid_scope = runner.invoke(app, ["--json", "context", str(retrieval_vault), "district", ".", "--query", "court"])
    invalid_limit = runner.invoke(app, ["--json", "context", str(retrieval_vault), "vault", ".", "--limit", "0"])

    assert invalid_scope.exit_code == 2
    assert json.loads(invalid_scope.stdout)["error"]["code"] == "context_scope_unknown"

    assert invalid_limit.exit_code == 2
    assert json.loads(invalid_limit.stdout)["error"]["code"] == "context_limit_invalid"


def test_context_reports_missing_targets(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])

    missing_note = runner.invoke(app, ["--json", "context", str(retrieval_vault), "note", "Unknown Prince"])
    missing_path = runner.invoke(app, ["--json", "context", str(retrieval_vault), "path", "13. Missing"])

    assert missing_note.exit_code == 2
    assert json.loads(missing_note.stdout)["error"]["code"] == "context_target_missing"

    assert missing_path.exit_code == 2
    assert json.loads(missing_path.stdout)["error"]["code"] == "context_target_missing"
