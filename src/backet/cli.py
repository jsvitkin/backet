from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from backet import __version__
from backet.errors import AppError
from backet.indexing import index_vault
from backet.memory import build_memory_capsules
from backet.output import CLIState, emit_error, emit_success, emit_version, ensure_state
from backet.retrieval import build_context_bundle
from backet.rules import audit_rules, ingest_rulebook, query_rules, repair_rules
from backet.skills import install_skills, skills_status, update_skills
from backet.vault import diagnose_vault, initialize_vault

app = typer.Typer(no_args_is_help=True, help="backet CLI")
skills_app = typer.Typer(help="Manage the backet Codex skill pack.")
memory_app = typer.Typer(help="Manage derived vault memory capsules.")
rules_app = typer.Typer(help="Manage ingested rulebook PDFs and raw rules retrieval.")
app.add_typer(skills_app, name="skills")
app.add_typer(memory_app, name="memory")
app.add_typer(rules_app, name="rules")

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


@app.command("index")
def index_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    full: Annotated[bool, typer.Option("--full", help="Force a full reindex of all Markdown notes.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = index_vault(vault.resolve(), full=full)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@app.command("context")
def context_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    scope: Annotated[str, typer.Argument(help="Retrieval scope: vault, note, path, or subtree.")] = "vault",
    target: Annotated[str, typer.Argument(help="Target note or path for the requested scope.")] = ".",
    query: Annotated[
        str | None,
        typer.Option("--query", help="Optional exact or semantic retrieval query to refine the context bundle."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum number of source chunks to return.")] = 8,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Rebuild missing or stale index state before retrieval when possible."),
    ] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = build_context_bundle(
            vault_root=vault.resolve(),
            scope=scope,
            target=target,
            query=query,
            limit=limit,
            refresh=refresh,
        )
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


@memory_app.command("build")
def memory_build_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    family: Annotated[
        str,
        typer.Option("--family", help="Memory family to rebuild: all, city, or subtree."),
    ] = "all",
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Rebuild missing or stale retrieval state before regenerating memory."),
    ] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = build_memory_capsules(vault.resolve(), family=family, refresh=refresh)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_app.command("ingest")
def rules_ingest_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    pdf: Annotated[Path, typer.Argument(help="Local path to the source PDF.", file_okay=True, dir_okay=False)] = Path("."),
    book_id: Annotated[str, typer.Option("--book-id", help="Stable identifier for the ingested book.")] = "",
    title: Annotated[str | None, typer.Option("--title", help="Display title for the ingested book.")] = None,
    tier: Annotated[str, typer.Option("--tier", help="Precedence tier: core or supplement.")] = "core",
    scope_tags: Annotated[
        list[str] | None,
        typer.Option("--scope-tag", help="Repeatable scope tag used for supplement precedence."),
    ] = None,
    force_ocr: Annotated[bool, typer.Option("--force-ocr", help="Force OCR instead of direct text extraction.")] = False,
    pages: Annotated[str | None, typer.Option("--pages", help="Optional page range, for example `3-5,9`.")] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        if not book_id.strip():
            raise AppError(
                code="rules_book_id_missing",
                message="A stable `--book-id` is required for rulebook ingestion.",
                hint="Re-run the command with `--book-id some-book-id`.",
                exit_code=2,
            )
        result = ingest_rulebook(
            vault_root=vault.resolve(),
            pdf_path=pdf.resolve(),
            book_id=book_id,
            title=title,
            tier=tier,
            scope_tags=scope_tags or [],
            force_ocr=force_ocr,
            pages_spec=pages,
        )
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_app.command("query")
def rules_query_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    query: Annotated[str, typer.Argument(help="Rule query text for raw chunk retrieval.")] = "",
    limit: Annotated[int, typer.Option("--limit", help="Maximum number of primary or fallback chunks to return.")] = 6,
    book_id: Annotated[str | None, typer.Option("--book-id", help="Restrict retrieval to a single ingested book.")] = None,
    scope_tags: Annotated[
        list[str] | None,
        typer.Option("--scope-tag", help="Repeatable scope tag used for precedence or filtering."),
    ] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        result = query_rules(
            vault_root=vault.resolve(),
            query=query,
            limit=limit,
            book_id=book_id,
            scope_tags=scope_tags or [],
        )
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_app.command("audit")
def rules_audit_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    book_id: Annotated[str | None, typer.Option("--book-id", help="Optional book identifier to audit.")] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        result = audit_rules(vault.resolve(), book_id=book_id)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_app.command("repair")
def rules_repair_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    book_id: Annotated[str, typer.Argument(help="Book identifier to repair.")] = "",
    pages: Annotated[str | None, typer.Option("--pages", help="Optional targeted page range, for example `3-5,9`.")] = None,
    force_ocr: Annotated[bool, typer.Option("--force-ocr", help="Force OCR during targeted repair.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = repair_rules(vault.resolve(), book_id=book_id, pages_spec=pages, force_ocr=force_ocr)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


def run() -> None:
    app()
