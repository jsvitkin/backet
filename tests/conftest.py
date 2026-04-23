from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_machine_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BACKET_CONFIG_HOME", str(tmp_path / "machine-config"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
