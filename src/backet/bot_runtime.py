from __future__ import annotations

import json
import sqlite3
import hashlib
from contextlib import closing
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from backet.bot_answers import (
    ANSWER_CLASS_RUNTIME_UNAVAILABLE,
    AnswerGenerator,
    AnswerPacket,
    ModelClient,
    TemplateAnswerGenerator,
    build_answer_packet,
    clean_bot_source_text,
    format_bot_source_label,
    generate_answer_from_config,
)
from backet.bot_access import ACCESS_TIER_PLAYER, ACCESS_TIER_STORYTELLER
from backet.bot_export import BOT_BUNDLE_SCHEMA_VERSION
from backet.bot_profiles import doctor_runtime_profile
from backet.embeddings import EmbeddingBackend, resolve_embedding_backend_from_config
from backet.errors import AppError
from backet.indexing import INDEX_SCHEMA_VERSION
from backet.models import CommandResult
from backet.retrieval import ScopeAnchor, assemble_context_chunks
from backet.rules import open_rules_database, query_rules_connection

DISCORD_MESSAGE_LIMIT = 2000
SAFE_DISCORD_MESSAGE_LIMIT = 1900
ACCESS_RANK = {ACCESS_TIER_PLAYER: 0, ACCESS_TIER_STORYTELLER: 1}
ANSWER_TRACE_SCHEMA_VERSION = 1
ANSWER_TRACE_SNIPPET_CHARS = 500


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
    answer_trace: dict[str, Any] = field(default_factory=dict)

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
            "answer_trace": self.answer_trace,
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
    runtime_health = doctor_runtime_profile(bundle.manifest, manifest=bundle.manifest)
    return CommandResult(
        message="Bot runtime bundle loaded",
        data={
            "bundle_root": str(bundle.root),
            "schema_version": bundle.manifest.get("schema_version"),
            "guild_id": bundle.manifest.get("bot", {}).get("guild_id"),
            "indexes": bundle.manifest.get("indexes", {}),
            "rules": bundle.manifest.get("rules", {}),
            "answer_mode": bundle.manifest.get("bot", {}).get("answer_mode", "template"),
            "runtime": bundle.manifest.get("runtime", {}),
            "runtime_health": runtime_health,
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
    runtime_health = doctor_runtime_profile(bundle.manifest, manifest=bundle.manifest)
    diagnostics: dict[str, Any] = {"access": access.to_dict(), "route": asdict(route), "runtime": runtime_health}

    if not tier_allows(access.tier, route.min_tier):
        text = sanitize_discord_mentions("Permission denied for that bot command.")
        parts = split_discord_response(text)
        trace = build_answer_trace(
            command=normalized_command,
            question=question,
            access=access,
            route=route,
            sources=[],
            retrieval_errors=[],
            generated=None,
            text=text,
            parts=parts,
            response_private=True,
            denied=True,
            retrieval_attempted=False,
        )
        return BotAnswer(
            command=normalized_command,
            access_tier=access.tier,
            text=text,
            parts=parts,
            sources=[],
            response_private=True,
            denied=True,
            retrieval_attempted=False,
            diagnostics=diagnostics,
            answer_trace=trace,
        )

    if runtime_health.get("blocking"):
        packet = AnswerPacket(
            question=question,
            response_class=ANSWER_CLASS_RUNTIME_UNAVAILABLE,
            evidence_status="runtime_unavailable",
            missing_evidence=["runtime_profile"],
            diagnostics={"runtime_health": runtime_health},
        )
        generated = TemplateAnswerGenerator().generate_from_packet(packet)
        text = sanitize_discord_mentions(generated.text)
        parts = split_discord_response(text)
        diagnostics["answer_generation"] = generated.to_dict()
        trace = build_answer_trace(
            command=normalized_command,
            question=question,
            access=access,
            route=route,
            sources=[],
            retrieval_errors=[{"code": "bot_runtime_profile_unavailable", "message": "Runtime profile services are unavailable."}],
            generated=generated.to_dict(),
            text=text,
            parts=parts,
            response_private=response_private,
            denied=False,
            retrieval_attempted=False,
        )
        trace["runtime"] = runtime_health
        return BotAnswer(
            command=normalized_command,
            access_tier=access.tier,
            text=text,
            parts=parts,
            sources=[],
            response_private=response_private,
            denied=False,
            retrieval_attempted=False,
            diagnostics=diagnostics,
            answer_trace=trace,
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
            retrieval_errors.append({"code": error.code, "message": error.message, "details": error.details})

    diagnostics["retrieval_errors"] = retrieval_errors
    answer_packet = build_answer_packet(question, sources, retrieval_errors=retrieval_errors)
    if answer_generator is not None:
        generator = getattr(answer_generator, "generate_from_packet", None)
        generated = generator(answer_packet) if callable(generator) else answer_generator.generate(question, sources)
    else:
        generated = generate_answer_from_config(
            bundle.manifest.get("bot", {}),
            question,
            sources,
            client=model_client,
            answer_packet=answer_packet,
        )
    diagnostics["answer_generation"] = generated.to_dict()
    text = generated.text
    text = sanitize_discord_mentions(text)
    parts = split_discord_response(text)
    trace = build_answer_trace(
        command=normalized_command,
        question=question,
        access=access,
        route=route,
        sources=sources,
        retrieval_errors=retrieval_errors,
        generated=generated.to_dict(),
        text=text,
        parts=parts,
        response_private=response_private,
        denied=False,
        retrieval_attempted=True,
    )
    trace["runtime"] = runtime_health
    return BotAnswer(
        command=normalized_command,
        access_tier=access.tier,
        text=text,
        parts=parts,
        sources=sources,
        response_private=response_private,
        retrieval_attempted=True,
        diagnostics=diagnostics,
        answer_trace=trace,
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


def build_answer_trace(
    *,
    command: str,
    question: str,
    access: ResolvedBotAccess,
    route: BotCommandRoute,
    sources: list[dict[str, Any]],
    retrieval_errors: list[dict[str, Any]],
    generated: dict[str, Any] | None,
    text: str,
    parts: list[str],
    response_private: bool,
    denied: bool,
    retrieval_attempted: bool,
) -> dict[str, Any]:
    source_traces = [_trace_source(source) for source in sources]
    generation = _trace_generation(generated, text=text, sources=sources)
    query_plan = _query_plan_from_sources_or_errors(sources, retrieval_errors)
    rag_v2 = _rag_v2_from_sources_or_errors(sources, retrieval_errors)
    evidence_packet = _evidence_packet_from_sources_or_errors(sources, retrieval_errors)
    answer_packet = _answer_packet_from_generation(generated)
    return {
        "trace_schema_version": ANSWER_TRACE_SCHEMA_VERSION,
        "question": {
            "fingerprint": _fingerprint_question(question),
            "preview": sanitize_discord_mentions(" ".join(question.strip().split()))[:240],
            "length": len(question),
        },
        "route": {
            "command": command,
            "min_tier": route.min_tier,
            "index_scope": route.index_scope,
            "topics": route.topics,
            "include_vault": route.include_vault,
            "include_rules": route.include_rules,
        },
        "access": access.to_dict(),
        "retrieval": {
            "attempted": retrieval_attempted,
            "source_count": len(sources),
            "source_counts": {
                "vault": sum(1 for source in sources if source.get("source_type") == "vault"),
                "rules": sum(1 for source in sources if source.get("source_type") == "rules"),
            },
            "rules_retrieval_mode": _first_source_field(sources, "retrieval_mode", source_type="rules"),
            "rules_embedding_backend": _first_source_field(sources, "embedding_backend", source_type="rules"),
            "rules_embedding_model": _first_source_field(sources, "embedding_model", source_type="rules"),
            "rules_evidence_status": _first_source_field(sources, "evidence_status", source_type="rules")
            or (evidence_packet or {}).get("evidence_status"),
            "vault_attempted": bool(route.include_vault and route.index_scope),
            "rules_attempted": bool(route.include_rules),
            "errors": retrieval_errors,
            "selected_sources": source_traces,
        },
        "stages": {
            "query_plan": _trace_query_plan(query_plan),
            "reranking": _trace_rag_v2_reranking(rag_v2),
            "answer_packet": _trace_answer_packet(answer_packet),
            "answerability": _trace_answerability(evidence_packet, answer_packet),
            "synthesis": _trace_synthesis(generation),
        },
        "generation": generation,
        "response": {
            "chars": len(text),
            "parts": len(parts),
            "private": response_private,
            "denied": denied,
        },
    }


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
    embedding_backend = _configured_rules_embedding_backend(bundle.manifest)
    with closing(bundle.open_rules()) as connection:
        result = query_rules_connection(
            connection,
            query=question,
            limit=limit,
            db_label=str(bundle.root / str(bundle.manifest["rules"]["path"])),
            embedding_backend=embedding_backend,
        )
    evidence_packet = result.data.get("evidence_packet") if isinstance(result.data.get("evidence_packet"), dict) else {}
    if evidence_packet and evidence_packet.get("evidence_status") != "answerable":
        raise AppError(
            code="rules_evidence_insufficient",
            message="Rules retrieval found related chunks but not enough answer evidence.",
            hint="Use a narrower rules question or ingest/index the relevant rules source.",
            details={
                "query_plan": result.data.get("query_plan"),
                "evidence_packet": evidence_packet,
                "rag_v2": result.data.get("rag_v2"),
            },
            exit_code=2,
        )
    raw_sources = (
        list(evidence_packet.get("selected_evidence") or [])
        if evidence_packet
        else result.data.get("primary_results", []) + result.data.get("fallback_results", [])
    )
    query_plan = result.data.get("query_plan")
    planned_retrieval = result.data.get("planned_retrieval")
    rag_v2 = result.data.get("rag_v2")
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
                "content": source["content"],
                "score": source["score"],
                "match_reasons": source["match_reasons"],
                "retrieval_mode": result.data.get("retrieval_mode"),
                "embedding_backend": result.data.get("embedding_backend"),
                "embedding_model": result.data.get("embedding_model"),
                "query_plan": query_plan,
                "planned_retrieval": planned_retrieval,
                "rag_v2": rag_v2,
                "evidence_packet": evidence_packet,
                "evidence_status": evidence_packet.get("evidence_status") if evidence_packet else None,
                "evidence_cues": source.get("evidence_cues", []),
                "retrieval_channels": source.get("retrieval_channels", []),
                "rule_units": source.get("rule_units", []),
                "rule_unit_kinds": source.get("rule_unit_kinds", []),
                "rule_unit_authority_roles": source.get("rule_unit_authority_roles", []),
                "rule_unit_answer_facets": source.get("rule_unit_answer_facets", []),
            }
        )
    return sources


def _configured_rules_embedding_backend(manifest: dict[str, Any]) -> EmbeddingBackend | None:
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    runtime_services = runtime.get("services") if isinstance(runtime.get("services"), dict) else {}
    service = runtime_services.get("embedding") if isinstance(runtime_services.get("embedding"), dict) else None
    if service is None:
        bot = manifest.get("bot") if isinstance(manifest.get("bot"), dict) else {}
        model_services = bot.get("model_services") if isinstance(bot.get("model_services"), dict) else {}
        service = model_services.get("embedding") if isinstance(model_services.get("embedding"), dict) else None
    if not service:
        return None
    provider = str(service.get("provider") or service.get("backend") or "").strip().lower()
    if not provider or provider == "disabled":
        return None
    return resolve_embedding_backend_from_config(service)


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


def _trace_source(source: dict[str, Any]) -> dict[str, Any]:
    traced: dict[str, Any] = {
        "citation": source.get("citation"),
        "source_type": source.get("source_type"),
        "label": _safe_source_label(source),
        "score": source.get("score"),
        "match_reasons": list(source.get("match_reasons") or []),
        "snippet": _bounded_source_snippet(source),
        "snippet_chars": ANSWER_TRACE_SNIPPET_CHARS,
    }
    if source.get("source_type") == "vault":
        traced.update(
            {
                "title": source.get("title"),
                "relative_path": source.get("relative_path"),
                "heading_path": source.get("heading_path"),
            }
        )
    elif source.get("source_type") == "rules":
        traced.update(
            {
                "book_id": source.get("book_id"),
                "book_title": source.get("book_title"),
                "page_start": source.get("page_start"),
                "page_end": source.get("page_end"),
                "section_label": source.get("section_label"),
                "retrieval_mode": source.get("retrieval_mode"),
                "embedding_backend": source.get("embedding_backend"),
                "embedding_model": source.get("embedding_model"),
                "evidence_status": source.get("evidence_status"),
                "evidence_cues": list(source.get("evidence_cues") or []),
                "retrieval_channels": list(source.get("retrieval_channels") or []),
                "rule_unit_kinds": list(source.get("rule_unit_kinds") or []),
                "rule_unit_authority_roles": list(source.get("rule_unit_authority_roles") or []),
                "rule_unit_answer_facets": list(source.get("rule_unit_answer_facets") or []),
            }
        )
    return traced


def _safe_source_label(source: dict[str, Any]) -> str:
    try:
        return format_bot_source_label(source)
    except Exception:
        return str(source.get("citation") or source.get("source_type") or "source")


def _bounded_source_snippet(source: dict[str, Any], limit: int = ANSWER_TRACE_SNIPPET_CHARS) -> str:
    text = clean_bot_source_text(str(source.get("excerpt") or source.get("content") or ""))
    text = sanitize_discord_mentions(text)
    if len(text) <= limit:
        return text
    end = text.rfind(" ", 0, max(0, limit - 4))
    if end < 80:
        end = max(0, limit - 4)
    return text[:end].rstrip(" ,;:") + " ..."


def _trace_generation(generated: dict[str, Any] | None, *, text: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    if generated is None:
        return {
            "available": False,
            "mode": None,
            "fallback_used": False,
            "fallback_reason": None,
            "citation_status": "not_checked",
            "diagnostics": {},
        }
    diagnostics = dict(generated.get("diagnostics", {}) or {})
    return {
        "available": True,
        "mode": generated.get("mode"),
        "fallback_used": bool(generated.get("fallback_used")),
        "fallback_reason": diagnostics.get("fallback_reason"),
        "citation_status": _citation_status(text, sources),
        "diagnostics": diagnostics,
    }


def _citation_status(text: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "not_required"
    labels = [format_bot_source_label(source) for source in sources]
    citations = [f"[{source.get('citation')}]" for source in sources if source.get("citation")]
    lowered = text.casefold()
    if any(citation in text for citation in citations):
        return "citation_present"
    if "sources:" in lowered and any(label.casefold() in lowered for label in labels):
        return "source_label_present"
    return "not_found"


def _unavailable_stage(reason: str) -> dict[str, Any]:
    return {"status": "unavailable", "reason": reason}


def _trace_query_plan(query_plan: Any) -> dict[str, Any]:
    if isinstance(query_plan, dict):
        return {"status": "available", "plan": query_plan}
    return _unavailable_stage("not_planned")


def _trace_rag_v2_reranking(rag_v2: Any) -> dict[str, Any]:
    if not isinstance(rag_v2, dict):
        return _unavailable_stage("not_available")
    return {
        "status": "available",
        "schema_version": rag_v2.get("schema_version"),
        "candidate_caps": rag_v2.get("candidate_caps", {}),
        "channels": rag_v2.get("channels", []),
        "semantic_quality": rag_v2.get("semantic_quality"),
    }


def _trace_answer_packet(answer_packet: Any) -> dict[str, Any]:
    if isinstance(answer_packet, dict):
        return {"status": "available", **answer_packet}
    return _unavailable_stage("not_available")


def _trace_answerability(evidence_packet: Any, answer_packet: Any = None) -> dict[str, Any]:
    if not isinstance(evidence_packet, dict):
        if isinstance(answer_packet, dict):
            return {
                "status": "available",
                "evidence_status": answer_packet.get("evidence_status"),
                "answerability_status": answer_packet.get("answerability_status"),
                "selected_evidence_count": answer_packet.get("selected_evidence_count", 0),
                "fallback_context_count": answer_packet.get("fallback_context_count", 0),
                "missing_evidence": list(answer_packet.get("missing_evidence") or []),
                "satisfied_evidence": [],
                "missing_facets": [],
                "satisfied_facets": [],
            }
        return _unavailable_stage("not_available")
    diagnostics = evidence_packet.get("retrieval_diagnostics") if isinstance(evidence_packet.get("retrieval_diagnostics"), dict) else {}
    return {
        "status": "available",
        "evidence_status": evidence_packet.get("evidence_status"),
        "answerability_status": evidence_packet.get("answerability_status"),
        "selected_evidence_count": len(evidence_packet.get("selected_evidence") or []),
        "fallback_context_count": len(evidence_packet.get("fallback_context") or []),
        "missing_evidence": list(evidence_packet.get("missing_evidence") or []),
        "satisfied_evidence": list(evidence_packet.get("satisfied_evidence") or []),
        "scenario_frame": evidence_packet.get("scenario_frame"),
        "evidence_contract": evidence_packet.get("evidence_contract"),
        "selected_evidence_ids": list(evidence_packet.get("selected_evidence_ids") or []),
        "missing_facets": list(evidence_packet.get("missing_facets") or []),
        "satisfied_facets": list(evidence_packet.get("satisfied_facets") or []),
        "failure_stage": evidence_packet.get("failure_stage"),
        "entity_anchor_status": diagnostics.get("entity_anchor_status"),
        "entity_first": diagnostics.get("entity_first"),
        "target_group_status": diagnostics.get("target_group_status"),
        "intent_evidence_status": diagnostics.get("intent_evidence_status"),
        "semantic_quality": diagnostics.get("semantic_quality"),
        "rejected_candidates": list(evidence_packet.get("rejected_candidates") or [])[:5],
    }


def _trace_synthesis(generation: Any) -> dict[str, Any]:
    if not isinstance(generation, dict):
        return _unavailable_stage("not_available")
    diagnostics = generation.get("diagnostics") if isinstance(generation.get("diagnostics"), dict) else {}
    synthesis = diagnostics.get("synthesis") if isinstance(diagnostics.get("synthesis"), dict) else {}
    outline = diagnostics.get("answer_outline") if isinstance(diagnostics.get("answer_outline"), dict) else {}
    if not synthesis and not outline:
        return _unavailable_stage("not_available")
    return {
        "status": "available",
        "mode": synthesis.get("mode") or generation.get("mode"),
        "validation_status": synthesis.get("validation_status"),
        "validation_error": synthesis.get("validation_error"),
        "fallback_reason": synthesis.get("fallback_reason") or diagnostics.get("fallback_reason"),
        "answer_shape": synthesis.get("answer_shape") or outline.get("answer_shape"),
        "stance": outline.get("stance"),
        "source_ids": list(synthesis.get("source_ids") or outline.get("source_ids") or []),
        "outline": outline,
    }


def _answer_packet_from_generation(generated: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(generated, dict):
        return None
    diagnostics = generated.get("diagnostics") if isinstance(generated.get("diagnostics"), dict) else {}
    packet = diagnostics.get("answer_packet") if isinstance(diagnostics, dict) else None
    return packet if isinstance(packet, dict) else None


def _query_plan_from_sources_or_errors(
    sources: list[dict[str, Any]],
    retrieval_errors: list[dict[str, Any]],
) -> dict[str, Any] | None:
    source_plan = _first_source_field(sources, "query_plan", source_type="rules")
    if isinstance(source_plan, dict):
        return source_plan
    for error in retrieval_errors:
        details = error.get("details") if isinstance(error, dict) else None
        if isinstance(details, dict) and isinstance(details.get("query_plan"), dict):
            return details["query_plan"]
    return None


def _rag_v2_from_sources_or_errors(
    sources: list[dict[str, Any]],
    retrieval_errors: list[dict[str, Any]],
) -> dict[str, Any] | None:
    source_rag_v2 = _first_source_field(sources, "rag_v2", source_type="rules")
    if isinstance(source_rag_v2, dict):
        return source_rag_v2
    for error in retrieval_errors:
        details = error.get("details") if isinstance(error, dict) else None
        if isinstance(details, dict) and isinstance(details.get("rag_v2"), dict):
            return details["rag_v2"]
    return None


def _evidence_packet_from_sources_or_errors(
    sources: list[dict[str, Any]],
    retrieval_errors: list[dict[str, Any]],
) -> dict[str, Any] | None:
    source_packet = _first_source_field(sources, "evidence_packet", source_type="rules")
    if isinstance(source_packet, dict):
        return source_packet
    for error in retrieval_errors:
        details = error.get("details") if isinstance(error, dict) else None
        if isinstance(details, dict) and isinstance(details.get("evidence_packet"), dict):
            return details["evidence_packet"]
    return None


def _first_source_field(sources: list[dict[str, Any]], key: str, *, source_type: str) -> Any:
    for source in sources:
        if source.get("source_type") == source_type and source.get(key) not in (None, ""):
            return source.get(key)
    return None


def _fingerprint_question(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def _compose_rule_ambiguity(details: dict[str, Any]) -> str:
    books = details.get("conflicting_books", [])
    if not books:
        return "I found multiple comparable rule sources. Please narrow the book or scope."
    labels = ", ".join(f"{book.get('book_title', book.get('book_id'))}" for book in books)
    return f"I found multiple comparable rule sources: {labels}. Please narrow the book or scope."
