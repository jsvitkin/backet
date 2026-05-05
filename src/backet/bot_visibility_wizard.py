from __future__ import annotations

from pathlib import Path

import click

from backet.bot_access import (
    TOPIC_CANON,
    TOPICS,
    VISIBILITIES,
    VISIBILITY_EXCLUDED,
    audit_bot_visibility,
    clear_bot_visibility,
    list_bot_visibility,
    set_bot_visibility,
)
from backet.bot_output import (
    emit_bot_visibility_audit_report,
    emit_bot_visibility_list_report,
    emit_bot_visibility_update_report,
)
from backet.models import CommandResult


def run_guided_visibility_wizard(vault_root: Path) -> CommandResult:
    click.echo("Bot visibility wizard")
    click.echo("Unmarked notes stay Storyteller-only. This wizard helps you mark the explicit exceptions.")
    click.echo()
    result = audit_bot_visibility(vault_root)
    emit_bot_visibility_audit_report(result)

    while True:
        click.echo()
        choice = click.prompt(
            "Action [p=mark player, s=mark Storyteller, e=exclude, l=list unclassified, c=clear, q=quit]",
            default="q",
            show_default=False,
        )
        normalized = _visibility_action(str(choice))
        if normalized is None:
            click.echo("Choose p, s, e, l, c, or q.")
            continue
        if normalized == "quit":
            return audit_bot_visibility(vault_root)
        if normalized == "list":
            listed = list_bot_visibility(vault_root, unclassified=True)
            emit_bot_visibility_list_report(listed)
            continue
        if normalized == "clear":
            _guided_clear(vault_root)
            continue
        _guided_set(vault_root, normalized)


def run_guided_visibility_set(
    vault_root: Path,
    *,
    target: str,
    visibility: str,
    topics: list[str],
    recursive: bool,
    dry_run: bool,
    yes: bool,
) -> CommandResult:
    resolved_target = target.strip() or _prompt_target("Target note or folder")
    resolved_visibility = visibility.strip() or _prompt_visibility()
    resolved_topics = list(topics)
    if resolved_visibility != VISIBILITY_EXCLUDED and not resolved_topics:
        resolved_topics = _prompt_topics(default=[TOPIC_CANON])
    resolved_recursive = recursive or _should_update_recursively(vault_root, resolved_target)

    preview = set_bot_visibility(
        vault_root,
        target=resolved_target,
        visibility=resolved_visibility,
        topics=resolved_topics,
        recursive=resolved_recursive,
        dry_run=True,
        yes=True,
    )
    emit_bot_visibility_update_report(preview)
    if dry_run or not yes:
        if dry_run:
            return preview
        if not click.confirm("Apply this visibility update?", default=False):
            return preview
    result = set_bot_visibility(
        vault_root,
        target=resolved_target,
        visibility=resolved_visibility,
        topics=resolved_topics,
        recursive=resolved_recursive,
        dry_run=False,
        yes=True,
    )
    emit_bot_visibility_update_report(result)
    return result


def run_guided_visibility_clear(
    vault_root: Path,
    *,
    target: str,
    recursive: bool,
    dry_run: bool,
    yes: bool,
) -> CommandResult:
    resolved_target = target.strip() or _prompt_target("Target note or folder to clear")
    resolved_recursive = recursive or _should_update_recursively(vault_root, resolved_target)
    preview = clear_bot_visibility(
        vault_root,
        target=resolved_target,
        recursive=resolved_recursive,
        dry_run=True,
        yes=True,
    )
    emit_bot_visibility_update_report(preview)
    if dry_run or not yes:
        if dry_run:
            return preview
        if not click.confirm("Apply this clear operation?", default=False):
            return preview
    result = clear_bot_visibility(
        vault_root,
        target=resolved_target,
        recursive=resolved_recursive,
        dry_run=False,
        yes=True,
    )
    emit_bot_visibility_update_report(result)
    return result


def _guided_set(vault_root: Path, visibility: str) -> CommandResult:
    target = _prompt_target("Target note or folder")
    topics = [] if visibility == VISIBILITY_EXCLUDED else _prompt_topics(default=[TOPIC_CANON])
    recursive = _should_update_recursively(vault_root, target)
    return run_guided_visibility_set(
        vault_root,
        target=target,
        visibility=visibility,
        topics=topics,
        recursive=recursive,
        dry_run=False,
        yes=False,
    )


def _guided_clear(vault_root: Path) -> CommandResult:
    target = _prompt_target("Target note or folder to clear")
    recursive = _should_update_recursively(vault_root, target)
    return run_guided_visibility_clear(
        vault_root,
        target=target,
        recursive=recursive,
        dry_run=False,
        yes=False,
    )


def _visibility_action(value: str) -> str | None:
    normalized = value.strip().lower()
    aliases = {
        "p": "player",
        "player": "player",
        "s": "storyteller",
        "st": "storyteller",
        "storyteller": "storyteller",
        "e": "excluded",
        "exclude": "excluded",
        "excluded": "excluded",
        "l": "list",
        "list": "list",
        "u": "list",
        "unclassified": "list",
        "c": "clear",
        "clear": "clear",
        "q": "quit",
        "quit": "quit",
        "done": "quit",
    }
    return aliases.get(normalized)


def _prompt_target(label: str) -> str:
    while True:
        target = str(click.prompt(label, default="", show_default=False)).strip()
        if target:
            return target
        click.echo("Enter a vault-relative note or folder path.")


def _prompt_visibility() -> str:
    choices = ", ".join(sorted(VISIBILITIES))
    while True:
        value = str(click.prompt(f"Visibility ({choices})", default="player")).strip().lower()
        if value in VISIBILITIES:
            return value
        click.echo(f"Use one of: {choices}.")


def _prompt_topics(*, default: list[str]) -> list[str]:
    default_text = ",".join(default)
    choices = ", ".join(sorted(TOPICS))
    while True:
        value = str(click.prompt(f"Topics ({choices})", default=default_text)).strip()
        topics = [item.strip().lower() for item in value.split(",") if item.strip()]
        invalid = [topic for topic in topics if topic not in TOPICS]
        if not invalid:
            return topics
        click.echo(f"Unsupported topic(s): {', '.join(invalid)}. Use: {choices}.")


def _should_update_recursively(vault_root: Path, target: str) -> bool:
    path = (vault_root / target).resolve()
    try:
        path.relative_to(vault_root.resolve())
    except ValueError:
        return False
    if path.is_dir():
        return click.confirm("Apply recursively to Markdown notes in this folder?", default=True)
    return False
