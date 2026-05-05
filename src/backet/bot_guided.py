from __future__ import annotations

from pathlib import Path

import click

from backet.bot_answers import validate_llama_model_files
from backet.bot_discord import run_discord_bot_result
from backet.bot_export import doctor_bot_bundle, export_bot_bundle
from backet.bot_output import (
    emit_bot_answer_report,
    emit_bot_bundle_doctor_report,
    emit_bot_bundle_inspect_report,
    emit_bot_export_report,
    emit_bot_model_check_report,
    emit_bot_policy_report,
)
from backet.bot_runtime import answer_bot_query_result, inspect_bot_bundle
from backet.bot_setup_wizard import GuidedBotSetupOptions, run_guided_bot_setup
from backet.bot_visibility_wizard import run_guided_visibility_wizard
from backet.bot_access import inspect_bot_policy
from backet.models import CommandResult


def run_guided_bot_command_center(default_path: Path) -> CommandResult:
    click.echo("Backet bot command center")
    click.echo("Choose a bot workflow and I will prompt for the needed values.")
    click.echo()
    click.echo("  1. Setup or deploy the private Discord bot")
    click.echo("  2. Review or edit bot visibility")
    click.echo("  3. Inspect bot policy")
    click.echo("  4. Export private bot bundle")
    click.echo("  5. Doctor exported bundle")
    click.echo("  6. Inspect exported bundle")
    click.echo("  7. Ask a dry-run bot question")
    click.echo("  8. Check local Llama model files")
    click.echo("  9. Run Discord bot in the foreground")
    click.echo("  10. Finish")
    choice = str(click.prompt("Choose a workflow", default="2", show_default=False)).strip().lower()
    if choice in {"10", "q", "quit", "finish"}:
        return CommandResult(message="Backet bot command center closed", data={})
    if choice in {"1", "setup", "deploy"}:
        vault = _prompt_path("Vault path", default_path)
        return run_guided_bot_setup(vault, GuidedBotSetupOptions())
    if choice in {"2", "visibility"}:
        vault = _prompt_path("Vault path", default_path)
        return run_guided_visibility_wizard(vault)
    if choice in {"3", "policy"}:
        vault = _prompt_path("Vault path", default_path)
        result = inspect_bot_policy(vault)
        emit_bot_policy_report(result)
        return result
    if choice in {"4", "export"}:
        return _guided_export(default_path)
    if choice in {"5", "doctor"}:
        bundle = _prompt_path("Bundle path", Path("dist/bot-data"))
        result = doctor_bot_bundle(bundle)
        emit_bot_bundle_doctor_report(result)
        return result
    if choice in {"6", "inspect"}:
        bundle = _prompt_path("Bundle path", Path("dist/bot-data"))
        result = inspect_bot_bundle(bundle)
        emit_bot_bundle_inspect_report(result)
        return result
    if choice in {"7", "ask"}:
        return _guided_ask()
    if choice in {"8", "model", "model-check"}:
        return _guided_model_check()
    if choice in {"9", "run"}:
        return _guided_run_bot()
    click.echo("Unknown action.")
    return CommandResult(message="Backet bot command center closed", data={"unknown_action": choice})


def _guided_export(default_path: Path) -> CommandResult:
    vault = _prompt_path("Vault path", default_path)
    output = _prompt_path("Bundle output path", Path("dist/bot-data"), must_exist=False)
    force = output.exists() and click.confirm("Output exists. Replace it?", default=False)
    result = export_bot_bundle(vault, output_path=output, force=force)
    emit_bot_export_report(result)
    if click.confirm("Run bundle doctor now?", default=True):
        doctor = doctor_bot_bundle(output)
        emit_bot_bundle_doctor_report(doctor)
    return result


def _guided_ask() -> CommandResult:
    bundle = _prompt_path("Bundle path", Path("dist/bot-data"))
    command = _prompt_command_route()
    question = str(click.prompt("Question", default="", show_default=False)).strip()
    role_ids = _prompt_csv("Discord role IDs for access simulation (blank for player default)")
    user_id = str(click.prompt("Discord user ID override (blank for none)", default="", show_default=False)).strip() or None
    private = None
    if click.confirm("Override response visibility?", default=False):
        private = click.confirm("Force private response?", default=True)
    result = answer_bot_query_result(
        bundle,
        command=command,
        question=question,
        user_id=user_id,
        role_ids=role_ids,
        private=private,
    )
    emit_bot_answer_report(result)
    return result


def _guided_model_check() -> CommandResult:
    bundle = _prompt_path("Bundle path", Path("dist/bot-data"))
    models_root_text = str(click.prompt("Models root (blank for /srv/backet-bot/models)", default="", show_default=False)).strip()
    models_root = Path(models_root_text).expanduser() if models_root_text else None
    result = validate_llama_model_files(bundle_root=bundle, models_root=models_root)
    emit_bot_model_check_report(result)
    return result


def _guided_run_bot() -> CommandResult:
    bundle = _prompt_path("Bundle path", Path("dist/bot-data"))
    click.echo("This starts the Discord bot in the foreground until you stop it.")
    if not click.confirm("Start the bot now?", default=False):
        return CommandResult(message="Discord bot start skipped", data={"bundle_root": str(bundle)})
    token = click.prompt("Discord bot token (hidden, blank to use DISCORD_TOKEN)", default="", hide_input=True, show_default=False)
    guild_id = str(click.prompt("Discord guild ID (blank to use bundle/env)", default="", show_default=False)).strip() or None
    return run_discord_bot_result(bundle_root=bundle, token=str(token).strip() or None, guild_id=guild_id)


def _prompt_path(label: str, default: Path, *, must_exist: bool = True) -> Path:
    default_text = str(default)
    while True:
        value = str(click.prompt(label, default=default_text)).strip()
        path = Path(value).expanduser().resolve()
        if not must_exist or path.exists():
            return path
        click.echo(f"Path does not exist: {path}")


def _prompt_command_route() -> str:
    routes = ["rules.ask", "canon.ask", "st.ask", "st.npc", "st.plot", "st.statblock"]
    click.echo("Commands:")
    for index, route in enumerate(routes, start=1):
        click.echo(f"  {index}. {route}")
    while True:
        value = str(click.prompt("Command", default="canon.ask")).strip().lower()
        if value.isdigit() and 1 <= int(value) <= len(routes):
            return routes[int(value) - 1]
        if value in routes:
            return value
        click.echo("Choose a listed command.")


def _prompt_csv(label: str) -> list[str]:
    value = str(click.prompt(label, default="", show_default=False)).strip()
    return [item.strip() for item in value.split(",") if item.strip()]
