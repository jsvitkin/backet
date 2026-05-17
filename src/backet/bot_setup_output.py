from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from backet.bot_setup import SETUP_PHASES
from backet.models import CommandResult, Issue
from backet.output import console

PHASE_LABELS = {
    "prerequisites": "Local prerequisites and deploy files",
    "discord": "Discord app, install, roles, and channels",
    "visibility": "Player-safe vault visibility",
    "github": "GitHub secrets, variables, and workflow",
    "oracle": "Oracle VM SSH and deploy layout",
    "deploy": "GitHub Actions deploy and smoke check",
}

PHASE_GUIDES = {
    "prerequisites": [
        "Install or refresh the local deployment files from the prerequisites step.",
        "Then commit and push `.github/workflows/deploy-backet-bot.yml` and `deploy/bot/*`.",
    ],
    "discord": [
        "Create or check the Discord application in the Developer Portal.",
        "Keep Message Content Intent disabled; Backet uses slash commands and private access policy.",
        "When Discord shows the bot token, continue through the guided Discord step.",
    ],
    "visibility": [
        "Review which notes the bot may show to players in the guided visibility editor.",
        "Preview broad metadata changes before confirming them.",
    ],
    "github": [
        "Authenticate GitHub CLI with repository and workflow access:",
        "  gh auth login",
        "  gh auth refresh -h github.com -s repo -s workflow",
        "Then continue through the guided GitHub step for repository, secrets, and variables.",
    ],
    "oracle": [
        "Check the Oracle VM over SSH from the guided Oracle step.",
        "If the deploy layout is missing, let the guided step offer bootstrap.",
    ],
    "deploy": [
        "After setup files and vault state are committed and pushed, continue through the guided deploy step.",
    ],
}


def emit_bot_setup_report(result: CommandResult, *, phase: str) -> None:
    data = result.data
    vault = str(data.get("vault") or ".")
    vault_arg = shlex.quote(vault)
    console.print("[bold green]Backet bot setup[/bold green]")
    console.print(result.message)
    _print_path_line("Vault", vault)
    _print_path_line("Setup state", _relative_to_vault(data.get("setup_state_path"), vault))
    _print_path_line("Runtime config", _relative_to_vault(data.get("runtime_config_path"), vault))
    console.print()

    _print_phase_progress(data, phase=phase)
    _print_repository_files(data)
    _print_phase_result(data, vault_arg=vault_arg)
    _print_bot_facts(data)
    _print_issue_list(result.issues)
    _print_next_steps(data, vault_arg=vault_arg)


def _print_path_line(label: str, value: Any) -> None:
    if value:
        console.print(f"{label}: {value}")


def _print_phase_progress(data: dict[str, Any], *, phase: str) -> None:
    phases = dict(data.get("phases", {}) or {})
    next_phase = data.get("next_phase")
    console.print("[bold]Progress[/bold]")
    for name in SETUP_PHASES:
        payload = dict(phases.get(name, {}) or {})
        status = str(payload.get("status") or "pending")
        marker = "next" if name == next_phase else status
        console.print(f"  {marker:12} {name:14} {PHASE_LABELS.get(name, name)}")
    if next_phase:
        console.print(f"Next phase: {next_phase}")
    else:
        console.print("Next phase: all phases complete")
    console.print()


def _print_repository_files(data: dict[str, Any]) -> None:
    files = dict(data.get("repository_files", {}) or {})
    if not files:
        return
    console.print("[bold]Deployment Files[/bold]")
    _print_path_line("Repository root", files.get("repo_root"))
    for label, key in (("Created", "created"), ("Updated", "updated"), ("Unchanged", "unchanged"), ("Skipped", "skipped")):
        values = list(files.get(key) or [])
        if values:
            console.print(f"{label}:")
            for value in values:
                console.print(f"  - {value}")
    console.print()


def _print_phase_result(data: dict[str, Any], *, vault_arg: str) -> None:
    result = dict(data.get("last_phase_result", {}) or {})
    if not result:
        return
    status = result.get("status")
    message = result.get("message")
    phase = result.get("phase")
    if message:
        console.print("[bold]Last Check[/bold]")
        console.print(f"{phase}: {message} ({status})")
    _print_messages("Warnings", result.get("warnings"))
    next_actions = [
        _humanize_setup_action(_format_vault_placeholder(str(action), vault_arg))
        for action in result.get("next_actions", []) or []
    ]
    _print_messages("Next Actions", next_actions)
    _print_discord_discovery(result)
    _print_visibility_summary(result)
    console.print()


def _print_discord_discovery(result: dict[str, Any]) -> None:
    if result.get("phase") != "discord":
        return
    data = dict(result.get("data", {}) or {})
    portal = data.get("developer_portal_url")
    invite_url = data.get("invite_url")
    if portal:
        console.print(f"Discord Developer Portal: {portal}")
    if invite_url:
        console.print(f"Private install URL: {invite_url}")
    _print_named_discord_objects("Visible servers", data.get("guilds"))
    _print_named_discord_objects("Roles visible to the bot", data.get("roles"))
    _print_named_discord_objects("Channels visible to the bot", data.get("channels"))


def _print_named_discord_objects(label: str, values: Any) -> None:
    if not values:
        return
    console.print(f"{label}:")
    for item in list(values)[:12]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "(unnamed)"
        object_id = item.get("id") or "(missing id)"
        console.print(f"  - {name} ({object_id})")


def _print_visibility_summary(result: dict[str, Any]) -> None:
    if result.get("phase") != "visibility":
        return
    summary = dict(dict(result.get("data", {}) or {}).get("summary", {}) or {})
    if not summary:
        return
    console.print("Visibility summary:")
    for key in (
        "player_index_notes",
        "storyteller_index_notes",
        "excluded_notes",
        "unclassified_notes",
        "invalid_topic_notes",
    ):
        if key in summary:
            console.print(f"  {key.replace('_', ' ')}: {summary[key]}")


def _print_bot_facts(data: dict[str, Any]) -> None:
    discord = dict(data.get("discord", {}) or {})
    github = dict(data.get("github", {}) or {})
    oracle = dict(data.get("oracle", {}) or {})
    if discord or github or oracle:
        console.print("[bold]Current Facts[/bold]")
    if discord:
        _print_path_line("Discord app", _named_id(discord.get("app_name"), discord.get("app_id")))
        _print_path_line("Discord server", _named_id(discord.get("guild_name"), discord.get("guild_id")))
    if github:
        _print_path_line("GitHub repository", github.get("repository"))
        _print_status_group("GitHub secrets", github.get("secrets"))
        _print_status_group("GitHub variables", github.get("variables"), only_missing=True)
    if oracle:
        _print_path_line("Oracle host", oracle.get("host"))
        _print_path_line("Oracle user", oracle.get("user"))
        _print_path_line("Oracle deploy path", oracle.get("deploy_path"))
    if discord or github or oracle:
        console.print()


def _print_status_group(label: str, values: Any, *, only_missing: bool = False) -> None:
    if not isinstance(values, dict) or not values:
        return
    selected = {key: value for key, value in values.items() if not only_missing or value == "missing"}
    if not selected:
        return
    console.print(f"{label}:")
    for key, value in sorted(selected.items()):
        console.print(f"  - {key}: {value}")


def _print_issue_list(issues: list[Issue]) -> None:
    if not issues:
        return
    console.print("[bold]Issues[/bold]")
    for issue in issues:
        console.print(f"  - {issue.message}")
        if issue.hint:
            console.print(f"    {issue.hint}")
    console.print()


def _print_next_steps(data: dict[str, Any], *, vault_arg: str) -> None:
    next_phase = data.get("resume_phase") or data.get("next_phase")
    actions = _collect_next_actions(data)
    guide = list(PHASE_GUIDES.get(str(next_phase), []))
    if not actions and not guide:
        return
    console.print("[bold]What To Do Next[/bold]")
    for action in actions:
        human_action = _humanize_setup_action(_format_vault_placeholder(str(action), vault_arg))
        console.print(f"  - {human_action}")
    for line in guide:
        console.print(_format_vault_placeholder(line, vault_arg))


def _collect_next_actions(data: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    result = dict(data.get("last_phase_result", {}) or {})
    actions.extend(str(item) for item in result.get("next_actions", []) if item)
    actions.extend(str(item) for item in data.get("next_actions", []) if item)
    files = dict(data.get("repository_files", {}) or {})
    actions.extend(str(item) for item in files.get("next_actions", []) if item)
    phase = data.get("next_phase")
    phases = dict(data.get("phases", {}) or {})
    phase_actions = dict(phases.get(phase, {}) or {}).get("next_actions", []) if phase else []
    actions.extend(str(item) for item in phase_actions if item)
    return _dedupe(actions)


def _print_messages(label: str, values: Any) -> None:
    messages = [str(item) for item in values or [] if item]
    if not messages:
        return
    console.print(f"{label}:")
    for message in messages:
        console.print(f"  - {message}")


def _named_id(name: Any, object_id: Any) -> str | None:
    if name and object_id:
        return f"{name} ({object_id})"
    if object_id:
        return str(object_id)
    return None


def _relative_to_vault(path_value: Any, vault: str) -> str | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    try:
        return path.relative_to(Path(vault)).as_posix()
    except ValueError:
        return path.as_posix()


def _format_vault_placeholder(value: str, vault_arg: str) -> str:
    return value.replace("<vault>", vault_arg).replace("{vault}", vault_arg)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _humanize_setup_action(value: str) -> str:
    if "backet bot setup files" in value:
        return "Install or refresh the local deployment files from the guided prerequisites step."
    if "backet bot setup discord" in value:
        return "Continue through the guided Discord step with the bot token, server, roles, and channels."
    if "backet bot setup visibility" in value:
        return "Continue through the guided visibility review."
    if "backet bot visibility set" in value:
        return "Open the guided visibility editor and mark safe player-facing notes, or explicitly allow empty player canon."
    if "backet bot setup github" in value:
        return "Continue through the guided GitHub step for repository, secrets, and variables."
    if "backet bot setup oracle" in value:
        return "Continue through the guided Oracle VM step."
    if "backet bot setup deploy" in value:
        return "Continue through the guided deploy step when setup files and vault state are pushed."
    if value.startswith("Run `backet bot setup"):
        return "Reopen the guided bot setup to continue from the next pending phase."
    return value
