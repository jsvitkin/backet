from __future__ import annotations

import json
from io import StringIO

import click
import pytest
import typer
from rich.console import Console

import backet.output
from backet.errors import AppError
from backet.models import CommandResult, Issue
from backet.output import CLIState, emit_error, emit_success, emit_version, ensure_state


def test_emit_success_supports_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = StringIO()
    monkeypatch.setattr(backet.output, "console", Console(file=buffer, force_terminal=False, color_system=None))

    emit_success(
        CLIState(json_output=False),
        CommandResult(
            message="All good",
            data={"vault": "/tmp/vault", "optional": None},
            created=[".backet/config.yaml"],
            fixed=[".backet/cache"],
            issues=[
                Issue(
                    code="missing_rebuildable_dir",
                    severity="warning",
                    message="Missing cache directory",
                    path=".backet/cache",
                    hint="Run doctor --fix",
                    safe_to_fix=True,
                )
            ],
        ),
    )

    output = buffer.getvalue()
    assert "All good" in output
    assert "Created:" in output
    assert "Fixed:" in output
    assert "Issues:" in output
    assert "vault: /tmp/vault" in output


def test_emit_success_supports_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    emit_success(CLIState(json_output=True), CommandResult(message="Done", data={"value": 3}))

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["data"]["value"] == 3


def test_emit_error_supports_human_and_json_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    buffer = StringIO()
    monkeypatch.setattr(backet.output, "console", Console(file=buffer, force_terminal=False, color_system=None))
    error = AppError(code="boom", message="Explosion", hint="Try again", details={"path": "x"}, exit_code=2)

    with pytest.raises(typer.Exit) as human_exit:
        emit_error(CLIState(json_output=False), error)
    assert human_exit.value.exit_code == 2
    assert "Explosion" in buffer.getvalue()
    assert "Try again" in buffer.getvalue()

    with pytest.raises(typer.Exit) as json_exit:
        emit_error(CLIState(json_output=True), error)
    assert json_exit.value.exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "boom"


def test_emit_version_and_ensure_state(capsys: pytest.CaptureFixture[str]) -> None:
    emit_version(json_output=False, version="0.1.4")
    assert capsys.readouterr().out.strip() == "0.1.4"

    emit_version(json_output=True, version="0.1.4")
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["version"] == "0.1.4"

    ctx = typer.Context(click.Command("backet"))
    state = ensure_state(ctx)
    assert state == CLIState(json_output=False)
    assert ensure_state(ctx) is state
