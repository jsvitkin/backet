from __future__ import annotations

import json
from pathlib import Path

from backet.cli import app


def test_init_creates_expected_vault_structure(runner, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    result = runner.invoke(app, ["--json", "init", str(vault)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert ".backetignore" in payload["created"]
    assert (vault / ".backetignore").exists()
    assert (vault / ".backet" / "config.yaml").exists()
    assert (vault / ".backet" / ".gitignore").exists()
    assert (vault / ".backet" / "state").is_dir()
    assert (vault / ".backet" / "memory").is_dir()
    assert (vault / ".backet" / "rules").is_dir()
    assert (vault / ".backet" / "cache").is_dir()
    assert (vault / ".backet" / "temp").is_dir()
    assert (vault / ".backet" / "ocr-work").is_dir()

    index_ignore = (vault / ".backetignore").read_text(encoding="utf-8")
    assert ".backet/" in index_ignore
    assert ".obsidian/" in index_ignore
    assert "Templates/" in index_ignore
    assert "Archive/" in index_ignore
    assert "Daily Notes/" in index_ignore


def test_init_refuses_to_overwrite_existing_bootstrap(runner, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    runner.invoke(app, ["init", str(vault)])

    result = runner.invoke(app, ["--json", "init", str(vault)])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "already_bootstrapped"


def test_doctor_reports_missing_safe_state_and_can_fix_it(runner, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    runner.invoke(app, ["init", str(vault)])

    (vault / ".backet" / "cache").rmdir()
    (vault / ".backet" / "temp").rmdir()
    (vault / ".backet" / "ocr-work").rmdir()
    (vault / ".backet" / ".gitignore").unlink()
    (vault / ".backetignore").unlink()

    dry_run = runner.invoke(app, ["--json", "doctor", str(vault)])
    dry_payload = json.loads(dry_run.stdout)
    issue_codes = {issue["code"] for issue in dry_payload["issues"]}

    assert dry_run.exit_code == 0
    assert {"missing_rebuildable_dir", "missing_gitignore", "missing_index_ignore"}.issubset(issue_codes)
    assert "tesseract" in dry_payload["data"]["system_dependencies"]

    fixed_run = runner.invoke(app, ["--json", "doctor", "--fix", str(vault)])
    fixed_payload = json.loads(fixed_run.stdout)

    assert fixed_run.exit_code == 0
    assert fixed_payload["data"]["safe_fix_applied"] is True
    assert (vault / ".backet" / "cache").is_dir()
    assert (vault / ".backet" / "temp").is_dir()
    assert (vault / ".backet" / "ocr-work").is_dir()
    assert (vault / ".backet" / ".gitignore").exists()
    assert (vault / ".backetignore").exists()


def test_doctor_fix_preserves_existing_index_ignore(runner, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    runner.invoke(app, ["init", str(vault)])

    custom_content = "Custom Canon Support/\n"
    (vault / ".backetignore").write_text(custom_content, encoding="utf-8")

    result = runner.invoke(app, ["--json", "doctor", "--fix", str(vault)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["data"]["safe_fix_applied"] is False
    assert (vault / ".backetignore").read_text(encoding="utf-8") == custom_content


def test_doctor_refuses_unsafe_repair_for_missing_durable_state(runner, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    runner.invoke(app, ["init", str(vault)])

    (vault / ".backet" / "config.yaml").unlink()

    result = runner.invoke(app, ["--json", "doctor", "--fix", str(vault)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["data"]["safe_fix_applied"] is False
    assert any(issue["code"] == "missing_durable_state" for issue in payload["issues"])
    assert not (vault / ".backet" / "config.yaml").exists()
