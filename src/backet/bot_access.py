from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backet.bot_profiles import (
    FALLBACK_TEMPLATE,
    RUNTIME_PROFILE_LITE,
    parse_runtime_profile_config,
)
from backet.errors import AppError
from backet.index_ignore import load_index_ignore_policy, normalize_relative_path
from backet.indexing import fingerprint_text
from backet.models import CommandResult
from backet.paths import bot_config_path
from backet.vault import ensure_bootstrapped_vault

FRONTMATTER_DELIMITER = "---"

VISIBILITY_PLAYER = "player"
VISIBILITY_STORYTELLER = "storyteller"
VISIBILITY_EXCLUDED = "excluded"
VISIBILITIES = {VISIBILITY_PLAYER, VISIBILITY_STORYTELLER, VISIBILITY_EXCLUDED}

ACCESS_TIER_PLAYER = "player"
ACCESS_TIER_STORYTELLER = "storyteller"
ACCESS_TIERS = {ACCESS_TIER_PLAYER, ACCESS_TIER_STORYTELLER}

TOPIC_CANON = "canon"
TOPIC_RULES_SUMMARY = "rules-summary"
TOPIC_NPC = "npc"
TOPIC_PLOTLINE = "plotline"
TOPIC_STATBLOCK = "statblock"
TOPICS = {TOPIC_CANON, TOPIC_RULES_SUMMARY, TOPIC_NPC, TOPIC_PLOTLINE, TOPIC_STATBLOCK}

DEFAULT_TOPIC = TOPIC_CANON
SECRET_KEY_MARKERS = ("secret", "password", "api_key", "apikey", "private_key")


@dataclass(slots=True)
class BotCommandPolicy:
    min_tier: str = ACCESS_TIER_PLAYER
    topics: list[str] = field(default_factory=list)
    channel_ids: list[str] = field(default_factory=list)
    public_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_tier": self.min_tier,
            "topics": self.topics,
            "channel_ids": self.channel_ids,
            "public_allowed": self.public_allowed,
        }


@dataclass(slots=True)
class BotConfig:
    schema_version: int = 1
    guild_id: str | None = None
    roles: dict[str, list[str]] = field(default_factory=dict)
    users: dict[str, list[str]] = field(default_factory=dict)
    commands: dict[str, BotCommandPolicy] = field(default_factory=dict)
    response_defaults: dict[str, bool] = field(default_factory=dict)
    answer_mode: str = "template"
    model: dict[str, Any] = field(default_factory=dict)
    runtime_profile: str = RUNTIME_PROFILE_LITE
    fallback_policy: str = FALLBACK_TEMPLATE
    model_services: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None
    exists: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "guild_id": self.guild_id,
            "roles": self.roles,
            "users": self.users,
            "commands": {key: value.to_dict() for key, value in self.commands.items()},
            "response_defaults": self.response_defaults,
            "answer_mode": self.answer_mode,
            "model": self.model,
            "runtime_profile": self.runtime_profile,
            "fallback_policy": self.fallback_policy,
            "model_services": self.model_services,
            "source_path": self.source_path,
            "exists": self.exists,
        }


@dataclass(slots=True)
class FrontmatterDocument:
    frontmatter: dict[str, Any]
    body: str
    had_frontmatter: bool


@dataclass(slots=True)
class BotVisibilityDecision:
    relative_path: str
    visibility: str
    topics: list[str]
    metadata_source: str
    included_in_player: bool
    included_in_storyteller: bool
    exclusion_reason: str | None
    missing_topics: bool
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "visibility": self.visibility,
            "topics": self.topics,
            "metadata_source": self.metadata_source,
            "included_in_player": self.included_in_player,
            "included_in_storyteller": self.included_in_storyteller,
            "exclusion_reason": self.exclusion_reason,
            "missing_topics": self.missing_topics,
            "content_hash": self.content_hash,
        }


@dataclass(slots=True)
class VisibilityUpdate:
    relative_path: str
    action: str
    changed: bool
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "action": self.action,
            "changed": self.changed,
            "skipped_reason": self.skipped_reason,
        }


def load_bot_config(vault_root: Path) -> BotConfig:
    ensure_bootstrapped_vault(vault_root)
    path = bot_config_path(vault_root)
    config = _default_bot_config()
    config.source_path = str(path)
    config.exists = path.exists()
    if not path.exists():
        return config

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise AppError(
            code="bot_config_invalid",
            message="Bot configuration must be a YAML mapping.",
            hint=f"Fix {path.relative_to(vault_root)}.",
            details={"path": str(path)},
            exit_code=2,
        )
    _reject_secret_like_keys(payload, path)

    schema_version = int(payload.get("schema_version", 1))
    if schema_version != 1:
        raise AppError(
            code="bot_config_schema_unsupported",
            message="Unsupported bot configuration schema version.",
            hint="Use schema_version: 1.",
            details={"schema_version": schema_version, "path": str(path)},
            exit_code=2,
        )

    config.schema_version = schema_version
    guild_id = payload.get("guild_id")
    config.guild_id = str(guild_id) if guild_id not in (None, "") else None
    config.roles = _string_list_map(payload.get("roles", {}), field_name="roles", path=path)
    config.users = _string_list_map(payload.get("users", {}), field_name="users", path=path)
    config.commands = _parse_command_policies(payload.get("commands", {}), path=path)
    config.response_defaults = _bool_map(payload.get("response_defaults", {}), field_name="response_defaults", path=path)
    answer_mode = str(payload.get("answer_mode", config.answer_mode)).strip() or "template"
    if answer_mode not in {"template", "llama-local"}:
        raise AppError(
            code="bot_config_answer_mode_invalid",
            message="Bot answer mode is invalid.",
            hint="Use answer_mode: template or answer_mode: llama-local.",
            details={"answer_mode": answer_mode, "path": str(path)},
            exit_code=2,
        )
    config.answer_mode = answer_mode
    model = payload.get("model", {})
    if model is not None and not isinstance(model, dict):
        raise AppError(
            code="bot_config_model_invalid",
            message="Bot model configuration must be a mapping.",
            hint="Use a YAML mapping under `model`.",
            details={"path": str(path)},
            exit_code=2,
        )
    config.model = dict(model or {})
    runtime_profile = parse_runtime_profile_config(
        {
            **payload,
            "answer_mode": config.answer_mode,
            "model": config.model,
        }
    )
    config.runtime_profile = runtime_profile.profile
    config.fallback_policy = runtime_profile.fallback_policy
    config.model_services = runtime_profile.to_config()["model_services"]
    return config


def audit_bot_visibility(vault_root: Path) -> CommandResult:
    decisions = scan_bot_visibility(vault_root)
    summary = summarize_visibility(decisions)
    return CommandResult(
        message="Bot visibility audit complete",
        data={
            "vault": str(vault_root),
            "summary": summary,
            "decisions": [decision.to_dict() for decision in decisions],
        },
    )


def list_bot_visibility(
    vault_root: Path,
    visibility: str | None = None,
    topic: str | None = None,
    unclassified: bool = False,
) -> CommandResult:
    normalized_visibility = _normalize_optional_visibility(visibility)
    normalized_topic = _normalize_optional_topic(topic)
    decisions = scan_bot_visibility(vault_root)
    filtered = []
    for decision in decisions:
        if normalized_visibility is not None and decision.visibility != normalized_visibility:
            continue
        if normalized_topic is not None and normalized_topic not in decision.topics:
            continue
        if unclassified and decision.metadata_source != "default":
            continue
        filtered.append(decision)
    return CommandResult(
        message="Bot visibility list",
        data={
            "vault": str(vault_root),
            "filters": {
                "visibility": normalized_visibility,
                "topic": normalized_topic,
                "unclassified": unclassified,
            },
            "count": len(filtered),
            "decisions": [decision.to_dict() for decision in filtered],
        },
    )


def inspect_bot_policy(vault_root: Path) -> CommandResult:
    config = load_bot_config(vault_root)
    decisions = scan_bot_visibility(vault_root)
    return CommandResult(
        message="Bot policy inspection complete",
        data={
            "vault": str(vault_root),
            "config": config.to_dict(),
            "visibility_summary": summarize_visibility(decisions),
        },
    )


def scan_bot_visibility(vault_root: Path) -> list[BotVisibilityDecision]:
    ensure_bootstrapped_vault(vault_root)
    notes = _scan_eligible_markdown(vault_root)
    decisions = [_decision_for_note(vault_root, relative_path, path) for relative_path, path in sorted(notes.items())]
    return decisions


def summarize_visibility(decisions: list[BotVisibilityDecision]) -> dict[str, Any]:
    by_visibility = {visibility: 0 for visibility in sorted(VISIBILITIES)}
    by_topic = {topic: 0 for topic in sorted(TOPICS)}
    for decision in decisions:
        by_visibility[decision.visibility] = by_visibility.get(decision.visibility, 0) + 1
        for topic in decision.topics:
            by_topic[topic] = by_topic.get(topic, 0) + 1
    return {
        "total_notes": len(decisions),
        "player_index_notes": sum(1 for decision in decisions if decision.included_in_player),
        "storyteller_index_notes": sum(1 for decision in decisions if decision.included_in_storyteller),
        "excluded_notes": sum(1 for decision in decisions if decision.visibility == VISIBILITY_EXCLUDED),
        "unclassified_notes": sum(1 for decision in decisions if decision.metadata_source == "default"),
        "missing_topic_notes": sum(1 for decision in decisions if decision.missing_topics),
        "by_visibility": by_visibility,
        "by_topic": by_topic,
    }


def set_bot_visibility(
    vault_root: Path,
    target: str,
    visibility: str,
    topics: list[str] | None = None,
    recursive: bool = False,
    dry_run: bool = False,
    yes: bool = False,
) -> CommandResult:
    normalized_visibility = _normalize_visibility(visibility)
    normalized_topics = normalize_topics(topics or [])
    if normalized_visibility == VISIBILITY_EXCLUDED:
        normalized_topics = []

    targets = _resolve_visibility_targets(vault_root, target, recursive=recursive)
    if recursive and not dry_run and not yes:
        raise AppError(
            code="bot_visibility_confirmation_required",
            message="Recursive bot visibility updates require confirmation.",
            hint="Re-run with --yes to apply changes, or use --dry-run to preview them.",
            details={"target": target, "candidate_count": len(targets)},
            exit_code=2,
        )

    updates: list[VisibilityUpdate] = []
    for relative_path, path in targets:
        changed = _set_note_visibility(path, normalized_visibility, normalized_topics, dry_run=dry_run)
        updates.append(VisibilityUpdate(relative_path=relative_path, action="set", changed=changed))
    return CommandResult(
        message="Bot visibility metadata updated" if not dry_run else "Bot visibility dry run complete",
        data={
            "vault": str(vault_root),
            "target": target,
            "visibility": normalized_visibility,
            "topics": normalized_topics,
            "recursive": recursive,
            "dry_run": dry_run,
            "changed_count": sum(1 for update in updates if update.changed),
            "updates": [update.to_dict() for update in updates],
        },
    )


def clear_bot_visibility(
    vault_root: Path,
    target: str,
    recursive: bool = False,
    dry_run: bool = False,
    yes: bool = False,
) -> CommandResult:
    targets = _resolve_visibility_targets(vault_root, target, recursive=recursive)
    if recursive and not dry_run and not yes:
        raise AppError(
            code="bot_visibility_confirmation_required",
            message="Recursive bot visibility updates require confirmation.",
            hint="Re-run with --yes to apply changes, or use --dry-run to preview them.",
            details={"target": target, "candidate_count": len(targets)},
            exit_code=2,
        )

    updates: list[VisibilityUpdate] = []
    for relative_path, path in targets:
        changed = _clear_note_visibility(path, dry_run=dry_run)
        updates.append(VisibilityUpdate(relative_path=relative_path, action="clear", changed=changed))
    return CommandResult(
        message="Bot visibility metadata cleared" if not dry_run else "Bot visibility dry run complete",
        data={
            "vault": str(vault_root),
            "target": target,
            "recursive": recursive,
            "dry_run": dry_run,
            "changed_count": sum(1 for update in updates if update.changed),
            "updates": [update.to_dict() for update in updates],
        },
    )


def normalize_topics(raw_topics: list[str]) -> list[str]:
    topics: list[str] = []
    for value in raw_topics:
        topic = str(value).strip().lower()
        if not topic:
            continue
        if topic not in TOPICS:
            raise AppError(
                code="bot_topic_invalid",
                message=f"Unsupported bot topic: {value}",
                hint=f"Use one of: {', '.join(sorted(TOPICS))}.",
                details={"topic": value},
                exit_code=2,
            )
        if topic not in topics:
            topics.append(topic)
    return topics


def read_note_frontmatter(path: Path) -> dict[str, Any] | None:
    document = parse_frontmatter_document(path.read_text(encoding="utf-8"))
    return document.frontmatter if document.had_frontmatter else None


def parse_frontmatter_document(text: str) -> FrontmatterDocument:
    lines = text.splitlines(keepends=True)
    if len(lines) < 3 or lines[0].strip() != FRONTMATTER_DELIMITER:
        return FrontmatterDocument(frontmatter={}, body=text, had_frontmatter=False)
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            frontmatter_text = "".join(lines[1:index])
            payload = yaml.safe_load(frontmatter_text) or {}
            if not isinstance(payload, dict):
                payload = {}
            body = "".join(lines[index + 1 :])
            return FrontmatterDocument(frontmatter=payload, body=body, had_frontmatter=True)
    return FrontmatterDocument(frontmatter={}, body=text, had_frontmatter=False)


def render_frontmatter_document(frontmatter: dict[str, Any], body: str) -> str:
    if not frontmatter:
        return body.lstrip("\n")
    frontmatter_text = yaml.safe_dump(frontmatter, sort_keys=False).strip()
    normalized_body = body.lstrip("\n")
    if normalized_body:
        return f"{FRONTMATTER_DELIMITER}\n{frontmatter_text}\n{FRONTMATTER_DELIMITER}\n\n{normalized_body}"
    return f"{FRONTMATTER_DELIMITER}\n{frontmatter_text}\n{FRONTMATTER_DELIMITER}\n"


def _default_bot_config() -> BotConfig:
    return BotConfig(
        commands={
            "rules": BotCommandPolicy(min_tier=ACCESS_TIER_PLAYER, topics=[TOPIC_RULES_SUMMARY], public_allowed=False),
            "canon": BotCommandPolicy(min_tier=ACCESS_TIER_PLAYER, topics=[TOPIC_CANON], public_allowed=False),
            "st": BotCommandPolicy(
                min_tier=ACCESS_TIER_STORYTELLER,
                topics=[TOPIC_CANON, TOPIC_NPC, TOPIC_PLOTLINE, TOPIC_STATBLOCK],
                public_allowed=False,
            ),
        },
        response_defaults={"player_public": False, "storyteller_ephemeral": True},
    )


def _parse_command_policies(value: Any, path: Path) -> dict[str, BotCommandPolicy]:
    defaults = _default_bot_config().commands
    if value in (None, ""):
        return defaults
    if not isinstance(value, dict):
        raise AppError(
            code="bot_config_commands_invalid",
            message="Bot commands configuration must be a mapping.",
            hint="Use a YAML mapping under `commands`.",
            details={"path": str(path)},
            exit_code=2,
        )
    commands = dict(defaults)
    for command_name, raw_policy in value.items():
        if not isinstance(raw_policy, dict):
            raise AppError(
                code="bot_config_command_invalid",
                message="Each bot command policy must be a mapping.",
                hint="Use keys such as min_tier, topics, channel_ids, and public_allowed.",
                details={"command": command_name, "path": str(path)},
                exit_code=2,
            )
        min_tier = str(raw_policy.get("min_tier", ACCESS_TIER_PLAYER)).strip().lower()
        if min_tier not in ACCESS_TIERS:
            raise AppError(
                code="bot_access_tier_invalid",
                message=f"Unsupported bot access tier: {min_tier}",
                hint=f"Use one of: {', '.join(sorted(ACCESS_TIERS))}.",
                details={"command": command_name, "path": str(path)},
                exit_code=2,
            )
        commands[str(command_name)] = BotCommandPolicy(
            min_tier=min_tier,
            topics=normalize_topics(_coerce_string_list(raw_policy.get("topics", []), "topics", path)),
            channel_ids=_coerce_string_list(raw_policy.get("channel_ids", []), "channel_ids", path),
            public_allowed=bool(raw_policy.get("public_allowed", False)),
        )
    return commands


def _decision_for_note(vault_root: Path, relative_path: str, path: Path) -> BotVisibilityDecision:
    text = path.read_text(encoding="utf-8")
    document = parse_frontmatter_document(text)
    backet_block = document.frontmatter.get("backet")
    if backet_block is None:
        backet_block = {}
    if not isinstance(backet_block, dict):
        raise AppError(
            code="bot_frontmatter_invalid",
            message="Backet frontmatter must be a mapping.",
            hint=f"Fix the `backet` frontmatter block in {relative_path}.",
            details={"relative_path": relative_path},
            exit_code=2,
        )

    raw_visibility = backet_block.get("visibility")
    metadata_source = "frontmatter" if raw_visibility not in (None, "") else "default"
    visibility = VISIBILITY_STORYTELLER if metadata_source == "default" else _normalize_visibility(str(raw_visibility), relative_path)

    raw_topics = backet_block.get("bot_topics", [])
    if raw_topics in (None, ""):
        raw_topics = []
    topics = normalize_topics(_coerce_string_list(raw_topics, "bot_topics", path, relative_path=relative_path))
    missing_topics = visibility != VISIBILITY_EXCLUDED and not topics
    if missing_topics:
        topics = [DEFAULT_TOPIC]

    included_in_player = visibility == VISIBILITY_PLAYER
    included_in_storyteller = visibility in {VISIBILITY_PLAYER, VISIBILITY_STORYTELLER}
    exclusion_reason = "bot-excluded" if visibility == VISIBILITY_EXCLUDED else None

    return BotVisibilityDecision(
        relative_path=relative_path,
        visibility=visibility,
        topics=topics,
        metadata_source=metadata_source,
        included_in_player=included_in_player,
        included_in_storyteller=included_in_storyteller,
        exclusion_reason=exclusion_reason,
        missing_topics=missing_topics,
        content_hash=fingerprint_text(json.dumps({"frontmatter": document.frontmatter, "body": document.body}, sort_keys=True)),
    )


def _scan_eligible_markdown(vault_root: Path) -> dict[str, Path]:
    ensure_bootstrapped_vault(vault_root)
    ignore_policy = load_index_ignore_policy(vault_root)
    notes: dict[str, Path] = {}
    for path in sorted(vault_root.rglob("*.md")):
        relative_path = path.relative_to(vault_root).as_posix()
        if ignore_policy.ignores(relative_path):
            continue
        notes[relative_path] = path
    return notes


def _resolve_visibility_targets(vault_root: Path, target: str, recursive: bool) -> list[tuple[str, Path]]:
    ensure_bootstrapped_vault(vault_root)
    target_path = _resolve_target_path(vault_root, target)
    ignore_policy = load_index_ignore_policy(vault_root)

    if target_path.is_dir():
        if not recursive:
            raise AppError(
                code="bot_visibility_recursive_required",
                message="Directory visibility updates require --recursive.",
                hint="Use --recursive with --dry-run first to preview changes.",
                details={"target": target},
                exit_code=2,
            )
        targets = []
        for path in sorted(target_path.rglob("*.md")):
            relative_path = path.relative_to(vault_root).as_posix()
            if ignore_policy.ignores(relative_path):
                continue
            targets.append((relative_path, path))
        if not targets:
            raise AppError(
                code="bot_visibility_target_empty",
                message="No eligible Markdown notes matched the visibility target.",
                hint="Check the target path and `.backetignore` policy.",
                details={"target": target},
                exit_code=2,
            )
        return targets

    if not target_path.exists() or not target_path.is_file() or target_path.suffix.lower() != ".md":
        raise AppError(
            code="bot_visibility_target_invalid",
            message="Bot visibility target must be a Markdown note or directory.",
            hint="Provide a vault-relative .md path, note stem, or directory.",
            details={"target": target},
            exit_code=2,
        )

    relative_path = target_path.relative_to(vault_root).as_posix()
    if ignore_policy.ignores(relative_path):
        raise AppError(
            code="bot_visibility_target_ignored",
            message="Bot visibility target is ignored by the vault index policy.",
            hint="Choose a canonical note outside ignored paths.",
            details={"target": target, "relative_path": relative_path},
            exit_code=2,
        )
    return [(relative_path, target_path)]


def _resolve_target_path(vault_root: Path, target: str) -> Path:
    raw_target = normalize_relative_path(target)
    if not raw_target:
        raise AppError(
            code="bot_visibility_target_invalid",
            message="Bot visibility target cannot be empty.",
            hint="Provide a vault-relative note or directory path.",
            exit_code=2,
        )
    candidate = Path(target).expanduser()
    if not candidate.is_absolute():
        candidate = vault_root / raw_target
    candidate = candidate.resolve()
    try:
        candidate.relative_to(vault_root)
    except ValueError as exc:
        raise AppError(
            code="bot_visibility_target_outside_vault",
            message="Bot visibility target must stay inside the vault.",
            hint="Use a vault-relative path.",
            details={"target": target},
            exit_code=2,
        ) from exc
    if candidate.exists():
        return candidate
    if candidate.suffix:
        return candidate
    markdown_candidate = candidate.with_suffix(".md")
    return markdown_candidate if markdown_candidate.exists() else candidate


def _set_note_visibility(path: Path, visibility: str, topics: list[str], dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    document = parse_frontmatter_document(text)
    frontmatter = dict(document.frontmatter)
    backet_block = frontmatter.get("backet")
    if backet_block is None:
        backet_block = {}
    if not isinstance(backet_block, dict):
        raise AppError(
            code="bot_frontmatter_invalid",
            message="Backet frontmatter must be a mapping.",
            hint=f"Fix the `backet` frontmatter block in {path}.",
            details={"path": str(path)},
            exit_code=2,
        )
    updated_backet = dict(backet_block)
    updated_backet["visibility"] = visibility
    if visibility == VISIBILITY_EXCLUDED:
        updated_backet.pop("bot_topics", None)
    elif topics:
        updated_backet["bot_topics"] = topics
    frontmatter["backet"] = updated_backet
    rendered = render_frontmatter_document(frontmatter, document.body)
    changed = rendered != text
    if changed and not dry_run:
        path.write_text(rendered, encoding="utf-8")
    return changed


def _clear_note_visibility(path: Path, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    document = parse_frontmatter_document(text)
    if not document.had_frontmatter:
        return False
    frontmatter = dict(document.frontmatter)
    backet_block = frontmatter.get("backet")
    if not isinstance(backet_block, dict):
        return False
    updated_backet = dict(backet_block)
    updated_backet.pop("visibility", None)
    updated_backet.pop("bot_topics", None)
    if updated_backet:
        frontmatter["backet"] = updated_backet
    else:
        frontmatter.pop("backet", None)
    rendered = render_frontmatter_document(frontmatter, document.body)
    changed = rendered != text
    if changed and not dry_run:
        path.write_text(rendered, encoding="utf-8")
    return changed


def _normalize_visibility(value: str, relative_path: str | None = None) -> str:
    normalized = value.strip().lower()
    if normalized not in VISIBILITIES:
        raise AppError(
            code="bot_visibility_invalid",
            message=f"Unsupported bot visibility: {value}",
            hint=f"Use one of: {', '.join(sorted(VISIBILITIES))}.",
            details={"visibility": value, "relative_path": relative_path},
            exit_code=2,
        )
    return normalized


def _normalize_optional_visibility(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    return _normalize_visibility(str(value))


def _normalize_optional_topic(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    return normalize_topics([str(value)])[0]


def _coerce_string_list(value: Any, field_name: str, path: Path, relative_path: str | None = None) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise AppError(
        code="bot_config_list_invalid",
        message=f"Bot `{field_name}` must be a string or list of strings.",
        hint="Use YAML list syntax for multiple values.",
        details={"field": field_name, "path": str(path), "relative_path": relative_path},
        exit_code=2,
    )


def _string_list_map(value: Any, field_name: str, path: Path) -> dict[str, list[str]]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise AppError(
            code="bot_config_mapping_invalid",
            message=f"Bot `{field_name}` must be a mapping.",
            hint="Use a YAML mapping.",
            details={"field": field_name, "path": str(path)},
            exit_code=2,
        )
    return {str(key): _coerce_string_list(item, field_name, path) for key, item in value.items()}


def _bool_map(value: Any, field_name: str, path: Path) -> dict[str, bool]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise AppError(
            code="bot_config_mapping_invalid",
            message=f"Bot `{field_name}` must be a mapping.",
            hint="Use a YAML mapping.",
            details={"field": field_name, "path": str(path)},
            exit_code=2,
        )
    return {str(key): bool(item) for key, item in value.items()}


def path_matches_any(path: str, patterns: list[str]) -> bool:
    normalized = normalize_relative_path(path)
    return any(fnmatch.fnmatchcase(normalized, normalize_relative_path(pattern)) for pattern in patterns)


def _reject_secret_like_keys(value: Any, path: Path, key_path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            current_path = f"{key_path}.{key_text}" if key_path else key_text
            if _is_secret_like_key(lowered):
                raise AppError(
                    code="bot_config_secret_field",
                    message="Bot configuration must not contain secret-like keys.",
                    hint="Put Discord tokens, SSH keys, model tokens, and other secrets in deployment secrets or environment variables.",
                    details={"path": str(path), "field": current_path},
                    exit_code=2,
                )
            _reject_secret_like_keys(item, path, current_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_like_keys(item, path, f"{key_path}[{index}]")


def _is_secret_like_key(lowered_key: str) -> bool:
    normalized = lowered_key.replace("-", "_")
    if normalized.endswith("_env") or normalized.endswith("_env_var") or normalized.endswith("_env_name"):
        return False
    if lowered_key == "token" or lowered_key.endswith("_token") or lowered_key.endswith("-token"):
        return True
    return any(marker in lowered_key for marker in SECRET_KEY_MARKERS)
