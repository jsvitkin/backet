from __future__ import annotations

from pathlib import Path

from backet.repository import default_skills_source, find_repo_root


def test_find_repo_root_walks_upward(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    nested = repo / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (repo / "openspec").mkdir()

    assert find_repo_root(nested) == repo

    monkeypatch.chdir(nested)
    assert find_repo_root() == repo


def test_default_skills_source_requires_manifest(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (repo / "openspec").mkdir()
    (repo / "skills").mkdir()

    monkeypatch.chdir(repo)
    assert default_skills_source() is None

    (repo / "skills" / "manifest.json").write_text("{}", encoding="utf-8")
    assert default_skills_source() == repo / "skills"
