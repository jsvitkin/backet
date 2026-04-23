from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import typer
from rich.console import Console
from rich.pretty import Pretty

from backet.errors import AppError
from backet.models import CommandResult

console = Console()


@dataclass(slots=True)
class CLIState:
    json_output: bool = False


def emit_success(state: CLIState, result: CommandResult) -> None:
    if state.json_output:
        typer.echo(
            json.dumps(
                {
                    "status": "ok",
                    **result.to_dict(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    console.print(f"[bold green]{result.message}[/bold green]")
    if result.created:
        console.print("Created:")
        for item in result.created:
            console.print(f"  - {item}")
    if result.fixed:
        console.print("Fixed:")
        for item in result.fixed:
            console.print(f"  - {item}")
    if result.issues:
        console.print("Issues:")
        for issue in result.issues:
            line = f"  - [{issue.severity}] {issue.message}"
            if issue.path:
                line += f" ({issue.path})"
            console.print(line)
            if issue.hint:
                console.print(f"    hint: {issue.hint}")
    for key, value in result.data.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            console.print(f"{key}:")
            console.print(Pretty(value, expand_all=True))
            continue
        console.print(f"{key}: {value}")


def emit_error(state: CLIState, error: AppError) -> None:
    if state.json_output:
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "hint": error.hint,
                        "details": error.details,
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise typer.Exit(error.exit_code)

    console.print(f"[bold red]{error.message}[/bold red]")
    console.print(f"code: {error.code}")
    if error.hint:
        console.print(f"hint: {error.hint}")
    if error.details:
        for key, value in error.details.items():
            console.print(f"{key}: {value}")
    raise typer.Exit(error.exit_code)


def emit_version(json_output: bool, version: str) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "status": "ok",
                    "message": "Version information",
                    "data": {"version": version},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    typer.echo(version)


def ensure_state(ctx: typer.Context) -> CLIState:
    state = ctx.obj
    if isinstance(state, CLIState):
        return state
    state = CLIState(json_output=False)
    ctx.obj = state
    return state
