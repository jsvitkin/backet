from __future__ import annotations

from typing import Any

from backet.models import CommandResult, Issue
from backet.output import console


def emit_bot_policy_report(result: CommandResult) -> None:
    data = result.data
    config = dict(data.get("config", {}) or {})
    summary = dict(data.get("visibility_summary", {}) or {})
    console.print("[bold green]Bot policy[/bold green]")
    _line("Vault", data.get("vault"))
    _line("Config", config.get("source_path"))
    _line("Config exists", _yes_no(config.get("exists")))
    _line("Guild", config.get("guild_id") or "not configured")
    _line("Answer mode", config.get("answer_mode"))
    _print_roles(config)
    _print_command_policies(config)
    _print_visibility_summary(summary)
    _print_next("Use `backet bot setup` to configure Discord/GitHub/Oracle deployment.")


def emit_bot_export_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Exported private bot bundle[/bold green]")
    _line("Vault", data.get("vault"))
    _line("Output", data.get("output_path"))
    _line("Manifest", data.get("manifest_path"))
    _print_visibility_summary(dict(data.get("summary", {}) or {}))
    rules = dict(data.get("rules", {}) or {})
    _line("Rules database", "included" if rules.get("included") else "not included")
    _print_created(result.created)
    _print_issues(result.issues)
    _print_next("Run `backet bot doctor <bundle>` before deploying or testing answers.")


def emit_bot_bundle_doctor_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Bot bundle doctor[/bold green]")
    _line("Bundle", data.get("bundle_root"))
    _line("Manifest", data.get("manifest_path"))
    _line("Schema", data.get("schema_version"))
    _line("Status", "ok" if data.get("ok") else "needs attention")
    _print_issues(result.issues)
    if data.get("ok"):
        _print_next("Run `backet bot inspect <bundle>` or `backet bot ask <bundle>` to test it.")
    else:
        _print_next("Re-export the bundle with `backet bot export <vault> --force` after fixing issues.")


def emit_bot_bundle_inspect_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Bot bundle[/bold green]")
    _line("Bundle", data.get("bundle_root"))
    _line("Schema", data.get("schema_version"))
    _line("Guild", data.get("guild_id") or "not configured")
    _line("Answer mode", data.get("answer_mode"))
    indexes = dict(data.get("indexes", {}) or {})
    if indexes:
        console.print("Indexes:")
        for name, meta in sorted(indexes.items()):
            if not isinstance(meta, dict):
                continue
            console.print(f"  - {name}: {meta.get('note_count', 0)} notes, {meta.get('chunk_count', 0)} chunks")
    rules = dict(data.get("rules", {}) or {})
    _line("Rules database", "included" if rules.get("included") else "not included")
    _print_next("Run `backet bot ask <bundle>` to test a simulated Discord question.")


def emit_bot_answer_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Bot answer dry run[/bold green]")
    _line("Command", data.get("command"))
    _line("Access tier", data.get("access_tier"))
    _line("Response visibility", "private" if data.get("response_private") else "public")
    _line("Denied", _yes_no(data.get("denied")))
    console.print()
    console.print("[bold]Answer[/bold]")
    console.print(str(data.get("text") or ""))
    sources = list(data.get("sources") or [])
    if sources:
        console.print()
        console.print("[bold]Sources[/bold]")
        for source in sources[:8]:
            if isinstance(source, dict):
                console.print(f"  - {source.get('citation')}: {_source_label(source)}")


def emit_bot_model_check_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Bot model check[/bold green]")
    if not data.get("required"):
        _line("Required", "no")
        _line("Answer mode", data.get("answer_mode"))
        _print_next("Template mode does not need local model files.")
        return
    _line("Required", "yes")
    _line("Model", data.get("model_path"))
    _line("Expected SHA256", data.get("expected_sha256") or "not configured")
    _line("Actual SHA256", data.get("actual_sha256") or "not available")
    _line("Status", "ok" if data.get("ok") else "needs attention")
    _print_issues(result.issues)


def emit_bot_visibility_audit_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Bot visibility audit[/bold green]")
    _line("Vault", data.get("vault"))
    _print_visibility_summary(dict(data.get("summary", {}) or {}))
    _print_visibility_guidance(dict(data.get("summary", {}) or {}))


def emit_bot_visibility_list_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Bot visibility list[/bold green]")
    _line("Vault", data.get("vault"))
    filters = dict(data.get("filters", {}) or {})
    active_filters = ", ".join(f"{key}={value}" for key, value in sorted(filters.items()) if value not in (None, False))
    _line("Filters", active_filters or "none")
    _line("Matches", data.get("count"))
    decisions = list(data.get("decisions") or [])
    for decision in decisions[:40]:
        if not isinstance(decision, dict):
            continue
        topics = ", ".join(decision.get("topics") or []) or "none"
        marker = "default" if decision.get("metadata_source") == "default" else "explicit"
        console.print(f"  - {decision.get('relative_path')} [{decision.get('visibility')}; {topics}; {marker}]")
    if len(decisions) > 40:
        console.print(f"  ... {len(decisions) - 40} more")
    _print_next("Run `backet bot visibility` for the guided visibility editor.")


def emit_bot_visibility_update_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]" + result.message + "[/bold green]")
    _line("Vault", data.get("vault"))
    _line("Target", data.get("target"))
    if data.get("visibility"):
        _line("Visibility", data.get("visibility"))
    topics = data.get("topics")
    if topics is not None:
        _line("Topics", ", ".join(topics) if topics else "none")
    _line("Recursive", _yes_no(data.get("recursive")))
    _line("Dry run", _yes_no(data.get("dry_run")))
    _line("Changed notes", data.get("changed_count"))
    updates = list(data.get("updates") or [])
    if updates:
        console.print("Updates:")
        for update in updates[:40]:
            if not isinstance(update, dict):
                continue
            changed = "changed" if update.get("changed") else "unchanged"
            console.print(f"  - {update.get('relative_path')}: {update.get('action')} ({changed})")
        if len(updates) > 40:
            console.print(f"  ... {len(updates) - 40} more")
    if data.get("dry_run"):
        _print_next("If the preview is right, rerun without `--dry-run`; recursive writes also need `--yes`.")
    else:
        _print_next("Run `backet bot visibility audit <vault>` to review the updated policy.")


def _print_roles(config: dict[str, Any]) -> None:
    roles = dict(config.get("roles", {}) or {})
    users = dict(config.get("users", {}) or {})
    if not roles and not users:
        return
    console.print("Access bindings:")
    for tier in ("player", "storyteller"):
        role_count = len(roles.get(tier, []) or [])
        user_count = len(users.get(tier, []) or [])
        console.print(f"  - {tier}: {role_count} role(s), {user_count} user override(s)")


def _print_command_policies(config: dict[str, Any]) -> None:
    commands = dict(config.get("commands", {}) or {})
    if not commands:
        return
    console.print("Commands:")
    for name, policy in sorted(commands.items()):
        if not isinstance(policy, dict):
            continue
        topics = ", ".join(policy.get("topics") or []) or "none"
        channel_count = len(policy.get("channel_ids") or [])
        public = "public allowed" if policy.get("public_allowed") else "private default"
        console.print(f"  - {name}: {policy.get('min_tier')} tier, topics {topics}, {channel_count} channel(s), {public}")


def _print_visibility_summary(summary: dict[str, Any]) -> None:
    if not summary:
        return
    console.print("Visibility:")
    for label, key in (
        ("total notes", "total_notes"),
        ("player-visible", "player_index_notes"),
        ("Storyteller-visible", "storyteller_index_notes"),
        ("excluded", "excluded_notes"),
        ("unclassified/default Storyteller", "unclassified_notes"),
        ("missing topics", "missing_topic_notes"),
    ):
        if key in summary:
            console.print(f"  - {label}: {summary[key]}")


def _print_visibility_guidance(summary: dict[str, Any]) -> None:
    actions: list[str] = []
    if summary.get("unclassified_notes", 0):
        actions.append("Run `backet bot visibility` to classify unmarked notes by folder or note.")
    if summary.get("player_index_notes", 0) == 0:
        actions.append("Mark player-facing canon with `backet bot visibility set ... --visibility player --topic canon`.")
    if summary.get("missing_topic_notes", 0):
        actions.append("Add bot topics to notes that should be queryable.")
    if not actions:
        actions.append("Policy looks classified. Re-run setup or export when ready.")
    console.print("Next:")
    for action in actions:
        console.print(f"  - {action}")


def _print_created(created: list[str]) -> None:
    if not created:
        return
    console.print("Created:")
    for value in created:
        console.print(f"  - {value}")


def _print_issues(issues: list[Issue]) -> None:
    if not issues:
        return
    console.print("Issues:")
    for issue in issues:
        path = f" ({issue.path})" if issue.path else ""
        console.print(f"  - [{issue.severity}] {issue.message}{path}")
        if issue.hint:
            console.print(f"    {issue.hint}")


def _print_next(message: str) -> None:
    console.print("Next:")
    console.print(f"  - {message}")


def _line(label: str, value: Any) -> None:
    if value is None:
        return
    console.print(f"{label}: {value}")


def _yes_no(value: Any) -> str:
    return "yes" if bool(value) else "no"


def _source_label(source: dict[str, Any]) -> str:
    if source.get("source_type") == "vault":
        return f"{source.get('title')} ({source.get('relative_path')})"
    if source.get("source_type") == "rules":
        page = source.get("page_start")
        if source.get("page_end") and source.get("page_end") != source.get("page_start"):
            page = f"{source.get('page_start')}-{source.get('page_end')}"
        return f"{source.get('book_title')} p. {page} ({source.get('section_label')})"
    return str(source)
