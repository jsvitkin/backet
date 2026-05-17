from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated, Any

import click
import typer

from backet import __version__
from backet.blueprints import apply_blueprint, blueprint_status
from backet.bot_answers import validate_llama_model_files
from backet.bot_access import (
    audit_bot_visibility,
    clear_bot_visibility,
    inspect_bot_policy,
    list_bot_visibility,
    set_bot_visibility,
)
from backet.bot_export import doctor_bot_bundle, export_bot_bundle
from backet.bot_discord import run_discord_bot_result
from backet.bot_guided import run_guided_bot_command_center
from backet.bot_output import (
    emit_bot_answer_report,
    emit_bot_bundle_doctor_report,
    emit_bot_bundle_inspect_report,
    emit_bot_export_report,
    emit_bot_model_check_report,
    emit_bot_policy_report,
    emit_bot_playground_report,
    emit_bot_qa_report,
    emit_bot_visibility_audit_report,
    emit_bot_visibility_list_report,
    emit_bot_visibility_update_report,
    emit_local_runtime_benchmark_report,
    emit_local_runtime_doctor_report,
)
from backet.bot_playground import run_bot_playground
from backet.bot_qa import run_bot_qa
from backet.bot_runtime import answer_bot_query_result, inspect_bot_bundle
from backet.bot_setup import (
    capture_secret_from_stdin_or_prompt,
    install_deployment_repository_files,
    reset_setup_state,
    resume_setup,
    run_deploy_setup,
    run_discord_setup,
    run_github_setup,
    run_oracle_setup,
    run_setup_overview,
    run_visibility_setup,
    setup_doctor,
    setup_status,
)
from backet.bot_setup_output import emit_bot_setup_report
from backet.bot_setup_wizard import GuidedBotSetupOptions, run_guided_bot_setup
from backet.bot_visibility_wizard import (
    run_guided_visibility_clear,
    run_guided_visibility_set,
    run_guided_visibility_wizard,
)
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
from backet.local_runtime import local_runtime_doctor, run_local_runtime_benchmark
from backet.memory import build_memory_capsules
from backet.models import CommandResult
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
    emit_rules_audit_review_card,
    emit_rules_ingest_report,
    emit_rules_scope_audit_report,
)
from backet.skills import install_skills, skills_status, update_skills
from backet.system_dependencies import check_system_dependencies, install_system_dependencies
from backet.system_dependencies_output import emit_system_dependencies_report
from backet.vault import diagnose_vault, initialize_vault

app = typer.Typer(no_args_is_help=True, help="backet CLI")
setup_app = typer.Typer(help="Check and install local system dependencies.")
skills_app = typer.Typer(help="Manage the backet Codex skill pack.")
memory_app = typer.Typer(help="Manage derived vault memory capsules.")
rules_app = typer.Typer(help="Manage ingested rulebook PDFs and raw rules retrieval.")
rules_scope_app = typer.Typer(help="Inspect and revise generated rule scope assertions.")
blueprint_app = typer.Typer(help="Manage workflow blueprint scaffolding and status.")
update_app = typer.Typer(help="Manage the installed backet CLI package.")
bot_app = typer.Typer(invoke_without_command=True, help="Manage private Backet bot configuration and exports.")
bot_visibility_app = typer.Typer(invoke_without_command=True, help="Inspect and update bot visibility metadata.")
bot_runtime_app = typer.Typer(help="Inspect and benchmark local model runtime services.")
app.add_typer(setup_app, name="setup")
app.add_typer(skills_app, name="skills")
app.add_typer(memory_app, name="memory")
app.add_typer(rules_app, name="rules")
app.add_typer(blueprint_app, name="blueprint")
app.add_typer(update_app, name="update")
app.add_typer(bot_app, name="bot")
rules_app.add_typer(rules_scope_app, name="scope")
bot_app.add_typer(bot_visibility_app, name="visibility")
bot_app.add_typer(bot_runtime_app, name="runtime")


@bot_app.callback(invoke_without_command=True)
def bot_callback(
    ctx: typer.Context,
    guided: Annotated[bool, typer.Option("--guided", help="Open the guided bot command center.")] = False,
    no_guided: Annotated[bool, typer.Option("--no-guided", help="Show command help without interactive prompts.")] = False,
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    state = ensure_state(ctx)
    try:
        if _should_start_guided_command(state, guided=guided, no_guided=no_guided):
            run_guided_bot_command_center(Path(".").resolve())
            raise typer.Exit()
        click.echo(ctx.get_help())
        raise typer.Exit()
    except AppError as error:
        _handle_error(ctx, error)


@bot_visibility_app.callback(invoke_without_command=True)
def bot_visibility_callback(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Option("--vault", help="Path to the target vault for the guided visibility wizard.")] = Path("."),
    guided: Annotated[bool, typer.Option("--guided", help="Open the guided visibility wizard.")] = False,
    no_guided: Annotated[bool, typer.Option("--no-guided", help="Show command help without interactive prompts.")] = False,
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    state = ensure_state(ctx)
    try:
        if _should_start_guided_command(state, guided=guided, no_guided=no_guided):
            run_guided_visibility_wizard(vault.resolve())
            raise typer.Exit()
        click.echo(ctx.get_help())
        raise typer.Exit()
    except AppError as error:
        _handle_error(ctx, error)

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


@setup_app.command("check")
def setup_check_command(ctx: typer.Context) -> None:
    state = ensure_state(ctx)
    try:
        result = check_system_dependencies()
        if state.json_output:
            emit_success(state, result)
            return
        emit_system_dependencies_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@setup_app.command("install")
def setup_install_command(
    ctx: typer.Context,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm installing or upgrading supported system dependencies.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = install_system_dependencies(yes=yes)
        if state.json_output:
            emit_success(state, result)
            return
        emit_system_dependencies_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_app.command("setup", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def bot_setup_command(
    ctx: typer.Context,
    token_stdin: Annotated[bool, typer.Option("--token-stdin", help="Read the Discord bot token from stdin.")] = False,
    prompt_token: Annotated[bool, typer.Option("--prompt-token", help="Prompt for the Discord bot token without echoing.")] = False,
    guild_id: Annotated[str | None, typer.Option("--guild-id", help="Discord server/guild ID after bot install.")] = None,
    player_role_ids: Annotated[
        list[str] | None,
        typer.Option("--player-role-id", help="Repeatable Discord player role ID."),
    ] = None,
    storyteller_role_ids: Annotated[
        list[str] | None,
        typer.Option("--storyteller-role-id", help="Repeatable Discord Storyteller role ID."),
    ] = None,
    canon_channel_ids: Annotated[
        list[str] | None,
        typer.Option("--canon-channel-id", help="Repeatable Discord channel ID for player-safe canon commands."),
    ] = None,
    allow_empty_player: Annotated[
        bool,
        typer.Option("--allow-empty-player", help="Allow deployment to continue with no player-visible canon notes."),
    ] = False,
    repo: Annotated[str | None, typer.Option("--repo", help="Private GitHub repository in OWNER/REPO form.")] = None,
    allow_public_repo: Annotated[
        bool,
        typer.Option("--allow-public-repo", help="Continue even when the repository is public."),
    ] = False,
    discord_token_stdin: Annotated[
        bool,
        typer.Option("--discord-token-stdin", help="Read DISCORD_TOKEN from stdin and send it directly to GitHub secrets."),
    ] = False,
    oracle_ssh_key_stdin: Annotated[
        bool,
        typer.Option("--oracle-ssh-key-stdin", help="Read ORACLE_VM_SSH_KEY from stdin and send it directly to GitHub secrets."),
    ] = False,
    model_token_stdin: Annotated[
        bool,
        typer.Option("--model-token-stdin", help="Read MODEL_DOWNLOAD_TOKEN from stdin and send it directly to GitHub secrets."),
    ] = False,
    host: Annotated[str | None, typer.Option("--host", help="Oracle VM public host or IP.")] = None,
    user: Annotated[str | None, typer.Option("--user", help="Oracle VM SSH username.")] = None,
    deploy_path: Annotated[str, typer.Option("--deploy-path", help="Remote deploy root.")] = "/srv/backet-bot",
    ssh_key: Annotated[
        Path | None,
        typer.Option("--ssh-key", help="Local SSH key path for validation only; key contents are not stored."),
    ] = None,
    bootstrap: Annotated[
        bool,
        typer.Option("--bootstrap", help="Create/check the remote deploy layout after SSH validation."),
    ] = False,
    vault_path: Annotated[str, typer.Option("--vault-path", help="Vault path inside the GitHub repository.")] = ".",
    release_id: Annotated[str | None, typer.Option("--release-id", help="Optional release ID for the workflow.")] = None,
    watch: Annotated[bool, typer.Option("--watch", help="Watch the GitHub Actions run after dispatch.")] = False,
    allow_dirty: Annotated[
        bool,
        typer.Option("--allow-dirty", help="Dispatch even if local Git state appears dirty or unpushed."),
    ] = False,
    repo_root: Annotated[
        Path | None,
        typer.Option("--repo-root", help="Repository root where setup deploy files should be installed."),
    ] = None,
    force_files: Annotated[
        bool,
        typer.Option("--force-files", help="Overwrite existing deploy files when running `backet bot setup files`."),
    ] = False,
    guided: Annotated[
        bool,
        typer.Option("--guided", help="Force the interactive guided setup wizard."),
    ] = False,
    no_guided: Annotated[
        bool,
        typer.Option("--no-guided", help="Show setup status/next action without interactive prompts."),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm setup state reset.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        phase, vault = _parse_bot_setup_args(ctx.args)
        resolved_vault = vault.resolve()
        if phase == "overview":
            if _should_start_guided_command(state, guided=guided, no_guided=no_guided):
                run_guided_bot_setup(
                    resolved_vault,
                    GuidedBotSetupOptions(
                        repo_root=repo_root,
                        force_files=force_files,
                        allow_public_repo=allow_public_repo,
                        allow_empty_player=allow_empty_player,
                        deploy_path=deploy_path,
                        vault_path=vault_path,
                        release_id=release_id,
                        watch=True,
                        allow_dirty=allow_dirty,
                    ),
                )
            else:
                _emit_bot_setup(state, run_setup_overview(resolved_vault), phase=phase)
        elif phase == "status":
            _emit_bot_setup(state, setup_status(resolved_vault), phase=phase)
        elif phase == "resume":
            _emit_bot_setup(state, resume_setup(resolved_vault), phase=phase)
        elif phase == "files":
            _emit_bot_setup(
                state,
                install_deployment_repository_files(resolved_vault, repo_root=repo_root, force=force_files),
                phase=phase,
            )
        elif phase == "discord":
            token = capture_secret_from_stdin_or_prompt("Discord bot token", use_stdin=token_stdin, prompt=prompt_token)
            _emit_bot_setup(
                state,
                run_discord_setup(
                    vault_root=resolved_vault,
                    token=token,
                    guild_id=guild_id,
                    player_role_ids=player_role_ids or [],
                    storyteller_role_ids=storyteller_role_ids or [],
                    canon_channel_ids=canon_channel_ids or [],
                ),
                phase=phase,
            )
        elif phase == "visibility":
            _emit_bot_setup(state, run_visibility_setup(resolved_vault, allow_empty_player=allow_empty_player), phase=phase)
        elif phase == "github":
            secret_values: dict[str, str] = {}
            if discord_token_stdin:
                secret_values["DISCORD_TOKEN"] = capture_secret_from_stdin_or_prompt("DISCORD_TOKEN", use_stdin=True) or ""
            if oracle_ssh_key_stdin:
                secret_values["ORACLE_VM_SSH_KEY"] = capture_secret_from_stdin_or_prompt("ORACLE_VM_SSH_KEY", use_stdin=True) or ""
            if model_token_stdin:
                secret_values["MODEL_DOWNLOAD_TOKEN"] = capture_secret_from_stdin_or_prompt("MODEL_DOWNLOAD_TOKEN", use_stdin=True) or ""
            _emit_bot_setup(
                state,
                run_github_setup(
                    vault_root=resolved_vault,
                    repo=repo,
                    secret_values=secret_values,
                    allow_public=allow_public_repo,
                ),
                phase=phase,
            )
        elif phase == "oracle":
            _emit_bot_setup(
                state,
                run_oracle_setup(
                    vault_root=resolved_vault,
                    host=host,
                    user=user,
                    deploy_path=deploy_path,
                    ssh_key_path=ssh_key,
                    bootstrap=bootstrap,
                ),
                phase=phase,
            )
        elif phase == "deploy":
            _emit_bot_setup(
                state,
                run_deploy_setup(
                    vault_root=resolved_vault,
                    vault_path=vault_path,
                    release_id=release_id,
                    watch=watch,
                    allow_dirty=allow_dirty,
                ),
                phase=phase,
            )
        elif phase == "doctor":
            _emit_bot_setup(state, setup_doctor(resolved_vault), phase=phase)
        elif phase == "reset":
            _emit_bot_setup(state, reset_setup_state(resolved_vault, yes=yes), phase=phase)
        else:
            raise typer.BadParameter(f"Unknown setup phase: {phase}")
    except AppError as error:
        _handle_error(ctx, error)


def _parse_bot_setup_args(args: list[str]) -> tuple[str, Path]:
    phases = {"status", "resume", "files", "discord", "visibility", "github", "oracle", "deploy", "doctor", "reset"}
    raw_args = list(args)
    if not raw_args:
        return "overview", Path(".")
    if raw_args[0] in phases:
        if len(raw_args) > 2:
            raise typer.BadParameter("Use `backet bot setup <phase> <vault>` with at most one vault path.")
        return raw_args[0], Path(raw_args[1]) if len(raw_args) == 2 else Path(".")
    if len(raw_args) > 1:
        raise typer.BadParameter("Use `backet bot setup <vault>` or `backet bot setup <phase> <vault>`.")
    return "overview", Path(raw_args[0])


def _emit_bot_setup(state: CLIState, result: CommandResult, *, phase: str) -> None:
    if state.json_output:
        emit_success(state, result)
        return
    emit_bot_setup_report(result, phase=phase)


def _should_start_guided_command(state: CLIState, *, guided: bool, no_guided: bool) -> bool:
    if state.json_output or no_guided:
        return False
    if guided:
        return True
    return sys.stdin.isatty() and sys.stdout.isatty()


@bot_app.command("policy")
def bot_policy_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
) -> None:
    state = ensure_state(ctx)
    try:
        result = inspect_bot_policy(vault.resolve())
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_policy_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_app.command("export")
def bot_export_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    output: Annotated[
        Path,
        typer.Option("--output", help="Directory where the private bot bundle should be written."),
    ] = Path("dist/bot-data"),
    force: Annotated[bool, typer.Option("--force", help="Replace an existing output directory.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = export_bot_bundle(vault.resolve(), output_path=output, force=force)
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_export_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_app.command("doctor")
def bot_doctor_command(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Argument(help="Path to an exported bot bundle.", file_okay=False, dir_okay=True)] = Path(
        "dist/bot-data"
    ),
) -> None:
    state = ensure_state(ctx)
    try:
        result = doctor_bot_bundle(bundle)
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_bundle_doctor_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_app.command("inspect")
def bot_inspect_command(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Argument(help="Path to an exported bot bundle.", file_okay=False, dir_okay=True)] = Path(
        "dist/bot-data"
    ),
) -> None:
    state = ensure_state(ctx)
    try:
        result = inspect_bot_bundle(bundle)
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_bundle_inspect_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_app.command("ask")
def bot_ask_command(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Argument(help="Path to an exported bot bundle.", file_okay=False, dir_okay=True)] = Path(
        "dist/bot-data"
    ),
    question: Annotated[str, typer.Argument(help="Question to answer from the bot bundle.")] = "",
    command: Annotated[
        str,
        typer.Option("--command", help="Dry-run command route: rules.ask, canon.ask, st.ask, st.npc, st.plot, st.statblock."),
    ] = "canon.ask",
    user_id: Annotated[str | None, typer.Option("--user-id", help="Discord user ID for access simulation.")] = None,
    role_ids: Annotated[
        list[str] | None,
        typer.Option("--role-id", help="Repeatable Discord role ID for access simulation."),
    ] = None,
    private: Annotated[
        bool | None,
        typer.Option("--private/--public", help="Override response visibility for the dry run."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum number of sources per corpus.")] = 4,
) -> None:
    state = ensure_state(ctx)
    try:
        result = answer_bot_query_result(
            bundle_root=bundle,
            command=command,
            question=question,
            user_id=user_id,
            role_ids=role_ids or [],
            private=private,
            limit=limit,
        )
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_answer_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_app.command("playground")
def bot_playground_command(
    ctx: typer.Context,
    target: Annotated[
        str,
        typer.Argument(help="Vault path, or the question when running from the vault directory."),
    ] = ".",
    question: Annotated[str, typer.Argument(help="Question to run through the local playground.")] = "",
    extra_questions: Annotated[
        list[str] | None,
        typer.Option("--question", help="Additional question to run. Can be repeated."),
    ] = None,
    command: Annotated[
        str,
        typer.Option("--command", help="Command route: rules.ask, canon.ask, st.ask, st.npc, st.plot, st.statblock."),
    ] = "rules.ask",
    user_id: Annotated[str | None, typer.Option("--user-id", help="Discord user ID for access simulation.")] = None,
    role_ids: Annotated[
        list[str] | None,
        typer.Option("--role-id", help="Repeatable Discord role ID for access simulation."),
    ] = None,
    private: Annotated[
        bool | None,
        typer.Option("--private/--public", help="Override response visibility for the playground run."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum number of sources per corpus.")] = 4,
    use_model: Annotated[
        bool,
        typer.Option("--use-model/--template-only", help="Use the configured local model instead of fast template mode."),
    ] = False,
    bundle_output: Annotated[
        Path | None,
        typer.Option("--bundle-output", help="Keep the exported playground bundle at this path."),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing --bundle-output directory.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        vault, questions = _resolve_bot_playground_args(target, question, extra_questions or [])
        result = run_bot_playground(
            vault_root=vault,
            questions=questions,
            command=command,
            user_id=user_id,
            role_ids=role_ids or [],
            private=private,
            limit=limit,
            use_model=use_model,
            bundle_output=bundle_output,
            force=force,
        )
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_playground_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_app.command("qa")
def bot_qa_command(
    ctx: typer.Context,
    target: Annotated[
        Path,
        typer.Argument(help="Vault path or exported bot bundle to run QA against.", file_okay=False, dir_okay=True),
    ] = Path("."),
    case_files: Annotated[
        list[Path] | None,
        typer.Option("--case-file", help="Answer QA case file. Can be repeated. Defaults to packaged standard cases."),
    ] = None,
    command: Annotated[
        str,
        typer.Option("--command", help="Default command route when a case does not specify one."),
    ] = "rules.ask",
    user_id: Annotated[str | None, typer.Option("--user-id", help="Discord user ID for access simulation.")] = None,
    role_ids: Annotated[
        list[str] | None,
        typer.Option("--role-id", help="Repeatable Discord role ID for access simulation."),
    ] = None,
    private: Annotated[
        bool | None,
        typer.Option("--private/--public", help="Override response visibility for QA answers."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum number of sources per corpus.")] = 4,
    use_model: Annotated[
        bool,
        typer.Option("--use-model/--template-only", help="Use the configured local model instead of fast template mode."),
    ] = False,
    bundle: Annotated[bool, typer.Option("--bundle", help="Treat TARGET as an exported bot bundle.")] = False,
    report_output: Annotated[
        Path | None,
        typer.Option("--report-output", help="Write JSON and Markdown QA reports to a file or directory."),
    ] = None,
    fail_on_failure: Annotated[
        bool,
        typer.Option("--fail-on-failure/--no-fail-on-failure", help="Exit non-zero when required cases fail."),
    ] = True,
) -> None:
    state = ensure_state(ctx)
    try:
        result = run_bot_qa(
            target=target,
            case_files=case_files or [],
            command=command,
            user_id=user_id,
            role_ids=role_ids or [],
            private=private,
            limit=limit,
            use_model=use_model,
            bundle=bundle,
            report_output=report_output,
        )
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_qa_report(result)
        if fail_on_failure and not result.data.get("ok"):
            raise typer.Exit(1)
    except AppError as error:
        _handle_error(ctx, error)


@bot_runtime_app.command("doctor")
def bot_runtime_doctor_command(
    ctx: typer.Context,
    endpoint: Annotated[str | None, typer.Option("--endpoint", help="Ollama API base URL.")] = None,
    embedding_model: Annotated[str | None, typer.Option("--embedding-model", help="Embedding model ID to require.")] = None,
    answer_model: Annotated[str | None, typer.Option("--answer-model", help="Answer model ID to require.")] = None,
    model_cache: Annotated[Path | None, typer.Option("--model-cache", help="Machine-local model cache path.")] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        result = local_runtime_doctor(
            endpoint=endpoint,
            embedding_model=embedding_model,
            answer_model=answer_model,
            model_cache=model_cache,
        )
        if state.json_output:
            emit_success(state, result)
        else:
            emit_local_runtime_doctor_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_runtime_app.command("benchmark")
def bot_runtime_benchmark_command(
    ctx: typer.Context,
    target: Annotated[
        Path | None,
        typer.Argument(help="Optional vault path or exported bundle for QA-backed benchmarking.", file_okay=False, dir_okay=True),
    ] = None,
    case_files: Annotated[
        list[Path] | None,
        typer.Option("--case-file", help="Answer QA case file. Can be repeated. Defaults to packaged standard cases."),
    ] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint", help="Ollama API base URL.")] = None,
    embedding_model: Annotated[str | None, typer.Option("--embedding-model", help="Embedding model ID to benchmark.")] = None,
    answer_model: Annotated[str | None, typer.Option("--answer-model", help="Answer model ID to benchmark.")] = None,
    model_cache: Annotated[Path | None, typer.Option("--model-cache", help="Machine-local model cache path.")] = None,
    command: Annotated[str, typer.Option("--command", help="Default bot command route for QA cases.")] = "rules.ask",
    user_id: Annotated[str | None, typer.Option("--user-id", help="Discord user ID for access simulation.")] = None,
    role_ids: Annotated[
        list[str] | None,
        typer.Option("--role-id", help="Repeatable Discord role ID for access simulation."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum number of sources per corpus.")] = 4,
    report_output: Annotated[
        Path | None,
        typer.Option("--report-output", help="Write JSON and Markdown benchmark reports to a file or directory."),
    ] = None,
    fail_on_failure: Annotated[
        bool,
        typer.Option("--fail-on-failure/--no-fail-on-failure", help="Exit non-zero when benchmark or required QA fails."),
    ] = True,
) -> None:
    state = ensure_state(ctx)
    try:
        result = run_local_runtime_benchmark(
            target=target,
            case_files=case_files or [],
            endpoint=endpoint,
            embedding_model=embedding_model,
            answer_model=answer_model,
            model_cache=model_cache,
            command=command,
            user_id=user_id,
            role_ids=role_ids or [],
            limit=limit,
            report_output=report_output,
        )
        if state.json_output:
            emit_success(state, result)
        else:
            emit_local_runtime_benchmark_report(result)
        if fail_on_failure and not result.data.get("ok"):
            raise typer.Exit(1)
    except AppError as error:
        _handle_error(ctx, error)


def _resolve_bot_playground_args(target: str, question: str, extra_questions: list[str]) -> tuple[Path, list[str]]:
    stripped_target = target.strip()
    stripped_question = question.strip()
    if stripped_question:
        return Path(stripped_target).expanduser().resolve(), [stripped_question, *extra_questions]
    candidate = Path(stripped_target).expanduser()
    if candidate.exists() and candidate.is_dir():
        return candidate.resolve(), extra_questions
    return Path(".").resolve(), [stripped_target, *extra_questions]


@bot_app.command("run")
def bot_run_command(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Argument(help="Path to an exported bot bundle.", file_okay=False, dir_okay=True)] = Path(
        "dist/bot-data"
    ),
    token: Annotated[str | None, typer.Option("--token", help="Discord bot token. Prefer DISCORD_TOKEN.")] = None,
    guild_id: Annotated[str | None, typer.Option("--guild-id", help="Configured Discord guild ID.")] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        emit_success(state, run_discord_bot_result(bundle_root=bundle, token=token, guild_id=guild_id))
    except AppError as error:
        _handle_error(ctx, error)


@bot_app.command("model-check")
def bot_model_check_command(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Argument(help="Path to an exported bot bundle.", file_okay=False, dir_okay=True)] = Path(
        "dist/bot-data"
    ),
    models_root: Annotated[
        Path | None,
        typer.Option("--models-root", help="VM-local model cache root for relative model paths."),
    ] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        result = validate_llama_model_files(bundle_root=bundle, models_root=models_root)
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_model_check_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_visibility_app.command("audit")
def bot_visibility_audit_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
) -> None:
    state = ensure_state(ctx)
    try:
        result = audit_bot_visibility(vault.resolve())
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_visibility_audit_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_visibility_app.command("list")
def bot_visibility_list_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    visibility: Annotated[str | None, typer.Option("--visibility", help="Filter by bot visibility.")] = None,
    topic: Annotated[str | None, typer.Option("--topic", help="Filter by bot topic.")] = None,
    unclassified: Annotated[bool, typer.Option("--unclassified", help="Show notes without explicit visibility metadata.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        result = list_bot_visibility(
            vault_root=vault.resolve(),
            visibility=visibility,
            topic=topic,
            unclassified=unclassified,
        )
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_visibility_list_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_visibility_app.command("set")
def bot_visibility_set_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    target: Annotated[str, typer.Argument(help="Vault-relative Markdown note or directory to update.")] = "",
    visibility: Annotated[str, typer.Option("--visibility", help="Bot visibility: player, storyteller, or excluded.")] = "",
    topics: Annotated[
        list[str] | None,
        typer.Option("--topic", help="Repeatable bot topic, such as canon, npc, plotline, statblock, or rules-summary."),
    ] = None,
    recursive: Annotated[bool, typer.Option("--recursive", help="Apply the update to Markdown notes under a directory.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing files.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm recursive writes without prompting.")] = False,
    guided: Annotated[bool, typer.Option("--guided", help="Prompt through preview and confirmation.")] = False,
    no_guided: Annotated[bool, typer.Option("--no-guided", help="Apply the focused command without interactive prompts.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        if _should_start_guided_command(state, guided=guided, no_guided=no_guided):
            run_guided_visibility_set(
                vault_root=vault.resolve(),
                target=target,
                visibility=visibility,
                topics=topics or [],
                recursive=recursive,
                dry_run=dry_run,
                yes=yes,
            )
            return
        result = set_bot_visibility(
            vault_root=vault.resolve(),
            target=target,
            visibility=visibility,
            topics=topics or [],
            recursive=recursive,
            dry_run=dry_run,
            yes=yes,
        )
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_visibility_update_report(result)
    except AppError as error:
        _handle_error(ctx, error)


@bot_visibility_app.command("clear")
def bot_visibility_clear_command(
    ctx: typer.Context,
    vault: Annotated[Path, typer.Argument(help="Path to the target vault.", file_okay=False, dir_okay=True)] = Path("."),
    target: Annotated[str, typer.Argument(help="Vault-relative Markdown note or directory to update.")] = "",
    recursive: Annotated[bool, typer.Option("--recursive", help="Clear metadata from Markdown notes under a directory.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing files.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm recursive writes without prompting.")] = False,
    guided: Annotated[bool, typer.Option("--guided", help="Prompt through preview and confirmation.")] = False,
    no_guided: Annotated[bool, typer.Option("--no-guided", help="Apply the focused command without interactive prompts.")] = False,
) -> None:
    state = ensure_state(ctx)
    try:
        if _should_start_guided_command(state, guided=guided, no_guided=no_guided):
            run_guided_visibility_clear(
                vault_root=vault.resolve(),
                target=target,
                recursive=recursive,
                dry_run=dry_run,
                yes=yes,
            )
            return
        result = clear_bot_visibility(
            vault_root=vault.resolve(),
            target=target,
            recursive=recursive,
            dry_run=dry_run,
            yes=yes,
        )
        if state.json_output:
            emit_success(state, result)
        else:
            emit_bot_visibility_update_report(result)
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
    review: Annotated[
        bool | None,
        typer.Option(
            "--review/--no-review",
            help="Enter guided human review for pending cards. Defaults on in interactive terminals.",
        ),
    ] = None,
) -> None:
    state = ensure_state(ctx)
    try:
        resolved_vault = vault.resolve()
        result = audit_rules(resolved_vault, book_id=book_id)
        if state.json_output:
            emit_success(state, result)
            return
        emit_rules_audit_report(result)
        if _should_start_rules_audit_review(review=review):
            _run_guided_rules_audit_review(resolved_vault, result)
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


def _should_start_rules_audit_review(*, review: bool | None) -> bool:
    if review is not None:
        return review
    return sys.stdin.isatty() and sys.stdout.isatty()


def _run_guided_rules_audit_review(vault_root: Path, audit_result) -> None:
    review_items = _audit_review_items(audit_result)
    if not review_items:
        click.echo("Review queue is clear.")
        return

    click.echo(f"Guided review: {len(review_items)} pending card(s)")
    for index, (book, card) in enumerate(review_items, start=1):
        emit_rules_audit_review_card(book, card, index=index, total=len(review_items))
        choice = _prompt_rules_audit_review_choice()
        if choice == "quit":
            click.echo("Stopped review.")
            return
        if choice == "skip":
            _apply_guided_review_decision(vault_root, book, card, "skipped")
            click.echo("Skipped for now.")
            continue
        if choice in {"accepted", "ignored", "excluded"}:
            _apply_guided_review_decision(vault_root, book, card, choice)
            click.echo(f"Marked {choice}.")
            continue
        if choice == "retry":
            _apply_guided_repair(vault_root, book, card)
            continue
        if choice == "replace":
            _apply_guided_replacement(vault_root, book, card)
            continue

    click.echo("Review queue complete.")


def _audit_review_items(audit_result) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    data = audit_result.data if isinstance(audit_result.data, dict) else {}
    books = data.get("books") if isinstance(data.get("books"), list) else []
    items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for book in books:
        if not isinstance(book, dict):
            continue
        cards = book.get("review_cards") if isinstance(book.get("review_cards"), list) else []
        for card in cards:
            if isinstance(card, dict):
                items.append((book, card))
    return items


def _prompt_rules_audit_review_choice() -> str:
    choices = {
        "a": "accepted",
        "accept": "accepted",
        "accepted": "accepted",
        "i": "ignored",
        "ignore": "ignored",
        "ignored": "ignored",
        "e": "excluded",
        "exclude": "excluded",
        "excluded": "excluded",
        "r": "retry",
        "retry": "retry",
        "repair": "retry",
        "m": "replace",
        "manual": "replace",
        "replace": "replace",
        "s": "skip",
        "skip": "skip",
        "skipped": "skip",
        "q": "quit",
        "quit": "quit",
    }
    while True:
        value = click.prompt(
            "Decision [a=accept, i=ignore, e=exclude, r=retry OCR, m=manual replace, s=skip, q=quit]",
            default="s",
            show_default=False,
        )
        normalized = choices.get(str(value).strip().lower())
        if normalized is not None:
            return normalized
        click.echo("Choose a, i, e, r, m, s, or q.")


def _apply_guided_review_decision(
    vault_root: Path,
    book: dict[str, Any],
    card: dict[str, Any],
    decision: str,
) -> None:
    book_id = str(book.get("book_id") or "")
    targets = _guided_review_targets(card)
    if not targets:
        raise AppError(
            code="rules_review_target_missing",
            message="This audit review card does not include a review target.",
            hint="Re-run `backet rules audit --json` and report the card payload.",
            details={"book_id": book_id, "page": card.get("page_start")},
            exit_code=2,
        )
    for target in targets:
        review_rule_audit(
            vault_root,
            book_id=book_id,
            page=int(target["page_start"]),
            chunk_index=target.get("chunk_index"),
            decision=decision,
            reason="guided audit review",
        )


def _guided_review_targets(card: dict[str, Any]) -> list[dict[str, Any]]:
    targets = card.get("targets") if isinstance(card.get("targets"), list) else []
    normalized: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict) or target.get("page_start") is None:
            continue
        chunk_index = target.get("chunk_index")
        normalized.append(
            {
                "page_start": int(target["page_start"]),
                "chunk_index": int(chunk_index) if chunk_index is not None else None,
            }
        )
    if normalized:
        return normalized
    page_start = card.get("page_start")
    if page_start is None:
        return []
    return [{"page_start": int(page_start), "chunk_index": None}]


def _apply_guided_repair(vault_root: Path, book: dict[str, Any], card: dict[str, Any]) -> None:
    book_id = str(book.get("book_id") or "")
    page = int(card["page_start"])
    try:
        repair_rules(vault_root, book_id=book_id, pages_spec=str(page), force_ocr=True)
    except AppError as error:
        click.echo(f"Automatic OCR retry did not run: {error.message}")
        if error.hint:
            click.echo(error.hint)
        return
    click.echo("Automatic OCR retry finished.")


def _apply_guided_replacement(vault_root: Path, book: dict[str, Any], card: dict[str, Any]) -> None:
    book_id = str(book.get("book_id") or "")
    page = int(card["page_start"])
    click.echo("Opening your editor for corrected page text.")
    try:
        text = _replacement_text_from_cli(text=None, text_file=None, read_stdin=False)
        replace_rule_page_text(vault_root, book_id=book_id, page=page, text=text, reason="guided audit review")
    except AppError as error:
        click.echo(f"Manual replacement was not saved: {error.message}")
        if error.hint:
            click.echo(error.hint)
        return
    click.echo("Manual replacement saved.")


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
