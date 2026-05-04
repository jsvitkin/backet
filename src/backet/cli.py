from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated

import click
import typer

from backet import __version__
from backet.blueprints import apply_blueprint, blueprint_status
from backet.cli_update import (
    SKIP_UPDATE_CHECK_ENV,
    already_current_result,
    apply_cli_update,
    check_cli_update,
    is_interactive_caller,
    is_update_snoozed,
    reexec_backet,
    snooze_update,
    status_for_version,
    update_check_result,
    update_required_error,
    update_skipped_result,
)
from backet.errors import AppError
from backet.indexing import index_vault
from backet.memory import build_memory_capsules
from backet.output import CLIState, emit_error, emit_success, emit_version, ensure_state
from backet.retrieval import build_context_bundle
from backet.rules import (
    apply_rule_scope_manifest,
    audit_rule_scopes,
    audit_rules,
    export_rule_scopes,
    index_rules,
    ingest_rulebook,
    query_rules,
    relink_rule_source,
    replace_rule_page_text,
    repair_rules,
    review_rule_audit,
)
from backet.rules_output import (
    RulesIngestProgressReporter,
    emit_rules_audit_report,
    emit_rules_ingest_report,
    emit_rules_scope_audit_report,
)
from backet.skills import install_skills, skills_status, update_skills
from backet.vault import diagnose_vault, initialize_vault

app = typer.Typer(no_args_is_help=True, help="backet CLI")
skills_app = typer.Typer(help="Manage the backet Codex skill pack.")
memory_app = typer.Typer(help="Manage derived vault memory capsules.")
rules_app = typer.Typer(help="Manage ingested rulebook PDFs and raw rules retrieval.")
rules_scope_app = typer.Typer(help="Inspect and revise generated rule scope assertions.")
blueprint_app = typer.Typer(help="Manage workflow blueprint scaffolding and status.")
update_app = typer.Typer(help="Manage the installed backet CLI package.")
app.add_typer(skills_app, name="skills")
app.add_typer(memory_app, name="memory")
app.add_typer(rules_app, name="rules")
app.add_typer(blueprint_app, name="blueprint")
app.add_typer(update_app, name="update")
rules_app.add_typer(rules_scope_app, name="scope")

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit deterministic JSON output.")] = False,
    version: Annotated[
        bool,
        typer.Option("--version", is_eager=True, help="Show the installed backet version."),
    ] = False,
) -> None:
    state = CLIState(json_output=json_output)
    ctx.obj = state
    if version:
        emit_version(json_output, __version__)
        raise typer.Exit()
    if not _should_skip_update_preflight(ctx):
        _run_update_preflight(state)


def _handle_error(ctx: typer.Context, error: AppError) -> None:
    emit_error(ensure_state(ctx), error)


def _should_skip_update_preflight(ctx: typer.Context) -> bool:
    skip_value = os.environ.get(SKIP_UPDATE_CHECK_ENV)
    if skip_value:
        if skip_value == "rerun":
            os.environ.pop(SKIP_UPDATE_CHECK_ENV, None)
        return True
    return ctx.invoked_subcommand in {None, "update"}


def _run_update_preflight(state: CLIState) -> None:
    status = check_cli_update(__version__, force_refresh=False, fail_on_error=False)
    if not status.update_available:
        return

    if is_interactive_caller(json_output=state.json_output):
        if is_update_snoozed(status):
            return
        click.echo(
            f"A newer Backet CLI is available: {status.installed_version} -> {status.latest_version}",
            err=True,
        )
        if not click.confirm("Update now?", default=True, err=True):
            snooze_update(status)
            return
        try:
            apply_cli_update(status, capture_output=False)
        except AppError as error:
            emit_error(state, error)
        reexec_backet(sys.argv)
        raise typer.Exit()

    emit_error(state, update_required_error(status))


@update_app.command("check")
def update_check_command(
    ctx: typer.Context,
    fresh: Annotated[
        bool,
        typer.Option("--fresh", help="Deprecated; update checks always query the repository."),
    ] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = update_check_result(check_cli_update(__version__, force_refresh=fresh, fail_on_error=True))
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@update_app.command("apply")
def update_apply_command(
    ctx: typer.Context,
    yes: Annotated[bool, typer.Option("--yes", help="Apply the update without an interactive confirmation prompt.")] = False,
    target_version: Annotated[
        str | None,
        typer.Option("--version", help="Install a specific Backet CLI version instead of the latest stable release."),
    ] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        status = (
            status_for_version(__version__, target_version)
            if target_version is not None
            else check_cli_update(__version__, force_refresh=True, fail_on_error=True)
        )
        if not status.update_available:
            emit_success(state, already_current_result(status))
            return
        if not yes:
            if not is_interactive_caller(json_output=state.json_output):
                raise AppError(
                    code="cli_update_confirmation_required",
                    message="Applying a Backet CLI update requires confirmation.",
                    hint="Re-run with `backet update apply --yes` in non-interactive environments.",
                    details=status.to_dict(),
                    exit_code=2,
                )
            click.echo(
                f"A newer Backet CLI is available: {status.installed_version} -> {status.latest_version}",
                err=True,
            )
            if not click.confirm("Update now?", default=True, err=True):
                emit_success(state, update_skipped_result(status))
                return
        emit_success(state, apply_cli_update(status, capture_output=state.json_output))
    except AppError as error:
        _handle_error(ctx, error)


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


@blueprint_app.command("apply")
def blueprint_apply_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    blueprint: Annotated[str, typer.Argument(help="Named workflow blueprint identifier.")] = "",
    slot_paths: Annotated[
        list[str] | None,
        typer.Option(
            "--slot-path",
            help="Repeatable slot override in `slot-id=relative/path.md` form.",
        ),
    ] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        result = apply_blueprint(vault.resolve(), blueprint_id=blueprint, slot_paths=slot_paths or [])
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@blueprint_app.command("status")
def blueprint_status_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    blueprint: Annotated[str, typer.Argument(help="Named workflow blueprint identifier.")] = "",
) -> None:
    state = ensure_state(ctx)
    try:
        result = blueprint_status(vault.resolve(), blueprint_id=blueprint)
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
        if state.json_output:
            result = ingest_rulebook(
                vault_root=vault.resolve(),
                pdf_path=pdf.resolve(),
                book_id=book_id,
                title=title,
                tier=tier,
                force_ocr=force_ocr,
                pages_spec=pages,
            )
            emit_success(state, result)
            return

        with RulesIngestProgressReporter() as progress:
            result = ingest_rulebook(
                vault_root=vault.resolve(),
                pdf_path=pdf.resolve(),
                book_id=book_id,
                title=title,
                tier=tier,
                force_ocr=force_ocr,
                pages_spec=pages,
                progress=progress,
            )
        emit_rules_ingest_report(result)
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


@rules_app.command("index")
def rules_index_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    book_id: Annotated[str | None, typer.Option("--book-id", help="Optional book identifier to index.")] = None,
    full: Annotated[bool, typer.Option("--full", help="Force a full semantic rules reindex.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = index_rules(vault.resolve(), book_id=book_id, full=full)
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
        if state.json_output:
            emit_success(state, result)
            return
        emit_rules_audit_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_scope_app.command("audit")
def rules_scope_audit_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    book_id: Annotated[str | None, typer.Option("--book-id", help="Optional book identifier to audit scopes for.")] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        result = audit_rule_scopes(vault.resolve(), book_id=book_id)
        if state.json_output:
            emit_success(state, result)
            return
        emit_rules_scope_audit_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_app.command("review")
def rules_review_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    book_id: Annotated[str, typer.Option("--book-id", help="Book identifier to review.")] = "",
    page: Annotated[int, typer.Option("--page", help="Page number from the audit review queue.")] = 0,
    decision: Annotated[
        str,
        typer.Option("--decision", help="Review decision: accepted, ignored, excluded, or skipped."),
    ] = "",
    chunk_index: Annotated[int | None, typer.Option("--chunk-index", help="Optional chunk index for chunk-level review.")] = None,
    reason: Annotated[str, typer.Option("--reason", help="Short reason to store with the decision.")] = "",
    notes: Annotated[str, typer.Option("--notes", help="Optional review notes.")] = "",
) -> None:
    state = ensure_state(ctx)
    try:
        if not book_id.strip():
            raise AppError(
                code="rules_book_id_missing",
                message="A stable `--book-id` is required for rules audit review.",
                hint="Re-run with `--book-id some-book-id`.",
                exit_code=2,
            )
        if page < 1:
            raise AppError(
                code="rules_review_page_missing",
                message="A `--page` value is required for rules audit review.",
                hint="Use a page number reported by `backet rules audit`.",
                exit_code=2,
            )
        if not decision.strip():
            raise AppError(
                code="rules_review_decision_missing",
                message="A `--decision` value is required for rules audit review.",
                hint="Use accepted, ignored, excluded, or skipped.",
                exit_code=2,
            )
        result = review_rule_audit(
            vault.resolve(),
            book_id=book_id,
            page=page,
            chunk_index=chunk_index,
            decision=decision,
            reason=reason,
            notes=notes,
        )
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_app.command("replace")
def rules_replace_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    book_id: Annotated[str, typer.Option("--book-id", help="Book identifier to update.")] = "",
    page: Annotated[int, typer.Option("--page", help="Page number whose extracted text should be replaced.")] = 0,
    text: Annotated[str | None, typer.Option("--text", help="Inline replacement text.")] = None,
    text_file: Annotated[
        Path | None,
        typer.Option("--text-file", help="Path to a UTF-8 text file containing replacement page text.", file_okay=True, dir_okay=False),
    ] = None,
    read_stdin: Annotated[bool, typer.Option("--stdin", help="Read replacement page text from stdin.")] = False,
    reason: Annotated[str, typer.Option("--reason", help="Short reason to store with the replacement.")] = "",
    notes: Annotated[str, typer.Option("--notes", help="Optional replacement notes.")] = "",
) -> None:
    state = ensure_state(ctx)
    try:
        if not book_id.strip():
            raise AppError(
                code="rules_book_id_missing",
                message="A stable `--book-id` is required for manual page replacement.",
                hint="Re-run with `--book-id some-book-id`.",
                exit_code=2,
            )
        if page < 1:
            raise AppError(
                code="rules_replace_page_missing",
                message="A `--page` value is required for manual page replacement.",
                hint="Use a page number reported by `backet rules audit`.",
                exit_code=2,
            )
        replacement_text = _replacement_text_from_cli(text=text, text_file=text_file, read_stdin=read_stdin)
        result = replace_rule_page_text(
            vault.resolve(),
            book_id=book_id,
            page=page,
            text=replacement_text,
            reason=reason,
            notes=notes,
        )
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_app.command("relink-source")
def rules_relink_source_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    pdf: Annotated[Path, typer.Argument(help="Local path to the source PDF.", file_okay=True, dir_okay=False)] = Path("."),
    book_id: Annotated[str, typer.Option("--book-id", help="Book identifier whose source should be relinked.")] = "",
    force: Annotated[
        bool,
        typer.Option("--force", help="Trust this PDF as the new source even when its fingerprint differs."),
    ] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        if not book_id.strip():
            raise AppError(
                code="rules_book_id_missing",
                message="A stable `--book-id` is required for source relink.",
                hint="Re-run with `--book-id some-book-id`.",
                exit_code=2,
            )
        result = relink_rule_source(vault.resolve(), book_id=book_id, pdf_path=pdf.resolve(), force=force)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_scope_app.command("export")
def rules_scope_export_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    book_id: Annotated[str, typer.Option("--book-id", help="Book identifier to export scopes for.")] = "",
) -> None:
    state = ensure_state(ctx)
    try:
        if not book_id.strip():
            raise AppError(
                code="rules_book_id_missing",
                message="A stable `--book-id` is required for rule scope export.",
                hint="Re-run the command with `--book-id some-book-id`.",
                exit_code=2,
            )
        result = export_rule_scopes(vault.resolve(), book_id=book_id)
        emit_success(state, result)
    except AppError as error:
        _handle_error(ctx, error)


@rules_scope_app.command("apply")
def rules_scope_apply_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    manifest: Annotated[Path, typer.Argument(help="Path to a reviewed rule scope manifest.", file_okay=True, dir_okay=False)] = Path("."),
) -> None:
    state = ensure_state(ctx)
    try:
        result = apply_rule_scope_manifest(vault.resolve(), manifest.resolve())
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


def _replacement_text_from_cli(*, text: str | None, text_file: Path | None, read_stdin: bool) -> str:
    selected = sum(1 for value in (text is not None, text_file is not None, read_stdin) if value)
    if selected > 1:
        raise AppError(
            code="rules_replace_text_source_ambiguous",
            message="Manual page replacement accepts one text source at a time.",
            hint="Use only one of `--text`, `--text-file`, or `--stdin`.",
            exit_code=2,
        )
    if text is not None:
        return text
    if text_file is not None:
        if not text_file.exists() or not text_file.is_file():
            raise AppError(
                code="rules_replace_text_file_missing",
                message=f"Replacement text file not found: {text_file}",
                hint="Provide a readable UTF-8 text file.",
                details={"text_file": str(text_file)},
                exit_code=2,
            )
        try:
            return text_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise AppError(
                code="rules_replace_text_file_unreadable",
                message="Replacement text file could not be read.",
                hint="Check file permissions and try again.",
                details={"text_file": str(text_file), "error": str(exc)},
                exit_code=2,
            ) from exc
    if read_stdin:
        return sys.stdin.read()
    edited = click.edit("")
    if edited is None:
        raise AppError(
            code="rules_replace_text_missing",
            message="No replacement text was provided.",
            hint="Use the editor, `--text`, `--text-file`, or `--stdin`.",
            exit_code=2,
        )
    return edited


def run() -> None:
    app()
