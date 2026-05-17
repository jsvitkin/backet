from __future__ import annotations

import json
from pathlib import Path

from backet.cli import app


def test_cli_skills_install_and_status_json(runner, tmp_path: Path) -> None:
    source_dir = _create_skill_source(tmp_path / "skills")

    install_result = runner.invoke(app, ["--json", "skills", "install", "--source", str(source_dir)])
    status_result = runner.invoke(app, ["--json", "skills", "status"])

    assert install_result.exit_code == 0
    install_payload = json.loads(install_result.stdout)
    assert install_payload["data"]["skills_installed"] == 1

    assert status_result.exit_code == 0
    status_payload = json.loads(status_result.stdout)
    assert status_payload["data"]["installed"] is True
    assert status_payload["data"]["compatible"] is True


def test_cli_skills_update_reports_missing_install(runner) -> None:
    result = runner.invoke(app, ["--json", "skills", "update"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "skills_not_installed"


def _create_skill_source(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "pack_version": "0.2.0",
        "cli_requirement": ">=0.2.0,<0.3.0",
        "skills": [{"name": "npc-author", "path": "npc-author"}],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    skill_dir = root / "npc-author"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# NPC author\n", encoding="utf-8")
    return root
