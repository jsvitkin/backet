from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from backet import __version__
from backet.errors import AppError
from backet.output import CLIState, emit_error, emit_success, emit_version, ensure_state
from backet.skills import install_skills, skills_status, update_skills
from backet.vault import diagnose_vault, initialize_vault

app = typer.Typer(no_args_is_help=True, help="backet CLI")
skills_app = typer.Typer(help="Manage the backet Codex skill pack.")
app.add_typer(skills_app, name="skills")

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit deterministic JSON output.")] = False,
    version: Annotated[
        bool,
        typer.Option("--version", is_eager=True, help="Show the installed backet version."),
    ] = False,
) -> None:
    ctx.obj = CLIState(json_output=json_output)
    if version:
        emit_version(json_output, __version__)
        raise typer.Exit()


def _handle_error(ctx: typer.Context, error: AppError) -> None:
    emit_error(ensure_state(ctx), error)


@app.command("init")
def init_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
) -> None:
    state = ensure_state(ctx)
    try:
        result = initialize_vault(vault.resolve(), cli_version=__version__)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@app.command("doctor")
def doctor_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    fix: Annotated[bool, typer.Option("--fix", help="Repair only deterministic rebuildable local artifacts.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = diagnose_vault(vault.resolve(), fix=fix)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@skills_app.command("status")
def skills_status_command(ctx: typer.Context) -> None:
    state = ensure_state(ctx)
    try:
        result = skills_status(cli_version=__version__)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@skills_app.command("install")
def skills_install_command(
    ctx: typer.Context,
    source: Annotated[
        Path | None,
        typer.Option(
            "--source",
            help="Path to a skill pack directory containing manifest.json.",
            file_okay=False,
            dir_okay=True,
            exists=False,
        ),
    ] = None,
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="GitHub repository in OWNER/REPO form for downloading the skill pack."),
    ] = None,
    ref: Annotated[
        str | None,
        typer.Option("--ref", help="Git ref to use when downloading the skill pack from a repository."),
    ] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        resolved_source = source.resolve() if source is not None else None
        result = install_skills(cli_version=__version__, source_dir=resolved_source, repository=repo, ref=ref)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@skills_app.command("update")
def skills_update_command(
    ctx: typer.Context,
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="Override the GitHub repository used to refresh the installed skill pack."),
    ] = None,
    ref: Annotated[
        str | None,
        typer.Option("--ref", help="Override the Git ref used to refresh the installed skill pack."),
    ] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        result = update_skills(cli_version=__version__, repository=repo, ref=ref)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


def run() -> None:
    app()
