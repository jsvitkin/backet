from __future__ import annotations

import textwrap
from typing import Any

from backet.bot_answers import format_bot_source_label
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
    _print_next("Open the guided bot setup when you are ready to configure Discord, GitHub, and Oracle deployment.")


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
    _print_next("Use the bundle doctor before deploying or testing answers.")


def emit_bot_bundle_doctor_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Bot bundle doctor[/bold green]")
    _line("Bundle", data.get("bundle_root"))
    _line("Manifest", data.get("manifest_path"))
    _line("Schema", data.get("schema_version"))
    _line("Status", "ok" if data.get("ok") else "needs attention")
    _print_issues(result.issues)
    if data.get("ok"):
        _print_next("Inspect the bundle or try a dry-run bot question when you are ready to test it.")
    else:
        _print_next("Fix the issues above, then re-export the bundle.")


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
    _print_next("Try a dry-run Discord question to verify access and answer behavior.")


def emit_bot_answer_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Bot answer dry run[/bold green]")
    _line("Command", data.get("command"))
    _line("Access tier", data.get("access_tier"))
    _line("Response visibility", "private" if data.get("response_private") else "public")
    _line("Denied", _yes_no(data.get("denied")))
    generation = dict(dict(data.get("diagnostics", {}) or {}).get("answer_generation", {}) or {})
    if generation:
        _line("Answer mode", generation.get("mode"))
        _line("Fallback used", _yes_no(generation.get("fallback_used")))
        if generation.get("diagnostics", {}).get("fallback_reason"):
            _line("Fallback reason", generation["diagnostics"]["fallback_reason"])
    console.print()
    console.print("[bold]Answer[/bold]")
    console.print(str(data.get("text") or ""), markup=False, soft_wrap=True)
    sources = list(data.get("sources") or [])
    if sources:
        console.print()
        console.print("[bold]Sources[/bold]")
        for source in sources[:8]:
            if isinstance(source, dict):
                console.print(f"  - {source.get('citation')}: {format_bot_source_label(source)}")


def emit_bot_playground_report(result: CommandResult) -> None:
    data = result.data
    console.print("[bold green]Bot playground[/bold green]")
    _line("Vault", data.get("vault"))
    _line("Bundle", data.get("bundle"))
    _line("Command", data.get("command"))
    _line("Mode", data.get("mode"))
    _line("Source limit", data.get("limit"))
    _print_visibility_summary(dict(data.get("export_summary", {}) or {}))
    _print_issues(result.issues)
    runs = list(data.get("runs") or [])
    for index, run in enumerate(runs, start=1):
        if not isinstance(run, dict):
            continue
        answer = dict(run.get("answer", {}) or {})
        generation = dict(dict(answer.get("diagnostics", {}) or {}).get("answer_generation", {}) or {})
        generation_diag = dict(generation.get("diagnostics", {}) or {})
        console.print()
        console.print(f"[bold]Run {index}[/bold]")
        _line("Question", run.get("question"))
        _line("Elapsed", f"{run.get('elapsed_seconds')}s")
        _line("Access tier", answer.get("access_tier"))
        _line("Response visibility", "private" if answer.get("response_private") else "public")
        _line("Denied", _yes_no(answer.get("denied")))
        if generation:
            _line("Answer mode", generation.get("mode"))
            _line("Fallback used", _yes_no(generation.get("fallback_used")))
            if generation_diag.get("fallback_reason"):
                _line("Fallback reason", generation_diag.get("fallback_reason"))
        console.print()
        console.print("[bold]Answer[/bold]")
        console.print(str(answer.get("text") or ""), markup=False, soft_wrap=True)
        debug_sources = list(run.get("source_debug") or [])
        if debug_sources:
            console.print()
            console.print("[bold]Retrieved Sources[/bold]")
            for source in debug_sources[:10]:
                if isinstance(source, dict):
                    _print_source_debug(source)
        else:
            console.print()
            console.print("[bold]Retrieved Sources[/bold]")
            console.print("  None")


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
        console.print(f"  - {decision.get('relative_path')} ({decision.get('visibility')}; {topics}; {marker})")
    if len(decisions) > 40:
        console.print(f"  ... {len(decisions) - 40} more")
    _print_next("Open the guided visibility editor to change these entries.")


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
        _print_next("Review the preview above. In guided mode, confirm the prompt to apply it.")
    else:
        _print_next("Review visibility again when you are ready to check the updated policy.")


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
        actions.append("Open the guided visibility editor to classify unmarked notes by folder or note.")
    if summary.get("player_index_notes", 0) == 0:
        actions.append("Mark at least one safe canon note as player-visible before expecting player canon answers.")
    if summary.get("missing_topic_notes", 0):
        actions.append("Add explicit bot topics to notes that should be queryable.")
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


def _print_source_debug(source: dict[str, Any]) -> None:
    citation = source.get("citation")
    kind = source.get("source_type")
    title = source.get("title") or "untitled"
    score = source.get("score")
    reasons = ", ".join(str(reason) for reason in source.get("match_reasons", []) or []) or "none"
    location = ""
    if kind == "vault" and source.get("relative_path"):
        location = f" ({source.get('relative_path')})"
    if kind == "rules" and source.get("page_start"):
        page = source.get("page_start")
        if source.get("page_end") and source.get("page_end") != source.get("page_start"):
            page = f"{source.get('page_start')}-{source.get('page_end')}"
        location = f" p. {page}"
    score_text = f"{float(score):.3f}" if isinstance(score, int | float) else str(score or "n/a")
    console.print(f"  - {citation}: {title}{location}")
    console.print(f"    score: {score_text}; matches: {reasons}")
    excerpt = " ".join(str(source.get("excerpt") or "").split())
    if excerpt:
        wrapped = textwrap.wrap(excerpt, width=72, break_long_words=False, break_on_hyphens=False)
        for line in wrapped[:3]:
            console.print(f"    {line}", markup=False)
        if len(wrapped) > 3:
            console.print("    ...")
