from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    emit_bot_visibility_list_report,
    emit_bot_visibility_update_report,
)
from backet.models import CommandResult


@dataclass(slots=True)
class _TargetCandidate:
    label: str
    target: str


def run_guided_visibility_wizard(vault_root: Path) -> CommandResult:
    click.echo("Bot visibility wizard")
    click.echo("Unmarked notes stay Storyteller-only. This wizard helps you mark the explicit exceptions.")
    click.echo()

    while True:
        result = audit_bot_visibility(vault_root)
        _emit_wizard_audit(result)
        click.echo()
        normalized = _prompt_menu(
            "What would you like to do?",
            [
                ("Mark player-facing notes as player-visible", "player"),
                ("Mark hidden notes as Storyteller-only", "storyteller"),
                ("Exclude notes from bot export", "excluded"),
                ("Review unclassified notes", "list"),
                ("Clear bot visibility metadata", "clear"),
                ("Refresh the audit", "refresh"),
                ("Finish", "quit"),
            ],
            default="list" if _summary_value(result, "unclassified_notes") else "quit",
        )
        if normalized == "quit":
            return audit_bot_visibility(vault_root)
        if normalized == "refresh":
            continue
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
    resolved_target = target.strip() or (
        _prompt_target(
            vault_root,
            "Choose the note or folder to update.",
            candidates=_target_candidates(vault_root, unclassified_only=True),
        )
        or ""
    )
    if not resolved_target:
        click.echo("No visibility changes selected.")
        return audit_bot_visibility(vault_root)
    resolved_visibility = visibility.strip() or _prompt_visibility()
    resolved_topics = list(topics)
    if resolved_visibility != VISIBILITY_EXCLUDED and not resolved_topics:
        resolved_topics = _prompt_topics(default=[TOPIC_CANON])
    resolved_recursive = recursive or _should_update_recursively(vault_root, resolved_target)
    if _target_is_directory(vault_root, resolved_target) and not resolved_recursive:
        click.echo("No folder changes selected.")
        return audit_bot_visibility(vault_root)

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
    resolved_target = target.strip() or (
        _prompt_target(
            vault_root,
            "Choose the note or folder whose bot metadata should be cleared.",
            candidates=_target_candidates(vault_root, explicit_only=True),
        )
        or ""
    )
    if not resolved_target:
        click.echo("No metadata clear selected.")
        return audit_bot_visibility(vault_root)
    resolved_recursive = recursive or _should_update_recursively(vault_root, resolved_target)
    if _target_is_directory(vault_root, resolved_target) and not resolved_recursive:
        click.echo("No folder changes selected.")
        return audit_bot_visibility(vault_root)
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
    target = _prompt_target(
        vault_root,
        "Choose the note or folder to update.",
        candidates=_target_candidates(vault_root, unclassified_only=True),
    )
    if not target:
        return audit_bot_visibility(vault_root)
    topics = [] if visibility == VISIBILITY_EXCLUDED else _prompt_topics(default=[TOPIC_CANON])
    recursive = _should_update_recursively(vault_root, target)
    if _target_is_directory(vault_root, target) and not recursive:
        click.echo("No folder changes selected.")
        return audit_bot_visibility(vault_root)
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
    target = _prompt_target(
        vault_root,
        "Choose the note or folder whose bot metadata should be cleared.",
        candidates=_target_candidates(vault_root, explicit_only=True),
    )
    if not target:
        return audit_bot_visibility(vault_root)
    recursive = _should_update_recursively(vault_root, target)
    if _target_is_directory(vault_root, target) and not recursive:
        click.echo("No folder changes selected.")
        return audit_bot_visibility(vault_root)
    return run_guided_visibility_clear(
        vault_root,
        target=target,
        recursive=recursive,
        dry_run=False,
        yes=False,
    )


def _emit_wizard_audit(result: CommandResult) -> None:
    data = result.data
    summary = dict(data.get("summary", {}) or {})
    click.echo("Current visibility")
    click.echo(f"  Vault: {data.get('vault')}")
    click.echo(f"  Total notes scanned: {summary.get('total_notes', 0)}")
    click.echo(f"  Player-visible notes: {summary.get('player_index_notes', 0)}")
    click.echo(f"  Storyteller-visible notes: {summary.get('storyteller_index_notes', 0)}")
    click.echo(f"  Excluded notes: {summary.get('excluded_notes', 0)}")
    click.echo(f"  Still unclassified: {summary.get('unclassified_notes', 0)}")
    click.echo(f"  Missing explicit topics: {summary.get('missing_topic_notes', 0)}")
    if summary.get("player_index_notes", 0) == 0:
        click.echo("  Player canon is empty until you explicitly mark safe notes as player-visible.")
    if summary.get("unclassified_notes", 0):
        click.echo("  Unclassified notes currently stay Storyteller-only by default.")


def _summary_value(result: CommandResult, key: str) -> int:
    summary = dict(result.data.get("summary", {}) or {})
    return int(summary.get(key, 0) or 0)


def _prompt_menu(title: str, options: list[tuple[str, str]], *, default: str) -> str:
    option_by_value = {value: label for label, value in options}
    default_index = next((index for index, (_, value) in enumerate(options, start=1) if value == default), 1)
    click.echo(title)
    for index, (label, _) in enumerate(options, start=1):
        click.echo(f"  {index}. {label}")
    while True:
        raw_value = str(click.prompt("Choose an option", default=str(default_index), show_default=False)).strip().lower()
        if raw_value.isdigit() and 1 <= int(raw_value) <= len(options):
            return options[int(raw_value) - 1][1]
        if raw_value in option_by_value:
            return raw_value
        for label, value in options:
            if raw_value == label.lower():
                return value
        click.echo("Choose one of the numbered options.")


def _prompt_target(vault_root: Path, label: str, *, candidates: list[_TargetCandidate]) -> str | None:
    click.echo(label)
    if candidates:
        click.echo("Suggested targets from this vault:")
        for index, candidate in enumerate(candidates[:25], start=1):
            click.echo(f"  {index}. {candidate.label}")
        if len(candidates) > 25:
            click.echo(f"  ... {len(candidates) - 25} more")
        click.echo("You can also type a vault-relative note or folder path.")
    else:
        click.echo("No obvious targets were found, but you can type a vault-relative note or folder path.")
    while True:
        target = str(click.prompt("Target", default="", show_default=False)).strip()
        if not target:
            return None
        if target.isdigit() and candidates and 1 <= int(target) <= min(len(candidates), 25):
            return candidates[int(target) - 1].target
        candidate_path = (vault_root / target).resolve()
        try:
            candidate_path.relative_to(vault_root.resolve())
        except ValueError:
            click.echo("Choose a path inside the vault.")
            continue
        return target


def _prompt_visibility() -> str:
    choices = ", ".join(sorted(VISIBILITIES))
    while True:
        value = str(click.prompt(f"Visibility ({choices})", default="player")).strip().lower()
        if value in VISIBILITIES:
            return value
        click.echo(f"Use one of: {choices}.")


def _prompt_topics(*, default: list[str]) -> list[str]:
    ordered_topics = [TOPIC_CANON, "npc", "plotline", "statblock", "rules-summary"]
    default_text = ",".join(default)
    click.echo("Topics decide which bot questions can use these notes.")
    for index, topic in enumerate(ordered_topics, start=1):
        click.echo(f"  {index}. {topic}")
    while True:
        value = str(click.prompt("Topics, comma-separated by number or name", default=default_text)).strip()
        topics = []
        invalid: list[str] = []
        for item in [part.strip().lower() for part in value.split(",") if part.strip()]:
            if item.isdigit() and 1 <= int(item) <= len(ordered_topics):
                topic = ordered_topics[int(item) - 1]
            else:
                topic = item
            if topic not in TOPICS:
                invalid.append(item)
                continue
            if topic not in topics:
                topics.append(topic)
        if not invalid:
            return topics
        click.echo("Choose topic numbers from the list, or type the listed topic names.")


def _should_update_recursively(vault_root: Path, target: str) -> bool:
    path = (vault_root / target).resolve()
    try:
        path.relative_to(vault_root.resolve())
    except ValueError:
        return False
    if path.is_dir():
        note_count = len(list(path.rglob("*.md")))
        return click.confirm(
            f"`{target}` is a folder with {note_count} Markdown note(s). Update the whole folder?",
            default=True,
        )
    return False


def _target_is_directory(vault_root: Path, target: str) -> bool:
    path = (vault_root / target).resolve()
    try:
        path.relative_to(vault_root.resolve())
    except ValueError:
        return False
    return path.is_dir()


def _target_candidates(
    vault_root: Path,
    *,
    unclassified_only: bool = False,
    explicit_only: bool = False,
) -> list[_TargetCandidate]:
    result = audit_bot_visibility(vault_root)
    decisions = [item for item in list(result.data.get("decisions") or []) if isinstance(item, dict)]
    selected: list[dict[str, Any]] = []
    for decision in decisions:
        metadata_source = str(decision.get("metadata_source") or "")
        if unclassified_only and metadata_source != "default":
            continue
        if explicit_only and metadata_source == "default":
            continue
        selected.append(decision)

    folder_counts: dict[str, int] = {}
    for decision in selected:
        parent = Path(str(decision.get("relative_path") or "")).parent.as_posix()
        if parent and parent != ".":
            folder_counts[parent] = folder_counts.get(parent, 0) + 1

    candidates: list[_TargetCandidate] = []
    for folder, count in sorted(folder_counts.items(), key=lambda item: (-item[1], item[0])):
        if count > 1:
            candidates.append(_TargetCandidate(label=f"{folder}/ folder ({count} notes)", target=folder))
    for decision in selected:
        relative_path = str(decision.get("relative_path") or "")
        if not relative_path:
            continue
        visibility = str(decision.get("visibility") or "storyteller")
        topics = ", ".join(list(decision.get("topics") or [])) or "no explicit topics"
        source = "unclassified" if decision.get("metadata_source") == "default" else "explicit"
        candidates.append(_TargetCandidate(label=f"{relative_path} ({visibility}, {topics}, {source})", target=relative_path))
    return candidates
