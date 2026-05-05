from __future__ import annotations

import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from backet.bot_setup import (
    DEFAULT_DEPLOY_PATH,
    DISCORD_PORTAL_URL,
    PHASE_DONE,
    PHASE_NEEDS_ACTION,
    SETUP_PHASES,
    configure_answer_setup,
    install_deployment_repository_files,
    load_or_initialize_setup_state,
    run_deploy_setup,
    run_discord_setup,
    run_github_setup,
    run_oracle_setup,
    run_setup_overview,
    run_visibility_setup,
    save_bot_setup_state,
    setup_status,
)
from backet.bot_visibility_wizard import run_guided_visibility_wizard
from backet.models import CommandResult


@dataclass(slots=True)
class GuidedBotSetupOptions:
    repo_root: Path | None = None
    force_files: bool = False
    allow_public_repo: bool = False
    allow_empty_player: bool = False
    deploy_path: str = DEFAULT_DEPLOY_PATH
    vault_path: str = "."
    release_id: str | None = None
    watch: bool = True
    allow_dirty: bool = False


def run_guided_bot_setup(vault_root: Path, options: GuidedBotSetupOptions | None = None) -> CommandResult:
    options = options or GuidedBotSetupOptions()
    memory = _WizardMemory()
    click.echo("Backet bot setup wizard")
    click.echo(f"Vault: {vault_root}")
    click.echo("I will guide one phase at a time and save only non-secret setup facts.")
    click.echo()

    result = run_setup_overview(vault_root)
    for phase in SETUP_PHASES:
        if _phase_is_done(vault_root, phase):
            _echo_phase_header(phase, status="already done")
            continue

        if phase == "prerequisites":
            result = _guide_prerequisites(vault_root, options)
        elif phase == "discord":
            result = _guide_discord(vault_root, memory)
        elif phase == "visibility":
            result = _guide_visibility(vault_root, options)
        elif phase == "github":
            _guide_answer_mode(vault_root, memory)
            _collect_oracle_facts_for_github(vault_root, options)
            result = _guide_github(vault_root, options, memory)
        elif phase == "oracle":
            result = _guide_oracle(vault_root, options)
        elif phase == "deploy":
            result = _guide_deploy(vault_root, options)
        else:  # pragma: no cover - SETUP_PHASES is fixed, keep the loop defensive.
            result = setup_status(vault_root)

        if not _result_phase_done(result):
            _echo_pending_result(result)
            return result
        if phase != SETUP_PHASES[-1] and not click.confirm("Continue to the next setup phase?", default=True):
            click.echo("Stopped. Run `backet bot setup` again to resume from here.")
            return setup_status(vault_root)

    click.echo()
    click.echo("Setup flow complete.")
    return setup_status(vault_root)


@dataclass(slots=True)
class _WizardMemory:
    discord_token: str | None = None
    model_download_token: str | None = None


def _guide_prerequisites(vault_root: Path, options: GuidedBotSetupOptions) -> CommandResult:
    _echo_phase_header("prerequisites")
    result = run_setup_overview(vault_root)
    phase = _last_phase(result)
    missing = list(dict(phase.get("data", {}) or {}).get("missing_deploy_files", []) or [])
    if missing:
        click.echo("The private deploy workflow/assets are missing from this repository checkout.")
        click.echo("These are safe-to-commit files: `.github/workflows/deploy-backet-bot.yml` and `deploy/bot/*`.")
        if click.confirm("Install or refresh those deployment files now?", default=True):
            result = install_deployment_repository_files(
                vault_root,
                repo_root=options.repo_root,
                force=options.force_files,
            )
            files = dict(result.data.get("repository_files", {}) or {})
            _echo_file_summary(files)
        else:
            click.echo("Skipped deployment file install.")
    else:
        click.echo("Local deployment files are present.")
    return result


def _guide_discord(vault_root: Path, memory: _WizardMemory) -> CommandResult:
    _echo_phase_header("discord")
    state = load_or_initialize_setup_state(vault_root, save=True)
    discord_state = dict(state.get("discord", {}) or {})

    click.echo("Discord still requires a browser consent step, but the CLI can validate and discover the IDs.")
    click.echo(f"Developer Portal: {DISCORD_PORTAL_URL}")
    click.echo("In the portal:")
    click.echo("  1. Create or open the Backet application.")
    click.echo("  2. Add/reset the bot token on the Bot page.")
    click.echo("  3. Keep Message Content Intent disabled.")
    click.echo("  4. Keep installation private to your server where Discord exposes that option.")
    _maybe_open_url("Open the Discord Developer Portal now?", DISCORD_PORTAL_URL)

    token = memory.discord_token or _prompt_hidden_optional("Discord bot token")
    if not token:
        return run_discord_setup(vault_root)
    memory.discord_token = token

    result = run_discord_setup(vault_root, token=token)
    data = _last_phase_data(result)
    invite_url = str(data.get("invite_url") or discord_state.get("invite_url") or "")
    if invite_url:
        click.echo()
        click.echo("Private install URL:")
        click.echo(invite_url)
        _maybe_open_url("Open the private bot install URL now?", invite_url)
        if click.confirm("Have you installed the bot into your private Discord server?", default=True):
            result = run_discord_setup(vault_root, token=token)
            data = _last_phase_data(result)

    guilds = _objects(data.get("guilds"))
    guild_id = str(discord_state.get("guild_id") or "")
    if not guild_id and guilds:
        guild_id = _prompt_object_choice("Choose the Discord server", guilds)
    if guild_id:
        result = run_discord_setup(vault_root, token=token, guild_id=guild_id)
        data = _last_phase_data(result)

    roles = _objects(data.get("roles"))
    channels = _objects(data.get("channels"))
    player_roles = _existing_selection(vault_root, "selected_role_ids", "player")
    storyteller_roles = _existing_selection(vault_root, "selected_role_ids", "storyteller")
    canon_channels = _existing_selection(vault_root, "selected_channel_ids", "canon")
    if roles and not player_roles:
        player_roles = _prompt_object_multi_choice("Choose player role(s)", roles)
    if roles and not storyteller_roles:
        storyteller_roles = _prompt_object_multi_choice("Choose Storyteller role(s)", roles)
    if channels and not canon_channels:
        canon_channels = _prompt_object_multi_choice("Choose player-safe canon channel(s)", channels, optional=True)

    if guild_id:
        result = run_discord_setup(
            vault_root,
            token=token,
            guild_id=guild_id,
            player_role_ids=player_roles,
            storyteller_role_ids=storyteller_roles,
            canon_channel_ids=canon_channels,
        )
    return result


def _guide_visibility(vault_root: Path, options: GuidedBotSetupOptions) -> CommandResult:
    _echo_phase_header("visibility")
    result = run_visibility_setup(vault_root, allow_empty_player=options.allow_empty_player)
    data = _last_phase_data(result)
    summary = dict(data.get("summary", {}) or {})
    if summary:
        click.echo("Visibility summary:")
        for key in ("player_index_notes", "storyteller_index_notes", "excluded_notes", "unclassified_notes"):
            click.echo(f"  {key.replace('_', ' ')}: {summary.get(key, 0)}")
    if _result_phase_done(result):
        return result
    if summary.get("player_index_notes", 0) == 0:
        click.echo("No player-visible canon notes are marked yet.")
        if click.confirm("Open the guided visibility editor now?", default=True):
            run_guided_visibility_wizard(vault_root)
            return run_visibility_setup(vault_root, allow_empty_player=options.allow_empty_player)
        if click.confirm("Continue with rules-only/player-canon-empty behavior for now?", default=False):
            return run_visibility_setup(vault_root, allow_empty_player=True)
    return result


def _guide_answer_mode(vault_root: Path, memory: _WizardMemory) -> CommandResult:
    click.echo()
    click.echo("Answer generation")
    state = load_or_initialize_setup_state(vault_root, save=True)
    answers = dict(state.get("answers", {}) or {})
    default_llama = answers.get("mode") == "llama-local"
    if not click.confirm("Enable local Llama synthesis on the Oracle VM?", default=default_llama):
        result = configure_answer_setup(vault_root, mode="template")
        click.echo("Using template/source-grounded answers. You can enable Llama later.")
        return result

    model = dict(answers.get("model", {}) or {})
    default_path = str(model.get("path") or "llama-3.2-3b-instruct-q4/model.gguf")
    model_path = click.prompt("Model path under `/srv/backet-bot/models`", default=default_path)
    model_url = click.prompt("Model download URL (leave blank if you will place it on the VM yourself)", default="", show_default=False)
    model_sha = click.prompt("Model SHA256 checksum (recommended, blank to skip)", default="", show_default=False)
    if model_url:
        token = _prompt_hidden_optional("Optional model download token")
        if token:
            memory.model_download_token = token
    result = configure_answer_setup(
        vault_root,
        mode="llama-local",
        model={"path": model_path, "url": model_url, "sha256": model_sha},
    )
    click.echo("Stored non-secret Llama model metadata for deployment.")
    return result


def _collect_oracle_facts_for_github(vault_root: Path, options: GuidedBotSetupOptions) -> None:
    state = load_or_initialize_setup_state(vault_root, save=True)
    oracle = dict(state.get("oracle", {}) or {})
    if not oracle.get("host"):
        oracle["host"] = click.prompt("Oracle VM host/IP for GitHub Actions", default="", show_default=False)
    if not oracle.get("user"):
        oracle["user"] = click.prompt("Oracle VM SSH user", default="ubuntu")
    oracle["deploy_path"] = click.prompt("Oracle VM deploy path", default=str(oracle.get("deploy_path") or options.deploy_path))
    state["oracle"] = oracle
    save_bot_setup_state(vault_root, state)


def _guide_github(vault_root: Path, options: GuidedBotSetupOptions, memory: _WizardMemory) -> CommandResult:
    _echo_phase_header("github")
    state = load_or_initialize_setup_state(vault_root, save=True)
    github = dict(state.get("github", {}) or {})
    default_repo = str(github.get("repository") or _infer_github_repository(options.repo_root or vault_root) or "")
    repo = click.prompt("Private GitHub repository (OWNER/REPO)", default=default_repo, show_default=bool(default_repo))
    secret_values: dict[str, str] = {}
    configured = set(github.get("secret_names", []) or [])
    if "DISCORD_TOKEN" not in configured:
        token = memory.discord_token or _prompt_hidden_optional("Discord bot token for GitHub secret DISCORD_TOKEN")
        if token:
            secret_values["DISCORD_TOKEN"] = token
            memory.discord_token = token
    if "ORACLE_VM_SSH_KEY" not in configured:
        key_value = _prompt_file_secret("Oracle VM SSH private key for GitHub secret ORACLE_VM_SSH_KEY")
        if key_value:
            secret_values["ORACLE_VM_SSH_KEY"] = key_value
    if memory.model_download_token:
        secret_values["MODEL_DOWNLOAD_TOKEN"] = memory.model_download_token

    result = run_github_setup(
        vault_root,
        repo=repo,
        secret_values=secret_values,
        allow_public=options.allow_public_repo,
    )
    last = _last_phase(result)
    if last.get("message") == "GitHub repository privacy needs confirmation.":
        if click.confirm("This repository is public. Continue anyway?", default=False):
            result = run_github_setup(vault_root, repo=repo, secret_values=secret_values, allow_public=True)
    return result


def _guide_oracle(vault_root: Path, options: GuidedBotSetupOptions) -> CommandResult:
    _echo_phase_header("oracle")
    state = load_or_initialize_setup_state(vault_root, save=True)
    oracle = dict(state.get("oracle", {}) or {})
    host = str(oracle.get("host") or click.prompt("Oracle VM host/IP", default="", show_default=False))
    user = str(oracle.get("user") or click.prompt("Oracle VM SSH user", default="ubuntu"))
    deploy_path = str(oracle.get("deploy_path") or options.deploy_path)
    key_path = _prompt_optional_path("SSH key path for validation (blank to use ssh-agent/default key)")
    result = run_oracle_setup(vault_root, host=host, user=user, deploy_path=deploy_path, ssh_key_path=key_path)
    if not _result_phase_done(result) and click.confirm("Bootstrap/check the Oracle deploy layout now?", default=True):
        result = run_oracle_setup(
            vault_root,
            host=host,
            user=user,
            deploy_path=deploy_path,
            ssh_key_path=key_path,
            bootstrap=True,
        )
    return result


def _guide_deploy(vault_root: Path, options: GuidedBotSetupOptions) -> CommandResult:
    _echo_phase_header("deploy")
    click.echo("GitHub Actions will export the private bot bundle, upload it to the VM, activate it, and smoke-check it.")
    if not click.confirm("Deploy now?", default=True):
        result = setup_status(vault_root)
        result.data["last_phase_result"] = {
            "phase": "deploy",
            "status": PHASE_NEEDS_ACTION,
            "message": "Deployment not dispatched",
            "next_actions": ["Run `backet bot setup deploy <vault> --watch` when you are ready."],
            "warnings": [],
            "data": {},
        }
        return result
    return run_deploy_setup(
        vault_root,
        vault_path=options.vault_path,
        release_id=options.release_id,
        watch=options.watch,
        allow_dirty=options.allow_dirty,
    )


def _echo_phase_header(phase: str, *, status: str | None = None) -> None:
    label = phase.replace("_", " ").title()
    suffix = f" ({status})" if status else ""
    click.echo()
    click.echo(f"== {label}{suffix} ==")


def _echo_pending_result(result: CommandResult) -> None:
    last = _last_phase(result)
    click.echo()
    click.echo(f"{last.get('phase', 'setup')}: {last.get('message', result.message)} ({last.get('status', 'pending')})")
    for warning in last.get("warnings", []) or []:
        click.echo(f"Warning: {warning}")
    actions = list(last.get("next_actions", []) or [])
    if actions:
        click.echo("Next:")
        for action in actions:
            click.echo(f"  - {action}")


def _echo_file_summary(files: dict[str, Any]) -> None:
    click.echo("Deployment files:")
    for label, key in (("created", "created"), ("updated", "updated"), ("unchanged", "unchanged"), ("skipped", "skipped")):
        values = list(files.get(key) or [])
        if values:
            click.echo(f"  {label}:")
            for value in values:
                click.echo(f"    - {value}")


def _maybe_open_url(prompt: str, url: str) -> None:
    if not url:
        return
    if click.confirm(prompt, default=False):
        opened = webbrowser.open(url)
        if not opened:
            click.echo("Could not open a browser automatically; copy the URL above.")


def _prompt_hidden_optional(label: str) -> str | None:
    value = click.prompt(f"{label} (hidden, blank to skip)", default="", hide_input=True, show_default=False)
    text = str(value).strip()
    return text or None


def _prompt_file_secret(label: str) -> str | None:
    while True:
        value = click.prompt(f"{label} path (blank to leave pending)", default="", show_default=False)
        text = str(value).strip()
        if not text:
            return None
        path = Path(text).expanduser()
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8")
        click.echo(f"File not found: {path}")


def _prompt_optional_path(label: str) -> Path | None:
    value = click.prompt(label, default="", show_default=False)
    text = str(value).strip()
    return Path(text).expanduser() if text else None


def _prompt_object_choice(label: str, items: list[dict[str, str]]) -> str:
    _echo_numbered_objects(items)
    while True:
        value = click.prompt(label, default="1" if len(items) == 1 else "", show_default=len(items) == 1)
        selected = _parse_object_selection(str(value), items, multiple=False)
        if selected:
            return selected[0]
        click.echo("Choose a number from the list or paste the ID.")


def _prompt_object_multi_choice(label: str, items: list[dict[str, str]], *, optional: bool = False) -> list[str]:
    _echo_numbered_objects(items)
    while True:
        value = click.prompt(f"{label} (comma-separated numbers or IDs)", default="", show_default=False)
        selected = _parse_object_selection(str(value), items, multiple=True)
        if selected or optional:
            return selected
        click.echo("Choose at least one entry.")


def _echo_numbered_objects(items: list[dict[str, str]]) -> None:
    for index, item in enumerate(items, start=1):
        name = item.get("name") or "(unnamed)"
        object_id = item.get("id") or ""
        click.echo(f"  {index}. {name} ({object_id})")


def _parse_object_selection(value: str, items: list[dict[str, str]], *, multiple: bool) -> list[str]:
    lookup = {str(index): str(item.get("id")) for index, item in enumerate(items, start=1) if item.get("id")}
    ids = {str(item.get("id")) for item in items if item.get("id")}
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not multiple and len(parts) > 1:
        return []
    selected: list[str] = []
    for part in parts:
        object_id = lookup.get(part) or (part if part in ids else None)
        if object_id and object_id not in selected:
            selected.append(object_id)
    return selected


def _existing_selection(vault_root: Path, group: str, key: str) -> list[str]:
    state = load_or_initialize_setup_state(vault_root, save=True)
    discord = dict(state.get("discord", {}) or {})
    values = dict(discord.get(group, {}) or {}).get(key, [])
    return [str(value) for value in values or [] if value]


def _objects(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    objects: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        objects.append({str(key): str(val) for key, val in item.items() if val is not None})
    return objects


def _last_phase(result: CommandResult) -> dict[str, Any]:
    return dict(result.data.get("last_phase_result", {}) or {})


def _last_phase_data(result: CommandResult) -> dict[str, Any]:
    return dict(_last_phase(result).get("data", {}) or {})


def _result_phase_done(result: CommandResult) -> bool:
    return _last_phase(result).get("status") == PHASE_DONE


def _phase_is_done(vault_root: Path, phase: str) -> bool:
    result = setup_status(vault_root)
    payload = dict(dict(result.data.get("phases", {}) or {}).get(phase, {}) or {})
    return payload.get("status") == PHASE_DONE


def _infer_github_repository(path: Path) -> str | None:
    git_root = _git_root(path)
    if git_root is None:
        return None
    completed = subprocess.run(
        ["git", "-C", str(git_root), "config", "--get", "remote.origin.url"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return _repository_from_remote(completed.stdout.strip())


def _git_root(path: Path) -> Path | None:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    output = completed.stdout.strip()
    return Path(output).resolve() if output else None


def _repository_from_remote(remote: str) -> str | None:
    if not remote:
        return None
    value = remote.strip()
    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    elif value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/")
    elif value.startswith("ssh://git@github.com/"):
        value = value.removeprefix("ssh://git@github.com/")
    else:
        return None
    value = value.removesuffix(".git").strip("/")
    if "/" not in value:
        return None
    owner, repo = value.split("/", 1)
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"
