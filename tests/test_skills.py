from __future__ import annotations

import json
import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest

from backet.errors import AppError
from backet.paths import resolve_machine_paths
from backet.skills import install_skills, skills_status, update_skills


def test_install_skills_from_local_source_copies_skill_directories(tmp_path: Path) -> None:
    source_dir = _create_skill_source(
        tmp_path / "source",
        pack_version="0.1.0",
        requirement=">=0.1.0,<0.2.0",
        skills={"npc-author": "# NPC author\n"},
    )

    result = install_skills(cli_version="0.1.0", source_dir=source_dir)
    machine = resolve_machine_paths()

    assert result.data["skills_installed"] == 1
    assert (machine.codex_skills_dir / "npc-author" / "SKILL.md").exists()
    manifest = json.loads(machine.skill_manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_kind"] == "directory"
    assert manifest["pack_version"] == "0.1.0"


def test_skills_status_reports_installed_manifest(tmp_path: Path) -> None:
    source_dir = _create_skill_source(
        tmp_path / "source",
        pack_version="0.1.0",
        requirement=">=0.1.0,<0.2.0",
        skills={"npc-author": "# NPC author\n"},
    )
    install_skills(cli_version="0.1.0", source_dir=source_dir)

    status = skills_status(cli_version="0.1.0")

    assert status.data["installed"] is True
    assert status.data["compatible"] is True
    assert status.data["installed_manifest"]["pack_version"] == "0.1.0"


def test_incompatible_skill_pack_is_rejected(tmp_path: Path) -> None:
    source_dir = _create_skill_source(
        tmp_path / "source",
        pack_version="0.2.0",
        requirement=">=0.2.0,<0.3.0",
        skills={"npc-author": "# NPC author\n"},
    )

    with pytest.raises(AppError, match="not compatible"):
        install_skills(cli_version="0.1.0", source_dir=source_dir)


def test_update_skills_from_local_source_removes_stale_directories(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    _create_skill_source(
        source_dir,
        pack_version="0.1.0",
        requirement=">=0.1.0,<0.2.0",
        skills={"old-skill": "# Old skill\n"},
    )
    install_skills(cli_version="0.1.0", source_dir=source_dir)

    _replace_skill_source(
        source_dir,
        pack_version="0.1.1",
        requirement=">=0.1.0,<0.2.0",
        skills={"new-skill": "# New skill\n"},
    )
    result = update_skills(cli_version="0.1.0")
    machine = resolve_machine_paths()

    assert result.data["skills_installed"] == 1
    assert (machine.codex_skills_dir / "new-skill" / "SKILL.md").exists()
    assert not (machine.codex_skills_dir / "old-skill").exists()
    assert any(path.endswith("old-skill") for path in result.fixed)


def test_install_skills_from_repository_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = _create_repo_archive(
        tmp_path / "repo-archive.zip",
        pack_version="0.3.0",
        requirement=">=0.1.0,<0.4.0",
        skills={"plot-author": "# Plot author\n"},
    )
    monkeypatch.setenv("BACKET_SKILLS_ARCHIVE_URL", archive_path.as_uri())
    monkeypatch.setattr("backet.skills.default_skills_source", lambda: None)

    result = install_skills(cli_version="0.1.0", repository="example/backet", ref="main")
    machine = resolve_machine_paths()
    manifest = json.loads(machine.skill_manifest_path.read_text(encoding="utf-8"))

    assert result.data["source_kind"] == "repository_archive"
    assert manifest["repository"] == "example/backet"
    assert manifest["ref"] == "main"
    assert (machine.codex_skills_dir / "plot-author" / "SKILL.md").exists()


def _create_skill_source(root: Path, pack_version: str, requirement: str, skills: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "pack_version": pack_version,
        "cli_requirement": requirement,
        "skills": [{"name": name, "path": name} for name in skills],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    for name, body in skills.items():
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    return root


def _replace_skill_source(root: Path, pack_version: str, requirement: str, skills: dict[str, str]) -> None:
    shutil.rmtree(root)
    _create_skill_source(root, pack_version=pack_version, requirement=requirement, skills=skills)


def _create_repo_archive(target: Path, pack_version: str, requirement: str, skills: dict[str, str]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w") as zip_file:
        manifest = {
            "schema_version": 1,
            "pack_version": pack_version,
            "cli_requirement": requirement,
            "skills": [{"name": name, "path": name} for name in skills],
        }
        zip_file.writestr("backet-main/skills/manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        for name, body in skills.items():
            zip_file.writestr(f"backet-main/skills/{name}/SKILL.md", body)
    return target
