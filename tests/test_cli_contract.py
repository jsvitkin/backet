from __future__ import annotations

import json
from pathlib import Path

from backet.cli import app


def test_version_supports_json_output(runner) -> None:
    result = runner.invoke(app, ["--json", "--version"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["data"]["version"] == "0.1.11"


def test_init_missing_vault_uses_actionable_json_error(runner, tmp_path: Path) -> None:
    missing_vault = tmp_path / "missing-vault"

    result = runner.invoke(app, ["--json", "init", str(missing_vault)])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "vault_not_found"
    assert "Create the vault directory first" in payload["error"]["hint"]


def test_doctor_requires_bootstrapped_vault(runner, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    result = runner.invoke(app, ["--json", "doctor", str(vault)])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "not_bootstrapped"
    assert "backet init" in payload["error"]["hint"]
