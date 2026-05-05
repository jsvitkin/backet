from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from backet.bot_answers import AnswerGenerator, ModelClient, generate_answer_from_config
from backet.bot_access import ACCESS_TIER_PLAYER, ACCESS_TIER_STORYTELLER
from backet.bot_export import BOT_BUNDLE_SCHEMA_VERSION
from backet.errors import AppError
from backet.indexing import INDEX_SCHEMA_VERSION
from backet.models import CommandResult
from backet.retrieval import ScopeAnchor, assemble_context_chunks
from backet.rules import open_rules_database, query_rules_connection

DISCORD_MESSAGE_LIMIT = 2000
SAFE_DISCORD_MESSAGE_LIMIT = 1900
ACCESS_RANK = {ACCESS_TIER_PLAYER: 0, ACCESS_TIER_STORYTELLER: 1}


@dataclass(slots=True)
class BotCommandRoute:
    command: str
    min_tier: str
    index_scope: str | None
    topics: list[str] = field(default_factory=list)
    include_vault: bool = True
    include_rules: bool = False
    private_default: bool = True


@dataclass(slots=True)
class ResolvedBotAccess:
    tier: str
    user_id: str | None
    role_ids: list[str]
    matched_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "user_id": self.user_id,
            "role_ids": self.role_ids,
            "matched_by": self.matched_by,
        }


@dataclass(slots=True)
class BotAnswer:
    command: str
    access_tier: str
    text: str
    parts: list[str]
    sources: list[dict[str, Any]]
    response_private: bool
    denied: bool = False
    retrieval_attempted: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "access_tier": self.access_tier,
            "text": self.text,
            "parts": self.parts,
            "sources": self.sources,
            "response_private": self.response_private,
            "denied": self.denied,
            "retrieval_attempted": self.retrieval_attempted,
            "diagnostics": self.diagnostics,
        }


IndexOpener = Callable[[Path], sqlite3.Connection]
RulesOpener = Callable[[Path], sqlite3.Connection]


class BotBundle:
    def __init__(
        self,
        root: Path,
        manifest: dict[str, Any],
        access_policy: dict[str, Any],
        index_opener: IndexOpener | None = None,
        rules_opener: RulesOpener | None = None,
    ) -> None:
        self.root = root
        self.manifest = manifest
        self.access_policy = access_policy
        self._index_opener = index_opener or open_index_readonly
        self._rules_opener = rules_opener or open_rules_readonly

    @classmethod
    def load(
        cls,
        bundle_root: Path,
        index_opener: IndexOpener | None = None,
        rules_opener: RulesOpener | None = None,
    ) -> BotBundle:
        root = bundle_root.expanduser().resolve()
        manifest_path = root / "manifest.json"
        policy_path = root / "access-policy.json"
        if not manifest_path.exists():
            raise AppError(
                code="bot_bundle_manifest_missing",
                message="Bot bundle manifest is missing.",
                hint="Export a bot bundle first.",
                details={"bundle_root": str(root)},
                exit_code=2,
            )
        if not policy_path.exists():
            raise AppError(
                code="bot_bundle_access_policy_missing",
                message="Bot bundle access policy is missing.",
                hint="Re-export the bot bundle.",
                details={"bundle_root": str(root)},
                exit_code=2,
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema_version = int(manifest.get("schema_version", 0))
        if schema_version != BOT_BUNDLE_SCHEMA_VERSION:
            raise AppError(
                code="bot_bundle_schema_unsupported",
                message="Bot bundle schema version is unsupported.",
                hint=f"Expected schema version {BOT_BUNDLE_SCHEMA_VERSION}.",
                details={"schema_version": schema_version, "bundle_root": str(root)},
                exit_code=2,
            )
        access_policy = json.loads(policy_path.read_text(encoding="utf-8"))
        if access_policy.get("access_policy_hash") != manifest.get("access_policy_hash"):
            raise AppError(
                code="bot_bundle_access_policy_hash_mismatch",
                message="Access policy hash does not match the bundle manifest.",
                hint="Re-export the bot bundle.",
                details={"bundle_root": str(root)},
                exit_code=2,
            )
        for scope, meta in manifest.get("indexes", {}).items():
            path = root / str(meta.get("path", ""))
            if not path.exists():
                raise AppError(
                    code="bot_bundle_index_missing",
                    message=f"Bot index for {scope} is missing.",
                    hint="Re-export the bot bundle.",
                    details={"scope": scope, "path": str(path)},
                    exit_code=2,
                )
        rules = manifest.get("rules", {})
        if rules.get("included"):
            rules_path = root / str(rules.get("path", ""))
            if not rules_path.exists():
                raise AppError(
                    code="bot_bundle_rules_missing",
                    message="Bundled shared rules database is missing.",
                    hint="Re-export the bot bundle.",
                    details={"path": str(rules_path)},
                    exit_code=2,
                )
        return cls(root, manifest, access_policy, index_opener=index_opener, rules_opener=rules_opener)

    def open_index(self, scope: str) -> sqlite3.Connection:
        meta = self.manifest.get("indexes", {}).get(scope)
        if not meta:
            raise AppError(
                code="bot_index_scope_missing",
                message=f"Bot index scope is not bundled: {scope}",
                hint="Re-export the bot bundle.",
                details={"scope": scope},
                exit_code=2,
            )
        return self._index_opener(self.root / str(meta["path"]))

    def open_rules(self) -> sqlite3.Connection:
        rules = self.manifest.get("rules", {})
        if not rules.get("included"):
            raise AppError(
                code="bot_rules_missing",
                message="This bot bundle does not include a rules database.",
                hint="Ingest rules locally and re-export the bot bundle.",
                exit_code=2,
            )
        return self._rules_opener(self.root / str(rules["path"]))

    def eligible_paths(self, index_scope: str, topics: list[str]) -> list[str]:
        requested_topics = set(topics)
        paths: list[str] = []
        for decision in self.access_policy.get("decisions", []):
            if index_scope == ACCESS_TIER_PLAYER and not decision.get("included_in_player"):
                continue
            if index_scope == ACCESS_TIER_STORYTELLER and not decision.get("included_in_storyteller"):
                continue
            if requested_topics and not requested_topics.intersection(set(decision.get("topics", []))):
                continue
            paths.append(str(decision["relative_path"]))
        return sorted(paths)


def open_index_readonly(db_path: Path) -> sqlite3.Connection:
    db_path = db_path.expanduser().resolve()
    if not db_path.exists():
        raise AppError(
            code="bot_index_missing",
            message="Bot vault index is missing.",
            hint="Re-export the bot bundle.",
            details={"path": str(db_path)},
            exit_code=2,
        )
    connection = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    _validate_index_schema(connection, db_path)
    return connection


def open_rules_readonly(db_path: Path) -> sqlite3.Connection:
    return open_rules_database(db_path, readonly=True)


def inspect_bot_bundle(bundle_root: Path) -> CommandResult:
    bundle = BotBundle.load(bundle_root)
    return CommandResult(
        message="Bot runtime bundle loaded",
        data={
            "bundle_root": str(bundle.root),
            "schema_version": bundle.manifest.get("schema_version"),
            "guild_id": bundle.manifest.get("bot", {}).get("guild_id"),
            "indexes": bundle.manifest.get("indexes", {}),
            "rules": bundle.manifest.get("rules", {}),
            "answer_mode": bundle.manifest.get("bot", {}).get("answer_mode", "template"),
        },
    )


def answer_bot_query(
    bundle: BotBundle,
    command: str,
    question: str,
    user_id: str | None = None,
    role_ids: list[str] | None = None,
    private: bool | None = None,
    limit: int = 4,
    answer_generator: AnswerGenerator | None = None,
    model_client: ModelClient | None = None,
) -> BotAnswer:
    normalized_command = normalize_bot_command(command)
    route = route_for_command(normalized_command)
    access = resolve_access_tier(bundle.manifest.get("bot", {}), user_id=user_id, role_ids=role_ids or [])
    response_private = route.private_default if private is None else private
    diagnostics: dict[str, Any] = {"access": access.to_dict(), "route": asdict(route)}

    if not tier_allows(access.tier, route.min_tier):
        text = sanitize_discord_mentions("Permission denied for that bot command.")
        return BotAnswer(
            command=normalized_command,
            access_tier=access.tier,
            text=text,
            parts=split_discord_response(text),
            sources=[],
            response_private=True,
            denied=True,
            retrieval_attempted=False,
            diagnostics=diagnostics,
        )

    sources: list[dict[str, Any]] = []
    retrieval_errors: list[dict[str, Any]] = []
    if route.include_vault and route.index_scope:
        try:
            sources.extend(retrieve_vault_sources(bundle, route, question, limit=limit))
        except AppError as error:
            retrieval_errors.append({"code": error.code, "message": error.message, "details": error.details})

    if route.include_rules:
        try:
            sources.extend(retrieve_rule_sources(bundle, question, limit=limit))
        except AppError as error:
            if error.code == "rules_query_ambiguous":
                text = _compose_rule_ambiguity(error.details)
                text = sanitize_discord_mentions(text)
                return BotAnswer(
                    command=normalized_command,
                    access_tier=access.tier,
                    text=text,
                    parts=split_discord_response(text),
                    sources=[],
                    response_private=response_private,
                    retrieval_attempted=True,
                    diagnostics={**diagnostics, "rules_ambiguity": error.details},
                )
            retrieval_errors.append({"code": error.code, "message": error.message, "details": error.details})

    diagnostics["retrieval_errors"] = retrieval_errors
    generated = (
        answer_generator.generate(question, sources)
        if answer_generator is not None
        else generate_answer_from_config(bundle.manifest.get("bot", {}), question, sources, client=model_client)
    )
    diagnostics["answer_generation"] = generated.to_dict()
    text = generated.text
    text = sanitize_discord_mentions(text)
    return BotAnswer(
        command=normalized_command,
        access_tier=access.tier,
        text=text,
        parts=split_discord_response(text),
        sources=sources,
        response_private=response_private,
        retrieval_attempted=True,
        diagnostics=diagnostics,
    )


def answer_bot_query_result(
    bundle_root: Path,
    command: str,
    question: str,
    user_id: str | None = None,
    role_ids: list[str] | None = None,
    private: bool | None = None,
    limit: int = 4,
    model_client: ModelClient | None = None,
) -> CommandResult:
    bundle = BotBundle.load(bundle_root)
    answer = answer_bot_query(
        bundle,
        command=command,
        question=question,
        user_id=user_id,
        role_ids=role_ids or [],
        private=private,
        limit=limit,
        model_client=model_client,
    )
    return CommandResult(message="Answered bot query from bundle", data=answer.to_dict())


def retrieve_vault_sources(bundle: BotBundle, route: BotCommandRoute, question: str, limit: int) -> list[dict[str, Any]]:
    if route.index_scope is None:
        return []
    eligible_paths = bundle.eligible_paths(route.index_scope, route.topics)
    if not eligible_paths:
        return []
    with closing(bundle.open_index(route.index_scope)) as connection:
        rows = _fetch_note_rows(connection, eligible_paths)
        anchor = ScopeAnchor(scope="vault", target=".", note_rows=rows)
        raw_sources = assemble_context_chunks(connection, anchor, query=question, limit=limit)
    sources: list[dict[str, Any]] = []
    for index, source in enumerate(raw_sources, start=1):
        sources.append(
            {
                "source_type": "vault",
                "citation": f"V{index}",
                "relative_path": source["relative_path"],
                "title": source["title"],
                "heading_path": source["heading_path"],
                "excerpt": source["excerpt"],
                "score": source["score"],
                "match_reasons": source["match_reasons"],
            }
        )
    return sources


def retrieve_rule_sources(bundle: BotBundle, question: str, limit: int) -> list[dict[str, Any]]:
    with closing(bundle.open_rules()) as connection:
        result = query_rules_connection(
            connection,
            query=question,
            limit=limit,
            db_label=str(bundle.root / str(bundle.manifest["rules"]["path"])),
        )
    raw_sources = result.data.get("primary_results", []) + result.data.get("fallback_results", [])
    sources: list[dict[str, Any]] = []
    for index, source in enumerate(raw_sources[:limit], start=1):
        sources.append(
            {
                "source_type": "rules",
                "citation": f"R{index}",
                "book_id": source["book_id"],
                "book_title": source["book_title"],
                "page_start": source["page_start"],
                "page_end": source["page_end"],
                "section_label": source["section_label"],
                "excerpt": source["excerpt"],
                "score": source["score"],
                "match_reasons": source["match_reasons"],
            }
        )
    return sources


def resolve_access_tier(bot_config: dict[str, Any], user_id: str | None, role_ids: list[str]) -> ResolvedBotAccess:
    normalized_user_id = str(user_id) if user_id not in (None, "") else None
    normalized_roles = [str(role_id) for role_id in role_ids if str(role_id)]
    users = bot_config.get("users", {}) or {}
    roles = bot_config.get("roles", {}) or {}
    for tier in (ACCESS_TIER_STORYTELLER, ACCESS_TIER_PLAYER):
        if normalized_user_id and normalized_user_id in {str(value) for value in users.get(tier, [])}:
            return ResolvedBotAccess(tier=tier, user_id=normalized_user_id, role_ids=normalized_roles, matched_by="user")
        configured_roles = {str(value) for value in roles.get(tier, [])}
        if configured_roles.intersection(normalized_roles):
            return ResolvedBotAccess(tier=tier, user_id=normalized_user_id, role_ids=normalized_roles, matched_by="role")
    return ResolvedBotAccess(tier=ACCESS_TIER_PLAYER, user_id=normalized_user_id, role_ids=normalized_roles, matched_by="default")


def route_for_command(command: str) -> BotCommandRoute:
    routes = {
        "rules.ask": BotCommandRoute(
            command="rules.ask",
            min_tier=ACCESS_TIER_PLAYER,
            index_scope=ACCESS_TIER_PLAYER,
            topics=["rules-summary", "canon"],
            include_rules=True,
            private_default=True,
        ),
        "canon.ask": BotCommandRoute(
            command="canon.ask",
            min_tier=ACCESS_TIER_PLAYER,
            index_scope=ACCESS_TIER_PLAYER,
            topics=["canon"],
            private_default=True,
        ),
        "st.ask": BotCommandRoute(
            command="st.ask",
            min_tier=ACCESS_TIER_STORYTELLER,
            index_scope=ACCESS_TIER_STORYTELLER,
            include_rules=True,
            private_default=True,
        ),
        "st.npc": BotCommandRoute(
            command="st.npc",
            min_tier=ACCESS_TIER_STORYTELLER,
            index_scope=ACCESS_TIER_STORYTELLER,
            topics=["npc", "statblock"],
            private_default=True,
        ),
        "st.plot": BotCommandRoute(
            command="st.plot",
            min_tier=ACCESS_TIER_STORYTELLER,
            index_scope=ACCESS_TIER_STORYTELLER,
            topics=["plotline"],
            private_default=True,
        ),
        "st.statblock": BotCommandRoute(
            command="st.statblock",
            min_tier=ACCESS_TIER_STORYTELLER,
            index_scope=ACCESS_TIER_STORYTELLER,
            topics=["statblock", "npc"],
            private_default=True,
        ),
    }
    if command not in routes:
        raise AppError(
            code="bot_command_unknown",
            message=f"Unsupported bot command: {command}",
            hint="Use one of: rules.ask, canon.ask, st.ask, st.npc, st.plot, st.statblock.",
            details={"command": command},
            exit_code=2,
        )
    return routes[command]


def normalize_bot_command(command: str) -> str:
    normalized = command.strip().lower().replace("/", "").replace(" ", ".")
    aliases = {
        "rules": "rules.ask",
        "rules.ask": "rules.ask",
        "canon": "canon.ask",
        "canon.ask": "canon.ask",
        "st": "st.ask",
        "st.ask": "st.ask",
        "st.npc": "st.npc",
        "st.plot": "st.plot",
        "st.statblock": "st.statblock",
    }
    return aliases.get(normalized, normalized)


def tier_allows(actual: str, required: str) -> bool:
    return ACCESS_RANK.get(actual, -1) >= ACCESS_RANK.get(required, 999)


def compose_template_answer(question: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "I do not have enough permitted source material to answer that."
    lines = ["I found permitted sources for that:"]
    for source in sources[:4]:
        lines.append(f"[{source['citation']}] {str(source['excerpt']).strip()}")
    labels = "; ".join(_source_label(source) for source in sources[:4])
    lines.append(f"Sources: {labels}")
    return "\n".join(lines)


def split_discord_response(text: str, limit: int = SAFE_DISCORD_MESSAGE_LIMIT) -> list[str]:
    if limit <= 0 or limit > DISCORD_MESSAGE_LIMIT:
        raise ValueError("Discord message split limit must be between 1 and 2000.")
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit
        parts.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


def sanitize_discord_mentions(text: str) -> str:
    spacer = "\u200b"
    sanitized = text.replace("@everyone", f"@{spacer}everyone").replace("@here", f"@{spacer}here")
    sanitized = sanitized.replace("<@", f"<@{spacer}").replace("<#", f"<#{spacer}").replace("<@&", f"<@&{spacer}")
    return sanitized


def _fetch_note_rows(connection: sqlite3.Connection, relative_paths: list[str]) -> list[sqlite3.Row]:
    if not relative_paths:
        return []
    placeholders = ", ".join("?" for _ in relative_paths)
    return connection.execute(
        f"SELECT * FROM notes WHERE relative_path IN ({placeholders}) ORDER BY top_level, relative_path",
        relative_paths,
    ).fetchall()


def _validate_index_schema(connection: sqlite3.Connection, db_path: Path) -> None:
    row = connection.execute("SELECT value FROM index_meta WHERE key = 'schema_version'").fetchone()
    if row is None or int(row["value"]) != INDEX_SCHEMA_VERSION:
        raise AppError(
            code="bot_index_schema_unsupported",
            message="Bot vault index schema version is unsupported.",
            hint="Re-export the bot bundle with this Backet version.",
            details={"path": str(db_path), "schema_version": row["value"] if row else None},
            exit_code=2,
        )


def _source_label(source: dict[str, Any]) -> str:
    if source["source_type"] == "vault":
        return f"[{source['citation']}] {source['title']} ({source['relative_path']})"
    page = source["page_start"]
    if source.get("page_end") and source["page_end"] != source["page_start"]:
        page = f"{source['page_start']}-{source['page_end']}"
    return f"[{source['citation']}] {source['book_title']} p. {page} ({source['section_label']})"


def _compose_rule_ambiguity(details: dict[str, Any]) -> str:
    books = details.get("conflicting_books", [])
    if not books:
        return "I found multiple comparable rule sources. Please narrow the book or scope."
    labels = ", ".join(f"{book.get('book_title', book.get('book_id'))}" for book in books)
    return f"I found multiple comparable rule sources: {labels}. Please narrow the book or scope."
