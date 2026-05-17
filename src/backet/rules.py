from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import time
from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

import yaml

from backet.embeddings import EmbeddingBackend, cosine_similarity, resolve_embedding_backend
from backet.errors import AppError
from backet.models import CommandResult
from backet.paths import rules_db_path
from backet.rules_query_planner import (
    INTENT_ADVANCEMENT,
    INTENT_BROAD_EXPLANATION,
    INTENT_CONSEQUENCE,
    INTENT_COST,
    INTENT_DEFINITION,
    INTENT_DICE_POOL,
    INTENT_TARGETING,
    INTENT_TIMING,
    TARGETED_MECHANIC_ALIASES,
    TARGETED_POWER_ALIASES,
    RulesQueryPlan,
    RulesRetrievalQuery,
    plan_rules_query,
)
from backet.rules_scope import (
    AUTHORITATIVE_SCOPE_ROLES,
    AUTO_APPLY_CONFIDENCE,
    SCOPE_GENERATOR,
    SCOPE_ROLE_SOURCE,
    SCOPE_STATUS_APPLIED,
    SCOPE_STATUS_REJECTED,
    SCOPE_STATUS_SUGGESTED,
    SCOPE_STATUSES,
    SUGGESTION_CONFIDENCE,
    TAXONOMY_ENTRIES,
    RulePdfOutlineEntry,
    ScopeAssertionDraft,
    canonicalize_scope_tag,
    generate_scope_assertions,
    is_known_scope_tag,
    manifest_pages_label,
    normalize_scope_tags as normalize_scope_tags_from_taxonomy,
    parse_manifest_pages,
    status_for_confidence,
)
from backet.system_dependencies import has_tesseract, tesseract_command, tesseract_install_hint
from backet.vault import ensure_bootstrapped_vault

RULES_SCHEMA_VERSION = 5
RULES_RAG_V2_METADATA_SCHEMA_VERSION = 2
RULES_RAG_V2_RETRIEVAL_SCHEMA_VERSION = 1
RULE_BLOCK_STRUCTURE_SCHEMA_VERSION = 1
RULE_UNIT_SCHEMA_VERSION = 1
RULES_ENTITY_CATALOG_SCHEMA_VERSION = 1
DEFAULT_PAGE_MIN_CHARS = 80
DEFAULT_CHUNK_WORDS = 220
SUPPORTED_TIERS = {"core", "supplement"}
SUSPECT_CONFIDENCE_THRESHOLD = 0.7
AUDIT_REVIEW_DECISIONS = {"accepted", "ignored", "excluded", "skipped"}
AUDIT_RESOLVING_DECISIONS = {"accepted", "ignored", "excluded", "replaced"}
AUDIT_FINDING_LOW_CONFIDENCE_PAGE = "low_confidence_page"
AUDIT_FINDING_LOW_CONFIDENCE_CHUNK = "low_confidence_chunk"
AUDIT_FINDING_MAINTENANCE = "rules_index_maintenance"
AUDIT_FINDING_SOURCE = "source_pdf"
AUDIT_FINDING_SCOPE = "scope_assertion"
AUDIT_FINDING_CATEGORIES = {"maintenance", "review", "notice", "blocked", "scope"}
MANUAL_REPLACEMENT_MIN_CHARS = 20
REPAIR_SCORE_IMPROVEMENT_THRESHOLD = 0.15
FTS_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")
RULE_QUERY_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "ask",
    "at",
    "be",
    "by",
    "can",
    "do",
    "does",
    "explain",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "tell",
    "that",
    "the",
    "to",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "work",
    "working",
    "works",
}
SEMANTIC_WEIGHT = 0.45
LEXICAL_COVERAGE_WEIGHT = 0.18
LEXICAL_FREQUENCY_WEIGHT = 0.08
LEXICAL_PROXIMITY_WEIGHT = 0.32
LEXICAL_DEFINITION_WEIGHT = 0.12
LEXICAL_DEFINITION_QUERY_WEIGHT = 0.5
LEXICAL_INCIDENTAL_COST_PENALTY = 0.25
RAG_V2_EXACT_CHANNEL_CAP = 50
RAG_V2_PHRASE_CHANNEL_CAP = 30
RAG_V2_ALIAS_CHANNEL_CAP = 30
RAG_V2_METADATA_CHANNEL_CAP = 40
RAG_V2_RAW_FALLBACK_CHANNEL_CAP = 20
RAG_V2_NEIGHBOR_EXPANSION_SEED_LIMIT = 8
RAG_V2_NEIGHBOR_EXPANSION_PER_SEED = 4
RAG_V2_SELECTED_LIMIT_FLOOR = 1
RAG_V2_REJECTED_LIMIT = 8
RAG_V2_FALLBACK_CONTEXT_LIMIT = 6
SUPPLEMENT_SCOPE_BOOST = 0.15
RULE_SEMANTIC_LIMIT = 40
NON_ANSWER_SECTION_PENALTIES = {
    "toc": 0.45,
    "index": 0.4,
    "sheet": 0.35,
    "art": 0.3,
    "furniture": 0.35,
}
RETRIEVAL_FLAG_PENALTIES = {
    "suspect_ocr": 0.2,
    "very_short": 0.15,
    "navigational": 0.25,
    "art_heavy": 0.2,
}
RULE_UNIT_CHANNEL_CAP = 40
RULE_UNIT_LOW_CONFIDENCE_THRESHOLD = 0.65


@dataclass(slots=True)
class ExtractedPage:
    page_number: int
    text: str
    extraction_method: str
    char_count: int
    alpha_ratio: float
    confidence: float
    suspect: bool
    quality_flags: list[str]
    section_label: str


@dataclass(slots=True)
class RulesIngestProgressEvent:
    phase: str
    message: str
    current: int | None = None
    total: int | None = None
    counters: dict[str, int] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


RulesIngestProgressCallback = Callable[[RulesIngestProgressEvent], None]


@dataclass(slots=True)
class RuleSourceStatus:
    status: str
    pdf_path: str
    stored_fingerprint: str
    current_fingerprint: str | None
    available: bool
    repair_eligible: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "pdf_path": self.pdf_path,
            "stored_fingerprint": self.stored_fingerprint,
            "current_fingerprint": self.current_fingerprint,
            "available": self.available,
            "repair_eligible": self.repair_eligible,
            "message": self.message,
        }


@dataclass(slots=True)
class RuleAuditFinding:
    book_id: str
    target_type: str
    page_start: int | None
    page_end: int | None
    chunk_index: int | None
    finding_kind: str
    category: str
    severity: str
    content_hash: str
    review_state: str
    resolved: bool
    reason: str
    excerpt: str
    quality_flags: list[str] = field(default_factory=list)
    extraction_method: str | None = None
    confidence: float | None = None
    section_label: str | None = None
    allowed_decisions: list[str] = field(default_factory=list)
    source_status: RuleSourceStatus | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "book_id": self.book_id,
            "target_type": self.target_type,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_index": self.chunk_index,
            "finding_kind": self.finding_kind,
            "category": self.category,
            "severity": self.severity,
            "content_hash": self.content_hash,
            "review_state": self.review_state,
            "resolved": self.resolved,
            "reason": self.reason,
            "excerpt": self.excerpt,
            "quality_flags": self.quality_flags,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
            "section_label": self.section_label,
            "allowed_decisions": self.allowed_decisions,
        }
        if self.source_status is not None:
            data["source_status"] = self.source_status.to_dict()
        return data


def _emit_progress(
    progress: RulesIngestProgressCallback | None,
    *,
    phase: str,
    message: str,
    current: int | None = None,
    total: int | None = None,
    counters: dict[str, int] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    if progress is None:
        return
    progress(
        RulesIngestProgressEvent(
            phase=phase,
            message=message,
            current=current,
            total=total,
            counters=counters or {},
            details=details or {},
        )
    )


@dataclass(slots=True)
class BookRegistryEntry:
    book_id: str
    title: str
    pdf_path: str
    tier: str
    scope_tags: list[str]
    page_count: int
    pdf_fingerprint: str


@dataclass(slots=True)
class RuleSearchCandidate:
    chunk_id: int
    book_id: str
    book_title: str
    tier: str
    book_scope_tags: list[str]
    scope_tags: list[str]
    scope_assertions: list[dict[str, Any]]
    scope_fallback_used: bool
    page_start: int
    page_end: int
    chunk_index: int
    section_label: str
    content: str
    excerpt: str
    confidence: float
    extraction_method: str
    word_count: int
    content_hash: str
    section_kind: str
    retrieval_flags: list[str]
    rule_block_id: str | None = None
    block_kind: str | None = None
    source_window: str | None = None
    structure_schema_version: int | None = None
    structure_flags: list[str] = field(default_factory=list)
    rag_schema_version: int | None = None
    heading_path: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    entity_locations: list[dict[str, Any]] = field(default_factory=list)
    evidence_cues: list[str] = field(default_factory=list)
    rule_units: list[dict[str, Any]] = field(default_factory=list)
    retrieval_channels: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    exact_score: float = 0.0
    semantic_score: float = 0.0
    lexical_score: float = 0.0
    evidence_score: float = 0.0
    quality_penalty: float = 0.0
    score: float = 0.0
    match_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SemanticRulesSearch:
    candidates: list[tuple[sqlite3.Row, float]]
    retrieval_mode: str
    backend_name: str | None
    model_name: str | None
    indexed_chunks: int
    error: dict[str, Any] | None = None


@dataclass(slots=True)
class RuleChunkRetrievalMetadata:
    rag_schema_version: int
    heading_path: list[str]
    aliases: list[str]
    entity_locations: list[dict[str, Any]]
    evidence_cues: list[str]
    section_kind: str
    retrieval_flags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rag_schema_version": self.rag_schema_version,
            "heading_path": self.heading_path,
            "aliases": self.aliases,
            "entity_locations": self.entity_locations,
            "evidence_cues": self.evidence_cues,
            "section_kind": self.section_kind,
            "retrieval_flags": self.retrieval_flags,
        }


@dataclass(slots=True)
class RuleBlockStructure:
    block_id: str
    heading_path: list[str]
    block_kind: str
    clean_content: str
    source_window: str
    structure_flags: list[str]
    schema_version: int = RULE_BLOCK_STRUCTURE_SCHEMA_VERSION


@dataclass(slots=True)
class RuleUnit:
    unit_id: str
    book_id: str
    page_start: int
    page_end: int
    heading_path: list[str]
    source_chunk_ids: list[int]
    source_content_hash: str
    unit_kind: str
    authority_role: str
    entity_tags: list[str]
    mechanic_tags: list[str]
    answer_facets: list[str]
    confidence: float
    warnings: list[str]
    source_window: str
    extractor_backend: str = "deterministic"
    extractor_model: str = "rules-rule-units-v1"
    schema_version: int = RULE_UNIT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "book_id": self.book_id,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "heading_path": self.heading_path,
            "source_chunk_ids": self.source_chunk_ids,
            "source_content_hash": self.source_content_hash,
            "unit_kind": self.unit_kind,
            "authority_role": self.authority_role,
            "entity_tags": self.entity_tags,
            "mechanic_tags": self.mechanic_tags,
            "answer_facets": self.answer_facets,
            "confidence": self.confidence,
            "warnings": self.warnings,
            "source_window": self.source_window,
            "extractor_backend": self.extractor_backend,
            "extractor_model": self.extractor_model,
            "schema_version": self.schema_version,
        }


@dataclass(slots=True)
class RagV2ChannelDiagnostics:
    channel: str
    cap: int
    elapsed_ms: float
    candidate_count: int
    query: str | None = None
    raw_fallback: bool = False
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "cap": self.cap,
            "elapsed_ms": self.elapsed_ms,
            "candidate_count": self.candidate_count,
            "query": self.query,
            "raw_fallback": self.raw_fallback,
            "error": self.error,
        }


@dataclass(slots=True)
class RagV2EvidencePacket:
    evidence_status: str
    selected_evidence: list[dict[str, Any]]
    fallback_context: list[dict[str, Any]]
    rejected_candidates: list[dict[str, Any]]
    missing_evidence: list[str]
    satisfied_evidence: list[str]
    candidate_counts: dict[str, int]
    retrieval_diagnostics: dict[str, Any]
    query_plan: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RULES_RAG_V2_RETRIEVAL_SCHEMA_VERSION,
            "evidence_status": self.evidence_status,
            "selected_evidence": self.selected_evidence,
            "fallback_context": self.fallback_context,
            "rejected_candidates": self.rejected_candidates,
            "missing_evidence": self.missing_evidence,
            "satisfied_evidence": self.satisfied_evidence,
            "candidate_counts": self.candidate_counts,
            "retrieval_diagnostics": self.retrieval_diagnostics,
            "query_plan": self.query_plan,
        }


def open_rules_connection(vault_root: Path) -> sqlite3.Connection:
    ensure_bootstrapped_vault(vault_root)
    db_path = rules_db_path(vault_root)
    return open_rules_database(db_path)


def open_rules_database(db_path: Path, readonly: bool = False) -> sqlite3.Connection:
    db_path = db_path.expanduser().resolve()
    if readonly:
        if not db_path.exists():
            raise AppError(
                code="rules_db_missing",
                message="Rules database is missing.",
                hint="Export or ingest rules before querying them.",
                details={"rules_db": str(db_path)},
                exit_code=2,
            )
        connection = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    ensure_rules_schema(connection)
    return connection


def ensure_rules_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS books (
            book_id TEXT PRIMARY KEY,
            book_title TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            pdf_fingerprint TEXT NOT NULL,
            tier TEXT NOT NULL,
            scope_tags_json TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            extraction_backend TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_ingested_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS page_audit (
            book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
            page_number INTEGER NOT NULL,
            extraction_method TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            alpha_ratio REAL NOT NULL,
            confidence REAL NOT NULL,
            suspect INTEGER NOT NULL,
            quality_flags_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            section_label TEXT NOT NULL,
            text_excerpt TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (book_id, page_number)
        );

        CREATE TABLE IF NOT EXISTS rule_chunks (
            id INTEGER PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
            page_start INTEGER NOT NULL,
            page_end INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            section_label TEXT NOT NULL,
            content TEXT NOT NULL,
            excerpt TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            confidence REAL NOT NULL,
            extraction_method TEXT NOT NULL,
            scope_tags_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            rule_block_id TEXT NOT NULL DEFAULT '',
            heading_path_json TEXT NOT NULL DEFAULT '[]',
            block_kind TEXT NOT NULL DEFAULT 'unknown',
            clean_content TEXT NOT NULL DEFAULT '',
            source_window TEXT NOT NULL DEFAULT '',
            structure_flags_json TEXT NOT NULL DEFAULT '[]',
            structure_schema_version INTEGER NOT NULL DEFAULT 0,
            UNIQUE (book_id, page_start, chunk_index)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS rule_chunks_fts USING fts5(
            chunk_id UNINDEXED,
            book_id UNINDEXED,
            book_title,
            tier,
            scope_tags,
            section_label,
            content
        );

        CREATE TABLE IF NOT EXISTS repair_history (
            id INTEGER PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
            pages_spec TEXT NOT NULL,
            force_ocr INTEGER NOT NULL,
            repaired_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rule_audit_reviews (
            id INTEGER PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
            target_type TEXT NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            chunk_index INTEGER,
            finding_kind TEXT NOT NULL,
            decision TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            decided_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rule_audit_reviews_lookup
        ON rule_audit_reviews(book_id, target_type, page_start, chunk_index, finding_kind, content_hash);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_audit_reviews_unique
        ON rule_audit_reviews(
            book_id,
            target_type,
            COALESCE(page_start, -1),
            COALESCE(page_end, -1),
            COALESCE(chunk_index, -1),
            finding_kind,
            content_hash
        );

        CREATE TABLE IF NOT EXISTS rule_retrieval_exclusions (
            id INTEGER PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
            chunk_id INTEGER REFERENCES rule_chunks(id) ON DELETE CASCADE,
            page_start INTEGER NOT NULL,
            page_end INTEGER NOT NULL,
            chunk_index INTEGER,
            content_hash TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE (book_id, chunk_id, content_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_rule_retrieval_exclusions_chunk
        ON rule_retrieval_exclusions(chunk_id, content_hash);

        CREATE INDEX IF NOT EXISTS idx_rule_retrieval_exclusions_book
        ON rule_retrieval_exclusions(book_id, page_start, chunk_index);

        CREATE TABLE IF NOT EXISTS rule_page_text_overrides (
            id INTEGER PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
            page_number INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            alpha_ratio REAL NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            replaced_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rule_page_text_overrides_book
        ON rule_page_text_overrides(book_id, page_number, replaced_at);

        CREATE TABLE IF NOT EXISTS rule_source_relinks (
            id INTEGER PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
            old_pdf_path TEXT NOT NULL,
            new_pdf_path TEXT NOT NULL,
            old_fingerprint TEXT NOT NULL,
            new_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL,
            forced INTEGER NOT NULL,
            relinked_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rule_source_relinks_book
        ON rule_source_relinks(book_id, relinked_at);

        CREATE TABLE IF NOT EXISTS rule_chunk_embeddings (
            chunk_id INTEGER PRIMARY KEY REFERENCES rule_chunks(id) ON DELETE CASCADE,
            backend TEXT NOT NULL,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            embedding_json TEXT NOT NULL,
            embedded_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rule_chunk_retrieval_metadata (
            chunk_id INTEGER PRIMARY KEY REFERENCES rule_chunks(id) ON DELETE CASCADE,
            content_hash TEXT NOT NULL,
            section_kind TEXT NOT NULL,
            retrieval_flags_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rule_units (
            unit_id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
            page_start INTEGER NOT NULL,
            page_end INTEGER NOT NULL,
            heading_path_json TEXT NOT NULL,
            source_chunk_ids_json TEXT NOT NULL,
            primary_chunk_id INTEGER REFERENCES rule_chunks(id) ON DELETE CASCADE,
            source_content_hash TEXT NOT NULL,
            unit_kind TEXT NOT NULL,
            authority_role TEXT NOT NULL,
            entity_tags_json TEXT NOT NULL,
            mechanic_tags_json TEXT NOT NULL,
            answer_facets_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            warnings_json TEXT NOT NULL,
            source_window TEXT NOT NULL,
            extractor_backend TEXT NOT NULL,
            extractor_model TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rule_units_book
        ON rule_units(book_id, unit_kind, authority_role);

        CREATE INDEX IF NOT EXISTS idx_rule_units_primary_chunk
        ON rule_units(primary_chunk_id);

        CREATE TABLE IF NOT EXISTS rule_entities (
            entity_id TEXT PRIMARY KEY,
            book_id TEXT,
            canonical_name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            aliases_json TEXT NOT NULL,
            source_anchors_json TEXT NOT NULL,
            source_pages_json TEXT NOT NULL,
            scope_tags_json TEXT NOT NULL,
            provenance TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            catalog_schema_version INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rule_entity_aliases (
            normalized_alias TEXT NOT NULL,
            alias TEXT NOT NULL,
            entity_id TEXT NOT NULL REFERENCES rule_entities(entity_id) ON DELETE CASCADE,
            provenance TEXT NOT NULL,
            confidence REAL NOT NULL,
            PRIMARY KEY (normalized_alias, entity_id, provenance)
        );

        CREATE INDEX IF NOT EXISTS idx_rule_entity_aliases_lookup
        ON rule_entity_aliases(normalized_alias);

        CREATE INDEX IF NOT EXISTS idx_rule_entities_book
        ON rule_entities(book_id, entity_type, canonical_name);

        CREATE TABLE IF NOT EXISTS rule_scope_assertions (
            id INTEGER PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
            tag TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            evidence_json TEXT NOT NULL,
            generator TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rule_scope_assertions_book
        ON rule_scope_assertions(book_id, status, tag);

        CREATE INDEX IF NOT EXISTS idx_rule_scope_assertions_span
        ON rule_scope_assertions(book_id, page_start, page_end);

        CREATE TABLE IF NOT EXISTS rule_chunk_scope_assertions (
            chunk_id INTEGER NOT NULL REFERENCES rule_chunks(id) ON DELETE CASCADE,
            assertion_id INTEGER NOT NULL REFERENCES rule_scope_assertions(id) ON DELETE CASCADE,
            PRIMARY KEY (chunk_id, assertion_id)
        );

        CREATE TABLE IF NOT EXISTS rules_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    _ensure_rule_chunk_structure_schema(connection)
    _ensure_rule_chunk_retrieval_metadata_schema(connection)
    _ensure_rule_units_schema(connection)
    _ensure_seed_rule_entities(connection)
    connection.execute(
        """
        INSERT INTO rules_meta (key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(RULES_SCHEMA_VERSION),),
    )
    _backfill_source_scope_assertions(connection)
    connection.commit()


def _ensure_rule_chunk_structure_schema(connection: sqlite3.Connection) -> None:
    existing = _table_columns(connection, "rule_chunks")
    additions = {
        "rule_block_id": "TEXT NOT NULL DEFAULT ''",
        "heading_path_json": "TEXT NOT NULL DEFAULT '[]'",
        "block_kind": "TEXT NOT NULL DEFAULT 'unknown'",
        "clean_content": "TEXT NOT NULL DEFAULT ''",
        "source_window": "TEXT NOT NULL DEFAULT ''",
        "structure_flags_json": "TEXT NOT NULL DEFAULT '[]'",
        "structure_schema_version": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, column_type in additions.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE rule_chunks ADD COLUMN {column} {column_type}")


def _ensure_rule_chunk_retrieval_metadata_schema(connection: sqlite3.Connection) -> None:
    existing = _table_columns(connection, "rule_chunk_retrieval_metadata")
    additions = {
        "rag_schema_version": "INTEGER",
        "heading_path_json": "TEXT",
        "aliases_json": "TEXT",
        "entity_locations_json": "TEXT",
        "evidence_cues_json": "TEXT",
    }
    for column, column_type in additions.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE rule_chunk_retrieval_metadata ADD COLUMN {column} {column_type}")


def _ensure_rule_units_schema(connection: sqlite3.Connection) -> None:
    existing = _table_columns(connection, "rule_units")
    additions = {
        "primary_chunk_id": "INTEGER REFERENCES rule_chunks(id) ON DELETE CASCADE",
        "extractor_backend": "TEXT NOT NULL DEFAULT 'deterministic'",
        "extractor_model": "TEXT NOT NULL DEFAULT 'rules-rule-units-v1'",
    }
    for column, column_type in additions.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE rule_units ADD COLUMN {column} {column_type}")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rule_units_book
        ON rule_units(book_id, unit_kind, authority_role)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rule_units_primary_chunk
        ON rule_units(primary_chunk_id)
        """
    )


def _ensure_seed_rule_entities(connection: sqlite3.Connection) -> None:
    for entry in _seed_rule_entity_entries():
        _upsert_rule_entity(connection, entry)


def _seed_rule_entity_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for canonical, meta in TARGETED_MECHANIC_ALIASES.items():
        entries.append(
            {
                "entity_id": "seed:mechanic:" + _slugify(canonical),
                "book_id": None,
                "canonical_name": canonical,
                "entity_type": "mechanic",
                "aliases": _dedupe_text_values(str(alias) for alias in meta["aliases"]),
                "source_anchors": [],
                "source_pages": [],
                "scope_tags": _dedupe_text_values(str(tag) for tag in meta.get("scope_tags", ())),
                "provenance": "curated_seed",
                "content_hash": fingerprint_text(json.dumps(meta, sort_keys=True)),
                "confidence": 0.9,
            }
        )
    for canonical, meta in TARGETED_POWER_ALIASES.items():
        entity_type = "discipline" if str(canonical).casefold() == "dominate" else "power"
        entries.append(
            {
                "entity_id": f"seed:{entity_type}:" + _slugify(canonical),
                "book_id": None,
                "canonical_name": canonical,
                "entity_type": entity_type,
                "aliases": _dedupe_text_values(str(alias) for alias in meta["aliases"]),
                "source_anchors": [],
                "source_pages": [],
                "scope_tags": _dedupe_text_values(str(tag) for tag in meta.get("scope_tags", ())),
                "provenance": "curated_seed",
                "content_hash": fingerprint_text(json.dumps(meta, sort_keys=True)),
                "confidence": 0.9,
            }
        )
    return entries


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
    except sqlite3.DatabaseError:
        return set()


def ingest_rulebook(
    vault_root: Path,
    pdf_path: Path,
    book_id: str,
    title: str | None,
    tier: str,
    scope_tags: list[str] | None = None,
    force_ocr: bool = False,
    pages_spec: str | None = None,
    progress: RulesIngestProgressCallback | None = None,
) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    normalized_tier = tier.strip().lower()
    if normalized_tier not in SUPPORTED_TIERS:
        raise AppError(
            code="rules_tier_invalid",
            message=f"Unsupported book tier: {tier}",
            hint="Use either `core` or `supplement`.",
            details={"tier": tier},
            exit_code=2,
        )
    normalized_tags = normalize_scope_tags(scope_tags or [])
    if not pdf_path.exists() or not pdf_path.is_file():
        raise AppError(
            code="rules_pdf_missing",
            message=f"Rulebook PDF not found: {pdf_path}",
            hint="Provide a readable local PDF path.",
            details={"pdf_path": str(pdf_path)},
            exit_code=2,
        )

    resolved_title = title or pdf_path.stem
    rules_db = rules_db_path(vault_root)
    _emit_progress(
        progress,
        phase="inspect",
        message="Inspecting rulebook PDF",
        current=0,
        total=1,
        details={
            "book_id": book_id,
            "book_title": resolved_title,
            "tier": normalized_tier,
            "pdf_path": str(pdf_path.resolve()),
            "rules_db": str(rules_db),
            "vault": str(vault_root),
        },
    )

    fitz = _require_pymupdf()
    document = fitz.open(str(pdf_path))
    try:
        page_count = document.page_count
        outline = _extract_pdf_outline(document)
        page_numbers = parse_pages_spec(pages_spec, document.page_count)
        _emit_progress(
            progress,
            phase="start",
            message="Starting rulebook ingestion",
            current=0,
            total=len(page_numbers),
            details={
                "book_id": book_id,
                "book_title": resolved_title,
                "tier": normalized_tier,
                "pdf_path": str(pdf_path.resolve()),
                "rules_db": str(rules_db),
                "vault": str(vault_root),
                "pages_spec": pages_spec,
                "page_count": page_count,
                "selected_pages": len(page_numbers),
            },
        )
        extracted_pages = _extract_pages(document, pdf_path, page_numbers, force_ocr=force_ocr, progress=progress)
    finally:
        document.close()

    if not extracted_pages:
        raise AppError(
            code="rules_no_pages_extracted",
            message="No rulebook pages were extracted for ingestion.",
            hint="Check the PDF and requested page range, then try again.",
            details={"pdf_path": str(pdf_path), "pages": pages_spec},
            exit_code=2,
        )

    _emit_progress(progress, phase="fingerprint", message="Fingerprinting PDF", current=0, total=1)
    pdf_fingerprint = fingerprint_bytes(pdf_path.read_bytes())
    _emit_progress(progress, phase="fingerprint", message="Fingerprinted PDF", current=1, total=1)
    entry = BookRegistryEntry(
        book_id=book_id,
        title=resolved_title,
        pdf_path=str(pdf_path.resolve()),
        tier=normalized_tier,
        scope_tags=normalized_tags,
        page_count=page_count,
        pdf_fingerprint=pdf_fingerprint,
    )

    db_created = not rules_db_path(vault_root).exists()
    created: list[str] = []
    if db_created:
        created.append(str(rules_db_path(vault_root).relative_to(vault_root)))

    with closing(open_rules_connection(vault_root)) as connection:
        _upsert_book(connection, entry)
        _replace_pages(connection, entry, extracted_pages, pages_spec=pages_spec, progress=progress)
        _emit_progress(progress, phase="scope", message="Generating rule scopes", current=0, total=1)
        scope_summary = _generate_and_apply_scope_assertions(
            connection,
            entry=entry,
            pages=extracted_pages,
            outline=outline,
        )
        _emit_progress(progress, phase="scope", message="Generated rule scopes", current=1, total=1)
        _rebuild_rule_chunks_fts(connection, book_id, progress=progress)
        semantic_index = _try_index_rule_chunks(connection, book_id=book_id, full=False, progress=progress)
        rule_units = _refresh_rule_units(connection, book_id=book_id, full=False)
        _emit_progress(progress, phase="audit", message="Summarizing ingest quality", current=0, total=1)
        audit_summary = _audit_summary(connection, book_id)
        _emit_progress(progress, phase="audit", message="Summarized ingest quality", current=1, total=1)
        connection.commit()

    return CommandResult(
        message="Ingested rulebook PDF",
        created=created,
        data={
            "vault": str(vault_root),
            "rules_db": str(rules_db_path(vault_root)),
            "book_id": book_id,
            "book_title": resolved_title,
            "tier": normalized_tier,
            "scope_tags": normalized_tags,
            "scope_assertions": scope_summary,
            "pdf_path": str(pdf_path.resolve()),
            "pages_processed": len(extracted_pages),
            "pages_spec": pages_spec,
            "ocr_used_on_pages": [page.page_number for page in extracted_pages if page.extraction_method == "ocr"],
            "suspect_pages": audit_summary["suspect_pages"],
            "chunk_count": audit_summary["chunk_count"],
            "semantic_index": semantic_index,
            "rule_units": rule_units,
        },
    )


def query_rules(
    vault_root: Path,
    query: str,
    limit: int,
    book_id: str | None = None,
    scope_tags: list[str] | None = None,
) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    with closing(open_rules_connection(vault_root)) as connection:
        return query_rules_connection(
            connection,
            query=query,
            limit=limit,
            book_id=book_id,
            scope_tags=scope_tags or [],
            db_label=str(vault_root),
            data_key="vault",
        )


def query_rules_connection(
    connection: sqlite3.Connection,
    query: str,
    limit: int,
    book_id: str | None = None,
    scope_tags: list[str] | None = None,
    db_label: str | None = None,
    data_key: str = "rules_db",
    embedding_backend: EmbeddingBackend | None = None,
) -> CommandResult:
    if limit <= 0:
        raise AppError(
            code="rules_limit_invalid",
            message="Rules query limits must be positive.",
            hint="Use a limit greater than zero.",
            details={"limit": limit},
            exit_code=2,
        )
    query_plan = _resolve_query_plan_entities(connection, plan_rules_query(query))
    query_terms = _rules_query_terms(query_plan.scoring_query) or _rules_query_terms(query_plan.semantic_query)
    normalized_tags = normalize_scope_tags(scope_tags or [])
    excluded_chunks = _active_excluded_chunk_count(connection, book_id)
    corpus_blockers = _query_corpus_blockers(connection, book_id=book_id)
    exact_rows, semantic, channel_matches, rag_v2_diagnostics = _generate_rag_v2_candidates(
        connection,
        query_plan=query_plan,
        book_id=book_id,
        scope_tags=normalized_tags,
        exact_limit=max(limit * 8, RAG_V2_EXACT_CHANNEL_CAP),
        semantic_limit=max(limit * 8, RULE_SEMANTIC_LIMIT),
        embedding_backend=embedding_backend,
    )
    if not rag_v2_diagnostics.get("channels") and not _rules_query_terms(query_plan.semantic_query):
        raise AppError(
            code="rules_query_invalid",
            message="Rules queries need at least one searchable term.",
            hint="Use a query containing letters or numbers.",
            details={"query": query, "query_plan": query_plan.to_dict()},
            exit_code=2,
        )

    rows = _merge_rule_candidates(
        exact_rows,
        semantic.candidates,
        scope_tags=normalized_tags,
        query_terms=query_terms,
        definition_query=INTENT_DEFINITION in query_plan.intents or _is_definition_rule_query(query),
        channel_matches=channel_matches,
    )
    _attach_rule_units_to_candidates(connection, rows)
    rows = _rerank_rag_v2_candidates(rows, query_plan=query_plan)
    neighbor_rows = _expand_rag_v2_neighbor_rows(
        connection,
        seeds=rows,
        query_plan=query_plan,
        book_id=book_id,
        scope_tags=normalized_tags,
        limit=RAG_V2_NEIGHBOR_EXPANSION_PER_SEED,
    )
    rag_v2_diagnostics["neighbor_expansion"] = {
        "seed_limit": RAG_V2_NEIGHBOR_EXPANSION_SEED_LIMIT,
        "candidate_count": len(neighbor_rows),
    }
    if neighbor_rows:
        neighbor_channel_matches = {int(row["chunk_id"]): {"neighbor_expansion"} for row in neighbor_rows}
        neighbor_candidates = _merge_rule_candidates(
            neighbor_rows,
            [],
            scope_tags=normalized_tags,
            query_terms=query_terms,
            definition_query=INTENT_DEFINITION in query_plan.intents or _is_definition_rule_query(query),
            channel_matches=neighbor_channel_matches,
        )
        rows = _merge_candidate_lists(rows, neighbor_candidates)
        _attach_rule_units_to_candidates(connection, rows)
        rows = _rerank_rag_v2_candidates(rows, query_plan=query_plan)
    if not rows:
        raise AppError(
            code="rules_query_empty",
            message="No ingested rule chunks matched the requested query.",
            hint="Adjust the query or ingest the relevant rulebook first.",
            details={
                "query": query,
                "book_id": book_id,
                "scope_tags": normalized_tags,
                "query_plan": query_plan.to_dict(),
                "rag_v2": rag_v2_diagnostics,
                "retrieval_mode": semantic.retrieval_mode,
                "semantic_error": semantic.error,
                "corpus_blockers": corpus_blockers,
                "reviewed_exclusions": {"excluded_chunks": excluded_chunks},
            },
            exit_code=2,
        )
    primary_rows, fallback_rows, ambiguity = _apply_precedence(rows, scope_tags=normalized_tags, explicit_book_id=book_id)
    if ambiguity is not None:
        ambiguity["evidence_status"] = "ambiguous"
        ambiguity["query_plan"] = query_plan.to_dict()
        ambiguity["rag_v2"] = rag_v2_diagnostics
        raise AppError(
            code="rules_query_ambiguous",
            message="Multiple supplement-specific rulebooks match this query with comparable precedence.",
            hint="Re-run the query with `--book-id` or narrower `--scope-tag` filters.",
            details=ambiguity,
            exit_code=2,
        )

    primary = [_row_to_rule_result(row) for row in primary_rows[:limit]]
    fallback = [_row_to_rule_result(row) for row in fallback_rows[:limit]]
    evidence_packet = _build_rag_v2_evidence_packet(
        query_plan=query_plan,
        primary_rows=primary_rows,
        fallback_rows=fallback_rows,
        all_rows=rows,
        limit=limit,
        rag_v2_diagnostics=rag_v2_diagnostics,
        semantic=semantic,
    )
    label = db_label or "rules.sqlite3"
    return CommandResult(
        message="Retrieved ingested rule chunks",
        data={
            data_key: label,
            "query": query,
            "query_plan": query_plan.to_dict(),
            "book_id": book_id,
            "scope_tags": normalized_tags,
            "retrieval_mode": semantic.retrieval_mode,
            "embedding_backend": semantic.backend_name,
            "embedding_model": semantic.model_name,
            "candidate_counts": {
                "exact": len(exact_rows),
                "semantic": len(semantic.candidates),
                "merged": len(rows),
                "semantic_indexed_chunks": semantic.indexed_chunks,
                "review_excluded": excluded_chunks,
                "planned_exact_queries": _channel_count(rag_v2_diagnostics, "planned_exact"),
                "rag_v2_channels": len(rag_v2_diagnostics.get("channels", [])),
            },
            "planned_retrieval": {
                "exact_queries": [
                    channel
                    for channel in rag_v2_diagnostics.get("channels", [])
                    if str(channel.get("channel", "")).startswith("planned_exact")
                ],
                "raw_fallback_used": bool(rag_v2_diagnostics.get("raw_fallback_used")),
                "semantic_query": query_plan.semantic_query,
            },
            "rag_v2": rag_v2_diagnostics,
            "evidence_packet": evidence_packet.to_dict(),
            "evidence_status": evidence_packet.evidence_status,
            "semantic_quality": rag_v2_diagnostics.get("semantic_quality"),
            "reviewed_exclusions": {"excluded_chunks": excluded_chunks},
            "corpus_blockers": corpus_blockers,
            "semantic_error": semantic.error,
            "primary_results": primary,
            "fallback_results": fallback,
        },
    )


def index_rules(vault_root: Path, book_id: str | None = None, full: bool = False) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    with closing(open_rules_connection(vault_root)) as connection:
        books = _fetch_books(connection, book_id=book_id)
        if not books:
            raise AppError(
                code="rules_book_missing",
                message="No ingested rulebooks matched the requested indexing scope.",
                hint="Ingest a rulebook first or choose a different `--book-id`.",
                details={"book_id": book_id},
                exit_code=2,
            )
        backend = resolve_embedding_backend()
        summary = _index_rule_chunks(connection, backend=backend, book_id=book_id, full=full)
        connection.commit()

    return CommandResult(
        message="Indexed ingested rule chunks",
        data={
            "vault": str(vault_root),
            "rules_db": str(rules_db_path(vault_root)),
            "book_id": book_id,
            "full": full,
            **summary,
        },
    )


def audit_rules(vault_root: Path, book_id: str | None = None) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    with closing(open_rules_connection(vault_root)) as connection:
        books = _fetch_books(connection, book_id=book_id)
        if not books:
            raise AppError(
                code="rules_book_missing",
                message="No ingested rulebooks matched the requested audit scope.",
                hint="Ingest a rulebook first or choose a different `--book-id`.",
                details={"book_id": book_id},
                exit_code=2,
            )

        suspects: list[dict[str, Any]] = []
        for book in books:
            suspects.append(_rules_audit_book_report(connection, book))
        semantic_index = _inspect_rule_semantic_index_for_current_backend(connection, book_id=book_id)
        corpus_health = _inspect_rules_corpus_health(connection, books=books, book_reports=suspects)

    return CommandResult(
        message="Audited ingested rulebooks",
        data={
            "vault": str(vault_root),
            "book_id": book_id,
            "books": suspects,
            "semantic_index": semantic_index,
            "corpus_health": corpus_health,
            "maintenance": _rules_audit_maintenance_findings(semantic_index),
        },
    )


def audit_rule_scopes(vault_root: Path, book_id: str | None = None) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    with closing(open_rules_connection(vault_root)) as connection:
        books = _fetch_books(connection, book_id=book_id)
        if not books:
            raise AppError(
                code="rules_book_missing",
                message="No ingested rulebooks matched the requested scope audit.",
                hint="Ingest a rulebook first or choose a different `--book-id`.",
                details={"book_id": book_id},
                exit_code=2,
            )
        summaries = []
        for book in books:
            summary = _scope_summary(connection, book_id=book["book_id"])
            summaries.append(
                {
                    "book_id": book["book_id"],
                    "book_title": book["book_title"],
                    "tier": book["tier"],
                    **summary,
                }
            )
    return CommandResult(
        message="Audited rule scope assertions",
        data={"vault": str(vault_root), "book_id": book_id, "books": summaries},
    )


def inspect_rule_units(vault_root: Path, book_id: str | None = None, unit_id: str | None = None) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    with closing(open_rules_connection(vault_root)) as connection:
        if unit_id:
            row = connection.execute(
                """
                SELECT
                    ru.*,
                    b.book_title,
                    rc.section_label,
                    rc.excerpt AS chunk_excerpt
                FROM rule_units ru
                JOIN books b ON b.book_id = ru.book_id
                LEFT JOIN rule_chunks rc ON rc.id = ru.primary_chunk_id
                WHERE ru.unit_id = ?
                """,
                (unit_id,),
            ).fetchone()
            if row is None:
                raise AppError(
                    code="rule_unit_missing",
                    message="No derived rule unit matches the requested ID.",
                    hint="Run `backet rules units <vault>` to list available units.",
                    details={"unit_id": unit_id},
                    exit_code=2,
                )
            return CommandResult(
                message="Inspected derived rule unit",
                data={"vault": str(vault_root), "unit": _rule_unit_row_to_dict(row)},
            )

        summary = _rule_units_summary(connection, book_id=book_id)
        parameters: list[Any] = []
        where_clause = ""
        if book_id:
            where_clause = "WHERE ru.book_id = ?"
            parameters.append(book_id)
        rows = connection.execute(
            f"""
            SELECT
                ru.*,
                b.book_title,
                rc.section_label,
                rc.excerpt AS chunk_excerpt
            FROM rule_units ru
            JOIN books b ON b.book_id = ru.book_id
            LEFT JOIN rule_chunks rc ON rc.id = ru.primary_chunk_id
            {where_clause}
            ORDER BY ru.book_id, ru.page_start, ru.unit_kind, ru.unit_id
            LIMIT 25
            """,
            parameters,
        ).fetchall()
    return CommandResult(
        message="Inspected derived rule units",
        data={
            "vault": str(vault_root),
            "book_id": book_id,
            "summary": summary,
            "units": [_rule_unit_row_to_dict(row, include_window=False) for row in rows],
            "next_command": "backet rules index <vault> --full" if summary["missing_rule_units"] or summary["stale_rule_units"] else None,
        },
    )


def _rules_audit_book_report(connection: sqlite3.Connection, book: sqlite3.Row) -> dict[str, Any]:
    current_book_id = str(book["book_id"])
    source_status = _inspect_rule_source_status(book)
    structure_health = _rules_structure_health(connection, current_book_id)
    pages = connection.execute(
        """
        SELECT * FROM page_audit
        WHERE book_id = ? AND suspect = 1
        ORDER BY page_number
        """,
        (current_book_id,),
    ).fetchall()
    ocr_pages = connection.execute(
        """
        SELECT page_number FROM page_audit
        WHERE book_id = ? AND extraction_method = 'ocr'
        ORDER BY page_number
        """,
        (current_book_id,),
    ).fetchall()
    suspect_chunks = connection.execute(
        """
        SELECT
            rc.*,
            m.section_kind,
            m.retrieval_flags_json,
            m.content_hash AS metadata_content_hash
        FROM rule_chunks rc
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        WHERE rc.book_id = ? AND rc.confidence < ?
        ORDER BY rc.page_start, rc.chunk_index
        """,
        (current_book_id, SUSPECT_CONFIDENCE_THRESHOLD),
    ).fetchall()
    chunk_count = connection.execute(
        "SELECT COUNT(*) AS count FROM rule_chunks WHERE book_id = ?",
        (current_book_id,),
    ).fetchone()["count"]

    findings: list[RuleAuditFinding] = []
    for page in pages:
        findings.append(_audit_finding_from_page(connection, book, page, source_status))
    page_finding_keys = {(finding.page_start, finding.finding_kind) for finding in findings}
    for chunk in suspect_chunks:
        key = (int(chunk["page_start"]), AUDIT_FINDING_LOW_CONFIDENCE_PAGE)
        if key in page_finding_keys:
            continue
        findings.append(_audit_finding_from_chunk(connection, book, chunk, source_status))

    notices = _audit_notices_for_pages(connection, book, ocr_pages, findings)
    review_cards = _build_review_cards(findings)
    category_counts = _audit_category_counts(findings + notices)
    resolved_count = sum(1 for finding in findings if finding.resolved)
    reviewable_pages = sorted({card["page_start"] for card in review_cards})
    excluded_chunks = _active_excluded_chunk_count(connection, current_book_id)

    report = {
        "book_id": current_book_id,
        "book_title": book["book_title"],
        "tier": book["tier"],
        "scope_tags": json.loads(book["scope_tags_json"]),
        "page_count": int(book["page_count"]),
        "chunk_count": int(chunk_count),
        "structure_health": structure_health,
        "ocr_fallback_pages": [int(row["page_number"]) for row in ocr_pages],
        "source_status": source_status.to_dict(),
        "repair_eligible": source_status.repair_eligible,
        "review_summary": {
            "pending_pages": len(reviewable_pages),
            "pending_findings": sum(1 for finding in findings if not finding.resolved and finding.category in {"review", "blocked"}),
            "resolved_findings": resolved_count,
            "notices": category_counts.get("notice", 0),
            "blocked": category_counts.get("blocked", 0),
            "pending_blocked": sum(1 for finding in findings if not finding.resolved and finding.category == "blocked"),
            "excluded_chunks": excluded_chunks,
            "by_category": category_counts,
        },
        "review_cards": review_cards,
        "findings": [finding.to_dict() for finding in findings],
        "notices": [notice.to_dict() for notice in notices],
        "suspect_pages": [
            {
                "page_number": page["page_number"],
                "extraction_method": page["extraction_method"],
                "confidence": page["confidence"],
                "quality_flags": json.loads(page["quality_flags_json"]),
                "content_hash": page["content_hash"],
                "review_state": _audit_review_state(
                    connection,
                    book_id=current_book_id,
                    target_type="page",
                    page_start=int(page["page_number"]),
                    page_end=int(page["page_number"]),
                    chunk_index=None,
                    finding_kind=AUDIT_FINDING_LOW_CONFIDENCE_PAGE,
                    content_hash=page["content_hash"],
                )[0],
                "excerpt": page["text_excerpt"],
            }
            for page in pages
        ],
        "suspect_chunks": [
            {
                "page_start": row["page_start"],
                "chunk_index": row["chunk_index"],
                "confidence": row["confidence"],
                "section_label": row["section_label"],
                "content_hash": row["content_hash"],
                "review_state": _audit_review_state(
                    connection,
                    book_id=current_book_id,
                    target_type="chunk",
                    page_start=int(row["page_start"]),
                    page_end=int(row["page_end"]),
                    chunk_index=int(row["chunk_index"]),
                    finding_kind=AUDIT_FINDING_LOW_CONFIDENCE_CHUNK,
                    content_hash=row["content_hash"],
                )[0],
                "excerpt": row["excerpt"],
            }
            for row in suspect_chunks
        ],
    }
    report["corpus_health"] = _rules_corpus_action_for_book(
        report,
        semantic_index=None,
        vault_label="<vault>",
    )
    return report


def _inspect_rules_corpus_health(
    connection: sqlite3.Connection,
    *,
    books: list[sqlite3.Row],
    book_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        backend = resolve_embedding_backend()
    except AppError as error:
        backend = None
        backend_error = _semantic_error(error)
    else:
        backend_error = None

    reports_by_id = {str(report.get("book_id")): report for report in book_reports}
    book_health: list[dict[str, Any]] = []
    for book in books:
        current_book_id = str(book["book_id"])
        report = reports_by_id.get(current_book_id, {})
        semantic_index = None
        if backend is not None:
            semantic_index = _semantic_index_summary(
                _fetch_rule_chunks_for_index(connection, book_id=current_book_id),
                backend=backend,
            )
        health = _rules_corpus_action_for_book(
            report,
            semantic_index=semantic_index,
            vault_label="<vault>",
            backend_error=backend_error,
        )
        report["corpus_health"] = health
        book_health.append(health)

    action_order = {"none": 0, "reindex": 1, "repair": 2, "reingest": 3}
    overall = max(book_health, key=lambda item: action_order.get(str(item.get("action")), 0), default={"action": "none"})
    return {
        "schema_version": 1,
        "action": overall.get("action", "none"),
        "books": book_health,
        "summary": {
            "none": sum(1 for item in book_health if item.get("action") == "none"),
            "reindex": sum(1 for item in book_health if item.get("action") == "reindex"),
            "repair": sum(1 for item in book_health if item.get("action") == "repair"),
            "reingest": sum(1 for item in book_health if item.get("action") == "reingest"),
        },
        "reingest_sources": [
            {
                "book_id": item.get("book_id"),
                "book_title": item.get("book_title"),
                "pdf_path": item.get("source", {}).get("pdf_path"),
                "source_status": item.get("source", {}).get("status"),
            }
            for item in book_health
            if item.get("action") == "reingest"
        ],
    }


def _rules_corpus_action_for_book(
    book: dict[str, Any],
    *,
    semantic_index: dict[str, Any] | None,
    vault_label: str,
    backend_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    book_id = str(book.get("book_id") or "")
    source = dict(book.get("source_status") or {})
    summary = dict(book.get("review_summary") or {})
    chunk_count = int(book.get("chunk_count") or 0)
    page_count = int(book.get("page_count") or 0)
    suspect_pages = len(book.get("suspect_pages") or [])
    suspect_chunks = len(book.get("suspect_chunks") or [])
    blocked = int(summary.get("blocked") or 0)
    pending_blocked = int(summary.get("pending_blocked") or 0)
    pending = int(summary.get("pending_pages") or 0)
    structure = dict(book.get("structure_health") or {})
    missing_structure = int(structure.get("missing_structure") or 0)
    stale_structure = int(structure.get("stale_structure") or 0)
    empty_blocks = int(structure.get("empty_blocks") or 0)
    reindex_eligible = bool(structure.get("reindex_eligible", True))
    reingest_recommended = bool(structure.get("reingest_recommended", False))
    actionable_suspect_pages = sum(
        1
        for page in book.get("suspect_pages") or []
        if str(page.get("review_state") or "pending") not in AUDIT_RESOLVING_DECISIONS
    )
    actionable_suspect_chunks = sum(
        1
        for chunk in book.get("suspect_chunks") or []
        if str(chunk.get("review_state") or "pending") not in AUDIT_RESOLVING_DECISIONS
    )
    reasons: list[str] = []

    missing = stale = 0
    if semantic_index is None:
        if backend_error is not None:
            reasons.append("embedding_backend_unavailable")
            missing = chunk_count
    else:
        missing = (
            int(semantic_index.get("missing_embeddings") or 0)
            + int(semantic_index.get("missing_metadata") or 0)
            + int(semantic_index.get("missing_structure") or 0)
        )
        stale = (
            int(semantic_index.get("stale_embeddings") or 0)
            + int(semantic_index.get("stale_metadata") or 0)
            + int(semantic_index.get("stale_structure") or 0)
        )
        if missing:
            reasons.append("missing_retrieval_index")
        if stale:
            reasons.append("stale_retrieval_index")
    if missing_structure:
        reasons.append("missing_rule_block_structure")
    if stale_structure:
        reasons.append("stale_rule_block_structure")
    if empty_blocks:
        reasons.append("empty_rule_blocks")

    unusable_ratio = (actionable_suspect_pages + actionable_suspect_chunks) / max(page_count + chunk_count, 1)
    if chunk_count == 0:
        action = "reingest"
        reasons.append("no_stored_chunks")
    elif reingest_recommended or not reindex_eligible:
        action = "reingest"
        reasons.append("stored_text_insufficient_for_structure")
    elif unusable_ratio >= 0.35 or pending_blocked > 0:
        action = "repair" if source.get("status") == "available" else "reingest"
        reasons.append("stored_text_quality")
    elif missing or stale or missing_structure or stale_structure or backend_error is not None:
        action = "reindex"
    elif pending:
        action = "repair"
        reasons.append("review_pending")
    else:
        action = "none"

    if action == "reindex":
        command = f"backet rules index {vault_label} --book-id {book_id} --full"
        source_pdf_required = False
    elif action == "repair":
        command = f"backet rules audit {vault_label} --book-id {book_id} --review"
        source_pdf_required = source.get("status") == "available"
    elif action == "reingest":
        command = f"backet rules ingest {vault_label} <source-pdf> --book-id {book_id}"
        source_pdf_required = True
    else:
        command = None
        source_pdf_required = False

    return {
        "book_id": book_id,
        "book_title": book.get("book_title"),
        "action": action,
        "reasons": sorted(set(reasons)),
        "next_command": command,
        "source_pdf_required": source_pdf_required,
        "source": {
            "status": source.get("status"),
            "pdf_path": source.get("pdf_path"),
            "stored_fingerprint": source.get("stored_fingerprint"),
        },
        "retrieval_index": {
            "missing": missing,
            "stale": stale,
            "backend_error": backend_error,
        },
        "structure": {
            "schema_version": structure.get("schema_version", RULE_BLOCK_STRUCTURE_SCHEMA_VERSION),
            "structured_blocks": int(structure.get("structured_blocks") or 0),
            "missing": missing_structure,
            "stale": stale_structure,
            "empty_blocks": empty_blocks,
            "reindex_eligible": reindex_eligible,
            "reingest_recommended": reingest_recommended,
        },
        "quality": {
            "suspect_pages": suspect_pages,
            "suspect_chunks": suspect_chunks,
            "actionable_suspect_pages": actionable_suspect_pages,
            "actionable_suspect_chunks": actionable_suspect_chunks,
            "pending_pages": pending,
            "blocked": blocked,
            "pending_blocked": pending_blocked,
            "unusable_ratio": round(unusable_ratio, 4),
        },
    }


def _query_corpus_blockers(connection: sqlite3.Connection, *, book_id: str | None) -> dict[str, Any]:
    try:
        backend = resolve_embedding_backend()
    except AppError as error:
        return {
            "action": "reindex",
            "blockers": ["embedding_backend_unavailable"],
            "repair_hint": "Configure a local embedding backend, then run `backet rules index <vault> --full`.",
            "semantic_error": _semantic_error(error),
        }
    summary = _semantic_index_summary(_fetch_rule_chunks_for_index(connection, book_id=book_id), backend=backend)
    rule_units = _rule_units_summary(connection, book_id=book_id)
    blockers: list[str] = []
    if summary["missing_embeddings"] or summary["missing_metadata"]:
        blockers.append("missing_retrieval_index")
    if summary["stale_embeddings"] or summary["stale_metadata"]:
        blockers.append("stale_retrieval_index")
    if summary["missing_structure"]:
        blockers.append("missing_rule_block_structure")
    if summary["stale_structure"]:
        blockers.append("stale_rule_block_structure")
    if rule_units["missing_rule_units"]:
        blockers.append("missing_rule_units")
    if rule_units["stale_rule_units"]:
        blockers.append("stale_rule_units")
    return {
        "action": "reindex" if blockers else "none",
        "blockers": blockers,
        "repair_hint": _rules_index_hint(book_id) if blockers else None,
        "missing": int(summary["missing_embeddings"])
        + int(summary["missing_metadata"])
        + int(summary["missing_structure"])
        + int(rule_units["missing_rule_units"]),
        "stale": int(summary["stale_embeddings"])
        + int(summary["stale_metadata"])
        + int(summary["stale_structure"])
        + int(rule_units["stale_rule_units"]),
        "structure": {
            "schema_version": RULE_BLOCK_STRUCTURE_SCHEMA_VERSION,
            "structured_blocks": int(summary["structure_chunks"]),
            "missing": int(summary["missing_structure"]),
            "stale": int(summary["stale_structure"]),
        },
        "rule_units": {
            "schema_version": RULE_UNIT_SCHEMA_VERSION,
            **rule_units,
        },
    }


def _resolve_query_plan_entities(connection: sqlite3.Connection, query_plan: RulesQueryPlan) -> RulesQueryPlan:
    catalog_matches = _catalog_matches_for_query(connection, query_plan.normalized_question)
    resolved = _merge_resolved_entities(query_plan.resolved_entities, catalog_matches)
    ambiguity_warnings = _entity_resolution_ambiguities(resolved)
    unresolved = list(query_plan.unresolved_high_value_terms)

    entities = {key: list(value) for key, value in query_plan.entities.items()}
    canonical_terms = list(query_plan.canonical_terms)
    expanded_terms = list(query_plan.expanded_terms)
    scope_tags = list(query_plan.scope_tags)
    for entity in resolved:
        canonical = str(entity.get("canonical_name") or "")
        entity_type = str(entity.get("entity_type") or "")
        if canonical:
            _add_unique(canonical_terms, canonical)
            _extend_unique(expanded_terms, entity.get("accepted_aliases") or [])
        if entity_type in {"mechanic", "rule", "table", "list"}:
            _add_unique(entities.setdefault("mechanics", []), canonical)
        elif entity_type == "discipline":
            _add_unique(entities.setdefault("disciplines", []), canonical)
        elif entity_type in {"power", "ritual"}:
            _add_unique(entities.setdefault("powers", []), canonical)
        _extend_unique(scope_tags, entity.get("scope_tags") or [])

    retrieval_queries = _entity_first_retrieval_queries(query_plan.retrieval_queries, resolved)
    warnings = list(query_plan.warnings)
    for warning in ambiguity_warnings:
        _add_unique(warnings, "ambiguous_entity_alias:" + str(warning.get("alias") or "unknown"))
    if unresolved:
        _add_unique(warnings, "unresolved_high_value_terms; broad fallback cannot prove answerability")
    confidence = max([float(entity.get("confidence") or 0.0) for entity in resolved], default=query_plan.resolution_confidence)
    semantic_terms = [*canonical_terms, *expanded_terms, *query_plan.required_evidence]
    if not canonical_terms:
        semantic_terms.extend(query_plan.raw_unknown_terms)
    return replace(
        query_plan,
        entities={key: _dedupe_text_values(value) for key, value in entities.items()},
        scope_tags=_dedupe_text_values(scope_tags),
        canonical_terms=_dedupe_text_values(canonical_terms),
        expanded_terms=_dedupe_text_values(expanded_terms),
        retrieval_queries=retrieval_queries,
        resolved_entities=resolved,
        unresolved_high_value_terms=_dedupe_text_values(unresolved),
        ambiguity_warnings=ambiguity_warnings,
        resolution_confidence=round(confidence, 3),
        warnings=warnings,
        semantic_query=" ".join(_dedupe_text_values(semantic_terms)) or query_plan.semantic_query,
    )


def _catalog_matches_for_query(connection: sqlite3.Connection, normalized_question: str) -> list[dict[str, Any]]:
    query_aliases = _catalog_query_aliases(normalized_question)
    if not query_aliases:
        return []
    matches: dict[str, dict[str, Any]] = {}
    for alias in query_aliases:
        try:
            rows = connection.execute(
                """
                SELECT
                    a.alias,
                    a.normalized_alias,
                    a.provenance AS alias_provenance,
                    a.confidence,
                    e.*
                FROM rule_entity_aliases a
                JOIN rule_entities e ON e.entity_id = a.entity_id
                WHERE a.normalized_alias = ?
                  AND e.catalog_schema_version = ?
                ORDER BY a.confidence DESC, e.provenance, e.canonical_name
                """,
                (alias, RULES_ENTITY_CATALOG_SCHEMA_VERSION),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        for row in rows:
            entity = matches.setdefault(str(row["entity_id"]), _resolved_entity_from_row(row))
            _add_unique(entity["matched_aliases"], str(row["alias"]))
            entity["confidence"] = max(float(entity.get("confidence") or 0.0), float(row["confidence"] or 0.0))
    return sorted(matches.values(), key=lambda item: (-float(item.get("confidence") or 0.0), str(item.get("canonical_name"))))


def _catalog_query_aliases(normalized_question: str) -> list[str]:
    raw_tokens = re.findall(r"[a-z0-9]+", normalized_question)
    tokens = [token for token in raw_tokens if token not in RULE_QUERY_STOPWORDS]
    aliases: list[str] = []
    for size in (5, 4, 3, 2, 1):
        for index in range(0, max(len(raw_tokens) - size + 1, 0)):
            phrase = " ".join(raw_tokens[index : index + size])
            if len(phrase) >= 3:
                _add_unique(aliases, _normalize_rule_alias(phrase))
    for size in (4, 3, 2, 1):
        for index in range(0, max(len(tokens) - size + 1, 0)):
            phrase = " ".join(tokens[index : index + size])
            if len(phrase) >= 3:
                _add_unique(aliases, _normalize_rule_alias(phrase))
    return aliases


def _resolved_entity_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "entity_id": row["entity_id"],
        "canonical_name": row["canonical_name"],
        "entity_type": row["entity_type"],
        "accepted_aliases": _json_text_list(row["aliases_json"]),
        "matched_aliases": [str(row["alias"])],
        "source_anchors": _json_dict_list(row["source_anchors_json"]),
        "source_pages": [int(page) for page in _json_list(row["source_pages_json"]) if str(page).isdigit()],
        "scope_tags": _json_text_list(row["scope_tags_json"]),
        "alias_provenance": row["alias_provenance"],
        "provenance": row["provenance"],
        "confidence": float(row["confidence"] or 0.0),
    }


def _merge_resolved_entities(seed_entities: list[dict[str, Any]], catalog_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for entity in [*seed_entities, *catalog_entities]:
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id:
            continue
        existing = merged.get(entity_id)
        if existing is None:
            merged[entity_id] = {**entity, "matched_aliases": list(entity.get("matched_aliases") or [])}
            continue
        _extend_unique(existing.setdefault("matched_aliases", []), entity.get("matched_aliases") or [])
        _extend_unique(existing.setdefault("accepted_aliases", []), entity.get("accepted_aliases") or [])
        source_anchors = existing.setdefault("source_anchors", [])
        for anchor in entity.get("source_anchors") or []:
            if anchor not in source_anchors:
                source_anchors.append(anchor)
        existing["confidence"] = max(float(existing.get("confidence") or 0.0), float(entity.get("confidence") or 0.0))
    return sorted(merged.values(), key=lambda item: (-float(item.get("confidence") or 0.0), str(item.get("canonical_name"))))


def _entity_resolution_ambiguities(resolved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_alias: dict[str, list[dict[str, Any]]] = {}
    for entity in resolved:
        for alias in entity.get("matched_aliases") or []:
            by_alias.setdefault(_normalize_rule_alias(str(alias)), []).append(entity)
    warnings: list[dict[str, Any]] = []
    for alias, entities in by_alias.items():
        canonical = {str(entity.get("canonical_name") or "") for entity in entities}
        if len(canonical) <= 1:
            continue
        top = max(float(entity.get("confidence") or 0.0) for entity in entities)
        comparable = [entity for entity in entities if top - float(entity.get("confidence") or 0.0) <= 0.1]
        if len(comparable) > 1:
            warnings.append(
                {
                    "alias": alias,
                    "entity_ids": [str(entity.get("entity_id")) for entity in comparable],
                    "canonical_names": sorted(str(entity.get("canonical_name")) for entity in comparable),
                }
            )
    return warnings


def _entity_first_retrieval_queries(
    existing: list[RulesRetrievalQuery],
    resolved_entities: list[dict[str, Any]],
) -> list[RulesRetrievalQuery]:
    queries: list[RulesRetrievalQuery] = []
    entity_terms: list[str] = []
    for entity in resolved_entities:
        _add_unique(entity_terms, str(entity.get("canonical_name") or ""))
        _extend_unique(entity_terms, entity.get("matched_aliases") or [])
        _extend_unique(entity_terms, entity.get("accepted_aliases") or [])
    entity_terms = _dedupe_text_values(entity_terms)
    if entity_terms:
        queries.append(
            RulesRetrievalQuery(
                role="entity_anchor",
                text=" ".join(entity_terms),
                terms=entity_terms,
                evidence=[],
                weight=1.35,
            )
        )
    queries.extend(existing)
    return _dedupe_rules_retrieval_queries(queries)


def _dedupe_rules_retrieval_queries(queries: list[RulesRetrievalQuery]) -> list[RulesRetrievalQuery]:
    seen: set[tuple[str, str]] = set()
    deduped: list[RulesRetrievalQuery] = []
    for query in queries:
        key = (query.role, query.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(query)
    return deduped


def _rules_structure_health(connection: sqlite3.Connection, book_id: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT
            id,
            rule_block_id,
            block_kind,
            clean_content,
            source_window,
            structure_flags_json,
            structure_schema_version
        FROM rule_chunks
        WHERE book_id = ?
        ORDER BY page_start, chunk_index
        """,
        (book_id,),
    ).fetchall()
    total = len(rows)
    structured = 0
    missing = 0
    stale = 0
    page_furniture = 0
    empty = 0
    mixed = 0
    table_blocks = 0
    list_blocks = 0
    sample_block_ids: list[str] = []
    stale_sample_block_ids: list[str] = []
    for row in rows:
        block_id = str(row["rule_block_id"] or "")
        block_kind = str(row["block_kind"] or "")
        flags = _json_list(row["structure_flags_json"])
        has_clean_text = bool(str(row["clean_content"] or "").strip())
        current_schema = int(row["structure_schema_version"] or 0) == RULE_BLOCK_STRUCTURE_SCHEMA_VERSION
        if "page_furniture_removed" in flags:
            page_furniture += 1
        if "empty_after_structure_clean" in flags or not has_clean_text:
            empty += 1
        if "possible_mixed_topic" in flags:
            mixed += 1
        if block_kind == "table":
            table_blocks += 1
        if block_kind == "list":
            list_blocks += 1
        if not block_id or not has_clean_text:
            missing += 1
            continue
        if not current_schema:
            stale += 1
            _add_unique(stale_sample_block_ids, block_id)
            continue
        structured += 1
        _add_unique(sample_block_ids, block_id)

    empty_ratio = empty / max(total, 1)
    reingest_recommended = total == 0 or empty_ratio >= 0.35
    return {
        "schema_version": RULE_BLOCK_STRUCTURE_SCHEMA_VERSION,
        "total_chunks": total,
        "structured_blocks": structured,
        "missing_structure": missing,
        "stale_structure": stale,
        "page_furniture_heavy_blocks": page_furniture,
        "empty_blocks": empty,
        "mixed_topic_blocks": mixed,
        "table_blocks": table_blocks,
        "list_blocks": list_blocks,
        "reindex_eligible": total > 0 and not reingest_recommended,
        "reingest_recommended": reingest_recommended,
        "sample_block_ids": sample_block_ids[:5],
        "stale_sample_block_ids": stale_sample_block_ids[:5],
    }


def _inspect_rule_source_status(book: sqlite3.Row) -> RuleSourceStatus:
    pdf_path = str(book["pdf_path"] or "")
    stored_fingerprint = str(book["pdf_fingerprint"] or "")
    if not pdf_path:
        return RuleSourceStatus(
            status="missing",
            pdf_path="",
            stored_fingerprint=stored_fingerprint,
            current_fingerprint=None,
            available=False,
            repair_eligible=False,
            message="No source PDF path is stored for this book.",
        )
    path = Path(pdf_path)
    if not path.exists() or not path.is_file():
        return RuleSourceStatus(
            status="missing",
            pdf_path=pdf_path,
            stored_fingerprint=stored_fingerprint,
            current_fingerprint=None,
            available=False,
            repair_eligible=False,
            message="The stored source PDF path does not exist.",
        )
    if path.suffix.casefold() != ".pdf":
        return RuleSourceStatus(
            status="unverified",
            pdf_path=pdf_path,
            stored_fingerprint=stored_fingerprint,
            current_fingerprint=None,
            available=False,
            repair_eligible=False,
            message="The stored source path is not a PDF file.",
        )
    try:
        current_fingerprint = fingerprint_bytes(path.read_bytes())
    except OSError:
        return RuleSourceStatus(
            status="unverified",
            pdf_path=pdf_path,
            stored_fingerprint=stored_fingerprint,
            current_fingerprint=None,
            available=False,
            repair_eligible=False,
            message="The stored source PDF could not be read.",
        )
    if current_fingerprint != stored_fingerprint:
        return RuleSourceStatus(
            status="mismatched",
            pdf_path=pdf_path,
            stored_fingerprint=stored_fingerprint,
            current_fingerprint=current_fingerprint,
            available=True,
            repair_eligible=False,
            message="The stored source PDF fingerprint does not match the ingested source.",
        )
    return RuleSourceStatus(
        status="available",
        pdf_path=pdf_path,
        stored_fingerprint=stored_fingerprint,
        current_fingerprint=current_fingerprint,
        available=True,
        repair_eligible=True,
        message="The original source PDF is available for targeted repair.",
    )


def _audit_finding_from_page(
    connection: sqlite3.Connection,
    book: sqlite3.Row,
    page: sqlite3.Row,
    source_status: RuleSourceStatus,
) -> RuleAuditFinding:
    book_id = str(book["book_id"])
    page_number = int(page["page_number"])
    flags = _json_list(page["quality_flags_json"])
    section_kind, _ = classify_rule_chunk(
        section_label=page["section_label"],
        content=page["text_excerpt"],
        word_count=len(str(page["text_excerpt"]).split()),
        confidence=float(page["confidence"]),
        extraction_method=str(page["extraction_method"]),
    )
    category = _audit_category_for_low_confidence(section_kind, source_status=source_status)
    review_state, resolved = _audit_review_state(
        connection,
        book_id=book_id,
        target_type="page",
        page_start=page_number,
        page_end=page_number,
        chunk_index=None,
        finding_kind=AUDIT_FINDING_LOW_CONFIDENCE_PAGE,
        content_hash=page["content_hash"],
    )
    return RuleAuditFinding(
        book_id=book_id,
        target_type="page",
        page_start=page_number,
        page_end=page_number,
        chunk_index=None,
        finding_kind=AUDIT_FINDING_LOW_CONFIDENCE_PAGE,
        category=category,
        severity="action" if category == "review" else category,
        content_hash=str(page["content_hash"]),
        review_state=review_state,
        resolved=resolved,
        reason=_audit_page_reason(flags, section_kind, source_status),
        excerpt=str(page["text_excerpt"]),
        quality_flags=flags,
        extraction_method=str(page["extraction_method"]),
        confidence=float(page["confidence"]),
        section_label=str(page["section_label"]),
        allowed_decisions=sorted(AUDIT_REVIEW_DECISIONS),
        source_status=source_status,
    )


def _audit_finding_from_chunk(
    connection: sqlite3.Connection,
    book: sqlite3.Row,
    chunk: sqlite3.Row,
    source_status: RuleSourceStatus,
) -> RuleAuditFinding:
    book_id = str(book["book_id"])
    section_kind = _row_optional(chunk, "section_kind")
    flags = _json_list(_row_optional(chunk, "retrieval_flags_json"))
    if not section_kind or _row_optional(chunk, "metadata_content_hash") != chunk["content_hash"]:
        section_kind, flags = classify_rule_chunk(
            section_label=chunk["section_label"],
            content=chunk["content"],
            word_count=int(chunk["word_count"]),
            confidence=float(chunk["confidence"]),
            extraction_method=str(chunk["extraction_method"]),
        )
    category = _audit_category_for_low_confidence(str(section_kind), source_status=source_status)
    review_state, resolved = _audit_review_state(
        connection,
        book_id=book_id,
        target_type="chunk",
        page_start=int(chunk["page_start"]),
        page_end=int(chunk["page_end"]),
        chunk_index=int(chunk["chunk_index"]),
        finding_kind=AUDIT_FINDING_LOW_CONFIDENCE_CHUNK,
        content_hash=chunk["content_hash"],
    )
    return RuleAuditFinding(
        book_id=book_id,
        target_type="chunk",
        page_start=int(chunk["page_start"]),
        page_end=int(chunk["page_end"]),
        chunk_index=int(chunk["chunk_index"]),
        finding_kind=AUDIT_FINDING_LOW_CONFIDENCE_CHUNK,
        category=category,
        severity="action" if category == "review" else category,
        content_hash=str(chunk["content_hash"]),
        review_state=review_state,
        resolved=resolved,
        reason=f"Chunk confidence is {float(chunk['confidence']):.2f}.",
        excerpt=str(chunk["excerpt"]),
        quality_flags=flags,
        extraction_method=str(chunk["extraction_method"]),
        confidence=float(chunk["confidence"]),
        section_label=str(chunk["section_label"]),
        allowed_decisions=sorted(AUDIT_REVIEW_DECISIONS),
        source_status=source_status,
    )


def _audit_notices_for_pages(
    connection: sqlite3.Connection,
    book: sqlite3.Row,
    ocr_pages: list[sqlite3.Row],
    findings: list[RuleAuditFinding],
) -> list[RuleAuditFinding]:
    book_id = str(book["book_id"])
    pages_with_findings = {finding.page_start for finding in findings}
    notices: list[RuleAuditFinding] = []
    for row in ocr_pages:
        page_number = int(row["page_number"])
        if page_number in pages_with_findings:
            continue
        page = connection.execute(
            """
            SELECT * FROM page_audit
            WHERE book_id = ? AND page_number = ?
            """,
            (book_id, page_number),
        ).fetchone()
        if page is None:
            continue
        notices.append(
            RuleAuditFinding(
                book_id=book_id,
                target_type="page",
                page_start=page_number,
                page_end=page_number,
                chunk_index=None,
                finding_kind="ocr_fallback_notice",
                category="notice",
                severity="notice",
                content_hash=str(page["content_hash"]),
                review_state="notice",
                resolved=True,
                reason="OCR fallback was used, but the extracted text is not currently suspicious.",
                excerpt=str(page["text_excerpt"]),
                quality_flags=_json_list(page["quality_flags_json"]),
                extraction_method=str(page["extraction_method"]),
                confidence=float(page["confidence"]),
                section_label=str(page["section_label"]),
                allowed_decisions=[],
            )
        )
    return notices


def _audit_category_for_low_confidence(section_kind: str, *, source_status: RuleSourceStatus) -> str:
    if section_kind in {"art", "toc", "index", "sheet", "furniture"}:
        return "notice"
    if not source_status.repair_eligible:
        return "blocked"
    return "review"


def _audit_page_reason(flags: list[str], section_kind: str, source_status: RuleSourceStatus) -> str:
    if section_kind in {"art", "toc", "index", "sheet", "furniture"}:
        return f"Likely {section_kind} material; review only if this page should answer rules queries."
    if not source_status.repair_eligible:
        return f"Extraction looks weak and automatic repair is blocked: {source_status.message}"
    if "low_text_density" in flags and "low_alpha_ratio" in flags:
        return "Extraction has little readable text and a low letter ratio."
    if "low_text_density" in flags:
        return "Extraction has very little readable text."
    if "low_alpha_ratio" in flags:
        return "Extraction has an unusually low letter ratio."
    return "Extraction confidence is low."


def _audit_review_state(
    connection: sqlite3.Connection,
    *,
    book_id: str,
    target_type: str,
    page_start: int,
    page_end: int | None,
    chunk_index: int | None,
    finding_kind: str,
    content_hash: str,
) -> tuple[str, bool]:
    row = connection.execute(
        """
        SELECT decision
        FROM rule_audit_reviews
        WHERE book_id = ?
          AND target_type = ?
          AND COALESCE(page_start, -1) = ?
          AND COALESCE(page_end, -1) = ?
          AND COALESCE(chunk_index, -1) = ?
          AND finding_kind = ?
          AND content_hash = ?
        ORDER BY decided_at DESC, id DESC
        LIMIT 1
        """,
        (
            book_id,
            target_type,
            page_start,
            page_end if page_end is not None else -1,
            chunk_index if chunk_index is not None else -1,
            finding_kind,
            content_hash,
        ),
    ).fetchone()
    if row is None:
        return "pending", False
    decision = str(row["decision"])
    return decision, decision in AUDIT_RESOLVING_DECISIONS


def _build_review_cards(findings: list[RuleAuditFinding]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[RuleAuditFinding]] = {}
    for finding in findings:
        if finding.resolved or finding.category not in {"review", "blocked"} or finding.page_start is None:
            continue
        grouped.setdefault((finding.book_id, finding.page_start), []).append(finding)

    cards: list[dict[str, Any]] = []
    for (book_id, page_start), page_findings in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        first = page_findings[0]
        reasons = sorted({finding.reason for finding in page_findings})
        cards.append(
            {
                "book_id": book_id,
                "page_start": page_start,
                "page_end": max(finding.page_end or page_start for finding in page_findings),
                "category": "blocked" if any(finding.category == "blocked" for finding in page_findings) else "review",
                "review_state": "pending",
                "finding_kinds": sorted({finding.finding_kind for finding in page_findings}),
                "reasons": reasons,
                "source_status": first.source_status.to_dict() if first.source_status else None,
                "extraction_method": first.extraction_method,
                "confidence": first.confidence,
                "quality_flags": sorted({flag for finding in page_findings for flag in finding.quality_flags}),
                "section_label": first.section_label,
                "excerpt": first.excerpt,
                "allowed_decisions": sorted(AUDIT_REVIEW_DECISIONS),
                "targets": [
                    {
                        "target_type": finding.target_type,
                        "page_start": finding.page_start,
                        "page_end": finding.page_end,
                        "chunk_index": finding.chunk_index,
                        "finding_kind": finding.finding_kind,
                    }
                    for finding in page_findings
                ],
            }
        )
    return cards


def _audit_category_counts(findings: list[RuleAuditFinding]) -> dict[str, int]:
    counts = {category: 0 for category in sorted(AUDIT_FINDING_CATEGORIES)}
    for finding in findings:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    return counts


def _rules_audit_maintenance_findings(semantic_index: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not semantic_index.get("available", False) or semantic_index.get("repair_hint"):
        rule_units = semantic_index.get("rule_units") if isinstance(semantic_index.get("rule_units"), dict) else {}
        missing = (
            int(semantic_index.get("missing_embeddings") or 0)
            + int(semantic_index.get("missing_metadata") or 0)
            + int(semantic_index.get("missing_structure") or 0)
            + int(rule_units.get("missing_rule_units") or 0)
        )
        stale = (
            int(semantic_index.get("stale_embeddings") or 0)
            + int(semantic_index.get("stale_metadata") or 0)
            + int(semantic_index.get("stale_structure") or 0)
            + int(rule_units.get("stale_rule_units") or 0)
        )
        if missing or stale or not semantic_index.get("available", False):
            findings.append(
                {
                    "finding_kind": AUDIT_FINDING_MAINTENANCE,
                    "category": "maintenance",
                    "reason": "Rules retrieval index coverage needs attention.",
                    "missing": missing,
                    "stale": stale,
                    "repair_hint": semantic_index.get("repair_hint"),
                }
            )
    return findings


def _active_excluded_chunk_count(connection: sqlite3.Connection, book_id: str | None = None) -> int:
    parameters: list[Any] = []
    where_clause = "WHERE rc.id IS NOT NULL AND rex.content_hash = rc.content_hash"
    if book_id:
        where_clause += " AND rex.book_id = ?"
        parameters.append(book_id)
    row = connection.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM rule_retrieval_exclusions rex
        JOIN rule_chunks rc ON rc.id = rex.chunk_id
        {where_clause}
        """,
        parameters,
    ).fetchone()
    return int(row["count"] if row is not None else 0)


def export_rule_scopes(vault_root: Path, book_id: str) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    with closing(open_rules_connection(vault_root)) as connection:
        book = _require_book(connection, book_id)
        manifest = _scope_manifest(connection, book)
    return CommandResult(
        message="Exported rule scope assertions",
        data={"vault": str(vault_root), "book_id": book_id, "manifest": manifest},
    )


def apply_rule_scope_manifest(vault_root: Path, manifest_path: Path) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    if not manifest_path.exists() or not manifest_path.is_file():
        raise AppError(
            code="rules_scope_manifest_missing",
            message=f"Rule scope manifest not found: {manifest_path}",
            hint="Provide a readable YAML or JSON manifest path.",
            details={"manifest_path": str(manifest_path)},
            exit_code=2,
        )
    try:
        payload = yaml.safe_load(manifest_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise AppError(
            code="rules_scope_manifest_invalid",
            message="Rule scope manifest could not be parsed.",
            hint="Provide valid YAML or JSON.",
            details={"manifest_path": str(manifest_path), "error": str(exc)},
            exit_code=2,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="rules_scope_manifest_invalid",
            message="Rule scope manifest must be a mapping.",
            hint="Export an existing manifest first, then edit and re-apply it.",
            details={"manifest_path": str(manifest_path)},
            exit_code=2,
        )
    book_id = str(payload.get("book_id") or "")
    if not book_id:
        raise AppError(
            code="rules_scope_manifest_invalid",
            message="Rule scope manifest is missing `book_id`.",
            hint="Export an existing manifest first, then edit and re-apply it.",
            details={"manifest_path": str(manifest_path)},
            exit_code=2,
        )

    with closing(open_rules_connection(vault_root)) as connection:
        _require_book(connection, book_id)
        assertions = _manifest_to_assertions(payload)
        connection.execute("DELETE FROM rule_scope_assertions WHERE book_id = ?", (book_id,))
        assertion_ids = [_insert_scope_assertion(connection, book_id, assertion) for assertion in assertions]
        _apply_scope_assertions_to_chunks(connection, book_id=book_id, assertion_ids=assertion_ids)
        _refresh_chunk_scope_tags(connection, book_id)
        _rebuild_rule_chunks_fts(connection, book_id)
        summary = _scope_summary(connection, book_id=book_id)
        connection.commit()
    return CommandResult(
        message="Applied rule scope manifest",
        data={"vault": str(vault_root), "book_id": book_id, "manifest_path": str(manifest_path), "scope_assertions": summary},
    )


def review_rule_audit(
    vault_root: Path,
    book_id: str,
    page: int,
    decision: str,
    *,
    chunk_index: int | None = None,
    reason: str = "",
    notes: str = "",
) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    normalized_decision = decision.strip().lower()
    if normalized_decision not in AUDIT_REVIEW_DECISIONS:
        raise AppError(
            code="rules_review_decision_invalid",
            message=f"Unsupported rules audit review decision: {decision}",
            hint="Use accepted, ignored, excluded, or skipped.",
            details={"decision": decision},
            exit_code=2,
        )
    if page < 1:
        raise AppError(
            code="rules_review_page_invalid",
            message="Rules audit review pages must be positive page numbers.",
            hint="Use a page number reported by `backet rules audit`.",
            details={"page": page},
            exit_code=2,
        )

    with closing(open_rules_connection(vault_root)) as connection:
        _require_book(connection, book_id)
        target = _review_target_row(connection, book_id=book_id, page=page, chunk_index=chunk_index)
        target_type = "chunk" if chunk_index is not None else "page"
        finding_kind = AUDIT_FINDING_LOW_CONFIDENCE_CHUNK if chunk_index is not None else AUDIT_FINDING_LOW_CONFIDENCE_PAGE
        page_end = int(target["page_end"]) if target_type == "chunk" else page
        content_hash = str(target["content_hash"])
        _insert_audit_review(
            connection,
            book_id=book_id,
            target_type=target_type,
            page_start=page,
            page_end=page_end,
            chunk_index=chunk_index,
            finding_kind=finding_kind,
            decision=normalized_decision,
            content_hash=content_hash,
            reason=reason,
            notes=notes,
        )
        excluded_chunks = 0
        if normalized_decision == "excluded":
            excluded_chunks = _store_retrieval_exclusion_for_target(
                connection,
                book_id=book_id,
                target_type=target_type,
                page_start=page,
                page_end=page_end,
                chunk_index=chunk_index,
                reason=reason,
            )
        connection.commit()

    return CommandResult(
        message="Recorded rules audit review decision",
        data={
            "vault": str(vault_root),
            "book_id": book_id,
            "page_start": page,
            "page_end": page_end,
            "chunk_index": chunk_index,
            "decision": normalized_decision,
            "content_hash": content_hash,
            "resolved": normalized_decision in AUDIT_RESOLVING_DECISIONS,
            "retrieval_excluded_chunks": excluded_chunks,
        },
    )


def replace_rule_page_text(
    vault_root: Path,
    book_id: str,
    page: int,
    text: str,
    *,
    reason: str = "",
    notes: str = "",
) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    normalized_text = normalize_text(text)
    if not _manual_replacement_is_usable(normalized_text):
        raise AppError(
            code="rules_manual_replacement_unusable",
            message="Manual replacement text is empty or too noisy to store as rule text.",
            hint="Provide corrected page text, or review the finding as ignored/excluded instead.",
            details={"book_id": book_id, "page": page, "char_count": len(normalized_text)},
            exit_code=2,
        )
    with closing(open_rules_connection(vault_root)) as connection:
        book = _require_book(connection, book_id)
        if page < 1 or page > int(book["page_count"]):
            raise AppError(
                code="rules_manual_replacement_page_invalid",
                message="Manual replacement page is outside the ingested book page range.",
                hint="Use a page number reported by `backet rules audit`.",
                details={"book_id": book_id, "page": page, "page_count": int(book["page_count"])},
                exit_code=2,
            )
        entry = _book_entry_from_row(book)
        page_result = _build_page_result(page, normalized_text, extraction_method="manual")
        _replace_pages(connection, entry, [page_result], pages_spec=str(page))
        scope_summary = _generate_and_apply_scope_assertions(connection, entry=entry, pages=[page_result], outline=[])
        _rebuild_rule_chunks_fts(connection, book_id)
        semantic_index = _try_index_rule_chunks(connection, book_id=book_id, full=False, progress=None)
        content_hash = fingerprint_text(normalized_text)
        _insert_page_text_override(
            connection,
            book_id=book_id,
            page=page,
            page_result=page_result,
            content_hash=content_hash,
            reason=reason,
            notes=notes,
        )
        _insert_audit_review(
            connection,
            book_id=book_id,
            target_type="page",
            page_start=page,
            page_end=page,
            chunk_index=None,
            finding_kind=AUDIT_FINDING_LOW_CONFIDENCE_PAGE,
            decision="replaced",
            content_hash=content_hash,
            reason=reason,
            notes=notes,
        )
        audit_summary = _audit_summary(connection, book_id)
        connection.commit()

    return CommandResult(
        message="Replaced ingested rulebook page text",
        data={
            "vault": str(vault_root),
            "book_id": book_id,
            "page": page,
            "content_hash": content_hash,
            "char_count": page_result.char_count,
            "alpha_ratio": page_result.alpha_ratio,
            "scope_assertions": scope_summary,
            "suspect_pages": audit_summary["suspect_pages"],
            "chunk_count": audit_summary["chunk_count"],
            "semantic_index": semantic_index,
        },
    )


def relink_rule_source(vault_root: Path, book_id: str, pdf_path: Path, *, force: bool = False) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    if not pdf_path.exists() or not pdf_path.is_file():
        raise AppError(
            code="rules_source_relink_missing",
            message=f"Replacement source PDF not found: {pdf_path}",
            hint="Provide a readable local PDF path.",
            details={"pdf_path": str(pdf_path)},
            exit_code=2,
        )
    if pdf_path.suffix.casefold() != ".pdf":
        raise AppError(
            code="rules_source_relink_not_pdf",
            message="Replacement source path must point to a PDF file.",
            hint="Use the original PDF or rerun with another PDF path.",
            details={"pdf_path": str(pdf_path)},
            exit_code=2,
        )
    try:
        new_fingerprint = fingerprint_bytes(pdf_path.read_bytes())
        new_page_count = document_page_count(pdf_path)
    except (OSError, RuntimeError) as exc:
        raise AppError(
            code="rules_source_relink_unreadable",
            message="Replacement source PDF could not be read.",
            hint="Check file permissions and make sure the path is a valid PDF.",
            details={"pdf_path": str(pdf_path), "error": str(exc)},
            exit_code=2,
        ) from exc

    with closing(open_rules_connection(vault_root)) as connection:
        book = _require_book(connection, book_id)
        old_path = str(book["pdf_path"])
        old_fingerprint = str(book["pdf_fingerprint"])
        if new_fingerprint != old_fingerprint and not force:
            raise AppError(
                code="rules_source_fingerprint_mismatch",
                message="Replacement source PDF does not match the ingested source fingerprint.",
                hint="Use the original PDF, or rerun with `--force` if this replacement should become the trusted repair source.",
                details={
                    "book_id": book_id,
                    "old_pdf_path": old_path,
                    "new_pdf_path": str(pdf_path),
                    "stored_fingerprint": old_fingerprint,
                    "new_fingerprint": new_fingerprint,
                },
                exit_code=2,
            )
        status = "matched" if new_fingerprint == old_fingerprint else "forced_mismatch"
        stored_fingerprint = old_fingerprint if status == "matched" else new_fingerprint
        page_count = int(book["page_count"]) if status == "matched" else new_page_count
        now = timestamp_now()
        connection.execute(
            """
            UPDATE books
            SET pdf_path = ?, pdf_fingerprint = ?, page_count = ?, updated_at = ?
            WHERE book_id = ?
            """,
            (str(pdf_path.resolve()), stored_fingerprint, page_count, now, book_id),
        )
        connection.execute(
            """
            INSERT INTO rule_source_relinks (
                book_id, old_pdf_path, new_pdf_path, old_fingerprint, new_fingerprint,
                status, forced, relinked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (book_id, old_path, str(pdf_path.resolve()), old_fingerprint, new_fingerprint, status, int(force), now),
        )
        source_status = _inspect_rule_source_status(_require_book(connection, book_id))
        connection.commit()

    return CommandResult(
        message="Relinked rulebook source PDF",
        data={
            "vault": str(vault_root),
            "book_id": book_id,
            "pdf_path": str(pdf_path.resolve()),
            "status": status,
            "forced": force,
            "source_status": source_status.to_dict(),
        },
    )


def repair_rules(
    vault_root: Path,
    book_id: str,
    pages_spec: str | None = None,
    force_ocr: bool = False,
) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    with closing(open_rules_connection(vault_root)) as connection:
        book = connection.execute("SELECT * FROM books WHERE book_id = ?", (book_id,)).fetchone()
        if book is None:
            raise AppError(
                code="rules_book_missing",
                message="No ingested rulebook matches the requested repair target.",
                hint="Run `backet rules ingest` first or choose another `--book-id`.",
                details={"book_id": book_id},
                exit_code=2,
            )
            # unreachable
        title = book["book_title"]
        tier = book["tier"]
        scope_tags = json.loads(book["scope_tags_json"])
        pdf_path = Path(book["pdf_path"])
        source_status = _inspect_rule_source_status(book)
        if not source_status.repair_eligible:
            raise AppError(
                code="rules_repair_source_unavailable",
                message="Targeted rules repair cannot run because the source PDF is not a verified match.",
                hint="Relink the original PDF with `backet rules relink-source`, or provide corrected text with `backet rules replace`.",
                details={"book_id": book_id, "source_status": source_status.to_dict()},
                exit_code=2,
            )

    result = ingest_rulebook(
        vault_root=vault_root,
        pdf_path=pdf_path,
        book_id=book_id,
        title=title,
        tier=tier,
        scope_tags=scope_tags,
        force_ocr=force_ocr,
        pages_spec=pages_spec,
    )
    with closing(open_rules_connection(vault_root)) as connection:
        connection.execute(
            """
            INSERT INTO repair_history (book_id, pages_spec, force_ocr, repaired_at)
            VALUES (?, ?, ?, ?)
            """,
            (book_id, pages_spec or "", int(force_ocr), timestamp_now()),
        )
        connection.commit()

    result.message = "Repaired ingested rulebook pages"
    return result


def _require_pymupdf():
    try:
        import fitz  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise AppError(
            code="rules_dependency_missing",
            message="PyMuPDF is not installed, so PDF ingestion is unavailable.",
            hint="Install the rules dependency set or reinstall backet with PyMuPDF available.",
            details={"dependency": "pymupdf"},
            exit_code=2,
        ) from exc
    return fitz


def _extract_pages(
    document,
    pdf_path: Path,
    page_numbers: list[int],
    force_ocr: bool,
    progress: RulesIngestProgressCallback | None = None,
) -> list[ExtractedPage]:
    extracted: list[ExtractedPage] = []
    total = len(page_numbers)
    ocr_pages = 0
    review_pages = 0
    counters = {"ocr_pages": ocr_pages, "review_pages": review_pages}
    _emit_progress(progress, phase="extract", message="Extracting pages", current=0, total=total, counters=counters)
    for index, page_number in enumerate(page_numbers, start=1):
        page = document.load_page(page_number - 1)
        direct_text = normalize_text(page.get_text("text"))
        direct_result = _build_page_result(page_number, direct_text, extraction_method="direct")
        if force_ocr or direct_result.suspect:
            _emit_progress(
                progress,
                phase="ocr",
                message=f"OCR fallback on page {page_number}",
                current=index - 1,
                total=total,
                counters={"ocr_pages": ocr_pages, "review_pages": review_pages},
                details={"page_number": page_number},
            )
            ocr_results = [
                _build_page_result(page_number, text, extraction_method="ocr")
                for text in _ocr_text_candidates(page, pdf_path, page_number)
            ]
            candidate_results = ocr_results if force_ocr else [direct_result, *ocr_results]
            selected_result = _select_best_extraction_candidate(candidate_results)
            if selected_result.extraction_method == "ocr":
                ocr_pages += 1
            if selected_result.suspect:
                review_pages += 1
            extracted.append(selected_result)
            _emit_progress(
                progress,
                phase="extract",
                message=f"Extracted page {page_number}",
                current=index,
                total=total,
                counters={"ocr_pages": ocr_pages, "review_pages": review_pages},
                details={"page_number": page_number},
            )
            continue
        if direct_result.suspect:
            review_pages += 1
        extracted.append(direct_result)
        _emit_progress(
            progress,
            phase="extract",
            message=f"Extracted page {page_number}",
            current=index,
            total=total,
            counters={"ocr_pages": ocr_pages, "review_pages": review_pages},
            details={"page_number": page_number},
        )
    return extracted


def _build_page_result(page_number: int, text: str, extraction_method: str) -> ExtractedPage:
    char_count = len(text)
    alpha_chars = sum(1 for char in text if char.isalpha())
    alpha_ratio = alpha_chars / char_count if char_count else 0.0
    suspect = char_count < DEFAULT_PAGE_MIN_CHARS or alpha_ratio < 0.45
    if extraction_method == "manual" and not suspect:
        confidence = 0.98
    elif extraction_method == "direct" and not suspect:
        confidence = 0.95
    elif extraction_method == "ocr" and not suspect:
        confidence = 0.85
    elif extraction_method == "ocr":
        confidence = 0.65
    else:
        confidence = 0.4
    flags: list[str] = []
    if char_count < DEFAULT_PAGE_MIN_CHARS:
        flags.append("low_text_density")
    if alpha_ratio < 0.45:
        flags.append("low_alpha_ratio")
    if extraction_method == "ocr":
        flags.append("ocr_fallback")
    section_label = infer_section_label(text, page_number)
    return ExtractedPage(
        page_number=page_number,
        text=text,
        extraction_method=extraction_method,
        char_count=char_count,
        alpha_ratio=round(alpha_ratio, 4),
        confidence=confidence,
        suspect=suspect,
        quality_flags=flags,
        section_label=section_label,
    )


def _select_best_extraction_candidate(candidates: list[ExtractedPage]) -> ExtractedPage:
    if not candidates:
        raise AppError(
            code="rules_no_extraction_candidates",
            message="No extraction candidates were produced for the requested rulebook page.",
            hint="Check the PDF and OCR installation, then rerun the command.",
            exit_code=2,
        )
    best = max(candidates, key=_extraction_candidate_sort_key)
    direct = next((candidate for candidate in candidates if candidate.extraction_method == "direct"), None)
    if direct is not None and best.extraction_method != "direct":
        direct_score = _score_extracted_page(direct)
        best_score = _score_extracted_page(best)
        if best_score < direct_score + REPAIR_SCORE_IMPROVEMENT_THRESHOLD:
            return direct
    return best


def _extraction_candidate_sort_key(page: ExtractedPage) -> tuple[float, int]:
    return (_score_extracted_page(page), -page.page_number)


def _score_extracted_page(page: ExtractedPage) -> float:
    text = page.text
    word_count = len(text.split())
    strange_ratio = _strange_symbol_ratio(text)
    section_kind, flags = classify_rule_chunk(
        section_label=page.section_label,
        content=text,
        word_count=word_count,
        confidence=page.confidence,
        extraction_method=page.extraction_method,
    )
    score = min(page.char_count / 1200, 1.0)
    score += min(word_count / 180, 1.0)
    score += page.alpha_ratio
    score -= strange_ratio
    if _looks_rules_substantive(text.casefold()):
        score += 0.35
    if section_kind in {"rules", "lore"}:
        score += 0.2
    if page.extraction_method == "manual":
        score += 0.2
    if page.extraction_method == "ocr":
        score += 0.05
    if page.suspect:
        score -= 0.5
    score -= 0.08 * len(flags)
    return round(score, 6)


def _strange_symbol_ratio(text: str) -> float:
    compact = "".join(text.split())
    if not compact:
        return 1.0
    strange = sum(1 for char in compact if not (char.isalnum() or char in ".,:;!?'-()/%+"))
    return strange / len(compact)


def _ocr_text_candidates(page, pdf_path: Path, page_number: int) -> list[str]:
    candidates = [_ocr_page(page, pdf_path=pdf_path, page_number=page_number)]
    if has_tesseract():
        for dpi, psm in ((300, "6"), (300, "3")):
            try:
                candidate = _ocr_page_with_options(page, page_number=page_number, dpi=dpi, psm=psm)
            except AppError:
                continue
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _ocr_page(page, pdf_path: Path, page_number: int) -> str:
    if not has_tesseract():
        raise AppError(
            code="rules_ocr_unavailable",
            message="OCR fallback is required for this PDF, but Tesseract is not available.",
            hint=tesseract_install_hint(),
            details={"pdf_path": str(pdf_path), "page_number": page_number},
            exit_code=2,
        )
    return _ocr_page_with_options(page, page_number=page_number, dpi=200, psm="6")


def _ocr_page_with_options(page, *, page_number: int, dpi: int, psm: str) -> str:
    with TemporaryDirectory(prefix="backet-rules-ocr-") as temp_dir:
        image_path = Path(temp_dir) / f"page-{page_number}-{dpi}-{psm}.png"
        pixmap = page.get_pixmap(dpi=dpi, alpha=False)
        pixmap.save(str(image_path))
        process = subprocess.run(
            [tesseract_command(), str(image_path), "stdout", "--psm", psm],
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            raise AppError(
                code="rules_ocr_failed",
                message="Tesseract failed while OCR-processing the requested rulebook page.",
                hint=tesseract_install_hint(),
                details={"stderr": process.stderr.strip(), "page_number": page_number, "dpi": dpi, "psm": psm},
                exit_code=2,
            )
        return normalize_text(process.stdout)


def _upsert_book(connection: sqlite3.Connection, entry: BookRegistryEntry) -> None:
    now = timestamp_now()
    connection.execute(
        """
        INSERT INTO books (
            book_id, book_title, pdf_path, pdf_fingerprint, tier, scope_tags_json, page_count,
            extraction_backend, status, created_at, updated_at, last_ingested_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(book_id) DO UPDATE SET
            book_title = excluded.book_title,
            pdf_path = excluded.pdf_path,
            pdf_fingerprint = excluded.pdf_fingerprint,
            tier = excluded.tier,
            scope_tags_json = excluded.scope_tags_json,
            page_count = excluded.page_count,
            extraction_backend = excluded.extraction_backend,
            status = excluded.status,
            updated_at = excluded.updated_at,
            last_ingested_at = excluded.last_ingested_at
        """,
        (
            entry.book_id,
            entry.title,
            entry.pdf_path,
            entry.pdf_fingerprint,
            entry.tier,
            json.dumps(entry.scope_tags),
            entry.page_count,
            "pymupdf+tesseract",
            "ready",
            now,
            now,
            now,
        ),
    )


def _replace_pages(
    connection: sqlite3.Connection,
    entry: BookRegistryEntry,
    pages: list[ExtractedPage],
    pages_spec: str | None,
    progress: RulesIngestProgressCallback | None = None,
) -> None:
    page_numbers = [page.page_number for page in pages]
    placeholders = ", ".join("?" for _ in page_numbers)
    if page_numbers:
        connection.execute(
            f"""
            DELETE FROM rule_scope_assertions
            WHERE book_id = ?
              AND page_start IS NOT NULL
              AND page_start IN ({placeholders})
            """,
            [entry.book_id, *page_numbers],
        )
        connection.execute(
            f"DELETE FROM page_audit WHERE book_id = ? AND page_number IN ({placeholders})",
            [entry.book_id, *page_numbers],
        )
        connection.execute(
            f"DELETE FROM rule_chunks WHERE book_id = ? AND page_start IN ({placeholders})",
            [entry.book_id, *page_numbers],
        )
    connection.execute("DELETE FROM rule_chunks_fts WHERE book_id = ?", (entry.book_id,))

    total_pages = len(pages)
    chunk_count = 0
    _emit_progress(
        progress,
        phase="store",
        message="Storing extracted pages and chunks",
        current=0,
        total=total_pages,
        counters={"chunks": chunk_count},
    )
    for index, page in enumerate(pages, start=1):
        connection.execute(
            """
            INSERT INTO page_audit (
                book_id, page_number, extraction_method, char_count, alpha_ratio, confidence,
                suspect, quality_flags_json, content_hash, section_label, text_excerpt, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.book_id,
                page.page_number,
                page.extraction_method,
                page.char_count,
                page.alpha_ratio,
                page.confidence,
                int(page.suspect),
                json.dumps(page.quality_flags),
                fingerprint_text(page.text),
                page.section_label,
                summarize_text(page.text),
                timestamp_now(),
            ),
        )
        page_chunks = split_rule_chunks(page.text)
        for chunk_index, chunk_text in enumerate(page_chunks, start=1):
            structure = derive_rule_block_structure(
                book_id=entry.book_id,
                section_label=page.section_label,
                content=chunk_text,
                page_start=page.page_number,
                chunk_index=chunk_index,
            )
            excerpt = structure.source_window or summarize_text(structure.clean_content or chunk_text)
            content_hash = fingerprint_text(chunk_text)
            cursor = connection.execute(
                """
                INSERT INTO rule_chunks (
                    book_id, page_start, page_end, chunk_index, section_label, content,
                    excerpt, word_count, confidence, extraction_method, scope_tags_json, content_hash,
                    rule_block_id, heading_path_json, block_kind, clean_content, source_window,
                    structure_flags_json, structure_schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.book_id,
                    page.page_number,
                    page.page_number,
                    chunk_index,
                    page.section_label,
                    chunk_text,
                    excerpt,
                    len(chunk_text.split()),
                    page.confidence,
                    page.extraction_method,
                    json.dumps(entry.scope_tags),
                    content_hash,
                    structure.block_id,
                    json.dumps(structure.heading_path),
                    structure.block_kind,
                    structure.clean_content,
                    structure.source_window,
                    json.dumps(structure.structure_flags),
                    structure.schema_version,
                ),
            )
            _upsert_rule_chunk_retrieval_metadata(
                connection,
                chunk_id=int(cursor.lastrowid),
                section_label=page.section_label,
                content=chunk_text,
                word_count=len(chunk_text.split()),
                confidence=page.confidence,
                extraction_method=page.extraction_method,
                content_hash=content_hash,
            )
        chunk_count += len(page_chunks)
        _emit_progress(
            progress,
            phase="store",
            message=f"Stored page {page.page_number}",
            current=index,
            total=total_pages,
            counters={"chunks": chunk_count},
            details={"page_number": page.page_number},
        )

def _rebuild_rule_chunks_fts(
    connection: sqlite3.Connection,
    book_id: str,
    progress: RulesIngestProgressCallback | None = None,
) -> None:
    connection.execute("DELETE FROM rule_chunks_fts WHERE book_id = ?", (book_id,))
    chunk_rows = connection.execute(
        """
        SELECT
            rc.id,
            rc.book_id,
            b.book_title,
            b.tier,
            rc.scope_tags_json,
            rc.section_label,
            COALESCE(NULLIF(rc.clean_content, ''), rc.content) AS content
        FROM rule_chunks rc
        JOIN books b ON b.book_id = rc.book_id
        WHERE rc.book_id = ?
        ORDER BY rc.page_start, rc.chunk_index
        """,
        (book_id,),
    ).fetchall()
    _emit_progress(
        progress,
        phase="index",
        message="Building rules search index",
        current=0,
        total=len(chunk_rows),
    )
    for index, row in enumerate(chunk_rows, start=1):
        connection.execute(
            """
            INSERT INTO rule_chunks_fts (chunk_id, book_id, book_title, tier, scope_tags, section_label, content)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["book_id"],
                row["book_title"],
                row["tier"],
                " ".join(json.loads(row["scope_tags_json"])),
                row["section_label"],
                row["content"],
            ),
        )
        _emit_progress(
            progress,
            phase="index",
            message="Building rules search index",
            current=index,
            total=len(chunk_rows),
        )


def _fetch_books(connection: sqlite3.Connection, book_id: str | None = None) -> list[sqlite3.Row]:
    if book_id:
        rows = connection.execute("SELECT * FROM books WHERE book_id = ? ORDER BY book_title", (book_id,)).fetchall()
    else:
        rows = connection.execute("SELECT * FROM books ORDER BY tier DESC, book_title").fetchall()
    return rows


def _extract_pdf_outline(document) -> list[RulePdfOutlineEntry]:
    try:
        toc = document.get_toc()
    except Exception:
        return []
    outline: list[RulePdfOutlineEntry] = []
    for item in toc:
        if len(item) < 3:
            continue
        level, title, page = item[:3]
        try:
            page_number = int(page)
        except (TypeError, ValueError):
            continue
        clean_title = " ".join(str(title).split())
        if clean_title:
            outline.append(RulePdfOutlineEntry(level=int(level), title=clean_title, page=page_number))
    return outline


def _generate_and_apply_scope_assertions(
    connection: sqlite3.Connection,
    *,
    entry: BookRegistryEntry,
    pages: list[ExtractedPage],
    outline: list[RulePdfOutlineEntry],
) -> dict[str, Any]:
    generated = generate_scope_assertions(
        book_id=entry.book_id,
        title=entry.title,
        tier=entry.tier,
        pdf_path=entry.pdf_path,
        pages=pages,
        outline=outline,
    )
    page_numbers = [page.page_number for page in pages]
    _delete_scope_assertions_for_pages(connection, book_id=entry.book_id, page_numbers=page_numbers)
    assertion_ids: list[int] = []
    for assertion in generated.assertions:
        assertion_ids.append(_insert_scope_assertion(connection, entry.book_id, assertion))
    _apply_scope_assertions_to_chunks(connection, book_id=entry.book_id, assertion_ids=assertion_ids)
    _refresh_chunk_scope_tags(connection, entry.book_id)
    return _scope_summary(connection, book_id=entry.book_id)


def _delete_scope_assertions_for_pages(connection: sqlite3.Connection, *, book_id: str, page_numbers: list[int]) -> None:
    if page_numbers:
        placeholders = ", ".join("?" for _ in page_numbers)
        connection.execute(
            f"""
            DELETE FROM rule_scope_assertions
            WHERE book_id = ?
              AND page_start IS NOT NULL
              AND page_start IN ({placeholders})
            """,
            [book_id, *page_numbers],
        )
    connection.execute(
        """
        DELETE FROM rule_scope_assertions
        WHERE book_id = ?
          AND page_start IS NULL
          AND generator = ?
        """,
        (book_id, SCOPE_GENERATOR),
    )


def _insert_scope_assertion(connection: sqlite3.Connection, book_id: str, assertion: ScopeAssertionDraft) -> int:
    now = timestamp_now()
    cursor = connection.execute(
        """
        INSERT INTO rule_scope_assertions (
            book_id, tag, role, status, confidence, page_start, page_end,
            evidence_json, generator, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            book_id,
            assertion.tag,
            assertion.role,
            assertion.status,
            round(assertion.confidence, 4),
            assertion.page_start,
            assertion.page_end,
            json.dumps(assertion.evidence, sort_keys=True),
            SCOPE_GENERATOR,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _apply_scope_assertions_to_chunks(
    connection: sqlite3.Connection,
    *,
    book_id: str,
    assertion_ids: list[int] | None = None,
) -> None:
    parameters: list[Any] = [book_id, SCOPE_STATUS_APPLIED]
    id_clause = ""
    if assertion_ids is not None:
        if not assertion_ids:
            return
        placeholders = ", ".join("?" for _ in assertion_ids)
        id_clause = f"AND id IN ({placeholders})"
        parameters.extend(assertion_ids)
    assertions = connection.execute(
        f"""
        SELECT *
        FROM rule_scope_assertions
        WHERE book_id = ?
          AND status = ?
          {id_clause}
        ORDER BY page_start, page_end, id
        """,
        parameters,
    ).fetchall()
    for assertion in assertions:
        if assertion["page_start"] is None or assertion["page_end"] is None:
            chunk_rows = connection.execute(
                "SELECT id FROM rule_chunks WHERE book_id = ? ORDER BY page_start, chunk_index",
                (book_id,),
            ).fetchall()
        else:
            chunk_rows = connection.execute(
                """
                SELECT id FROM rule_chunks
                WHERE book_id = ?
                  AND page_start BETWEEN ? AND ?
                ORDER BY page_start, chunk_index
                """,
                (book_id, assertion["page_start"], assertion["page_end"]),
            ).fetchall()
        for row in chunk_rows:
            connection.execute(
                """
                INSERT OR IGNORE INTO rule_chunk_scope_assertions (chunk_id, assertion_id)
                VALUES (?, ?)
                """,
                (row["id"], assertion["id"]),
            )


def _refresh_chunk_scope_tags(connection: sqlite3.Connection, book_id: str) -> None:
    book = connection.execute("SELECT scope_tags_json FROM books WHERE book_id = ?", (book_id,)).fetchone()
    fallback_tags = json.loads(book["scope_tags_json"]) if book is not None else []
    chunk_rows = connection.execute("SELECT id FROM rule_chunks WHERE book_id = ?", (book_id,)).fetchall()
    for row in chunk_rows:
        tag_rows = connection.execute(
            """
            SELECT DISTINCT rsa.tag
            FROM rule_chunk_scope_assertions csa
            JOIN rule_scope_assertions rsa ON rsa.id = csa.assertion_id
            WHERE csa.chunk_id = ?
              AND rsa.status = ?
            ORDER BY rsa.tag
            """,
            (row["id"], SCOPE_STATUS_APPLIED),
        ).fetchall()
        tags = [tag_row["tag"] for tag_row in tag_rows]
        if not tags:
            tags = fallback_tags
        connection.execute(
            "UPDATE rule_chunks SET scope_tags_json = ? WHERE id = ?",
            (json.dumps(tags), row["id"]),
        )


def _scope_summary(connection: sqlite3.Connection, book_id: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT *
        FROM rule_scope_assertions
        WHERE book_id = ?
        ORDER BY
            CASE WHEN page_start IS NULL THEN -1 ELSE page_start END,
            page_end,
            role,
            tag
        """,
        (book_id,),
    ).fetchall()
    by_status: dict[str, int] = {}
    by_role: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        by_role[row["role"]] = by_role.get(row["role"], 0) + 1
    source_scope = sorted({row["tag"] for row in rows if row["role"] == SCOPE_ROLE_SOURCE and row["status"] == SCOPE_STATUS_APPLIED})
    notable = [
        _scope_assertion_to_dict(row, include_evidence=False)
        for row in rows
        if row["status"] in {SCOPE_STATUS_APPLIED, SCOPE_STATUS_SUGGESTED}
    ][:8]
    return {
        "generated": len(rows),
        "applied": by_status.get(SCOPE_STATUS_APPLIED, 0),
        "suggested": by_status.get(SCOPE_STATUS_SUGGESTED, 0),
        "review_needed": by_status.get(SCOPE_STATUS_SUGGESTED, 0),
        "rejected": by_status.get(SCOPE_STATUS_REJECTED, 0),
        "source_scope": source_scope,
        "by_status": by_status,
        "by_role": by_role,
        "confidence_thresholds": {
            "auto_apply": AUTO_APPLY_CONFIDENCE,
            "suggest": SUGGESTION_CONFIDENCE,
        },
        "notable": notable,
    }


def _scope_manifest(connection: sqlite3.Connection, book: sqlite3.Row) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT *
        FROM rule_scope_assertions
        WHERE book_id = ?
        ORDER BY
            CASE WHEN page_start IS NULL THEN -1 ELSE page_start END,
            page_end,
            role,
            tag
        """,
        (book["book_id"],),
    ).fetchall()
    source_scope = sorted(
        {
            row["tag"]
            for row in rows
            if row["role"] == SCOPE_ROLE_SOURCE and row["status"] == SCOPE_STATUS_APPLIED
        }
    )
    scopes = []
    for row in rows:
        if row["role"] == SCOPE_ROLE_SOURCE and row["page_start"] is None:
            continue
        scopes.append(_scope_assertion_to_dict(row, include_evidence=True))
    return {
        "book_id": book["book_id"],
        "book_title": book["book_title"],
        "tier": book["tier"],
        "source_scope": source_scope,
        "scopes": scopes,
    }


def _scope_assertion_to_dict(row: sqlite3.Row, *, include_evidence: bool = True) -> dict[str, Any]:
    data = {
        "id": row["id"],
        "tag": row["tag"],
        "role": row["role"],
        "status": row["status"],
        "confidence": row["confidence"],
        "pages": manifest_pages_label(row["page_start"], row["page_end"]),
    }
    if include_evidence:
        try:
            data["evidence"] = json.loads(row["evidence_json"])
        except json.JSONDecodeError:
            data["evidence"] = {}
    return data


def _require_book(connection: sqlite3.Connection, book_id: str) -> sqlite3.Row:
    book = connection.execute("SELECT * FROM books WHERE book_id = ?", (book_id,)).fetchone()
    if book is None:
        raise AppError(
            code="rules_book_missing",
            message="No ingested rulebook matches the requested scope operation.",
            hint="Ingest the rulebook first or choose a different `--book-id`.",
            details={"book_id": book_id},
            exit_code=2,
        )
    return book


def _book_entry_from_row(book: sqlite3.Row) -> BookRegistryEntry:
    return BookRegistryEntry(
        book_id=str(book["book_id"]),
        title=str(book["book_title"]),
        pdf_path=str(book["pdf_path"]),
        tier=str(book["tier"]),
        scope_tags=json.loads(book["scope_tags_json"]),
        page_count=int(book["page_count"]),
        pdf_fingerprint=str(book["pdf_fingerprint"]),
    )


def _review_target_row(
    connection: sqlite3.Connection,
    *,
    book_id: str,
    page: int,
    chunk_index: int | None,
) -> sqlite3.Row:
    if chunk_index is not None:
        row = connection.execute(
            """
            SELECT *
            FROM rule_chunks
            WHERE book_id = ? AND page_start = ? AND chunk_index = ?
            """,
            (book_id, page, chunk_index),
        ).fetchone()
        if row is None:
            raise AppError(
                code="rules_review_target_missing",
                message="No ingested rule chunk matches the requested review target.",
                hint="Use a page and chunk reported by `backet rules audit --json`.",
                details={"book_id": book_id, "page": page, "chunk_index": chunk_index},
                exit_code=2,
            )
        return row
    row = connection.execute(
        """
        SELECT page_number AS page_start, page_number AS page_end, content_hash
        FROM page_audit
        WHERE book_id = ? AND page_number = ?
        """,
        (book_id, page),
    ).fetchone()
    if row is None:
        raise AppError(
            code="rules_review_target_missing",
            message="No ingested rulebook page matches the requested review target.",
            hint="Use a page reported by `backet rules audit`.",
            details={"book_id": book_id, "page": page},
            exit_code=2,
        )
    return row


def _insert_audit_review(
    connection: sqlite3.Connection,
    *,
    book_id: str,
    target_type: str,
    page_start: int,
    page_end: int | None,
    chunk_index: int | None,
    finding_kind: str,
    decision: str,
    content_hash: str,
    reason: str,
    notes: str,
) -> None:
    connection.execute(
        """
        INSERT INTO rule_audit_reviews (
            book_id, target_type, page_start, page_end, chunk_index,
            finding_kind, decision, content_hash, reason, notes, decided_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO UPDATE SET
            decision = excluded.decision,
            reason = excluded.reason,
            notes = excluded.notes,
            decided_at = excluded.decided_at
        """,
        (
            book_id,
            target_type,
            page_start,
            page_end,
            chunk_index,
            finding_kind,
            decision,
            content_hash,
            reason,
            notes,
            timestamp_now(),
        ),
    )


def _store_retrieval_exclusion_for_target(
    connection: sqlite3.Connection,
    *,
    book_id: str,
    target_type: str,
    page_start: int,
    page_end: int,
    chunk_index: int | None,
    reason: str,
) -> int:
    if target_type == "chunk":
        rows = connection.execute(
            """
            SELECT id, page_start, page_end, chunk_index, content_hash
            FROM rule_chunks
            WHERE book_id = ? AND page_start = ? AND chunk_index = ?
            ORDER BY page_start, chunk_index
            """,
            (book_id, page_start, chunk_index),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT id, page_start, page_end, chunk_index, content_hash
            FROM rule_chunks
            WHERE book_id = ? AND page_start BETWEEN ? AND ?
            ORDER BY page_start, chunk_index
            """,
            (book_id, page_start, page_end),
        ).fetchall()
    now = timestamp_now()
    for row in rows:
        connection.execute(
            """
            INSERT INTO rule_retrieval_exclusions (
                book_id, chunk_id, page_start, page_end, chunk_index, content_hash, reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id, chunk_id, content_hash) DO UPDATE SET
                reason = excluded.reason,
                created_at = excluded.created_at
            """,
            (
                book_id,
                int(row["id"]),
                int(row["page_start"]),
                int(row["page_end"]),
                int(row["chunk_index"]),
                str(row["content_hash"]),
                reason,
                now,
            ),
        )
    return len(rows)


def _insert_page_text_override(
    connection: sqlite3.Connection,
    *,
    book_id: str,
    page: int,
    page_result: ExtractedPage,
    content_hash: str,
    reason: str,
    notes: str,
) -> None:
    connection.execute(
        """
        INSERT INTO rule_page_text_overrides (
            book_id, page_number, content_hash, char_count, alpha_ratio, reason, notes, replaced_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            book_id,
            page,
            content_hash,
            page_result.char_count,
            page_result.alpha_ratio,
            reason,
            notes,
            timestamp_now(),
        ),
    )


def _manual_replacement_is_usable(text: str) -> bool:
    if len(text) < MANUAL_REPLACEMENT_MIN_CHARS:
        return False
    alpha_chars = sum(1 for char in text if char.isalpha())
    alpha_ratio = alpha_chars / len(text) if text else 0.0
    return alpha_ratio >= 0.45


def _manifest_to_assertions(payload: dict[str, Any]) -> list[ScopeAssertionDraft]:
    assertions: list[ScopeAssertionDraft] = []
    for tag_value in _manifest_list(payload.get("source_scope")):
        tag = canonicalize_scope_tag(tag_value)
        assertions.append(
            ScopeAssertionDraft(
                tag=tag,
                role=SCOPE_ROLE_SOURCE,
                status=SCOPE_STATUS_APPLIED,
                confidence=1.0,
                evidence={"source": "reviewed_manifest", "generator": SCOPE_GENERATOR},
            )
        )
    for item in _manifest_list(payload.get("scopes")):
        if not isinstance(item, dict):
            raise AppError(
                code="rules_scope_manifest_invalid",
                message="Each scope manifest entry must be a mapping.",
                hint="Use entries with pages, tags, role, status, and confidence.",
                details={"entry": item},
                exit_code=2,
            )
        try:
            page_start, page_end = parse_manifest_pages(item.get("pages"))
        except (TypeError, ValueError) as exc:
            raise AppError(
                code="rules_scope_manifest_invalid",
                message="Scope manifest entry has an invalid page span.",
                hint="Use a page number, a range like `159-168`, or `book`.",
                details={"entry": item},
                exit_code=2,
            ) from exc
        role = str(item.get("role") or SCOPE_ROLE_SOURCE)
        status = str(item.get("status") or SCOPE_STATUS_APPLIED)
        if role not in {
            "source",
            "mechanical-authority",
            "setting-authority",
            "perspective",
            "mention",
        }:
            raise AppError(
                code="rules_scope_manifest_invalid",
                message="Scope manifest entry has an invalid role.",
                hint="Use source, mechanical-authority, setting-authority, perspective, or mention.",
                details={"role": role},
                exit_code=2,
            )
        if status not in SCOPE_STATUSES:
            raise AppError(
                code="rules_scope_manifest_invalid",
                message="Scope manifest entry has an invalid status.",
                hint="Use applied, suggested, rejected, or superseded.",
                details={"status": status},
                exit_code=2,
            )
        confidence = float(item.get("confidence") if item.get("confidence") is not None else 1.0)
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        tags = _manifest_list(item.get("tags") or item.get("tag"))
        if not tags:
            raise AppError(
                code="rules_scope_manifest_invalid",
                message="Scope manifest entry is missing tags.",
                hint="Use `tags: [sect:camarilla]` or `tag: sect:camarilla`.",
                details={"entry": item},
                exit_code=2,
            )
        for tag_value in tags:
            tag = canonicalize_scope_tag(str(tag_value))
            effective_status = status
            if not is_known_scope_tag(tag) and status == SCOPE_STATUS_APPLIED:
                effective_status = status_for_confidence(min(confidence, SUGGESTION_CONFIDENCE), tag)
            assertions.append(
                ScopeAssertionDraft(
                    tag=tag,
                    role=role,
                    status=effective_status,
                    confidence=confidence,
                    page_start=page_start,
                    page_end=page_end,
                    evidence={**evidence, "source": "reviewed_manifest", "generator": SCOPE_GENERATOR},
                )
            )
    return assertions


def _manifest_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _backfill_source_scope_assertions(connection: sqlite3.Connection) -> None:
    books = connection.execute("SELECT book_id, scope_tags_json FROM books").fetchall()
    now = timestamp_now()
    changed_books: set[str] = set()
    for book in books:
        try:
            tags = normalize_scope_tags(json.loads(book["scope_tags_json"]))
        except (TypeError, json.JSONDecodeError):
            tags = []
        for tag in tags:
            existing = connection.execute(
                """
                SELECT id FROM rule_scope_assertions
                WHERE book_id = ? AND tag = ? AND role = ? AND page_start IS NULL
                """,
                (book["book_id"], tag, SCOPE_ROLE_SOURCE),
            ).fetchone()
            if existing is not None:
                continue
            connection.execute(
                """
                INSERT INTO rule_scope_assertions (
                    book_id, tag, role, status, confidence, page_start, page_end,
                    evidence_json, generator, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)
                """,
                (
                    book["book_id"],
                    tag,
                    SCOPE_ROLE_SOURCE,
                    SCOPE_STATUS_APPLIED,
                    1.0,
                    json.dumps({"source": "migrated_book_scope_tags", "generator": SCOPE_GENERATOR}, sort_keys=True),
                    "migration",
                    now,
                    now,
                ),
            )
            changed_books.add(book["book_id"])
    for current_book_id in changed_books:
        _apply_scope_assertions_to_chunks(connection, book_id=current_book_id, assertion_ids=None)
        _refresh_chunk_scope_tags(connection, current_book_id)
        _rebuild_rule_chunks_fts(connection, current_book_id)


def _search_rule_chunks(
    connection: sqlite3.Connection,
    fts_query: str,
    book_id: str | None,
    scope_tags: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT
            rc.id AS chunk_id,
            rc.book_id,
            b.book_title,
            b.tier,
            b.scope_tags_json AS book_scope_tags_json,
            rc.scope_tags_json AS chunk_scope_tags_json,
            rc.page_start,
            rc.page_end,
            rc.chunk_index,
            rc.section_label,
            COALESCE(NULLIF(rc.clean_content, ''), rc.content) AS content,
            COALESCE(NULLIF(rc.source_window, ''), rc.excerpt) AS excerpt,
            rc.word_count,
            rc.content_hash,
            rc.confidence,
            rc.extraction_method,
            rc.rule_block_id,
            rc.heading_path_json AS block_heading_path_json,
            rc.block_kind,
            rc.source_window,
            rc.structure_flags_json,
            rc.structure_schema_version,
            m.section_kind,
            m.retrieval_flags_json,
            m.content_hash AS metadata_content_hash,
            m.rag_schema_version,
            m.heading_path_json,
            m.aliases_json,
            m.entity_locations_json,
            m.evidence_cues_json,
            COALESCE((
                SELECT json_group_array(json_object(
                    'id', rsa.id,
                    'tag', rsa.tag,
                    'role', rsa.role,
                    'status', rsa.status,
                    'confidence', rsa.confidence
                ))
                FROM rule_chunk_scope_assertions csa
                JOIN rule_scope_assertions rsa ON rsa.id = csa.assertion_id
                WHERE csa.chunk_id = rc.id
                  AND rsa.status = 'applied'
            ), '[]') AS scope_assertions_json,
            bm25(rule_chunks_fts) AS rank
        FROM rule_chunks_fts
        JOIN rule_chunks rc ON rc.id = rule_chunks_fts.chunk_id
        JOIN books b ON b.book_id = rc.book_id
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        LEFT JOIN rule_retrieval_exclusions rex
          ON rex.chunk_id = rc.id
         AND rex.content_hash = rc.content_hash
        WHERE rule_chunks_fts MATCH ?
          AND rex.id IS NULL
        ORDER BY rank
        LIMIT ?
        """,
        (fts_query, limit),
    ).fetchall()
    filtered: list[sqlite3.Row] = []
    for row in rows:
        if book_id and row["book_id"] != book_id:
            continue
        if row["tier"] == "supplement" and scope_tags and not _row_matches_scope(row, scope_tags):
            continue
        filtered.append(row)
    return filtered


def _search_planned_rule_chunks(
    connection: sqlite3.Connection,
    *,
    query_plan: RulesQueryPlan,
    book_id: str | None,
    scope_tags: list[str],
    limit: int,
) -> tuple[list[sqlite3.Row], list[dict[str, Any]], bool]:
    rows: list[sqlite3.Row] = []
    executed_queries: list[dict[str, Any]] = []

    for retrieval_query in query_plan.retrieval_queries:
        if retrieval_query.role == "raw_fallback":
            continue
        fts_query = build_rules_fts_query(retrieval_query.text)
        if not fts_query:
            continue
        current_rows = _search_rule_chunks(
            connection,
            fts_query,
            book_id=book_id,
            scope_tags=scope_tags,
            limit=limit,
        )
        rows.extend(current_rows)
        executed_queries.append(
            {
                "role": retrieval_query.role,
                "text": retrieval_query.text,
                "terms": retrieval_query.terms,
                "evidence": retrieval_query.evidence,
                "fts_query": fts_query,
                "matched_chunks": len(current_rows),
                "raw_fallback": False,
            }
        )

    raw_fallback_used = False
    if not rows:
        fallback = next((query for query in query_plan.retrieval_queries if query.role == "raw_fallback"), None)
        if fallback is not None:
            fts_query = build_rules_fts_query(fallback.text)
            if fts_query:
                current_rows = _search_rule_chunks(
                    connection,
                    fts_query,
                    book_id=book_id,
                    scope_tags=scope_tags,
                    limit=limit,
                )
                rows.extend(current_rows)
                raw_fallback_used = True
                executed_queries.append(
                    {
                        "role": fallback.role,
                        "text": fallback.text,
                        "terms": fallback.terms,
                        "evidence": fallback.evidence,
                        "fts_query": fts_query,
                        "matched_chunks": len(current_rows),
                        "raw_fallback": True,
                    }
                )

    return rows, executed_queries, raw_fallback_used


def _generate_rag_v2_candidates(
    connection: sqlite3.Connection,
    *,
    query_plan: RulesQueryPlan,
    book_id: str | None,
    scope_tags: list[str],
    exact_limit: int,
    semantic_limit: int,
    embedding_backend: EmbeddingBackend | None = None,
) -> tuple[list[sqlite3.Row], SemanticRulesSearch, dict[int, set[str]], dict[str, Any]]:
    exact_rows: list[sqlite3.Row] = []
    channel_matches: dict[int, set[str]] = {}
    channels: list[RagV2ChannelDiagnostics] = []

    def run_channel(channel: str, cap: int, query: str | None, callback: Callable[[], list[sqlite3.Row]], *, raw_fallback: bool = False) -> None:
        started = time.perf_counter()
        error: dict[str, Any] | None = None
        try:
            rows = callback()
        except sqlite3.Error as exc:
            rows = []
            error = {"code": "rules_retrieval_channel_failed", "message": str(exc)}
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        exact_rows.extend(rows)
        for row in rows:
            channel_matches.setdefault(int(row["chunk_id"]), set()).add(channel)
        channels.append(
            RagV2ChannelDiagnostics(
                channel=channel,
                cap=cap,
                elapsed_ms=elapsed_ms,
                candidate_count=len(rows),
                query=query,
                raw_fallback=raw_fallback,
                error=error,
            )
        )

    if query_plan.resolved_entities:
        run_channel(
            "entity_anchor",
            RAG_V2_EXACT_CHANNEL_CAP,
            " | ".join(str(entity.get("canonical_name") or "") for entity in query_plan.resolved_entities),
            lambda: _search_rule_chunks_by_entity_anchors(
                connection,
                resolved_entities=query_plan.resolved_entities,
                book_id=book_id,
                scope_tags=scope_tags,
                limit=RAG_V2_EXACT_CHANNEL_CAP,
            ),
        )

    for retrieval_query in query_plan.retrieval_queries:
        if retrieval_query.role == "raw_fallback":
            continue
        fts_query = build_rules_fts_query(retrieval_query.text)
        if not fts_query:
            continue
        run_channel(
            f"planned_exact:{retrieval_query.role}",
            min(exact_limit, RAG_V2_EXACT_CHANNEL_CAP),
            retrieval_query.text,
            lambda fts_query=fts_query: _search_rule_chunks(
                connection,
                fts_query,
                book_id=book_id,
                scope_tags=scope_tags,
                limit=min(exact_limit, RAG_V2_EXACT_CHANNEL_CAP),
            ),
        )

    phrase_queries = _rag_v2_phrase_queries(query_plan)
    for phrase in phrase_queries:
        fts_query = build_rules_phrase_fts_query(phrase)
        if not fts_query:
            continue
        run_channel(
            "phrase",
            RAG_V2_PHRASE_CHANNEL_CAP,
            phrase,
            lambda fts_query=fts_query: _search_rule_chunks(
                connection,
                fts_query,
                book_id=book_id,
                scope_tags=scope_tags,
                limit=RAG_V2_PHRASE_CHANNEL_CAP,
            ),
        )

    alias_query = " ".join(_rag_v2_alias_terms(query_plan))
    alias_fts = build_rules_fts_query(alias_query)
    if alias_fts:
        run_channel(
            "alias",
            RAG_V2_ALIAS_CHANNEL_CAP,
            alias_query,
            lambda: _search_rule_chunks(
                connection,
                alias_fts,
                book_id=book_id,
                scope_tags=scope_tags,
                limit=RAG_V2_ALIAS_CHANNEL_CAP,
            ),
        )

    metadata_terms = _rag_v2_metadata_terms(query_plan)
    if metadata_terms:
        run_channel(
            "metadata",
            RAG_V2_METADATA_CHANNEL_CAP,
            " ".join(metadata_terms),
            lambda: _search_rule_chunks_by_metadata(
                connection,
                metadata_terms=metadata_terms,
                book_id=book_id,
                scope_tags=scope_tags,
                limit=RAG_V2_METADATA_CHANNEL_CAP,
            ),
        )

    rule_unit_terms = _rag_v2_rule_unit_terms(query_plan)
    if rule_unit_terms:
        run_channel(
            "rule_unit",
            RULE_UNIT_CHANNEL_CAP,
            " ".join(rule_unit_terms),
            lambda: _search_rule_chunks_by_rule_units(
                connection,
                terms=rule_unit_terms,
                book_id=book_id,
                scope_tags=scope_tags,
                limit=RULE_UNIT_CHANNEL_CAP,
            ),
        )

    raw_fallback = next((query for query in query_plan.retrieval_queries if query.role == "raw_fallback"), None)
    if raw_fallback is not None:
        raw_fts = build_rules_fts_query(raw_fallback.text)
        if raw_fts:
            run_channel(
                "raw_fallback",
                RAG_V2_RAW_FALLBACK_CHANNEL_CAP,
                raw_fallback.text,
                lambda: _search_rule_chunks(
                    connection,
                    raw_fts,
                    book_id=book_id,
                    scope_tags=scope_tags,
                    limit=RAG_V2_RAW_FALLBACK_CHANNEL_CAP,
                ),
                raw_fallback=True,
            )

    semantic_started = time.perf_counter()
    semantic = _search_semantic_rule_chunks(
        connection,
        query_plan.semantic_query,
        book_id=book_id,
        scope_tags=scope_tags,
        limit=semantic_limit,
        embedding_backend=embedding_backend,
    )
    semantic_elapsed = round((time.perf_counter() - semantic_started) * 1000, 3)
    for row, _score in semantic.candidates:
        channel_matches.setdefault(int(row["chunk_id"]), set()).add("semantic")
    channels.append(
        RagV2ChannelDiagnostics(
            channel="semantic",
            cap=semantic_limit,
            elapsed_ms=semantic_elapsed,
            candidate_count=len(semantic.candidates),
            query=query_plan.semantic_query,
            error=semantic.error,
        )
    )

    diagnostics = {
        "schema_version": RULES_RAG_V2_RETRIEVAL_SCHEMA_VERSION,
        "channels": [channel.to_dict() for channel in channels],
        "candidate_caps": {
            "planned_exact": RAG_V2_EXACT_CHANNEL_CAP,
            "phrase": RAG_V2_PHRASE_CHANNEL_CAP,
            "alias": RAG_V2_ALIAS_CHANNEL_CAP,
            "metadata": RAG_V2_METADATA_CHANNEL_CAP,
            "rule_unit": RULE_UNIT_CHANNEL_CAP,
            "raw_fallback": RAG_V2_RAW_FALLBACK_CHANNEL_CAP,
            "semantic": semantic_limit,
        },
        "semantic_quality": _semantic_quality(semantic),
        "raw_fallback_used": any(channel.raw_fallback and channel.candidate_count > 0 for channel in channels),
    }
    return exact_rows, semantic, channel_matches, diagnostics


def build_rules_phrase_fts_query(text: str) -> str:
    terms = _rules_query_terms(text)
    if len(terms) < 2:
        return ""
    return '"' + " ".join(term.replace('"', "") for term in terms) + '"'


def _rag_v2_phrase_queries(query_plan: RulesQueryPlan) -> list[str]:
    return [
        term
        for term in _dedupe_text_values([*query_plan.canonical_terms, *query_plan.expanded_terms])
        if len(_rules_query_terms(term)) > 1
    ][:6]


def _rag_v2_alias_terms(query_plan: RulesQueryPlan) -> list[str]:
    terms: list[str] = []
    _extend_unique(terms, query_plan.canonical_terms)
    _extend_unique(terms, query_plan.expanded_terms)
    for values in query_plan.entities.values():
        _extend_unique(terms, values)
    return _dedupe_text_values(terms)[:24]


def _rag_v2_metadata_terms(query_plan: RulesQueryPlan) -> list[str]:
    terms: list[str] = []
    _extend_unique(terms, query_plan.canonical_terms)
    _extend_unique(terms, query_plan.expanded_terms)
    _extend_unique(terms, query_plan.required_evidence)
    _extend_unique(terms, _intent_evidence_cues(query_plan.intents))
    return _dedupe_text_values(terms)[:24]


def _rag_v2_rule_unit_terms(query_plan: RulesQueryPlan) -> list[str]:
    terms: list[str] = []
    _extend_unique(terms, query_plan.canonical_terms)
    _extend_unique(terms, query_plan.expanded_terms)
    _extend_unique(terms, query_plan.required_evidence)
    _extend_unique(terms, _intent_evidence_cues(query_plan.intents))
    for intent in query_plan.intents:
        if intent == INTENT_DEFINITION:
            _extend_unique(terms, ["base_rule", "definition", "effect"])
        elif intent == INTENT_ADVANCEMENT:
            _extend_unique(terms, ["advancement", "prerequisite", "cost"])
        elif intent == INTENT_TARGETING:
            _extend_unique(terms, ["target", "system", "restriction"])
        elif intent == INTENT_COST:
            _extend_unique(terms, ["cost", "prerequisite"])
    return _dedupe_text_values(terms)[:28]


def _search_rule_chunks_by_entity_anchors(
    connection: sqlite3.Connection,
    *,
    resolved_entities: list[dict[str, Any]],
    book_id: str | None,
    scope_tags: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    chunk_ids: list[int] = []
    block_ids: list[str] = []
    for entity in resolved_entities:
        for anchor in entity.get("source_anchors") or []:
            if not isinstance(anchor, dict):
                continue
            try:
                chunk_id = int(anchor.get("chunk_id") or 0)
            except (TypeError, ValueError):
                chunk_id = 0
            if chunk_id:
                chunk_ids.append(chunk_id)
            block_id = str(anchor.get("rule_block_id") or "")
            if block_id:
                block_ids.append(block_id)
    chunk_ids = sorted(set(chunk_ids))
    block_ids = sorted(set(block_ids))
    if not chunk_ids and not block_ids:
        return []
    where_parts: list[str] = []
    parameters: list[Any] = []
    if chunk_ids:
        where_parts.append(f"rc.id IN ({','.join('?' for _ in chunk_ids)})")
        parameters.extend(chunk_ids)
    if block_ids:
        where_parts.append(f"rc.rule_block_id IN ({','.join('?' for _ in block_ids)})")
        parameters.extend(block_ids)
    rows = connection.execute(
        f"""
        SELECT
            rc.id AS chunk_id,
            rc.book_id,
            b.book_title,
            b.tier,
            b.scope_tags_json AS book_scope_tags_json,
            rc.scope_tags_json AS chunk_scope_tags_json,
            rc.page_start,
            rc.page_end,
            rc.chunk_index,
            rc.section_label,
            COALESCE(NULLIF(rc.clean_content, ''), rc.content) AS content,
            COALESCE(NULLIF(rc.source_window, ''), rc.excerpt) AS excerpt,
            rc.word_count,
            rc.content_hash,
            rc.confidence,
            rc.extraction_method,
            rc.rule_block_id,
            rc.heading_path_json AS block_heading_path_json,
            rc.block_kind,
            rc.source_window,
            rc.structure_flags_json,
            rc.structure_schema_version,
            m.section_kind,
            m.retrieval_flags_json,
            m.content_hash AS metadata_content_hash,
            m.rag_schema_version,
            m.heading_path_json,
            m.aliases_json,
            m.entity_locations_json,
            m.evidence_cues_json,
            COALESCE((
                SELECT json_group_array(json_object(
                    'id', rsa.id,
                    'tag', rsa.tag,
                    'role', rsa.role,
                    'status', rsa.status,
                    'confidence', rsa.confidence
                ))
                FROM rule_chunk_scope_assertions csa
                JOIN rule_scope_assertions rsa ON rsa.id = csa.assertion_id
                WHERE csa.chunk_id = rc.id
                  AND rsa.status = 'applied'
            ), '[]') AS scope_assertions_json,
            -1.0 AS rank
        FROM rule_chunks rc
        JOIN books b ON b.book_id = rc.book_id
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        LEFT JOIN rule_retrieval_exclusions rex
          ON rex.chunk_id = rc.id
         AND rex.content_hash = rc.content_hash
        WHERE rex.id IS NULL
          AND ({' OR '.join(where_parts)})
        ORDER BY rc.book_id, rc.page_start, rc.chunk_index
        LIMIT ?
        """,
        [*parameters, limit],
    ).fetchall()
    filtered: list[sqlite3.Row] = []
    for row in rows:
        if book_id and row["book_id"] != book_id:
            continue
        if row["tier"] == "supplement" and scope_tags and not _row_matches_scope(row, scope_tags):
            continue
        filtered.append(row)
    return filtered


def _search_rule_chunks_by_metadata(
    connection: sqlite3.Connection,
    *,
    metadata_terms: list[str],
    book_id: str | None,
    scope_tags: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    patterns = [f"%{term.casefold()}%" for term in metadata_terms if term]
    if not patterns:
        return []
    where_parts: list[str] = []
    parameters: list[Any] = []
    for pattern in patterns:
        where_parts.append(
            "("
            "m.aliases_json LIKE ? OR m.entity_locations_json LIKE ? OR m.evidence_cues_json LIKE ? "
            "OR rc.section_label LIKE ? OR rc.heading_path_json LIKE ? OR rc.clean_content LIKE ? OR rc.source_window LIKE ?"
            ")"
        )
        parameters.extend([pattern, pattern, pattern, pattern, pattern, pattern, pattern])
    rows = connection.execute(
        f"""
        SELECT
            rc.id AS chunk_id,
            rc.book_id,
            b.book_title,
            b.tier,
            b.scope_tags_json AS book_scope_tags_json,
            rc.scope_tags_json AS chunk_scope_tags_json,
            rc.page_start,
            rc.page_end,
            rc.chunk_index,
            rc.section_label,
            COALESCE(NULLIF(rc.clean_content, ''), rc.content) AS content,
            COALESCE(NULLIF(rc.source_window, ''), rc.excerpt) AS excerpt,
            rc.word_count,
            rc.content_hash,
            rc.confidence,
            rc.extraction_method,
            rc.rule_block_id,
            rc.heading_path_json AS block_heading_path_json,
            rc.block_kind,
            rc.source_window,
            rc.structure_flags_json,
            rc.structure_schema_version,
            m.section_kind,
            m.retrieval_flags_json,
            m.content_hash AS metadata_content_hash,
            m.rag_schema_version,
            m.heading_path_json,
            m.aliases_json,
            m.entity_locations_json,
            m.evidence_cues_json,
            COALESCE((
                SELECT json_group_array(json_object(
                    'id', rsa.id,
                    'tag', rsa.tag,
                    'role', rsa.role,
                    'status', rsa.status,
                    'confidence', rsa.confidence
                ))
                FROM rule_chunk_scope_assertions csa
                JOIN rule_scope_assertions rsa ON rsa.id = csa.assertion_id
                WHERE csa.chunk_id = rc.id
                  AND rsa.status = 'applied'
            ), '[]') AS scope_assertions_json,
            0.0 AS rank
        FROM rule_chunks rc
        JOIN books b ON b.book_id = rc.book_id
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        LEFT JOIN rule_retrieval_exclusions rex
          ON rex.chunk_id = rc.id
         AND rex.content_hash = rc.content_hash
        WHERE rex.id IS NULL
          AND ({' OR '.join(where_parts)})
        ORDER BY rc.book_id, rc.page_start, rc.chunk_index
        LIMIT ?
        """,
        [*parameters, limit],
    ).fetchall()
    filtered: list[sqlite3.Row] = []
    for row in rows:
        if book_id and row["book_id"] != book_id:
            continue
        if row["tier"] == "supplement" and scope_tags and not _row_matches_scope(row, scope_tags):
            continue
        filtered.append(row)
    return filtered


def _search_rule_chunks_by_rule_units(
    connection: sqlite3.Connection,
    *,
    terms: list[str],
    book_id: str | None,
    scope_tags: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    patterns = [f"%{term.casefold()}%" for term in terms if term]
    if not patterns:
        return []
    where_parts: list[str] = []
    parameters: list[Any] = []
    for pattern in patterns:
        where_parts.append(
            "("
            "ru.unit_id LIKE ? OR ru.unit_kind LIKE ? OR ru.authority_role LIKE ? "
            "OR ru.heading_path_json LIKE ? OR ru.entity_tags_json LIKE ? OR ru.mechanic_tags_json LIKE ? "
            "OR ru.answer_facets_json LIKE ? OR ru.source_window LIKE ?"
            ")"
        )
        parameters.extend([pattern, pattern, pattern, pattern, pattern, pattern, pattern, pattern])
    rows = connection.execute(
        f"""
        SELECT
            rc.id AS chunk_id,
            rc.book_id,
            b.book_title,
            b.tier,
            b.scope_tags_json AS book_scope_tags_json,
            rc.scope_tags_json AS chunk_scope_tags_json,
            rc.page_start,
            rc.page_end,
            rc.chunk_index,
            rc.section_label,
            COALESCE(NULLIF(rc.clean_content, ''), rc.content) AS content,
            COALESCE(NULLIF(rc.source_window, ''), rc.excerpt) AS excerpt,
            rc.word_count,
            rc.content_hash,
            rc.confidence,
            rc.extraction_method,
            rc.rule_block_id,
            rc.heading_path_json AS block_heading_path_json,
            rc.block_kind,
            rc.source_window,
            rc.structure_flags_json,
            rc.structure_schema_version,
            m.section_kind,
            m.retrieval_flags_json,
            m.content_hash AS metadata_content_hash,
            m.rag_schema_version,
            m.heading_path_json,
            m.aliases_json,
            m.entity_locations_json,
            m.evidence_cues_json,
            COALESCE((
                SELECT json_group_array(json_object(
                    'id', rsa.id,
                    'tag', rsa.tag,
                    'role', rsa.role,
                    'status', rsa.status,
                    'confidence', rsa.confidence
                ))
                FROM rule_chunk_scope_assertions csa
                JOIN rule_scope_assertions rsa ON rsa.id = csa.assertion_id
                WHERE csa.chunk_id = rc.id
                  AND rsa.status = 'applied'
            ), '[]') AS scope_assertions_json,
            0.0 AS rank
        FROM rule_units ru
        JOIN rule_chunks rc ON rc.id = ru.primary_chunk_id
        JOIN books b ON b.book_id = rc.book_id
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        LEFT JOIN rule_retrieval_exclusions rex
          ON rex.chunk_id = rc.id
         AND rex.content_hash = rc.content_hash
        WHERE rex.id IS NULL
          AND ru.source_content_hash = rc.content_hash
          AND ru.schema_version = ?
          AND ({' OR '.join(where_parts)})
        GROUP BY rc.id
        ORDER BY MAX(ru.confidence) DESC, rc.book_id, rc.page_start, rc.chunk_index
        LIMIT ?
        """,
        [RULE_UNIT_SCHEMA_VERSION, *parameters, limit],
    ).fetchall()
    filtered: list[sqlite3.Row] = []
    for row in rows:
        if book_id and row["book_id"] != book_id:
            continue
        if row["tier"] == "supplement" and scope_tags and not _row_matches_scope(row, scope_tags):
            continue
        filtered.append(row)
    return filtered


def _semantic_quality(semantic: SemanticRulesSearch) -> dict[str, Any]:
    if semantic.retrieval_mode == "semantic_unavailable":
        return {
            "status": "unavailable",
            "backend": semantic.backend_name,
            "model": semantic.model_name,
            "message": "Semantic retrieval is unavailable; exact, phrase, alias, and metadata channels were used.",
        }
    if semantic.backend_name == "hash":
        return {
            "status": "degraded",
            "backend": semantic.backend_name,
            "model": semantic.model_name,
            "message": "Hash embeddings are a deterministic fallback and are not sentence-level semantic retrieval.",
        }
    return {
        "status": "production",
        "backend": semantic.backend_name,
        "model": semantic.model_name,
        "message": "Semantic retrieval used the configured embedding backend.",
    }


def _row_matches_scope(row: sqlite3.Row, scope_tags: list[str]) -> bool:
    requested = set(scope_tags)
    chunk_tags = set(_json_list(_row_optional(row, "chunk_scope_tags_json")))
    if requested.issubset(chunk_tags):
        return True
    assertions = _json_assertions(_row_optional(row, "scope_assertions_json"))
    if assertions and requested.issubset({assertion["tag"] for assertion in assertions}):
        return True
    book_tags = set(_json_list(_row_optional(row, "book_scope_tags_json")))
    return not assertions and requested.issubset(book_tags)


def _apply_precedence(
    rows: list[RuleSearchCandidate],
    scope_tags: list[str],
    explicit_book_id: str | None,
) -> tuple[list[RuleSearchCandidate], list[RuleSearchCandidate], dict[str, Any] | None]:
    rows = sorted(rows, key=_candidate_sort_key)
    supplements = [row for row in rows if row.tier == "supplement"]
    cores = [row for row in rows if row.tier == "core"]
    authority_supplements = [
        row for row in supplements if _candidate_has_precedence_scope(row, scope_tags)
    ]
    contextual_supplements = [row for row in supplements if row not in authority_supplements]
    if explicit_book_id:
        return rows, [], None
    if not authority_supplements:
        if cores:
            return cores, contextual_supplements, None
        if contextual_supplements:
            return contextual_supplements, [], None
        return cores, [], None

    by_book: dict[str, list[RuleSearchCandidate]] = {}
    for row in authority_supplements:
        by_book.setdefault(row.book_id, []).append(row)

    book_scores = []
    for current_book_id, current_rows in by_book.items():
        score = max(row.score for row in current_rows)
        row_tags = current_rows[0].scope_tags
        overlap = len(set(row_tags) & set(scope_tags)) if scope_tags else len(row_tags)
        book_scores.append((current_book_id, score, overlap, current_rows))

    book_scores.sort(key=lambda item: (-item[1], -item[2], item[0]))
    primary_book_id, primary_score, _, primary_rows = book_scores[0]
    competing = [
        {
            "book_id": book_id,
            "book_title": rows_for_book[0].book_title,
            "score": round(score, 6),
            "scope_tags": rows_for_book[0].scope_tags,
        }
        for book_id, score, _, rows_for_book in book_scores[1:]
        if abs(score - primary_score) <= 0.2
    ]
    if competing:
        return [], [], {
            "query_scope_tags": scope_tags,
            "preferred_book": primary_book_id,
            "conflicting_books": [
                {
                    "book_id": primary_book_id,
                    "book_title": primary_rows[0].book_title,
                    "score": round(primary_score, 6),
                    "scope_tags": primary_rows[0].scope_tags,
                },
                *competing,
            ],
        }

    primary = [row for row in authority_supplements if row.book_id == primary_book_id]
    fallback = cores + contextual_supplements
    return primary, fallback, None


def _row_to_rule_result(row: RuleSearchCandidate) -> dict[str, Any]:
    return {
        "book_id": row.book_id,
        "book_title": row.book_title,
        "tier": row.tier,
        "scope_tags": row.scope_tags,
        "book_scope_tags": row.book_scope_tags,
        "scope_assertions": row.scope_assertions,
        "scope_fallback_used": row.scope_fallback_used,
        "page_start": row.page_start,
        "page_end": row.page_end,
        "chunk_index": row.chunk_index,
        "section_label": row.section_label,
        "excerpt": _candidate_source_window(row),
        "content": row.content,
        "confidence": row.confidence,
        "extraction_method": row.extraction_method,
        "score": round(row.score, 6),
        "exact_score": round(row.exact_score, 6),
        "semantic_score": round(row.semantic_score, 6),
        "lexical_score": round(row.lexical_score, 6),
        "evidence_score": round(row.evidence_score, 6),
        "quality_penalty": round(row.quality_penalty, 6),
        "match_reasons": sorted(set(row.match_reasons)),
        "section_kind": row.section_kind,
        "retrieval_flags": row.retrieval_flags,
        "rule_block_id": row.rule_block_id,
        "block_kind": row.block_kind,
        "source_window": row.source_window,
        "structure_schema_version": row.structure_schema_version,
        "structure_flags": row.structure_flags,
        "rag_schema_version": row.rag_schema_version,
        "heading_path": row.heading_path,
        "aliases": row.aliases,
        "entity_locations": row.entity_locations,
        "evidence_cues": row.evidence_cues,
        "rule_units": row.rule_units,
        "rule_unit_kinds": sorted({str(unit.get("unit_kind")) for unit in row.rule_units if unit.get("unit_kind")}),
        "rule_unit_authority_roles": sorted({str(unit.get("authority_role")) for unit in row.rule_units if unit.get("authority_role")}),
        "rule_unit_answer_facets": sorted(
            {
                str(facet)
                for unit in row.rule_units
                for facet in (unit.get("answer_facets") if isinstance(unit.get("answer_facets"), list) else [])
            }
        ),
        "retrieval_channels": sorted(set(row.retrieval_channels)),
        "rejection_reasons": sorted(set(row.rejection_reasons)),
    }


def _candidate_source_window(candidate: RuleSearchCandidate, limit: int = 360) -> str:
    if candidate.source_window and candidate.structure_schema_version == RULE_BLOCK_STRUCTURE_SCHEMA_VERSION:
        return summarize_text(candidate.source_window, limit=limit)
    content = " ".join(str(candidate.content or "").split())
    if not content:
        return str(candidate.excerpt or "")
    anchors: list[str] = []
    _extend_unique(anchors, candidate.aliases)
    _extend_unique(anchors, [str(entity.get("alias") or "") for entity in candidate.entity_locations])
    cue_anchors = {
        "system": "system:",
        "cost": "cost:",
        "dice_pool": "dice pool",
        "targeting": "target",
        "advancement": "experience",
        "consequence": "on a success",
        "definition": str(candidate.section_label or ""),
    }
    for cue in candidate.evidence_cues:
        if cue in cue_anchors:
            _add_unique(anchors, cue_anchors[cue])
    normalized = _normalize_rule_alias(content)
    best_index = -1
    for anchor in anchors:
        needle = _normalize_rule_alias(anchor)
        if not needle:
            continue
        match = re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", normalized)
        if match is not None:
            best_index = match.start()
            break
    if best_index < 0:
        return str(candidate.excerpt or content[:limit])

    # Use a raw-content search for a readable start whenever possible; normalized
    # positions are only approximate after punctuation and whitespace cleanup.
    raw_lower = content.casefold()
    raw_indexes = [raw_lower.find(str(anchor).casefold().rstrip(":")) for anchor in anchors if str(anchor).strip()]
    raw_indexes = [index for index in raw_indexes if index >= 0]
    raw_index = min(raw_indexes) if raw_indexes else min(best_index, len(content))
    start = max(0, raw_index - 80)
    end = min(len(content), start + limit)
    if start > 0:
        previous_space = content.find(" ", start)
        if previous_space > 0 and previous_space < start + 40:
            start = previous_space + 1
    if end < len(content):
        end_space = content.rfind(" ", start, end)
        if end_space > start + 80:
            end = end_space
    window = content[start:end].strip()
    if start > 0:
        window = f"... {window}"
    if end < len(content):
        window = f"{window} ..."
    return window


def _candidate_has_precedence_scope(candidate: RuleSearchCandidate, scope_tags: list[str]) -> bool:
    if not scope_tags:
        return False
    requested = set(scope_tags)
    authoritative_tags = {
        assertion["tag"]
        for assertion in candidate.scope_assertions
        if assertion.get("role") in AUTHORITATIVE_SCOPE_ROLES
    }
    if requested.issubset(authoritative_tags):
        return True
    return candidate.scope_fallback_used and requested.issubset(set(candidate.scope_tags))


def _search_semantic_rule_chunks(
    connection: sqlite3.Connection,
    query: str,
    book_id: str | None,
    scope_tags: list[str],
    limit: int,
    embedding_backend: EmbeddingBackend | None = None,
) -> SemanticRulesSearch:
    try:
        backend = embedding_backend or resolve_embedding_backend()
        query_vector = backend.encode_many([query]).vectors[0]
    except AppError as error:
        return SemanticRulesSearch(
            candidates=[],
            retrieval_mode="semantic_unavailable",
            backend_name=None,
            model_name=None,
            indexed_chunks=0,
            error=_semantic_error(error),
        )
    except Exception as exc:  # pragma: no cover - defensive guard for optional ML backends
        return SemanticRulesSearch(
            candidates=[],
            retrieval_mode="semantic_unavailable",
            backend_name=None,
            model_name=None,
            indexed_chunks=0,
            error={"code": "rules_semantic_query_failed", "message": str(exc)},
        )

    rows = connection.execute(
        """
        SELECT
            rc.id AS chunk_id,
            rc.book_id,
            b.book_title,
            b.tier,
            b.scope_tags_json AS book_scope_tags_json,
            rc.scope_tags_json AS chunk_scope_tags_json,
            rc.page_start,
            rc.page_end,
            rc.chunk_index,
            rc.section_label,
            COALESCE(NULLIF(rc.clean_content, ''), rc.content) AS content,
            COALESCE(NULLIF(rc.source_window, ''), rc.excerpt) AS excerpt,
            rc.word_count,
            rc.content_hash,
            rc.confidence,
            rc.extraction_method,
            rc.rule_block_id,
            rc.heading_path_json AS block_heading_path_json,
            rc.block_kind,
            rc.source_window,
            rc.structure_flags_json,
            rc.structure_schema_version,
            e.embedding_json,
            m.section_kind,
            m.retrieval_flags_json,
            m.content_hash AS metadata_content_hash,
            m.rag_schema_version,
            m.heading_path_json,
            m.aliases_json,
            m.entity_locations_json,
            m.evidence_cues_json,
            COALESCE((
                SELECT json_group_array(json_object(
                    'id', rsa.id,
                    'tag', rsa.tag,
                    'role', rsa.role,
                    'status', rsa.status,
                    'confidence', rsa.confidence
                ))
                FROM rule_chunk_scope_assertions csa
                JOIN rule_scope_assertions rsa ON rsa.id = csa.assertion_id
                WHERE csa.chunk_id = rc.id
                  AND rsa.status = 'applied'
            ), '[]') AS scope_assertions_json
        FROM rule_chunks rc
        JOIN books b ON b.book_id = rc.book_id
        JOIN rule_chunk_embeddings e ON e.chunk_id = rc.id
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        LEFT JOIN rule_retrieval_exclusions rex
          ON rex.chunk_id = rc.id
         AND rex.content_hash = rc.content_hash
        WHERE e.backend = ? AND e.model = ? AND e.content_hash = rc.content_hash
          AND rex.id IS NULL
        ORDER BY rc.book_id, rc.page_start, rc.chunk_index
        """,
        (backend.name, backend.model_name),
    ).fetchall()

    filtered: list[sqlite3.Row] = []
    for row in rows:
        if book_id and row["book_id"] != book_id:
            continue
        if row["tier"] == "supplement" and scope_tags and not _row_matches_scope(row, scope_tags):
            continue
        filtered.append(row)

    if not filtered:
        return SemanticRulesSearch(
            candidates=[],
            retrieval_mode="exact_only",
            backend_name=backend.name,
            model_name=backend.model_name,
            indexed_chunks=0,
        )

    scored: list[tuple[sqlite3.Row, float]] = []
    for row in filtered:
        try:
            vector = json.loads(row["embedding_json"])
        except json.JSONDecodeError:
            continue
        score = max(cosine_similarity(query_vector, vector), 0.0)
        if score > 0:
            scored.append((row, score))

    scored.sort(key=lambda item: (-item[1], int(item[0]["chunk_id"])))
    return SemanticRulesSearch(
        candidates=scored[:limit],
        retrieval_mode="hybrid",
        backend_name=backend.name,
        model_name=backend.model_name,
        indexed_chunks=len(filtered),
    )


def _merge_rule_candidates(
    exact_rows: list[sqlite3.Row],
    semantic_rows: list[tuple[sqlite3.Row, float]],
    scope_tags: list[str],
    query_terms: list[str],
    definition_query: bool,
    channel_matches: dict[int, set[str]] | None = None,
) -> list[RuleSearchCandidate]:
    channel_matches = channel_matches or {}
    candidates: dict[int, RuleSearchCandidate] = {}
    for row in exact_rows:
        candidate = candidates.setdefault(int(row["chunk_id"]), _candidate_from_row(row))
        candidate.exact_score = max(candidate.exact_score, fts_rank_to_score(float(row["rank"])))
        candidate.match_reasons.append("exact")
        _extend_unique(candidate.retrieval_channels, channel_matches.get(int(row["chunk_id"]), set()))

    for row, semantic_score in semantic_rows:
        candidate = candidates.setdefault(int(row["chunk_id"]), _candidate_from_row(row))
        candidate.semantic_score = max(candidate.semantic_score, semantic_score)
        candidate.match_reasons.append("semantic")
        _add_unique(candidate.retrieval_channels, "semantic")

    for candidate in candidates.values():
        _score_rule_candidate(
            candidate,
            scope_tags=scope_tags,
            query_terms=query_terms,
            definition_query=definition_query,
        )
    return sorted(candidates.values(), key=_candidate_sort_key)


def _attach_rule_units_to_candidates(connection: sqlite3.Connection, candidates: list[RuleSearchCandidate]) -> None:
    chunk_ids = sorted({candidate.chunk_id for candidate in candidates})
    if not chunk_ids:
        return
    placeholders = ", ".join("?" for _ in chunk_ids)
    rows = connection.execute(
        f"""
        SELECT
            ru.*,
            b.book_title,
            rc.section_label
        FROM rule_units ru
        JOIN books b ON b.book_id = ru.book_id
        LEFT JOIN rule_chunks rc ON rc.id = ru.primary_chunk_id
        WHERE ru.primary_chunk_id IN ({placeholders})
          AND ru.schema_version = ?
          AND ru.source_content_hash = rc.content_hash
        ORDER BY ru.confidence DESC, ru.unit_id
        """,
        [*chunk_ids, RULE_UNIT_SCHEMA_VERSION],
    ).fetchall()
    by_chunk_id: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        primary_chunk_id = int(row["primary_chunk_id"])
        by_chunk_id.setdefault(primary_chunk_id, []).append(_rule_unit_row_to_dict(row, include_window=False))
    for candidate in candidates:
        candidate.rule_units = by_chunk_id.get(candidate.chunk_id, [])


def _expand_rag_v2_neighbor_rows(
    connection: sqlite3.Connection,
    *,
    seeds: list[RuleSearchCandidate],
    query_plan: RulesQueryPlan,
    book_id: str | None,
    scope_tags: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    if not seeds:
        return []
    rows: list[sqlite3.Row] = []
    returned: set[int] = set()
    expansion_seeds = [
        seed
        for seed in seeds[:RAG_V2_NEIGHBOR_EXPANSION_SEED_LIMIT]
        if _candidate_has_entity_anchor(seed, query_plan)
        and _candidate_answerability_rejections(seed, query_plan)
        and seed.section_kind not in {"toc", "index", "sheet", "art", "furniture"}
    ]
    for seed in expansion_seeds:
        for row in _neighbor_rows_for_seed(connection, seed=seed, book_id=book_id, scope_tags=scope_tags, limit=limit):
            chunk_id = int(row["chunk_id"])
            if chunk_id in returned:
                continue
            returned.add(chunk_id)
            rows.append(row)
    return rows


def _neighbor_rows_for_seed(
    connection: sqlite3.Connection,
    *,
    seed: RuleSearchCandidate,
    book_id: str | None,
    scope_tags: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT
            rc.id AS chunk_id,
            rc.book_id,
            b.book_title,
            b.tier,
            b.scope_tags_json AS book_scope_tags_json,
            rc.scope_tags_json AS chunk_scope_tags_json,
            rc.page_start,
            rc.page_end,
            rc.chunk_index,
            rc.section_label,
            COALESCE(NULLIF(rc.clean_content, ''), rc.content) AS content,
            COALESCE(NULLIF(rc.source_window, ''), rc.excerpt) AS excerpt,
            rc.word_count,
            rc.content_hash,
            rc.confidence,
            rc.extraction_method,
            rc.rule_block_id,
            rc.heading_path_json AS block_heading_path_json,
            rc.block_kind,
            rc.source_window,
            rc.structure_flags_json,
            rc.structure_schema_version,
            m.section_kind,
            m.retrieval_flags_json,
            m.content_hash AS metadata_content_hash,
            m.rag_schema_version,
            m.heading_path_json,
            m.aliases_json,
            m.entity_locations_json,
            m.evidence_cues_json,
            COALESCE((
                SELECT json_group_array(json_object(
                    'id', rsa.id,
                    'tag', rsa.tag,
                    'role', rsa.role,
                    'status', rsa.status,
                    'confidence', rsa.confidence
                ))
                FROM rule_chunk_scope_assertions csa
                JOIN rule_scope_assertions rsa ON rsa.id = csa.assertion_id
                WHERE csa.chunk_id = rc.id
                  AND rsa.status = 'applied'
            ), '[]') AS scope_assertions_json,
            0.0 AS rank
        FROM rule_chunks rc
        JOIN books b ON b.book_id = rc.book_id
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        LEFT JOIN rule_retrieval_exclusions rex
          ON rex.chunk_id = rc.id
         AND rex.content_hash = rc.content_hash
        WHERE rc.book_id = ?
          AND rc.id != ?
          AND rex.id IS NULL
          AND rc.page_start = ?
          AND ABS(rc.chunk_index - ?) <= 1
        ORDER BY ABS(rc.chunk_index - ?), rc.chunk_index
        LIMIT ?
        """,
        (seed.book_id, seed.chunk_id, seed.page_start, seed.chunk_index, seed.chunk_index, limit),
    ).fetchall()
    filtered: list[sqlite3.Row] = []
    for row in rows:
        if book_id and row["book_id"] != book_id:
            continue
        if row["tier"] == "supplement" and scope_tags and not _row_matches_scope(row, scope_tags):
            continue
        filtered.append(row)
    return filtered


def _merge_candidate_lists(
    base: list[RuleSearchCandidate],
    additions: list[RuleSearchCandidate],
) -> list[RuleSearchCandidate]:
    merged: dict[int, RuleSearchCandidate] = {candidate.chunk_id: candidate for candidate in base}
    for candidate in additions:
        existing = merged.get(candidate.chunk_id)
        if existing is None:
            merged[candidate.chunk_id] = candidate
            continue
        existing.exact_score = max(existing.exact_score, candidate.exact_score)
        existing.semantic_score = max(existing.semantic_score, candidate.semantic_score)
        existing.lexical_score = max(existing.lexical_score, candidate.lexical_score)
        existing.evidence_score = max(existing.evidence_score, candidate.evidence_score)
        existing.score = max(existing.score, candidate.score)
        _extend_unique(existing.match_reasons, candidate.match_reasons)
        _extend_unique(existing.retrieval_channels, candidate.retrieval_channels)
        _extend_unique(existing.rejection_reasons, candidate.rejection_reasons)
    return sorted(merged.values(), key=_candidate_sort_key)


def _dedupe_candidates(candidates: list[RuleSearchCandidate]) -> list[RuleSearchCandidate]:
    seen: set[int] = set()
    deduped: list[RuleSearchCandidate] = []
    for candidate in candidates:
        if candidate.chunk_id in seen:
            continue
        seen.add(candidate.chunk_id)
        deduped.append(candidate)
    return deduped


def _candidate_from_row(row: sqlite3.Row) -> RuleSearchCandidate:
    section_kind = _row_optional(row, "section_kind")
    retrieval_flags = _json_list(_row_optional(row, "retrieval_flags_json"))
    rag_schema_version = _row_optional(row, "rag_schema_version")
    heading_path = _json_text_list(_row_optional(row, "heading_path_json"))
    block_heading_path = _json_text_list(_row_optional(row, "block_heading_path_json"))
    aliases = _json_text_list(_row_optional(row, "aliases_json"))
    entity_locations = _json_dict_list(_row_optional(row, "entity_locations_json"))
    evidence_cues = _json_text_list(_row_optional(row, "evidence_cues_json"))
    rule_block_id = str(_row_optional(row, "rule_block_id") or "") or None
    block_kind = str(_row_optional(row, "block_kind") or "") or None
    source_window = str(_row_optional(row, "source_window") or "") or None
    structure_schema_version = int(_row_optional(row, "structure_schema_version") or 0) or None
    structure_flags = _json_list(_row_optional(row, "structure_flags_json"))
    scope_assertions = _json_assertions(_row_optional(row, "scope_assertions_json"))
    book_scope_tags = _json_list(_row_optional(row, "book_scope_tags_json"))
    scope_tags = _json_list(_row_optional(row, "chunk_scope_tags_json"))
    if not scope_tags:
        scope_tags = book_scope_tags
    scope_fallback_used = not scope_assertions and bool(scope_tags and scope_tags == book_scope_tags)
    if (
        not section_kind
        or _row_optional(row, "metadata_content_hash") != row["content_hash"]
        or int(rag_schema_version or 0) != RULES_RAG_V2_METADATA_SCHEMA_VERSION
    ):
        metadata = classify_rule_chunk_rag_metadata(
            section_label=row["section_label"],
            content=row["content"],
            word_count=int(row["word_count"]),
            confidence=float(row["confidence"]),
            extraction_method=row["extraction_method"],
        )
        section_kind = metadata.section_kind
        retrieval_flags = metadata.retrieval_flags
        rag_schema_version = metadata.rag_schema_version
        heading_path = metadata.heading_path
        aliases = metadata.aliases
        entity_locations = metadata.entity_locations
        evidence_cues = metadata.evidence_cues
    if block_heading_path:
        heading_path = block_heading_path
    return RuleSearchCandidate(
        chunk_id=int(row["chunk_id"]),
        book_id=str(row["book_id"]),
        book_title=str(row["book_title"]),
        tier=str(row["tier"]),
        book_scope_tags=book_scope_tags,
        scope_tags=scope_tags,
        scope_assertions=scope_assertions,
        scope_fallback_used=scope_fallback_used,
        page_start=int(row["page_start"]),
        page_end=int(row["page_end"]),
        chunk_index=int(_row_optional(row, "chunk_index") or 0),
        section_label=str(row["section_label"]),
        content=str(row["content"]),
        excerpt=str(row["excerpt"]),
        confidence=float(row["confidence"]),
        extraction_method=str(row["extraction_method"]),
        word_count=int(row["word_count"]),
        content_hash=str(row["content_hash"]),
        section_kind=str(section_kind or "unknown"),
        retrieval_flags=retrieval_flags,
        rule_block_id=rule_block_id,
        block_kind=block_kind,
        source_window=source_window,
        structure_schema_version=structure_schema_version,
        structure_flags=structure_flags,
        rag_schema_version=int(rag_schema_version or 0) or None,
        heading_path=heading_path,
        aliases=aliases,
        entity_locations=entity_locations,
        evidence_cues=evidence_cues,
    )


def _score_rule_candidate(
    candidate: RuleSearchCandidate,
    scope_tags: list[str],
    query_terms: list[str],
    definition_query: bool,
) -> None:
    candidate.lexical_score = _lexical_rule_score(candidate, query_terms, definition_query=definition_query)
    score = candidate.exact_score + (candidate.semantic_score * SEMANTIC_WEIGHT) + candidate.lexical_score
    reasons = set(candidate.match_reasons)
    if candidate.lexical_score > 0:
        reasons.add("lexical")

    if candidate.section_kind != "unknown" or candidate.retrieval_flags:
        reasons.add("retrieval-metadata")
    if candidate.rule_units:
        reasons.add("rule-unit")
        score += _rule_unit_base_score(candidate)

    if candidate.tier == "supplement":
        authoritative_overlap = _scope_assertion_overlap(candidate, scope_tags, authoritative=True)
        contextual_overlap = _scope_assertion_overlap(candidate, scope_tags, authoritative=False)
        fallback_overlap = len(set(candidate.scope_tags) & set(scope_tags)) if candidate.scope_fallback_used else 0
        if authoritative_overlap:
            reasons.add("supplement-precedence")
            reasons.add("scope-assertion")
            score += SUPPLEMENT_SCOPE_BOOST + (0.04 * authoritative_overlap)
        elif contextual_overlap:
            reasons.add("scope-assertion")
            reasons.add("scope-context")
            score += 0.04 * contextual_overlap
        elif fallback_overlap:
            reasons.add("supplement-precedence")
            reasons.add("source-scope-fallback")
            score += SUPPLEMENT_SCOPE_BOOST + (0.03 * fallback_overlap)
        elif scope_tags:
            reasons.add("scope-mismatch")
    elif scope_tags:
        reasons.add("core-fallback")

    penalty = _rule_quality_penalty(candidate)
    if definition_query and candidate.lexical_score >= 1.0 and candidate.exact_score > 0:
        reasons.add("definition-match")
        penalty = min(penalty, 0.15)
    if penalty > 0:
        reasons.add("quality-penalty")
    candidate.quality_penalty = penalty
    candidate.score = max(score - penalty, 0.0)
    candidate.match_reasons = sorted(reasons)


def _rule_unit_base_score(candidate: RuleSearchCandidate) -> float:
    score = 0.0
    roles = {str(unit.get("authority_role") or "") for unit in candidate.rule_units}
    kinds = {str(unit.get("unit_kind") or "") for unit in candidate.rule_units}
    if roles & {"base", "specific", "exception"}:
        score += 0.2
    if kinds & {"base_rule", "discipline_power", "ritual", "formula", "ceremony", "merit", "flaw", "table_row"}:
        score += 0.15
    if roles <= {"example", "flavor"}:
        score -= 0.25
    return score


def _rerank_rag_v2_candidates(
    candidates: list[RuleSearchCandidate],
    *,
    query_plan: RulesQueryPlan,
) -> list[RuleSearchCandidate]:
    for candidate in candidates:
        evidence_score = _rag_v2_evidence_score(candidate, query_plan)
        entity_score = _rag_v2_entity_score(candidate, query_plan)
        channel_score = _rag_v2_channel_score(candidate)
        section_penalty = _rag_v2_section_penalty(candidate)
        candidate.evidence_score = round(evidence_score, 6)
        candidate.score = round(max(candidate.score + evidence_score + entity_score + channel_score - section_penalty, 0.0), 6)
        if evidence_score > 0:
            candidate.match_reasons.append("evidence-cue")
        if entity_score > 0:
            candidate.match_reasons.append("entity-coverage")
        if channel_score > 0:
            candidate.match_reasons.append("rag-v2-channel")
        candidate.match_reasons.append("rag-v2-reranked")
        candidate.rejection_reasons = _rag_v2_rejection_reasons(candidate, query_plan)
        candidate.match_reasons = sorted(set(candidate.match_reasons))
    return sorted(candidates, key=_candidate_sort_key)


def _rag_v2_evidence_score(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> float:
    score = 0.0
    cues = set(candidate.evidence_cues)
    score += _rule_unit_query_score(candidate, query_plan)
    for intent in query_plan.intents:
        required = set(_intent_evidence_cues([intent]))
        if not required:
            continue
        if intent == INTENT_ADVANCEMENT:
            if "advancement" in cues:
                score += 1.25
            else:
                score -= 0.9
            continue
        if intent == INTENT_TIMING:
            if _candidate_has_timing_answer(candidate, query_plan):
                score += 1.4
                score += _candidate_timing_subject_score(candidate, query_plan)
            elif "duration" in cues:
                score += 0.5
            else:
                score -= 0.45
            continue
        if cues & required:
            score += 0.85
        elif intent in {INTENT_ADVANCEMENT, INTENT_TARGETING, INTENT_DEFINITION, INTENT_COST, INTENT_TIMING, INTENT_DICE_POOL, INTENT_CONSEQUENCE}:
            score -= 0.35
    if INTENT_DEFINITION in query_plan.intents and _candidate_has_definition_anchor(candidate, query_plan):
        score += 0.8
    if INTENT_DEFINITION in query_plan.intents and "cost" in cues and not cues.intersection({"definition", "system"}):
        score -= 0.25
    return score


def _rule_unit_query_score(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> float:
    if not candidate.rule_units:
        return 0.0
    score = 0.0
    required_facets = set(_rule_unit_required_facets(query_plan))
    unit_facets = {
        str(facet)
        for unit in candidate.rule_units
        for facet in (unit.get("answer_facets") if isinstance(unit.get("answer_facets"), list) else [])
    }
    roles = {str(unit.get("authority_role") or "") for unit in candidate.rule_units}
    kinds = {str(unit.get("unit_kind") or "") for unit in candidate.rule_units}
    if required_facets and unit_facets & required_facets:
        score += 0.45 + (0.08 * len(unit_facets & required_facets))
    if roles & {"base", "specific", "exception"}:
        score += 0.2
    if roles <= {"example", "flavor"}:
        score -= 0.5
    if INTENT_DEFINITION in query_plan.intents and "base_rule" in kinds and "effect" in unit_facets:
        score += 0.35
    if INTENT_TARGETING in query_plan.intents and "target" in unit_facets:
        score += 0.4
    if INTENT_ADVANCEMENT in query_plan.intents and "prerequisite" in unit_facets:
        score += 0.25
    return score


def _rule_unit_required_facets(query_plan: RulesQueryPlan) -> list[str]:
    facets: list[str] = []
    for intent in query_plan.intents:
        _extend_unique(facets, _rule_unit_required_facets_for_intent(intent))
    return facets


def _rule_unit_required_facets_for_intent(intent: str) -> list[str]:
    mapping = {
        INTENT_DEFINITION: ["effect"],
        INTENT_ADVANCEMENT: ["cost", "prerequisite"],
        INTENT_TARGETING: ["target", "effect", "limit"],
        INTENT_COST: ["cost"],
        INTENT_TIMING: ["duration"],
        INTENT_DICE_POOL: ["dice_pool"],
        INTENT_CONSEQUENCE: ["consequence"],
    }
    return mapping.get(intent, [])


def _candidate_has_definition_anchor(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> bool:
    terms = _query_entity_anchor_terms(query_plan) or query_plan.canonical_terms
    if not terms:
        return False
    haystack = _normalize_rule_alias(f"{candidate.section_label} {candidate.content}")
    definition_cues = r"(?:is|are|means|refers to|represents|creates|create|becomes|become|anyone who|after three)"
    for term in terms:
        normalized = _normalize_rule_alias(term)
        if not normalized:
            continue
        if normalized in haystack and any(
            cue in haystack
            for cue in (
                f"{normalized} creates",
                "anyone who drinks",
                "after three drinks",
                "becomes progressively",
                "term the source",
            )
        ):
            return True
        if re.search(rf"\b(?:the\s+)?{re.escape(normalized)}\b.{0,180}\b{definition_cues}\b", haystack):
            return True
        if re.search(rf"\b{definition_cues}\b.{0,180}\b{re.escape(normalized)}\b", haystack):
            return True
    return False


def _candidate_has_timing_answer(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan | None = None) -> bool:
    if query_plan is not None and INTENT_TIMING not in query_plan.intents:
        return False
    haystack = _normalize_rule_alias(f"{candidate.section_label} {candidate.content}")
    return bool(
        re.search(r"\b(?:five|5)\s+minutes?\s+per\s+(?:level|ritual|ceremony)\b", haystack)
        or re.search(r"\bperforming\s+(?:a\s+)?(?:ritual|ceremony)\s+requires\b.{0,180}\bminutes?\b", haystack)
    )


def _candidate_timing_subject_score(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> float:
    haystack = _normalize_rule_alias(f"{candidate.section_label} {candidate.content}")
    mechanics = {_normalize_rule_alias(term) for term in query_plan.entities.get("mechanics", [])}
    if "ritual" in mechanics:
        if re.search(r"\bperforming\s+(?:a\s+)?ritual\s+requires\b", haystack) or re.search(
            r"\brituals\s+unless\s+otherwise\s+noted\b.{0,120}\bperforming\s+(?:a\s+)?ritual\s+requires\b",
            haystack,
        ):
            return 1.6
        if re.search(r"\bperforming\s+(?:a\s+)?ceremony\s+requires\b", haystack):
            return -0.75
    if "ceremony" in mechanics:
        if re.search(r"\bperforming\s+(?:a\s+)?ceremony\s+requires\b", haystack) or re.search(
            r"\bceremonies\s+unless\s+otherwise\s+noted\b.{0,120}\bperforming\s+(?:a\s+)?ceremony\s+requires\b",
            haystack,
        ):
            return 1.6
        if re.search(r"\bperforming\s+(?:a\s+)?ritual\s+requires\b", haystack):
            return -0.75
    return 0.0


def _rag_v2_entity_score(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> float:
    terms = [*query_plan.canonical_terms, *query_plan.expanded_terms]
    if not terms:
        return 0.0
    haystack = " ".join([candidate.section_label, candidate.content, " ".join(candidate.aliases)]).casefold()
    hits = 0
    for term in terms:
        normalized = _normalize_rule_alias(term)
        if normalized and _contains_normalized_phrase(_normalize_rule_alias(haystack), normalized):
            hits += 1
    score = min(hits, 5) * 0.12
    if _candidate_matches_resolved_source_anchor(candidate, query_plan):
        score += 0.8
    canonical_names = [_normalize_rule_alias(str(entity.get("canonical_name") or "")) for entity in query_plan.resolved_entities]
    if _normalize_rule_alias(candidate.section_label) in canonical_names:
        score += 0.45
    return score


def _rag_v2_channel_score(candidate: RuleSearchCandidate) -> float:
    channels = set(candidate.retrieval_channels)
    score = 0.0
    if any(channel.startswith("planned_exact") for channel in channels):
        score += 0.18
    if "entity_anchor" in channels:
        score += 0.35
    if any(channel == "planned_exact:entity_anchor" for channel in channels):
        score += 0.1
    if "phrase" in channels:
        score += 0.18
    if "alias" in channels:
        score += 0.12
    if "metadata" in channels:
        score += 0.22
    if "rule_unit" in channels:
        score += 0.28
    if "raw_fallback" in channels and len(channels) == 1:
        score -= 0.2
    return score


def _rag_v2_section_penalty(candidate: RuleSearchCandidate) -> float:
    if candidate.section_kind in {"toc", "index", "sheet", "art", "furniture"}:
        return 0.9
    if candidate.rule_units:
        roles = {str(unit.get("authority_role") or "") for unit in candidate.rule_units}
        if roles and roles <= {"example", "flavor"}:
            return 0.45
    if candidate.section_kind == "lore" and candidate.evidence_cues == ["lore"]:
        return 0.35
    return 0.0


def _rag_v2_rejection_reasons(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> list[str]:
    reasons: list[str] = []
    strong_answer = _candidate_has_strong_intent_answer(candidate, query_plan)
    if candidate.section_kind in {"toc", "index", "sheet", "art", "furniture"} and not strong_answer:
        _add_unique(reasons, "low_quality_section")
    general_advancement = INTENT_ADVANCEMENT in query_plan.intents and "advancement" in set(candidate.evidence_cues)
    if _query_requires_entity_anchor(query_plan) and not _candidate_has_entity_anchor(candidate, query_plan) and not general_advancement:
        _add_unique(reasons, "missing_entity_anchor")
    if _query_target_group_terms(query_plan) and not _candidate_has_target_group(candidate, query_plan):
        _add_unique(reasons, "missing_target_group")
    strict = _strict_evidence_requirements(query_plan.intents)
    if strict and not _candidate_satisfies_any_requirement(candidate, strict):
        if _candidate_mentions_query_entity(candidate, query_plan):
            _add_unique(reasons, "mere_mention")
        _add_unique(reasons, "missing_intent_evidence")
        _add_unique(reasons, "missing_evidence_cue")
    if candidate.retrieval_flags and not strong_answer:
        _add_unique(reasons, "retrieval_flagged")
    return reasons


def _strict_evidence_requirements(intents: list[str]) -> dict[str, set[str]]:
    requirements: dict[str, set[str]] = {}
    mapping = {
        INTENT_ADVANCEMENT: {"advancement"},
        INTENT_TARGETING: {"system", "targeting"},
        INTENT_DEFINITION: {"definition"},
        INTENT_COST: {"cost", "prerequisite"},
        INTENT_TIMING: {"duration", "system"},
        INTENT_DICE_POOL: {"dice_pool", "system"},
        INTENT_CONSEQUENCE: {"consequence", "system"},
    }
    for intent in intents:
        cues = mapping.get(intent)
        if cues:
            requirements[intent] = cues
    return requirements


def _intent_evidence_cues(intents: list[str]) -> list[str]:
    cues: list[str] = []
    for values in _strict_evidence_requirements(intents).values():
        _extend_unique(cues, values)
    if INTENT_BROAD_EXPLANATION in intents:
        _extend_unique(cues, ["definition", "system", "example"])
    return cues


def _candidate_satisfies_any_requirement(candidate: RuleSearchCandidate, requirements: dict[str, set[str]]) -> bool:
    cues = set(candidate.evidence_cues)
    for intent, required in requirements.items():
        required_facets = set(_rule_unit_required_facets_for_intent(intent))
        if required_facets and _candidate_rule_unit_facets(candidate) & required_facets:
            return True
        if intent == INTENT_TIMING:
            if _candidate_has_timing_answer(candidate):
                return True
            continue
        if cues & required:
            return True
    return False


def _candidate_has_strong_intent_answer(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> bool:
    if INTENT_TIMING in query_plan.intents and _candidate_has_timing_answer(candidate, query_plan):
        return True
    return False


def _candidate_mentions_query_entity(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> bool:
    return _rag_v2_entity_score(candidate, query_plan) > 0 or bool(candidate.aliases)


def _query_requires_entity_anchor(query_plan: RulesQueryPlan) -> bool:
    return bool(_query_entity_anchor_terms(query_plan))


def _query_entity_anchor_terms(query_plan: RulesQueryPlan) -> list[str]:
    entities = query_plan.entities
    terms: list[str] = []
    for entity in query_plan.resolved_entities:
        _add_unique(terms, str(entity.get("canonical_name") or ""))
        _extend_unique(terms, entity.get("matched_aliases") or [])
    for key in ("powers", "disciplines", "mechanics", "clans"):
        _extend_unique(terms, entities.get(key, []))
    _extend_unique(terms, query_plan.canonical_terms)
    return [
        term
        for term in _dedupe_text_values(terms)
        if _normalize_rule_alias(term) not in {"power", "discipline", "rules", "system"}
    ]


def _candidate_has_entity_anchor(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> bool:
    terms = _query_entity_anchor_terms(query_plan)
    if not terms:
        return True
    if _candidate_matches_resolved_source_anchor(candidate, query_plan):
        return True
    haystack = _candidate_anchor_haystack(candidate)
    return any(_contains_normalized_phrase(haystack, _normalize_rule_alias(term)) for term in terms)


def _candidate_matches_resolved_source_anchor(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> bool:
    if not candidate.rule_block_id:
        return False
    for entity in query_plan.resolved_entities:
        for anchor in entity.get("source_anchors") or []:
            if isinstance(anchor, dict) and str(anchor.get("rule_block_id") or "") == candidate.rule_block_id:
                return True
    return False


def _query_target_group_terms(query_plan: RulesQueryPlan) -> list[str]:
    if INTENT_TARGETING not in query_plan.intents:
        return []
    normalized = query_plan.normalized_question
    groups: list[str] = list(query_plan.target_groups)
    target_groups = {
        "vampire": ("vampire", "vampires", "kindred", "other vampire", "other vampires"),
        "mortal": ("mortal", "mortals", "human", "humans", "kine"),
        "ghoul": ("ghoul", "ghouls"),
        "animal": ("animal", "animals"),
    }
    for canonical, aliases in target_groups.items():
        if any(_contains_normalized_phrase(normalized, _normalize_rule_alias(alias)) for alias in aliases):
            _add_unique(groups, canonical)
            _extend_unique(groups, aliases)
    return _dedupe_text_values(groups)


def _candidate_has_target_group(candidate: RuleSearchCandidate, query_plan: RulesQueryPlan) -> bool:
    terms = _query_target_group_terms(query_plan)
    if not terms:
        return True
    haystack = _candidate_anchor_haystack(candidate)
    return any(_contains_normalized_phrase(haystack, _normalize_rule_alias(term)) for term in terms)


def _candidate_anchor_haystack(candidate: RuleSearchCandidate) -> str:
    entity_text: list[str] = []
    for entity in candidate.entity_locations:
        entity_text.extend([str(entity.get("alias") or ""), str(entity.get("canonical") or ""), str(entity.get("scope_tag") or "")])
    rule_unit_text: list[str] = []
    for unit in candidate.rule_units:
        for key in ("unit_kind", "authority_role", "section_label"):
            rule_unit_text.append(str(unit.get(key) or ""))
        for key in ("heading_path", "entity_tags", "mechanic_tags", "answer_facets"):
            values = unit.get(key)
            if isinstance(values, list):
                rule_unit_text.extend(str(value) for value in values)
    return _normalize_rule_alias(
        " ".join(
            [
                candidate.section_label,
                candidate.content,
                " ".join(candidate.aliases),
                " ".join(candidate.scope_tags),
                " ".join(entity_text),
                " ".join(rule_unit_text),
            ]
        )
    )


def _build_rag_v2_evidence_packet(
    *,
    query_plan: RulesQueryPlan,
    primary_rows: list[RuleSearchCandidate],
    fallback_rows: list[RuleSearchCandidate],
    all_rows: list[RuleSearchCandidate],
    limit: int,
    rag_v2_diagnostics: dict[str, Any],
    semantic: SemanticRulesSearch,
) -> RagV2EvidencePacket:
    strict_requirements = _strict_evidence_requirements(query_plan.intents)
    candidate_limit = max(limit, RAG_V2_SELECTED_LIMIT_FLOOR)
    entity_bridge_available = any(
        _candidate_has_entity_anchor(candidate, query_plan)
        for candidate in primary_rows
        if candidate.section_kind not in {"toc", "index", "sheet", "art", "furniture"}
    )
    eligible_rows = [
        candidate
        for candidate in primary_rows
        if not _candidate_answerability_rejections(
            candidate,
            query_plan,
            entity_bridge_available=entity_bridge_available,
        )
    ]
    if entity_bridge_available and any("neighbor_expansion" in set(candidate.retrieval_channels) for candidate in eligible_rows):
        candidate_limit = max(candidate_limit, 2)
        bridged_anchor_rows = [
            candidate
            for candidate in primary_rows
            if _candidate_has_entity_anchor(candidate, query_plan)
            and "neighbor_expansion" not in set(candidate.retrieval_channels)
            and candidate.section_kind not in {"toc", "index", "sheet", "art", "furniture"}
        ]
        eligible_rows = _dedupe_candidates([*bridged_anchor_rows[:1], *eligible_rows])
    candidate_pool = eligible_rows[:candidate_limit]
    satisfied = _satisfied_evidence_types(candidate_pool, strict_requirements)
    missing = [intent for intent in strict_requirements if intent not in satisfied]
    entity_status = _entity_anchor_status(query_plan, candidate_pool)
    target_status = _target_group_status(query_plan, candidate_pool)
    if entity_status["required"] and not entity_status["satisfied"]:
        missing.insert(0, "entity_anchor")
    if target_status["required"] and not target_status["satisfied"]:
        missing.insert(0, "target_group")
    if query_plan.unresolved_high_value_terms:
        missing.insert(0, "unresolved_entity")

    if (strict_requirements or entity_status["required"] or target_status["required"] or query_plan.unresolved_high_value_terms) and missing:
        status = "insufficient"
        selected_evidence: list[dict[str, Any]] = []
        fallback_context = [_row_to_rule_result(row) for row in (primary_rows + fallback_rows)[:RAG_V2_FALLBACK_CONTEXT_LIMIT]]
    else:
        status = "answerable"
        selected_evidence = [_row_to_rule_result(row) for row in candidate_pool]
        fallback_context = [_row_to_rule_result(row) for row in fallback_rows[:RAG_V2_FALLBACK_CONTEXT_LIMIT]]

    selected_ids = {item["book_id"] + ":" + str(item["page_start"]) + ":" + item["section_label"] for item in selected_evidence}
    rejected = []
    semantic_quality = _semantic_quality(semantic)
    for candidate in all_rows:
        candidate_key = candidate.book_id + ":" + str(candidate.page_start) + ":" + candidate.section_label
        if candidate_key in selected_ids:
            continue
        reasons = [*candidate.rejection_reasons]
        if set(candidate.retrieval_channels) == {"semantic"} and semantic_quality.get("status") != "available":
            _add_unique(reasons, "degraded_semantic_only")
        if not reasons:
            reasons = ["lower_ranked"]
        rejected.append(_rag_v2_candidate_summary(candidate, reasons=reasons))
        if len(rejected) >= RAG_V2_REJECTED_LIMIT:
            break

    counts = _rag_v2_candidate_counts(rag_v2_diagnostics, all_rows=all_rows, selected_count=len(selected_evidence), rejected_count=len(rejected))
    diagnostics = {
        **rag_v2_diagnostics,
        "reranked_candidates": len(all_rows),
        "semantic_quality": semantic_quality,
        "entity_anchor_status": entity_status,
        "target_group_status": target_status,
        "intent_evidence_status": {
            "required": sorted(strict_requirements),
            "satisfied": sorted(satisfied),
            "missing": missing,
        },
        "entity_first": {
            "mode": "entity_first" if query_plan.resolved_entities else "fallback",
            "resolved_entities": query_plan.resolved_entities,
            "unresolved_high_value_terms": query_plan.unresolved_high_value_terms,
            "target_groups": query_plan.target_groups,
            "situational_constraints": query_plan.situational_constraints,
            "ambiguity_warnings": query_plan.ambiguity_warnings,
        },
    }
    return RagV2EvidencePacket(
        evidence_status=status,
        selected_evidence=selected_evidence,
        fallback_context=fallback_context,
        rejected_candidates=rejected,
        missing_evidence=missing,
        satisfied_evidence=sorted(satisfied),
        candidate_counts=counts,
        retrieval_diagnostics=diagnostics,
        query_plan=query_plan.to_dict(),
    )


def _satisfied_evidence_types(
    candidates: list[RuleSearchCandidate],
    requirements: dict[str, set[str]],
) -> set[str]:
    satisfied: set[str] = set()
    for intent, cues in requirements.items():
        required_facets = set(_rule_unit_required_facets_for_intent(intent))
        if required_facets and any(_candidate_rule_unit_facets(candidate) & required_facets for candidate in candidates):
            satisfied.add(intent)
            continue
        if intent == INTENT_TIMING:
            if any(_candidate_has_timing_answer(candidate) for candidate in candidates):
                satisfied.add(intent)
            continue
        if any(set(candidate.evidence_cues) & cues for candidate in candidates):
            satisfied.add(intent)
    return satisfied


def _candidate_rule_unit_facets(candidate: RuleSearchCandidate) -> set[str]:
    return {
        str(facet)
        for unit in candidate.rule_units
        for facet in (unit.get("answer_facets") if isinstance(unit.get("answer_facets"), list) else [])
    }


def _candidate_answerability_rejections(
    candidate: RuleSearchCandidate,
    query_plan: RulesQueryPlan,
    *,
    entity_bridge_available: bool = False,
) -> list[str]:
    reasons: list[str] = []
    entity_bridged = entity_bridge_available and "neighbor_expansion" in set(candidate.retrieval_channels)
    general_advancement = INTENT_ADVANCEMENT in query_plan.intents and "advancement" in set(candidate.evidence_cues)
    if (
        _query_requires_entity_anchor(query_plan)
        and not _candidate_has_entity_anchor(candidate, query_plan)
        and not entity_bridged
        and not general_advancement
    ):
        _add_unique(reasons, "missing_entity_anchor")
    if _query_target_group_terms(query_plan) and not _candidate_has_target_group(candidate, query_plan):
        _add_unique(reasons, "missing_target_group")
    strict = _strict_evidence_requirements(query_plan.intents)
    if strict and not _candidate_satisfies_any_requirement(candidate, strict):
        _add_unique(reasons, "missing_intent_evidence")
    if candidate.section_kind in {"toc", "index", "sheet", "art", "furniture"} and not _candidate_has_strong_intent_answer(
        candidate, query_plan
    ):
        _add_unique(reasons, "low_quality_section")
    if reasons:
        for reason in reasons:
            _add_unique(candidate.rejection_reasons, reason)
    return reasons


def _entity_anchor_status(query_plan: RulesQueryPlan, candidates: list[RuleSearchCandidate]) -> dict[str, Any]:
    terms = _query_entity_anchor_terms(query_plan)
    if not terms:
        return {"required": False, "satisfied": True, "terms": [], "missing_terms": []}
    if INTENT_ADVANCEMENT in query_plan.intents and any("advancement" in set(candidate.evidence_cues) for candidate in candidates):
        return {
            "required": True,
            "satisfied": True,
            "terms": terms,
            "matched_terms": ["general_advancement_rule"],
            "missing_terms": [],
        }
    matched = [
        term
        for term in terms
        if any(_contains_normalized_phrase(_candidate_anchor_haystack(candidate), _normalize_rule_alias(term)) for candidate in candidates)
    ]
    return {
        "required": True,
        "satisfied": bool(matched),
        "terms": terms,
        "matched_terms": _dedupe_text_values(matched),
        "missing_terms": [term for term in terms if term not in matched],
    }


def _target_group_status(query_plan: RulesQueryPlan, candidates: list[RuleSearchCandidate]) -> dict[str, Any]:
    terms = _query_target_group_terms(query_plan)
    if not terms:
        return {"required": False, "satisfied": True, "terms": [], "missing_terms": []}
    matched = [
        term
        for term in terms
        if any(_contains_normalized_phrase(_candidate_anchor_haystack(candidate), _normalize_rule_alias(term)) for candidate in candidates)
    ]
    return {
        "required": True,
        "satisfied": bool(matched),
        "terms": terms,
        "matched_terms": _dedupe_text_values(matched),
        "missing_terms": [term for term in terms if term not in matched],
    }


def _rag_v2_candidate_summary(candidate: RuleSearchCandidate, *, reasons: list[str]) -> dict[str, Any]:
    return {
        "book_id": candidate.book_id,
        "book_title": candidate.book_title,
        "page_start": candidate.page_start,
        "page_end": candidate.page_end,
        "chunk_index": candidate.chunk_index,
        "section_label": candidate.section_label,
        "rule_block_id": candidate.rule_block_id,
        "block_kind": candidate.block_kind,
        "score": round(candidate.score, 6),
        "evidence_score": round(candidate.evidence_score, 6),
        "section_kind": candidate.section_kind,
        "evidence_cues": candidate.evidence_cues,
        "rule_unit_kinds": sorted({str(unit.get("unit_kind")) for unit in candidate.rule_units if unit.get("unit_kind")}),
        "rule_unit_authority_roles": sorted(
            {str(unit.get("authority_role")) for unit in candidate.rule_units if unit.get("authority_role")}
        ),
        "rule_unit_answer_facets": sorted(_candidate_rule_unit_facets(candidate)),
        "retrieval_channels": sorted(set(candidate.retrieval_channels)),
        "rejection_reasons": sorted(set(reasons)),
        "excerpt": candidate.excerpt,
    }


def _rag_v2_candidate_counts(
    diagnostics: dict[str, Any],
    *,
    all_rows: list[RuleSearchCandidate],
    selected_count: int,
    rejected_count: int,
) -> dict[str, int]:
    counts: dict[str, int] = {
        "reranked": len(all_rows),
        "selected_evidence": selected_count,
        "rejected": rejected_count,
    }
    for channel in diagnostics.get("channels", []):
        name = str(channel.get("channel") or "unknown").split(":", 1)[0]
        counts[name] = counts.get(name, 0) + int(channel.get("candidate_count") or 0)
    return counts


def _channel_count(diagnostics: dict[str, Any], prefix: str) -> int:
    return sum(
        1
        for channel in diagnostics.get("channels", [])
        if str(channel.get("channel") or "").startswith(prefix)
    )


def _scope_assertion_overlap(candidate: RuleSearchCandidate, scope_tags: list[str], *, authoritative: bool) -> int:
    if not scope_tags:
        return 0
    requested = set(scope_tags)
    roles = AUTHORITATIVE_SCOPE_ROLES if authoritative else set()
    tags = {
        assertion["tag"]
        for assertion in candidate.scope_assertions
        if (assertion.get("role") in roles if authoritative else assertion.get("role") not in AUTHORITATIVE_SCOPE_ROLES)
    }
    return len(requested & tags)


def _rule_quality_penalty(candidate: RuleSearchCandidate) -> float:
    penalty = NON_ANSWER_SECTION_PENALTIES.get(candidate.section_kind, 0.0)
    for flag in candidate.retrieval_flags:
        penalty += RETRIEVAL_FLAG_PENALTIES.get(flag, 0.0)
    if candidate.confidence < SUSPECT_CONFIDENCE_THRESHOLD:
        penalty += 0.1
    return min(penalty, 0.9)


def _candidate_sort_key(candidate: RuleSearchCandidate) -> tuple[float, int, int]:
    return (-candidate.score, candidate.page_start, candidate.chunk_id)


def _lexical_rule_score(candidate: RuleSearchCandidate, query_terms: list[str], *, definition_query: bool) -> float:
    if not query_terms:
        return 0.0
    haystack = " ".join(
        str(part)
        for part in (
            candidate.book_title,
            candidate.section_label,
            candidate.content,
        )
        if part
    ).lower()
    term_counts = [_term_count(haystack, term) for term in query_terms]
    hit_terms = sum(1 for count in term_counts if count > 0)
    if hit_terms == 0:
        return 0.0
    coverage = hit_terms / len(query_terms)
    frequency = min(sum(term_counts), 8) / 8
    proximity = _ordered_term_proximity(haystack, query_terms)
    definition = 1.0 if proximity and _definition_cue_near_terms(haystack, query_terms) else 0.0
    score = (
        (coverage * LEXICAL_COVERAGE_WEIGHT)
        + (frequency * LEXICAL_FREQUENCY_WEIGHT)
        + (proximity * LEXICAL_PROXIMITY_WEIGHT)
        + (definition * LEXICAL_DEFINITION_WEIGHT)
    )
    if definition_query:
        score += _definition_query_cue_score(haystack, query_terms) * LEXICAL_DEFINITION_QUERY_WEIGHT
        if _incidental_cost_near_terms(haystack, query_terms):
            score -= LEXICAL_INCIDENTAL_COST_PENALTY
    return round(max(score, 0.0), 6)


def _term_count(text: str, term: str) -> int:
    return len(re.findall(rf"\b{re.escape(term)}\b", text))


def _ordered_term_proximity(text: str, terms: list[str]) -> float:
    if len(terms) == 1:
        return 1.0 if _term_count(text, terms[0]) else 0.0
    positions: list[list[int]] = []
    for term in terms:
        current = [match.start() for match in re.finditer(rf"\b{re.escape(term)}\b", text)]
        if not current:
            return 0.0
        positions.append(current)
    best_span: int | None = None
    for start in positions[0]:
        previous = start
        span_start = start
        for current_positions in positions[1:]:
            next_position = next((position for position in current_positions if position > previous), None)
            if next_position is None:
                break
            previous = next_position
        else:
            span = previous - span_start
            best_span = span if best_span is None else min(best_span, span)
    if best_span is None:
        return 0.35
    if best_span <= 80:
        return 1.0
    if best_span <= 180:
        return 0.7
    return 0.45


def _definition_cue_near_terms(text: str, terms: list[str]) -> bool:
    first = terms[0]
    first_index = text.find(first)
    if first_index < 0:
        return False
    window_start = max(0, first_index - 80)
    window_end = min(len(text), first_index + 260)
    window = text[window_start:window_end]
    return any(cue in window for cue in ("to make", "system:", "cost:", "dice pool", "dice pools", "on a success", "on a failure"))


def _definition_query_cue_score(text: str, terms: list[str]) -> float:
    phrase = " ".join(terms)
    if not phrase:
        return 0.0
    if re.search(rf"\b{re.escape(phrase)}\b\s*:", text):
        return 1.0
    if re.search(rf"\b(?:committing|performing|using)\s+{re.escape(phrase)}\b[^.?!]{{0,180}}\b(?:to begin|begin|requires|must)\b", text):
        return 1.0
    if re.search(rf"\b(?:to make|rules call for|failure on|success on)\b[^.?!]{{0,160}}\b{re.escape(phrase)}\b", text):
        return 1.0
    if re.search(rf"\b{re.escape(phrase)}\b[^.?!]{{0,160}}\b(?:player rolls|rolls? a single die)\b", text):
        return 1.0
    if re.search(rf"\b{re.escape(phrase)}\b[^.?!]{{0,200}}\b(?:hunger remains|hunger increases|hunger die)\b", text):
        return 0.5
    return 0.0


def _incidental_cost_near_terms(text: str, terms: list[str]) -> bool:
    start = _ordered_terms_start(text, terms)
    if start < 0:
        return False
    window = text[max(0, start - 90) : min(len(text), start + 140)]
    return bool(re.search(r"\b(?:activation\s+)?cost\s*:", window))


def _ordered_terms_start(text: str, terms: list[str]) -> int:
    if not terms:
        return -1
    first = re.search(rf"\b{re.escape(terms[0])}\b", text)
    if first is None:
        return -1
    previous = first.start()
    for term in terms[1:]:
        match = re.search(rf"\b{re.escape(term)}\b", text[previous + 1 :])
        if match is None:
            return -1
        previous = previous + 1 + match.start()
    return first.start()


def _try_index_rule_chunks(
    connection: sqlite3.Connection,
    book_id: str,
    full: bool,
    progress: RulesIngestProgressCallback | None,
) -> dict[str, Any]:
    _emit_progress(progress, phase="semantic-index", message="Building rules semantic index", current=0, total=1)
    connection.execute("SAVEPOINT rules_semantic_index")
    try:
        backend = resolve_embedding_backend()
        summary = _index_rule_chunks(connection, backend=backend, book_id=book_id, full=full)
        connection.execute("RELEASE rules_semantic_index")
        _emit_progress(progress, phase="semantic-index", message="Built rules semantic index", current=1, total=1)
        return {
            "available": True,
            "retrieval_mode": "hybrid" if summary["indexed_chunks"] else "exact_only",
            **summary,
        }
    except AppError as error:
        connection.execute("ROLLBACK TO rules_semantic_index")
        connection.execute("RELEASE rules_semantic_index")
        _emit_progress(progress, phase="semantic-index", message="Rules semantic index unavailable", current=1, total=1)
        return {
            "available": False,
            "retrieval_mode": "exact_only",
            "error": _semantic_error(error),
            "repair_hint": f"Run `backet rules index <vault> --book-id {book_id}` after configuring a local embedding backend.",
        }
    except Exception as exc:  # pragma: no cover - defensive guard for optional ML backends
        connection.execute("ROLLBACK TO rules_semantic_index")
        connection.execute("RELEASE rules_semantic_index")
        _emit_progress(progress, phase="semantic-index", message="Rules semantic index unavailable", current=1, total=1)
        return {
            "available": False,
            "retrieval_mode": "exact_only",
            "error": {"code": "rules_semantic_index_failed", "message": str(exc)},
            "repair_hint": f"Run `backet rules index <vault> --book-id {book_id}` after configuring a local embedding backend.",
        }


def _index_rule_chunks(
    connection: sqlite3.Connection,
    backend: EmbeddingBackend,
    book_id: str | None,
    full: bool,
) -> dict[str, Any]:
    rows = _fetch_rule_chunks_for_index(connection, book_id=book_id)
    before = _semantic_index_summary(rows, backend=backend)
    structure_rows = [row for row in rows if full or _structure_needs_refresh(row)]
    refreshed_structure_ids = {int(row["chunk_id"]) for row in structure_rows}
    affected_book_ids = sorted({str(row["book_id"]) for row in structure_rows})

    for row in structure_rows:
        _update_rule_chunk_structure(connection, row)

    for current_book_id in affected_book_ids:
        _rebuild_rule_chunks_fts(connection, current_book_id)

    if structure_rows:
        rows = _fetch_rule_chunks_for_index(connection, book_id=book_id)

    embedding_rows = [
        row
        for row in rows
        if full or _embedding_needs_refresh(row, backend) or int(row["chunk_id"]) in refreshed_structure_ids
    ]
    metadata_rows = [
        row for row in rows if full or _metadata_needs_refresh(row) or int(row["chunk_id"]) in refreshed_structure_ids
    ]

    if embedding_rows:
        result = backend.encode_many([row["content"] for row in embedding_rows])
        now = timestamp_now()
        for row, vector in zip(embedding_rows, result.vectors, strict=True):
            connection.execute(
                """
                INSERT INTO rule_chunk_embeddings (
                    chunk_id, backend, model, dimensions, content_hash, embedding_json, embedded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    backend = excluded.backend,
                    model = excluded.model,
                    dimensions = excluded.dimensions,
                    content_hash = excluded.content_hash,
                    embedding_json = excluded.embedding_json,
                    embedded_at = excluded.embedded_at
                """,
                (
                    int(row["chunk_id"]),
                    result.backend_name,
                    result.model_name,
                    len(vector),
                    row["content_hash"],
                    json.dumps(vector),
                    now,
                ),
            )

    for row in metadata_rows:
        _upsert_rule_chunk_retrieval_metadata(
            connection,
            chunk_id=int(row["chunk_id"]),
            section_label=row["section_label"],
            content=row["content"],
            word_count=int(row["word_count"]),
            confidence=float(row["confidence"]),
            extraction_method=row["extraction_method"],
            content_hash=row["content_hash"],
        )

    catalog_summary = _refresh_rules_entity_catalog(connection, book_id=book_id, full=full)
    rule_units_summary = _refresh_rule_units(connection, book_id=book_id, full=full)
    refreshed_rows = _fetch_rule_chunks_for_index(connection, book_id=book_id)
    summary = _semantic_index_summary(refreshed_rows, backend=backend)
    summary.update(
        {
            "indexed_chunks_before": before["indexed_chunks"],
            "missing_embeddings_before": before["missing_embeddings"],
            "stale_embeddings_before": before["stale_embeddings"],
            "metadata_chunks_before": before["metadata_chunks"],
            "missing_metadata_before": before["missing_metadata"],
            "stale_metadata_before": before["stale_metadata"],
            "structure_chunks_before": before["structure_chunks"],
            "missing_structure_before": before["missing_structure"],
            "stale_structure_before": before["stale_structure"],
            "refreshed_embeddings": len(embedding_rows),
            "refreshed_metadata": len(metadata_rows),
            "refreshed_structure": len(structure_rows),
            "entity_catalog": catalog_summary,
            "rule_units": rule_units_summary,
            "full_reindex": full,
            "source_pdf_required": False,
            "source_operation": "stored_chunk_text",
        }
    )
    return summary


def _inspect_rule_semantic_index_for_current_backend(
    connection: sqlite3.Connection,
    book_id: str | None,
) -> dict[str, Any]:
    try:
        backend = resolve_embedding_backend()
    except AppError as error:
        return {
            "available": False,
            "retrieval_mode": "semantic_unavailable",
            "error": _semantic_error(error),
            "repair_hint": "Configure a local embedding backend, then run `backet rules index`.",
        }

    rows = _fetch_rule_chunks_for_index(connection, book_id=book_id)
    summary = _semantic_index_summary(rows, backend=backend)
    rule_units = _rule_units_summary(connection, book_id=book_id)
    needs_repair = (
        summary["missing_embeddings"] > 0
        or summary["stale_embeddings"] > 0
        or summary["missing_metadata"] > 0
        or summary["stale_metadata"] > 0
        or summary["missing_structure"] > 0
        or summary["stale_structure"] > 0
        or rule_units["missing_rule_units"] > 0
        or rule_units["stale_rule_units"] > 0
    )
    summary.update(
        {
            "available": summary["indexed_chunks"] > 0,
            "retrieval_mode": "hybrid" if summary["indexed_chunks"] > 0 else "exact_only",
            "rag_v2_metadata": {
                "schema_version": RULES_RAG_V2_METADATA_SCHEMA_VERSION,
                "available_chunks": summary["metadata_chunks"],
                "missing_chunks": summary["missing_metadata"],
                "stale_chunks": summary["stale_metadata"],
            },
            "rule_block_structure": {
                "schema_version": RULE_BLOCK_STRUCTURE_SCHEMA_VERSION,
                "available_chunks": summary["structure_chunks"],
                "missing_chunks": summary["missing_structure"],
                "stale_chunks": summary["stale_structure"],
            },
            "rule_units": {
                "schema_version": RULE_UNIT_SCHEMA_VERSION,
                **rule_units,
            },
            "repair_hint": _rules_index_hint(book_id) if needs_repair else None,
        }
    )
    return summary


def _semantic_index_summary(rows: list[sqlite3.Row], backend: EmbeddingBackend) -> dict[str, Any]:
    missing_embeddings = 0
    stale_embeddings = 0
    indexed_chunks = 0
    missing_metadata = 0
    stale_metadata = 0
    metadata_chunks = 0
    structure_chunks = 0
    missing_structure = 0
    stale_structure = 0
    for row in rows:
        if _embedding_missing(row):
            missing_embeddings += 1
        elif _embedding_needs_refresh(row, backend):
            stale_embeddings += 1
        else:
            indexed_chunks += 1

        if _row_optional(row, "metadata_content_hash") is None:
            missing_metadata += 1
        elif _metadata_needs_refresh(row):
            stale_metadata += 1
        else:
            metadata_chunks += 1

        if _structure_missing(row):
            missing_structure += 1
        elif _structure_needs_refresh(row):
            stale_structure += 1
        else:
            structure_chunks += 1

    return {
        "embedding_backend": backend.name,
        "embedding_model": backend.model_name,
        "total_chunks": len(rows),
        "indexed_chunks": indexed_chunks,
        "missing_embeddings": missing_embeddings,
        "stale_embeddings": stale_embeddings,
        "missing_count": missing_embeddings,
        "stale_count": stale_embeddings,
        "metadata_chunks": metadata_chunks,
        "missing_metadata": missing_metadata,
        "stale_metadata": stale_metadata,
        "rag_metadata_schema_version": RULES_RAG_V2_METADATA_SCHEMA_VERSION,
        "structure_chunks": structure_chunks,
        "missing_structure": missing_structure,
        "stale_structure": stale_structure,
        "rule_block_structure_schema_version": RULE_BLOCK_STRUCTURE_SCHEMA_VERSION,
    }


def _structure_missing(row: sqlite3.Row) -> bool:
    return not str(_row_optional(row, "rule_block_id") or "").strip() or not str(
        _row_optional(row, "clean_content") or ""
    ).strip()


def _structure_needs_refresh(row: sqlite3.Row) -> bool:
    if _structure_missing(row):
        return True
    return int(_row_optional(row, "structure_schema_version") or 0) != RULE_BLOCK_STRUCTURE_SCHEMA_VERSION


def _update_rule_chunk_structure(connection: sqlite3.Connection, row: sqlite3.Row) -> None:
    content = str(_row_optional(row, "raw_content") or row["content"] or "")
    structure = derive_rule_block_structure(
        book_id=str(row["book_id"]),
        section_label=str(row["section_label"]),
        content=content,
        page_start=int(row["page_start"]),
        chunk_index=int(row["chunk_index"]),
    )
    connection.execute(
        """
        UPDATE rule_chunks
        SET rule_block_id = ?,
            heading_path_json = ?,
            block_kind = ?,
            clean_content = ?,
            source_window = ?,
            structure_flags_json = ?,
            structure_schema_version = ?
        WHERE id = ?
        """,
        (
            structure.block_id,
            json.dumps(structure.heading_path),
            structure.block_kind,
            structure.clean_content,
            structure.source_window,
            json.dumps(structure.structure_flags),
            structure.schema_version,
            int(row["chunk_id"]),
        ),
    )


def _refresh_rules_entity_catalog(connection: sqlite3.Connection, *, book_id: str | None, full: bool) -> dict[str, Any]:
    _ensure_seed_rule_entities(connection)
    if not full:
        return _rules_entity_catalog_summary(connection, book_id=book_id, refreshed=0)

    parameters: list[Any] = []
    where_clause = "WHERE rc.structure_schema_version = ? AND rc.rule_block_id != '' AND rc.clean_content != ''"
    parameters.append(RULE_BLOCK_STRUCTURE_SCHEMA_VERSION)
    if book_id:
        where_clause += " AND rc.book_id = ?"
        parameters.append(book_id)
    rows = connection.execute(
        f"""
        SELECT
            rc.id AS chunk_id,
            rc.book_id,
            rc.page_start,
            rc.page_end,
            rc.chunk_index,
            rc.section_label,
            rc.content_hash,
            rc.rule_block_id,
            rc.heading_path_json AS block_heading_path_json,
            rc.block_kind,
            COALESCE(NULLIF(rc.clean_content, ''), rc.content) AS content,
            rc.scope_tags_json AS chunk_scope_tags_json,
            m.aliases_json,
            m.entity_locations_json,
            m.evidence_cues_json
        FROM rule_chunks rc
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        {where_clause}
        ORDER BY rc.book_id, rc.page_start, rc.chunk_index
        """,
        parameters,
    ).fetchall()
    refreshed = 0
    for row in rows:
        entry = _catalog_entry_from_rule_block(row)
        if entry is None:
            continue
        _upsert_rule_entity(connection, entry)
        refreshed += 1
    return _rules_entity_catalog_summary(connection, book_id=book_id, refreshed=refreshed)


def _catalog_entry_from_rule_block(row: sqlite3.Row) -> dict[str, Any] | None:
    heading_path = _json_text_list(_row_optional(row, "block_heading_path_json"))
    canonical = _catalog_canonical_name(row, heading_path)
    if not canonical:
        return None
    aliases = _dedupe_text_values(
        [
            canonical,
            *heading_path,
            str(row["section_label"]),
        ]
    )
    source_anchor = {
        "book_id": row["book_id"],
        "chunk_id": int(row["chunk_id"]),
        "rule_block_id": row["rule_block_id"],
        "page_start": int(row["page_start"]),
        "page_end": int(row["page_end"]),
        "section_label": row["section_label"],
    }
    scope_tags = _json_list(_row_optional(row, "chunk_scope_tags_json"))
    entity_type = _catalog_entity_type(canonical=canonical, block_kind=str(row["block_kind"] or ""), content=str(row["content"] or ""))
    return {
        "entity_id": f"{row['book_id']}:{row['rule_block_id']}",
        "book_id": row["book_id"],
        "canonical_name": canonical,
        "entity_type": entity_type,
        "aliases": aliases,
        "source_anchors": [source_anchor],
        "source_pages": [int(row["page_start"])],
        "scope_tags": scope_tags,
        "provenance": "generated_block",
        "content_hash": fingerprint_text(
            "|".join(
                [
                    str(row["content_hash"]),
                    json.dumps(heading_path, sort_keys=True),
                    str(row["block_kind"] or ""),
                ]
            )
        ),
        "confidence": 0.78,
    }


def _catalog_canonical_name(row: sqlite3.Row, heading_path: list[str]) -> str:
    for heading in reversed(heading_path):
        normalized = " ".join(str(heading or "").strip().split())
        if _catalog_heading_is_name(normalized):
            return normalized
    first_line = str(row["content"] or "").splitlines()[0] if str(row["content"] or "").splitlines() else ""
    first_sentence = re.split(r"[.:]", first_line, maxsplit=1)[0]
    normalized = " ".join(first_sentence.strip().split())
    return normalized if _catalog_heading_is_name(normalized) else ""


def _catalog_heading_is_name(value: str) -> bool:
    if not (3 <= len(value) <= 80):
        return False
    if len(value.split()) > 8:
        return False
    if re.search(r"^(?:cost|system|duration|dice pools?|amalgam|prerequisite|chapter|page)\b", value, re.I):
        return False
    if re.fullmatch(r"(?:[A-Z]\s+){4,}[A-Z0-9 ]+", value):
        return False
    return True


def _catalog_entity_type(*, canonical: str, block_kind: str, content: str) -> str:
    normalized = _normalize_rule_alias(f"{canonical} {content}")
    if block_kind in {"power", "ritual", "table", "list"}:
        return block_kind
    if "discipline" in normalized and len(canonical.split()) <= 2:
        return "discipline"
    if re.search(r"\b(?:ritual|ceremony|formula)\b", normalized):
        return "ritual"
    if re.search(r"\b(?:cost|system|duration|dice pool|rouse check|hunger|blood bond)\b", normalized):
        return "mechanic"
    return "rule"


def _upsert_rule_entity(connection: sqlite3.Connection, entry: dict[str, Any]) -> None:
    now = timestamp_now()
    entity_id = str(entry["entity_id"])
    aliases = _dedupe_text_values(entry.get("aliases") or [])
    connection.execute(
        """
        INSERT INTO rule_entities (
            entity_id, book_id, canonical_name, entity_type, aliases_json, source_anchors_json,
            source_pages_json, scope_tags_json, provenance, content_hash, catalog_schema_version, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_id) DO UPDATE SET
            book_id = excluded.book_id,
            canonical_name = excluded.canonical_name,
            entity_type = excluded.entity_type,
            aliases_json = excluded.aliases_json,
            source_anchors_json = excluded.source_anchors_json,
            source_pages_json = excluded.source_pages_json,
            scope_tags_json = excluded.scope_tags_json,
            provenance = excluded.provenance,
            content_hash = excluded.content_hash,
            catalog_schema_version = excluded.catalog_schema_version,
            updated_at = excluded.updated_at
        """,
        (
            entity_id,
            entry.get("book_id"),
            str(entry["canonical_name"]),
            str(entry["entity_type"]),
            json.dumps(aliases),
            json.dumps(entry.get("source_anchors") or []),
            json.dumps(entry.get("source_pages") or []),
            json.dumps(entry.get("scope_tags") or []),
            str(entry["provenance"]),
            str(entry["content_hash"]),
            RULES_ENTITY_CATALOG_SCHEMA_VERSION,
            now,
        ),
    )
    for alias in aliases:
        normalized_alias = _normalize_rule_alias(alias)
        if not normalized_alias:
            continue
        connection.execute(
            """
            INSERT INTO rule_entity_aliases (normalized_alias, alias, entity_id, provenance, confidence)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(normalized_alias, entity_id, provenance) DO UPDATE SET
                alias = excluded.alias,
                confidence = excluded.confidence
            """,
            (
                normalized_alias,
                alias,
                entity_id,
                str(entry["provenance"]),
                float(entry.get("confidence") or 0.75),
            ),
        )


def _rules_entity_catalog_summary(connection: sqlite3.Connection, *, book_id: str | None, refreshed: int) -> dict[str, Any]:
    parameters: list[Any] = []
    where_clause = ""
    if book_id:
        where_clause = "WHERE book_id = ? OR book_id IS NULL"
        parameters.append(book_id)
    rows = connection.execute(
        f"""
        SELECT entity_type, provenance, COUNT(*) AS count
        FROM rule_entities
        {where_clause}
        GROUP BY entity_type, provenance
        ORDER BY entity_type, provenance
        """,
        parameters,
    ).fetchall()
    by_type: dict[str, int] = {}
    by_provenance: dict[str, int] = {}
    for row in rows:
        by_type[str(row["entity_type"])] = by_type.get(str(row["entity_type"]), 0) + int(row["count"])
        by_provenance[str(row["provenance"])] = by_provenance.get(str(row["provenance"]), 0) + int(row["count"])
    return {
        "schema_version": RULES_ENTITY_CATALOG_SCHEMA_VERSION,
        "refreshed_entities": refreshed,
        "entity_count": sum(int(row["count"]) for row in rows),
        "by_type": by_type,
        "by_provenance": by_provenance,
    }


def _refresh_rule_units(connection: sqlite3.Connection, *, book_id: str | None, full: bool) -> dict[str, Any]:
    rows = _fetch_rule_chunks_for_index(connection, book_id=book_id)
    before = _rule_units_summary(connection, book_id=book_id)
    refresh_rows = [row for row in rows if full or _rule_units_need_refresh(connection, row)]
    refreshed = 0
    skipped = 0
    for row in refresh_rows:
        connection.execute("DELETE FROM rule_units WHERE primary_chunk_id = ?", (int(row["chunk_id"]),))
        units = derive_rule_units_from_chunk(row)
        if not units:
            skipped += 1
            continue
        for unit in units:
            _upsert_rule_unit(connection, unit)
            refreshed += 1
    after = _rule_units_summary(connection, book_id=book_id)
    return {
        **after,
        "rule_unit_schema_version": RULE_UNIT_SCHEMA_VERSION,
        "rule_units_before": before["rule_units"],
        "missing_rule_units_before": before["missing_rule_units"],
        "stale_rule_units_before": before["stale_rule_units"],
        "low_confidence_rule_units_before": before["low_confidence_rule_units"],
        "refreshed_rule_units": refreshed,
        "skipped_rule_unit_chunks": skipped,
        "source_pdf_required": False,
        "source_operation": "stored_chunk_text",
    }


def _rule_units_summary(connection: sqlite3.Connection, *, book_id: str | None) -> dict[str, Any]:
    parameters: list[Any] = []
    book_filter = ""
    if book_id:
        book_filter = "WHERE rc.book_id = ?"
        parameters.append(book_id)
    rows = connection.execute(
        f"""
        SELECT
            rc.id AS chunk_id,
            rc.book_id,
            rc.content_hash,
            ru.unit_id,
            ru.source_content_hash,
            ru.schema_version,
            ru.confidence,
            ru.warnings_json
        FROM rule_chunks rc
        LEFT JOIN rule_units ru ON ru.primary_chunk_id = rc.id
        {book_filter}
        ORDER BY rc.book_id, rc.page_start, rc.chunk_index
        """,
        parameters,
    ).fetchall()
    chunk_ids = {int(row["chunk_id"]) for row in rows}
    unit_count = 0
    stale_unit_ids: list[str] = []
    low_confidence_unit_ids: list[str] = []
    warned_unit_ids: list[str] = []
    chunks_with_units: set[int] = set()
    for row in rows:
        unit_id = row["unit_id"]
        if unit_id is None:
            continue
        unit_count += 1
        chunks_with_units.add(int(row["chunk_id"]))
        if row["source_content_hash"] != row["content_hash"] or int(row["schema_version"] or 0) != RULE_UNIT_SCHEMA_VERSION:
            stale_unit_ids.append(str(unit_id))
        if float(row["confidence"] or 0.0) < RULE_UNIT_LOW_CONFIDENCE_THRESHOLD:
            low_confidence_unit_ids.append(str(unit_id))
        if _json_list(row["warnings_json"]):
            warned_unit_ids.append(str(unit_id))
    return {
        "rule_units": unit_count,
        "rule_unit_chunks": len(chunks_with_units),
        "missing_rule_units": len(chunk_ids - chunks_with_units),
        "stale_rule_units": len(set(stale_unit_ids)),
        "low_confidence_rule_units": len(set(low_confidence_unit_ids)),
        "warned_rule_units": len(set(warned_unit_ids)),
        "stale_unit_ids": sorted(set(stale_unit_ids))[:20],
        "low_confidence_unit_ids": sorted(set(low_confidence_unit_ids))[:20],
        "warned_unit_ids": sorted(set(warned_unit_ids))[:20],
    }


def _rule_units_need_refresh(connection: sqlite3.Connection, row: sqlite3.Row) -> bool:
    units = connection.execute(
        """
        SELECT source_content_hash, schema_version
        FROM rule_units
        WHERE primary_chunk_id = ?
        """,
        (int(row["chunk_id"]),),
    ).fetchall()
    if not units:
        return True
    return any(
        unit["source_content_hash"] != row["content_hash"]
        or int(unit["schema_version"] or 0) != RULE_UNIT_SCHEMA_VERSION
        for unit in units
    )


def derive_rule_units_from_chunk(row: sqlite3.Row | dict[str, Any]) -> list[RuleUnit]:
    content = str(_row_or_dict(row, "content") or "")
    if not content.strip():
        return []
    metadata = _rule_unit_chunk_metadata(row)
    heading_path = metadata["heading_path"]
    section_label = str(_row_or_dict(row, "section_label") or "")
    unit_kind = _infer_rule_unit_kind(
        section_label=section_label,
        content=content,
        block_kind=str(_row_or_dict(row, "block_kind") or ""),
        section_kind=metadata["section_kind"],
        evidence_cues=metadata["evidence_cues"],
    )
    authority_role = _infer_rule_unit_authority_role(
        unit_kind=unit_kind,
        section_kind=metadata["section_kind"],
        evidence_cues=metadata["evidence_cues"],
        content=content,
    )
    answer_facets = _rule_unit_answer_facets(metadata["evidence_cues"], content)
    entity_tags = _rule_unit_entity_tags(metadata["entity_locations"], _json_list(_row_or_dict(row, "chunk_scope_tags_json")))
    mechanic_tags = _rule_unit_mechanic_tags(entity_tags, metadata["aliases"], content)
    confidence, warnings = _rule_unit_confidence_and_warnings(
        row=row,
        unit_kind=unit_kind,
        authority_role=authority_role,
        answer_facets=answer_facets,
        content=content,
    )
    chunk_id = int(_row_or_dict(row, "chunk_id") or 0)
    page_start = int(_row_or_dict(row, "page_start") or 0)
    page_end = int(_row_or_dict(row, "page_end") or page_start)
    chunk_index = int(_row_or_dict(row, "chunk_index") or 0)
    book_id = str(_row_or_dict(row, "book_id") or "")
    unit_id = _rule_unit_id(
        book_id=book_id,
        page_start=page_start,
        chunk_index=chunk_index,
        heading_path=heading_path,
        unit_kind=unit_kind,
        content_hash=str(_row_or_dict(row, "content_hash") or fingerprint_text(content)),
    )
    return [
        RuleUnit(
            unit_id=unit_id,
            book_id=book_id,
            page_start=page_start,
            page_end=page_end,
            heading_path=heading_path,
            source_chunk_ids=[chunk_id],
            source_content_hash=str(_row_or_dict(row, "content_hash") or fingerprint_text(content)),
            unit_kind=unit_kind,
            authority_role=authority_role,
            entity_tags=entity_tags,
            mechanic_tags=mechanic_tags,
            answer_facets=answer_facets,
            confidence=confidence,
            warnings=warnings,
            source_window=summarize_text(str(_row_or_dict(row, "source_window") or _row_or_dict(row, "excerpt") or content), 520),
        )
    ]


def _rule_unit_chunk_metadata(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    section_kind = str(_row_or_dict(row, "section_kind") or "")
    rag_schema_version = int(_row_or_dict(row, "rag_schema_version") or 0)
    metadata_hash = _row_or_dict(row, "metadata_content_hash")
    if not section_kind or metadata_hash != _row_or_dict(row, "content_hash") or rag_schema_version != RULES_RAG_V2_METADATA_SCHEMA_VERSION:
        metadata = classify_rule_chunk_rag_metadata(
            section_label=str(_row_or_dict(row, "section_label") or ""),
            content=str(_row_or_dict(row, "content") or ""),
            word_count=int(_row_or_dict(row, "word_count") or 0),
            confidence=float(_row_or_dict(row, "confidence") or 0.0),
            extraction_method=str(_row_or_dict(row, "extraction_method") or ""),
        )
        heading_path = metadata.heading_path
        aliases = metadata.aliases
        entity_locations = metadata.entity_locations
        evidence_cues = metadata.evidence_cues
        section_kind = metadata.section_kind
    else:
        heading_path = _json_text_list(_row_or_dict(row, "heading_path_json"))
        aliases = _json_text_list(_row_or_dict(row, "aliases_json"))
        entity_locations = _json_dict_list(_row_or_dict(row, "entity_locations_json"))
        evidence_cues = _json_text_list(_row_or_dict(row, "evidence_cues_json"))
    block_heading_path = _json_text_list(_row_or_dict(row, "block_heading_path_json"))
    if block_heading_path:
        heading_path = block_heading_path
    if not heading_path:
        heading_path = _infer_heading_path(str(_row_or_dict(row, "section_label") or ""), str(_row_or_dict(row, "content") or ""))
    return {
        "section_kind": section_kind,
        "heading_path": heading_path,
        "aliases": aliases,
        "entity_locations": entity_locations,
        "evidence_cues": evidence_cues,
    }


def _infer_rule_unit_kind(
    *,
    section_label: str,
    content: str,
    block_kind: str,
    section_kind: str,
    evidence_cues: list[str],
) -> str:
    text = _normalize_rule_alias(f"{section_label} {content}")
    if section_kind == "lore" or ("lore" in evidence_cues and not {"system", "cost", "dice_pool"} & set(evidence_cues)):
        return "flavor_lore"
    if "example" in evidence_cues and not {"system", "cost", "dice_pool", "targeting", "duration"} & set(evidence_cues):
        return "example"
    if re.search(r"\b(?:except|exception|unless|cannot|can't|may not)\b", text):
        return "exception"
    if block_kind == "table" or _looks_like_structured_table(content):
        return "table_row"
    if re.search(r"\bformula\b", text):
        return "formula"
    if re.search(r"\bceremony\b", text):
        return "ceremony"
    if re.search(r"\britual\b", text):
        return "ritual"
    if re.search(r"\bmerit\b", text):
        return "merit"
    if re.search(r"\bflaw\b", text):
        return "flaw"
    if block_kind == "power" or re.search(r"\b(?:discipline|power|amalgam|level\s+\d)\b", text):
        return "discipline_power"
    if section_kind in {"toc", "index", "sheet", "art", "furniture"}:
        return section_kind
    return "base_rule"


def _infer_rule_unit_authority_role(*, unit_kind: str, section_kind: str, evidence_cues: list[str], content: str) -> str:
    text = _normalize_rule_alias(content)
    if unit_kind == "exception":
        return "exception"
    if unit_kind == "example" or "example" in evidence_cues:
        return "example"
    if unit_kind == "flavor_lore" or section_kind == "lore":
        return "flavor"
    if re.search(r"\b(?:optional|storyteller may|at the storyteller s discretion)\b", text):
        return "optional"
    if unit_kind in {"discipline_power", "ritual", "formula", "ceremony", "merit", "flaw", "table_row"}:
        return "specific"
    return "base"


def _rule_unit_answer_facets(evidence_cues: list[str], content: str) -> list[str]:
    facets: list[str] = []
    cue_map = {
        "cost": "cost",
        "dice_pool": "dice_pool",
        "targeting": "target",
        "duration": "duration",
        "prerequisite": "prerequisite",
        "consequence": "consequence",
        "definition": "effect",
        "system": "effect",
        "advancement": "prerequisite",
    }
    for cue in evidence_cues:
        mapped = cue_map.get(cue)
        if mapped:
            _add_unique(facets, mapped)
    text = _normalize_rule_alias(content)
    if re.search(r"\b(?:limit|maximum|minimum|only|cannot|may not|unless|except)\b", text):
        _add_unique(facets, "limit")
    if re.search(r"\b(?:see|refer to|as described on|p\s*\d+|page\s+\d+)\b", text):
        _add_unique(facets, "source_reference")
    return facets


def _rule_unit_entity_tags(entity_locations: list[dict[str, Any]], scope_tags: list[str]) -> list[str]:
    tags: list[str] = []
    _extend_unique(tags, scope_tags)
    for entity in entity_locations:
        tag = str(entity.get("scope_tag") or "")
        if tag:
            _add_unique(tags, tag)
    return sorted(set(tags))


def _rule_unit_mechanic_tags(entity_tags: list[str], aliases: list[str], content: str) -> list[str]:
    tags = [tag for tag in entity_tags if tag.startswith(("mechanic:", "discipline:", "power:", "topic:", "content:"))]
    for alias in aliases:
        normalized = _slugify(alias)
        if normalized:
            _add_unique(tags, f"alias:{normalized}")
    text = _normalize_rule_alias(content)
    for label, pattern in {
        "mechanic:cost": r"\bcost\b",
        "mechanic:dice-pool": r"\bdice pool\b",
        "mechanic:duration": r"\bduration\b",
        "mechanic:targeting": r"\btarget",
    }.items():
        if re.search(pattern, text):
            _add_unique(tags, label)
    return sorted(set(tags))


def _rule_unit_confidence_and_warnings(
    *,
    row: sqlite3.Row | dict[str, Any],
    unit_kind: str,
    authority_role: str,
    answer_facets: list[str],
    content: str,
) -> tuple[float, list[str]]:
    confidence = float(_row_or_dict(row, "confidence") or 0.0)
    warnings: list[str] = []
    if confidence < SUSPECT_CONFIDENCE_THRESHOLD:
        _add_unique(warnings, "low_source_confidence")
    if not answer_facets and authority_role in {"base", "specific", "exception"}:
        confidence = min(confidence, 0.62)
        _add_unique(warnings, "no_answer_facets_detected")
    if unit_kind in {"toc", "index", "sheet", "art", "furniture"}:
        confidence = min(confidence, 0.5)
        _add_unique(warnings, "non_answer_section")
    if len(content.split()) < 18:
        confidence = min(confidence, 0.6)
        _add_unique(warnings, "very_short_unit")
    for flag in _json_list(_row_or_dict(row, "structure_flags_json")):
        if flag in {"possible_mixed_topic", "page_furniture_removed"}:
            _add_unique(warnings, flag)
    return round(max(min(confidence, 1.0), 0.0), 4), sorted(set(warnings))


def _rule_unit_id(
    *,
    book_id: str,
    page_start: int,
    chunk_index: int,
    heading_path: list[str],
    unit_kind: str,
    content_hash: str,
) -> str:
    heading = heading_path[-1] if heading_path else f"chunk-{chunk_index}"
    slug = _slugify(f"{unit_kind}-{heading}")[:48] or f"{unit_kind}-chunk-{chunk_index}"
    return f"{book_id}:unit:p{page_start}:c{chunk_index}:{slug}:{content_hash[:10]}"


def _upsert_rule_unit(connection: sqlite3.Connection, unit: RuleUnit) -> None:
    now = timestamp_now()
    connection.execute(
        """
        INSERT INTO rule_units (
            unit_id, book_id, page_start, page_end, heading_path_json, source_chunk_ids_json,
            primary_chunk_id, source_content_hash, unit_kind, authority_role, entity_tags_json,
            mechanic_tags_json, answer_facets_json, confidence, warnings_json, source_window,
            extractor_backend, extractor_model, schema_version, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(unit_id) DO UPDATE SET
            book_id = excluded.book_id,
            page_start = excluded.page_start,
            page_end = excluded.page_end,
            heading_path_json = excluded.heading_path_json,
            source_chunk_ids_json = excluded.source_chunk_ids_json,
            primary_chunk_id = excluded.primary_chunk_id,
            source_content_hash = excluded.source_content_hash,
            unit_kind = excluded.unit_kind,
            authority_role = excluded.authority_role,
            entity_tags_json = excluded.entity_tags_json,
            mechanic_tags_json = excluded.mechanic_tags_json,
            answer_facets_json = excluded.answer_facets_json,
            confidence = excluded.confidence,
            warnings_json = excluded.warnings_json,
            source_window = excluded.source_window,
            extractor_backend = excluded.extractor_backend,
            extractor_model = excluded.extractor_model,
            schema_version = excluded.schema_version,
            updated_at = excluded.updated_at
        """,
        (
            unit.unit_id,
            unit.book_id,
            unit.page_start,
            unit.page_end,
            json.dumps(unit.heading_path),
            json.dumps(unit.source_chunk_ids),
            unit.source_chunk_ids[0] if unit.source_chunk_ids else None,
            unit.source_content_hash,
            unit.unit_kind,
            unit.authority_role,
            json.dumps(unit.entity_tags),
            json.dumps(unit.mechanic_tags),
            json.dumps(unit.answer_facets),
            unit.confidence,
            json.dumps(unit.warnings),
            unit.source_window,
            unit.extractor_backend,
            unit.extractor_model,
            unit.schema_version,
            now,
        ),
    )


def _rule_unit_row_to_dict(row: sqlite3.Row, *, include_window: bool = True) -> dict[str, Any]:
    data = {
        "unit_id": row["unit_id"],
        "book_id": row["book_id"],
        "book_title": _row_optional(row, "book_title"),
        "page_start": int(row["page_start"]),
        "page_end": int(row["page_end"]),
        "heading_path": _json_text_list(row["heading_path_json"]),
        "source_chunk_ids": [int(value) for value in _json_text_list(row["source_chunk_ids_json"]) if str(value).isdigit()],
        "primary_chunk_id": int(row["primary_chunk_id"]) if row["primary_chunk_id"] is not None else None,
        "source_content_hash": row["source_content_hash"],
        "unit_kind": row["unit_kind"],
        "authority_role": row["authority_role"],
        "entity_tags": _json_text_list(row["entity_tags_json"]),
        "mechanic_tags": _json_text_list(row["mechanic_tags_json"]),
        "answer_facets": _json_text_list(row["answer_facets_json"]),
        "confidence": float(row["confidence"]),
        "warnings": _json_text_list(row["warnings_json"]),
        "extractor_backend": row["extractor_backend"],
        "extractor_model": row["extractor_model"],
        "schema_version": int(row["schema_version"]),
        "section_label": _row_optional(row, "section_label"),
    }
    if include_window:
        data["source_window"] = summarize_text(str(row["source_window"] or ""), 520)
    return data


def _fetch_rule_chunks_for_index(connection: sqlite3.Connection, book_id: str | None) -> list[sqlite3.Row]:
    parameters: list[Any] = []
    where_clause = ""
    if book_id:
        where_clause = "WHERE rc.book_id = ?"
        parameters.append(book_id)
    return connection.execute(
        f"""
        SELECT
            rc.id AS chunk_id,
            rc.book_id,
            rc.page_start,
            rc.page_end,
            rc.chunk_index,
            rc.section_label,
            rc.content AS raw_content,
            rc.excerpt AS raw_excerpt,
            COALESCE(NULLIF(rc.clean_content, ''), rc.content) AS content,
            COALESCE(NULLIF(rc.source_window, ''), rc.excerpt) AS excerpt,
            rc.scope_tags_json AS chunk_scope_tags_json,
            rc.word_count,
            rc.confidence,
            rc.extraction_method,
            rc.content_hash,
            rc.rule_block_id,
            rc.heading_path_json AS block_heading_path_json,
            rc.block_kind,
            rc.clean_content,
            rc.source_window,
            rc.structure_flags_json,
            rc.structure_schema_version,
            e.backend AS embedding_backend,
            e.model AS embedding_model,
            e.dimensions AS embedding_dimensions,
            e.content_hash AS embedding_content_hash,
            m.content_hash AS metadata_content_hash,
            m.section_kind,
            m.retrieval_flags_json,
            m.rag_schema_version,
            m.heading_path_json,
            m.aliases_json,
            m.entity_locations_json,
            m.evidence_cues_json
        FROM rule_chunks rc
        LEFT JOIN rule_chunk_embeddings e ON e.chunk_id = rc.id
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        {where_clause}
        ORDER BY rc.book_id, rc.page_start, rc.chunk_index
        """,
        parameters,
    ).fetchall()


def _embedding_missing(row: sqlite3.Row) -> bool:
    return _row_optional(row, "embedding_backend") is None


def _embedding_needs_refresh(row: sqlite3.Row, backend: EmbeddingBackend) -> bool:
    if _embedding_missing(row):
        return True
    return (
        row["embedding_backend"] != backend.name
        or row["embedding_model"] != backend.model_name
        or row["embedding_content_hash"] != row["content_hash"]
    )


def _metadata_needs_refresh(row: sqlite3.Row) -> bool:
    return (
        _row_optional(row, "metadata_content_hash") != row["content_hash"]
        or int(_row_optional(row, "rag_schema_version") or 0) != RULES_RAG_V2_METADATA_SCHEMA_VERSION
    )


def _upsert_rule_chunk_retrieval_metadata(
    connection: sqlite3.Connection,
    chunk_id: int,
    section_label: str,
    content: str,
    word_count: int,
    confidence: float,
    extraction_method: str,
    content_hash: str,
) -> None:
    metadata = classify_rule_chunk_rag_metadata(
        section_label=section_label,
        content=content,
        word_count=word_count,
        confidence=confidence,
        extraction_method=extraction_method,
    )
    connection.execute(
        """
        INSERT INTO rule_chunk_retrieval_metadata (
            chunk_id, content_hash, section_kind, retrieval_flags_json, rag_schema_version,
            heading_path_json, aliases_json, entity_locations_json, evidence_cues_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
            content_hash = excluded.content_hash,
            section_kind = excluded.section_kind,
            retrieval_flags_json = excluded.retrieval_flags_json,
            rag_schema_version = excluded.rag_schema_version,
            heading_path_json = excluded.heading_path_json,
            aliases_json = excluded.aliases_json,
            entity_locations_json = excluded.entity_locations_json,
            evidence_cues_json = excluded.evidence_cues_json,
            updated_at = excluded.updated_at
        """,
        (
            chunk_id,
            content_hash,
            metadata.section_kind,
            json.dumps(metadata.retrieval_flags),
            metadata.rag_schema_version,
            json.dumps(metadata.heading_path),
            json.dumps(metadata.aliases),
            json.dumps(metadata.entity_locations),
            json.dumps(metadata.evidence_cues),
            timestamp_now(),
        ),
    )


def classify_rule_chunk_rag_metadata(
    section_label: str,
    content: str,
    word_count: int,
    confidence: float,
    extraction_method: str,
) -> RuleChunkRetrievalMetadata:
    section_kind, flags = classify_rule_chunk(
        section_label=section_label,
        content=content,
        word_count=word_count,
        confidence=confidence,
        extraction_method=extraction_method,
    )
    heading_path = _infer_heading_path(section_label, content)
    aliases, entity_locations = _detect_rule_aliases_and_entities(section_label=section_label, content=content)
    evidence_cues = _detect_evidence_cues(
        section_label=section_label,
        content=content,
        section_kind=section_kind,
    )
    return RuleChunkRetrievalMetadata(
        rag_schema_version=RULES_RAG_V2_METADATA_SCHEMA_VERSION,
        heading_path=heading_path,
        aliases=aliases,
        entity_locations=entity_locations,
        evidence_cues=evidence_cues,
        section_kind=section_kind,
        retrieval_flags=flags,
    )


def classify_rule_chunk(
    section_label: str,
    content: str,
    word_count: int,
    confidence: float,
    extraction_method: str,
) -> tuple[str, list[str]]:
    combined = f"{section_label}\n{content}".casefold()
    compact = re.sub(r"[^a-z0-9]+", "", combined)
    label_compact = re.sub(r"[^a-z0-9]+", "", section_label.casefold())
    flags: list[str] = []

    if "tableofcontents" in compact or compact.startswith("contents"):
        section_kind = "toc"
    elif label_compact.startswith("index") or compact.startswith("index"):
        section_kind = "index"
    elif _looks_page_furniture(section_label, content, word_count):
        section_kind = "furniture"
    elif (
        "character sheet" in combined
        or "relationship map" in combined
        or "reference sheet" in combined
        or ("clan:" in combined and "disciplines and powers" in combined)
    ):
        section_kind = "sheet"
    elif _looks_art_heavy(content, word_count=word_count):
        section_kind = "art"
    elif "loresheet" in combined or "lore sheet" in combined or "lore" in section_label.casefold():
        section_kind = "lore"
    elif _looks_rules_substantive(combined):
        section_kind = "rules"
    else:
        section_kind = "unknown"

    if word_count < 12:
        flags.append("very_short")
    if extraction_method == "ocr" and confidence < SUSPECT_CONFIDENCE_THRESHOLD:
        flags.append("suspect_ocr")
    if section_kind in {"toc", "index", "sheet", "furniture"}:
        flags.append("navigational")
    if section_kind == "furniture":
        flags.append("page_furniture")
    if section_kind == "art":
        flags.append("art_heavy")
    return section_kind, sorted(set(flags))


def _infer_heading_path(section_label: str, content: str) -> list[str]:
    candidates = [str(section_label or "").strip()]
    for line in str(content or "").splitlines()[:4]:
        stripped = line.strip(" \t#")
        if 3 <= len(stripped) <= 120 and len(stripped.split()) <= 12:
            candidates.append(stripped)
    return _dedupe_text_values(candidates)[:4]


def _detect_rule_aliases_and_entities(*, section_label: str, content: str) -> tuple[list[str], list[dict[str, Any]]]:
    heading = str(section_label or "")
    body = str(content or "")
    aliases: list[str] = []
    entities: list[dict[str, Any]] = []

    for entry in TAXONOMY_ENTRIES:
        for alias in entry.aliases:
            location = _alias_location(alias, heading=heading, body=body)
            if location is None:
                continue
            canonical = entry.aliases[0] if entry.aliases else entry.tag.split(":", 1)[-1].replace("-", " ")
            normalized_alias = _normalize_rule_alias(alias)
            _add_unique(aliases, normalized_alias)
            entities.append(
                {
                    "alias": normalized_alias,
                    "canonical": _normalize_rule_alias(canonical),
                    "scope_tag": canonicalize_scope_tag(entry.tag),
                    "location": location,
                }
            )
            break

    for canonical, meta in TARGETED_MECHANIC_ALIASES.items():
        for alias in meta["aliases"]:
            location = _alias_location(str(alias), heading=heading, body=body)
            if location is None:
                continue
            normalized_alias = _normalize_rule_alias(str(alias))
            _add_unique(aliases, normalized_alias)
            for tag in meta.get("scope_tags", ()):
                entities.append(
                    {
                        "alias": normalized_alias,
                        "canonical": _normalize_rule_alias(canonical),
                        "scope_tag": canonicalize_scope_tag(str(tag)),
                        "location": location,
                    }
                )
            break

    for canonical, meta in TARGETED_POWER_ALIASES.items():
        for alias in meta["aliases"]:
            location = _alias_location(str(alias), heading=heading, body=body)
            if location is None:
                continue
            normalized_alias = _normalize_rule_alias(str(alias))
            _add_unique(aliases, normalized_alias)
            entities.append(
                {
                    "alias": normalized_alias,
                    "canonical": str(canonical),
                    "scope_tag": "power:" + _slugify(str(canonical)),
                    "location": location,
                }
            )
            for tag in meta.get("scope_tags", ()):
                entities.append(
                    {
                        "alias": normalized_alias,
                        "canonical": str(canonical),
                        "scope_tag": canonicalize_scope_tag(str(tag)),
                        "location": location,
                    }
                )
            break

    return aliases, _dedupe_entity_locations(entities)


def _detect_evidence_cues(*, section_label: str, content: str, section_kind: str) -> list[str]:
    text = f"{section_label}\n{content}".casefold()
    cues: list[str] = []
    if section_kind in {"toc", "index", "sheet", "lore"}:
        _add_unique(cues, section_kind)
    if re.search(r"\b(?:is|are|means|refers to|represents|rules call for|to make)\b", text) or re.search(
        r"(?m)^\s*(?!(?:cost|system|duration|dice pool)\s*:)[a-z][a-z0-9 '\-]{2,48}\s*:",
        str(content or "").casefold(),
    ):
        _add_unique(cues, "definition")
    if re.search(r"\bsystem\s*:", text) or re.search(r"\b(?:system|systems)\b", section_label.casefold()):
        _add_unique(cues, "system")
    if re.search(r"\bcost\s*:", text) or re.search(r"\b(?:cost|costs|experience|xp|spend|spent)\b", text):
        _add_unique(cues, "cost")
    if re.search(r"\b(?:dice pool|pool|roll|test|check|difficulty)\b", text):
        _add_unique(cues, "dice_pool")
    if re.search(r"\b(?:duration|lasts?|until|scene|turns?|rounds?)\b", text):
        _add_unique(cues, "duration")
    if re.search(r"\b(?:prerequisite|requires?|must|teacher|out of clan|access to|permission)\b", text):
        _add_unique(cues, "prerequisite")
    if re.search(r"\b(?:target|targets|targeting|subject|affect|affects|choose|range|eligible|line of sight)\b", text):
        _add_unique(cues, "targeting")
    if (
        re.search(r"\b(?:advancement|advance|acquire|acquisition|new discipline|new power|teacher|out of clan)\b", text)
        or re.search(r"\blearn(?:ing)?\s+(?:a\s+)?(?:new\s+)?(?:discipline|power|ceremony|ritual)\b", text)
        or re.search(r"\b(?:experience points|trait costs?|spend(?:ing)?\s+\d+\s+experience|costs?\s+\d+\s+experience)\b", text)
    ):
        _add_unique(cues, "advancement")
    if re.search(r"\b(?:on a success|on success|on a failure|on failure|succeeds?|fails?|result|consequence)\b", text):
        _add_unique(cues, "consequence")
    if re.search(r"\b(?:for example|for instance|e\.g\.|example)\b", text):
        _add_unique(cues, "example")
    if re.search(r"\b(?:lore|legend|history|rumor|storyteller may|chronicle)\b", text):
        _add_unique(cues, "lore")
    return cues


def _alias_location(alias: str, *, heading: str, body: str) -> str | None:
    normalized_alias = _normalize_rule_alias(alias)
    if not normalized_alias:
        return None
    if _contains_normalized_phrase(_normalize_rule_alias(heading), normalized_alias):
        return "heading"
    if _contains_normalized_phrase(_normalize_rule_alias(body), normalized_alias):
        return "body"
    return None


def _contains_normalized_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _normalize_rule_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).casefold()).strip("-")


def _dedupe_text_values(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        _add_unique(deduped, " ".join(str(value).split()))
    return deduped


def _add_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _extend_unique(values: list[str], items: Iterable[str]) -> None:
    for item in items:
        _add_unique(values, str(item))


def _dedupe_entity_locations(entities: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for entity in entities:
        key = (
            str(entity.get("alias") or ""),
            str(entity.get("canonical") or ""),
            str(entity.get("scope_tag") or ""),
            str(entity.get("location") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entity)
    return deduped


def _looks_rules_substantive(text: str) -> bool:
    rules_terms = (
        "advantage",
        "attribute",
        "character",
        "chasse",
        "clan",
        "compulsion",
        "dice",
        "discipline",
        "domain",
        "feeding",
        "hunting",
        "lien",
        "merit",
        "portillon",
        "predator",
        "rouse",
        "system",
        "test",
        "willpower",
    )
    return any(term in text for term in rules_terms)


def _looks_page_furniture(section_label: str, content: str, word_count: int) -> bool:
    combined = f"{section_label} {content}".casefold()
    compact = re.sub(r"[^a-z0-9]+", "", combined)
    if word_count <= 18 and re.search(r"\b(?:core book|players guide|vampire the masquerade|chapter)\b", combined):
        return True
    if re.fullmatch(r"(?:page)?\d{1,4}", compact):
        return True
    spaced_caps = re.sub(r"\s+", " ", str(section_label or "").strip())
    if len(spaced_caps) >= 12 and re.fullmatch(r"(?:[A-Z]\s+){4,}[A-Z]", spaced_caps):
        return True
    return False


def _looks_art_heavy(content: str, word_count: int) -> bool:
    normalized = "".join(content.split())
    if not normalized:
        return True
    alpha_ratio = sum(1 for char in normalized if char.isalpha()) / len(normalized)
    return word_count < 25 and alpha_ratio < 0.45


def _row_optional(row: sqlite3.Row, key: str) -> Any | None:
    return row[key] if key in row.keys() else None


def _row_or_dict(row: sqlite3.Row | dict[str, Any], key: str) -> Any | None:
    if isinstance(row, dict):
        return row.get(key)
    return _row_optional(row, key)


def _json_list(payload: Any) -> list[str]:
    if not payload:
        return []
    try:
        value = json.loads(str(payload))
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _json_text_list(payload: Any) -> list[str]:
    return _json_list(payload)


def _json_dict_list(payload: Any) -> list[dict[str, Any]]:
    if not payload:
        return []
    try:
        value = json.loads(str(payload))
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _json_assertions(payload: Any) -> list[dict[str, Any]]:
    if not payload:
        return []
    try:
        value = json.loads(str(payload))
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    assertions: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "")
        if not tag:
            continue
        assertions.append(
            {
                "id": item.get("id"),
                "tag": tag,
                "role": str(item.get("role") or ""),
                "status": str(item.get("status") or ""),
                "confidence": float(item.get("confidence") or 0.0),
            }
        )
    return assertions


def _semantic_error(error: AppError) -> dict[str, Any]:
    return {"code": error.code, "message": error.message, "hint": error.hint, "details": error.details}


def _rules_index_hint(book_id: str | None) -> str:
    if book_id:
        return f"Run `backet rules index <vault> --book-id {book_id} --full` to refresh rules retrieval metadata."
    return "Run `backet rules index <vault> --full` to refresh rules retrieval metadata."


def _audit_summary(connection: sqlite3.Connection, book_id: str) -> dict[str, Any]:
    suspect_pages = [
        row["page_number"]
        for row in connection.execute(
            "SELECT page_number FROM page_audit WHERE book_id = ? AND suspect = 1 ORDER BY page_number",
            (book_id,),
        ).fetchall()
    ]
    chunk_count = connection.execute(
        "SELECT COUNT(*) AS count FROM rule_chunks WHERE book_id = ?",
        (book_id,),
    ).fetchone()["count"]
    return {"suspect_pages": suspect_pages, "chunk_count": chunk_count}


def build_rules_fts_query(text: str) -> str:
    terms = _rules_query_terms(text)
    return " OR ".join(f'"{term}"' for term in terms)


def _rules_query_terms(text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for term in FTS_TOKEN_PATTERN.findall(text.lower()):
        if len(term) <= 1 or term in RULE_QUERY_STOPWORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _is_definition_rule_query(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return bool(re.search(r"\b(?:what\s+(?:is|are)|how\s+(?:does|do)|define|explain)\b", normalized))


def split_rule_chunks(text: str) -> list[str]:
    normalized = normalize_text(text)
    paragraphs = _split_rule_block_candidates(normalized)
    if not paragraphs:
        return [normalized] if normalized else []

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for paragraph in paragraphs:
        paragraph_words = len(paragraph.split())
        if current and current_words + paragraph_words > DEFAULT_CHUNK_WORDS:
            chunks.append("\n\n".join(current).strip())
            current = []
            current_words = 0
        if paragraph_words > DEFAULT_CHUNK_WORDS:
            words = paragraph.split()
            for start in range(0, len(words), DEFAULT_CHUNK_WORDS):
                chunks.append(" ".join(words[start : start + DEFAULT_CHUNK_WORDS]))
            continue
        current.append(paragraph)
        current_words += paragraph_words
    if current:
        chunks.append("\n\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _split_rule_block_candidates(text: str) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in str(text or "").split("\n\n") if paragraph.strip()]
    if len(paragraphs) > 1:
        return paragraphs

    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return []

    blocks: list[list[str]] = []
    current: list[str] = []
    for index, line in enumerate(lines):
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if current and _looks_rule_block_heading_line(line, next_line):
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)
    return ["\n".join(block).strip() for block in blocks if "\n".join(block).strip()]


def _looks_rule_block_heading_line(line: str, next_line: str) -> bool:
    stripped = " ".join(str(line or "").strip().split())
    if not (3 <= len(stripped) <= 90):
        return False
    if len(stripped.split()) > 10:
        return False
    if re.search(r"^(?:cost|system|duration|dice pools?|amalgam|prerequisite|ingredients|process)\s*:", stripped, re.I):
        return False
    if stripped.endswith((".", ",", ";", ":")):
        return False
    if re.fullmatch(r"(?:[A-Z]\s+){4,}[A-Z0-9 ]+", stripped):
        return False
    next_is_stat = bool(
        re.search(r"^(?:cost|system|duration|dice pools?|amalgam|prerequisite|ingredients|process)\s*:", next_line, re.I)
    )
    if next_is_stat:
        return True
    words = stripped.split()
    titled_words = sum(1 for word in words if word[:1].isupper() and any(char.islower() for char in word[1:]))
    return len(words) <= 6 and titled_words >= max(1, len(words) - 1)


def derive_rule_block_structure(
    *,
    book_id: str,
    section_label: str,
    content: str,
    page_start: int,
    chunk_index: int,
) -> RuleBlockStructure:
    clean_content, flags = _clean_rule_block_text(content, section_label=section_label)
    heading_path = _infer_heading_path(section_label, clean_content)
    block_kind = _infer_rule_block_kind(section_label, clean_content)
    if block_kind in {"table", "list", "power", "ritual"}:
        _add_unique(flags, f"block_kind:{block_kind}")
    slug_source = heading_path[-1] if heading_path else section_label or f"chunk-{chunk_index}"
    slug = _slugify(slug_source)[:48] or f"chunk-{chunk_index}"
    block_id = f"{book_id}:p{int(page_start)}:c{int(chunk_index)}:{slug}"
    source_window = _rule_block_source_window(clean_content, heading_path=heading_path)
    return RuleBlockStructure(
        block_id=block_id,
        heading_path=heading_path,
        block_kind=block_kind,
        clean_content=clean_content,
        source_window=source_window,
        structure_flags=sorted(set(flags)),
    )


def _clean_rule_block_text(content: str, *, section_label: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    lines: list[str] = []
    seen_non_furniture = False
    for raw_line in str(content or "").splitlines():
        line = " ".join(raw_line.strip().split())
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        line, inline_furniture_removed = _strip_inline_rule_page_furniture(line)
        if inline_furniture_removed:
            _add_unique(flags, "page_furniture_removed")
        if not line:
            continue
        if _looks_rule_block_page_furniture(line, section_label=section_label, seen_non_furniture=seen_non_furniture):
            _add_unique(flags, "page_furniture_removed")
            continue
        seen_non_furniture = True
        lines.append(line)
    clean = "\n".join(lines).strip()
    if not clean:
        _add_unique(flags, "empty_after_structure_clean")
        clean = normalize_text(content)
    if len(clean.split()) < 12:
        _add_unique(flags, "very_short_block")
    if len(re.findall(r"\b(?:system|cost|duration)\s*:", clean, flags=re.I)) >= 6:
        _add_unique(flags, "possible_mixed_topic")
    return clean, flags


def _strip_inline_rule_page_furniture(line: str) -> tuple[str, bool]:
    parts = str(line or "").split()
    removed = False
    while parts:
        prefix = 0
        for part in parts:
            token = re.sub(r"[^A-Za-z0-9]+", "", part)
            if not token or len(token) == 1 or token.isdigit():
                prefix += 1
                continue
            break
        if prefix < 8:
            break
        parts = parts[prefix:]
        removed = True
    if removed:
        return " ".join(parts).strip(), True
    return line, False


def _looks_rule_block_page_furniture(line: str, *, section_label: str, seen_non_furniture: bool) -> bool:
    compact = re.sub(r"[^a-z0-9]+", "", line.casefold())
    if re.fullmatch(r"(?:page)?\d{1,4}", compact):
        return True
    if re.fullmatch(r"(?:[a-z]\s+){4,}[a-z]", line.casefold()):
        return True
    if len(line.split()) <= 5 and re.search(r"\b(?:vampire|masquerade|core rulebook|players guide)\b", line, flags=re.I):
        return True
    if not seen_non_furniture and line.strip() == str(section_label or "").strip() and _looks_page_furniture(section_label, line, len(line.split())):
        return True
    return False


def _infer_rule_block_kind(section_label: str, content: str) -> str:
    text = f"{section_label}\n{content}".casefold()
    if _looks_like_structured_table(content):
        return "table"
    if re.search(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", content):
        return "list"
    if re.search(r"\b(?:level\s+\d|amalgam|cost\s*:|dice pools?\s*:|duration\s*:|system\s*:)", text):
        if re.search(r"\b(?:discipline|amalgam|level\s+\d)\b", text):
            return "power"
        if re.search(r"\b(?:ritual|ceremony|formula)\b", text):
            return "ritual"
        return "rules"
    section_kind, _flags = classify_rule_chunk(
        section_label=section_label,
        content=content,
        word_count=len(content.split()),
        confidence=1.0,
        extraction_method="direct",
    )
    return section_kind


def _looks_like_structured_table(content: str) -> bool:
    rows = [line.strip() for line in str(content or "").splitlines() if line.strip()]
    if len(rows) < 2:
        return False
    label_value_rows = sum(1 for line in rows if re.search(r"\b[A-Za-z][A-Za-z /+\-]{2,40}\s{2,}[A-Za-z0-9]", line))
    colon_rows = sum(
        1
        for line in rows
        if re.search(r"^[A-Za-z][A-Za-z /+\-]{2,40}\s*:", line)
        and not re.search(r"^(?:cost|system|duration|dice pools?|amalgam|prerequisite|ingredients|process)\s*:", line, re.I)
    )
    return label_value_rows >= 2 or colon_rows >= 3


def _rule_block_source_window(content: str, *, heading_path: list[str], limit: int = 520) -> str:
    normalized = " ".join(str(content or "").split())
    if not normalized:
        return ""
    heading_starts = [
        normalized.casefold().find(heading.casefold().rstrip(":"))
        for heading in heading_path
        if heading
    ]
    heading_starts = [start for start in heading_starts if start >= 0]
    start = min(heading_starts) if heading_starts else 0
    if not heading_starts:
        for pattern in (r"\bcost\s*:", r"\bsystem\s*:", r"\bdice pools?\s*:", r"\bduration\s*:"):
            match = re.search(pattern, normalized, flags=re.I)
            if match:
                start = max(0, match.start() - 160)
                if start > 0:
                    start = normalized.find(" ", start)
                    if start < 0:
                        start = 0
                break
    end = min(len(normalized), start + limit)
    if end < len(normalized):
        end = max(start + 80, normalized.rfind(" ", start, end))
    window = normalized[start:end].strip()
    if start > 0:
        window = f"... {window}"
    if end < len(normalized):
        window = f"{window} ..."
    return window


def infer_section_label(text: str, page_number: int) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) >= 4:
            return stripped[:120]
    return f"Page {page_number}"


def normalize_scope_tags(scope_tags: list[str]) -> list[str]:
    return normalize_scope_tags_from_taxonomy(scope_tags)


def parse_pages_spec(pages_spec: str | None, page_count: int) -> list[int]:
    if not pages_spec:
        return list(range(1, page_count + 1))
    pages: set[int] = set()
    try:
        for part in pages_spec.split(","):
            current = part.strip()
            if not current:
                continue
            if "-" in current:
                start_str, end_str = current.split("-", 1)
                start = int(start_str)
                end = int(end_str)
                if start > end:
                    raise AppError(
                        code="rules_pages_invalid",
                        message="Page ranges must increase from start to end.",
                        hint="Use a page expression like `3-5,9`.",
                        details={"pages": pages_spec},
                        exit_code=2,
                    )
                pages.update(range(start, end + 1))
            else:
                pages.add(int(current))
    except ValueError as exc:
        raise AppError(
            code="rules_pages_invalid",
            message="Page ranges must contain only whole page numbers.",
            hint="Use a page expression like `3-5,9`.",
            details={"pages": pages_spec},
            exit_code=2,
        ) from exc
    if not pages or min(pages) < 1 or max(pages) > page_count:
        raise AppError(
            code="rules_pages_invalid",
            message="Requested pages fall outside the available PDF page range.",
            hint="Check the page range and try again.",
            details={"pages": pages_spec, "page_count": page_count},
            exit_code=2,
        )
    return sorted(pages)


def normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").splitlines()).strip()


def summarize_text(text: str, limit: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "â€¦"


def fingerprint_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def timestamp_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def fts_rank_to_score(rank: float) -> float:
    positive_rank = abs(rank)
    return positive_rank / (positive_rank + 8.0)


def document_page_count(pdf_path: Path) -> int:
    fitz = _require_pymupdf()
    document = fitz.open(str(pdf_path))
    try:
        return document.page_count
    finally:
        document.close()
