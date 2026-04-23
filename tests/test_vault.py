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
    assert (vault / ".backet" / "config.yaml").exists()
    assert (vault / ".backet" / ".gitignore").exists()
    assert (vault / ".backet" / "state").is_dir()
    assert (vault / ".backet" / "memory").is_dir()
    assert (vault / ".backet" / "rules").is_dir()
    assert (vault / ".backet" / "cache").is_dir()
    assert (vault / ".backet" / "temp").is_dir()
    assert (vault / ".backet" / "ocr-work").is_dir()


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

    dry_run = runner.invoke(app, ["--json", "doctor", str(vault)])
    dry_payload = json.loads(dry_run.stdout)
    issue_codes = {issue["code"] for issue in dry_payload["issues"]}

    assert dry_run.exit_code == 0
    assert issue_codes == {"missing_rebuildable_dir", "missing_gitignore"}

    fixed_run = runner.invoke(app, ["--json", "doctor", "--fix", str(vault)])
    fixed_payload = json.loads(fixed_run.stdout)

    assert fixed_run.exit_code == 0
    assert fixed_payload["data"]["safe_fix_applied"] is True
    assert (vault / ".backet" / "cache").is_dir()
    assert (vault / ".backet" / "temp").is_dir()
    assert (vault / ".backet" / "ocr-work").is_dir()
    assert (vault / ".backet" / ".gitignore").exists()


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
