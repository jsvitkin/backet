from __future__ import annotations

from pathlib import Path
import shutil

import pytest
from typer.testing import CliRunner

from backet.vault import initialize_vault


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_machine_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BACKET_CONFIG_HOME", str(tmp_path / "machine-config"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("BACKET_EMBEDDING_BACKEND", "hash")


@pytest.fixture
def retrieval_vault(tmp_path: Path) -> Path:
    fixture_root = Path(__file__).parent / "fixtures" / "vaults" / "retrieval-sample"
    vault_root = tmp_path / "retrieval-vault"
    shutil.copytree(fixture_root, vault_root)
    initialize_vault(vault_root, cli_version="0.1.0")
    return vault_root
