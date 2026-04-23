from __future__ import annotations

import json
from pathlib import Path

import pytest

from backet.cli import app


def test_memory_build_writes_city_and_subtree_capsules(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])

    result = runner.invoke(app, ["--json", "memory", "build", str(retrieval_vault)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["data"]["capsules_written"] >= 2

    city_capsule = retrieval_vault / ".backet" / "memory" / "city" / "overview.md"
    subtree_capsule = retrieval_vault / ".backet" / "memory" / "subtrees" / "11-plotlines.md"
    assert city_capsule.exists()
    assert subtree_capsule.exists()
    assert "## Source References" in city_capsule.read_text(encoding="utf-8")
    assert "`11. Plotlines/11.1 Blood Doll Trade/11.1.1 Premise & Summary.md`" in subtree_capsule.read_text(
        encoding="utf-8"
    )


def test_memory_capsules_remain_committable(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])
    runner.invoke(app, ["memory", "build", str(retrieval_vault)])

    gitignore = (retrieval_vault / ".backet" / ".gitignore").read_text(encoding="utf-8")

    assert "memory/" not in gitignore
    assert "state/" not in gitignore
    assert "cache/" in gitignore
    assert "temp/" in gitignore


def test_memory_build_rejects_unknown_family(runner, retrieval_vault: Path) -> None:
    runner.invoke(app, ["index", str(retrieval_vault)])

    result = runner.invoke(app, ["--json", "memory", "build", str(retrieval_vault), "--family", "unknown"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "memory_family_unknown"
