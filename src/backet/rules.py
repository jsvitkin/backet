from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

import yaml

from backet.embeddings import EmbeddingBackend, cosine_similarity, resolve_embedding_backend
from backet.errors import AppError
from backet.models import CommandResult
from backet.paths import rules_db_path
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
from backet.vault import ensure_bootstrapped_vault

RULES_SCHEMA_VERSION = 4
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
SUPPLEMENT_SCOPE_BOOST = 0.15
RULE_SEMANTIC_LIMIT = 40
NON_ANSWER_SECTION_PENALTIES = {
    "toc": 0.45,
    "index": 0.4,
    "sheet": 0.35,
    "art": 0.3,
}
RETRIEVAL_FLAG_PENALTIES = {
    "suspect_ocr": 0.2,
    "very_short": 0.15,
    "navigational": 0.25,
    "art_heavy": 0.2,
}


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
    section_label: str
    content: str
    excerpt: str
    confidence: float
    extraction_method: str
    word_count: int
    content_hash: str
    section_kind: str
    retrieval_flags: list[str]
    exact_score: float = 0.0
    semantic_score: float = 0.0
    lexical_score: float = 0.0
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
) -> CommandResult:
    if limit <= 0:
        raise AppError(
            code="rules_limit_invalid",
            message="Rules query limits must be positive.",
            hint="Use a limit greater than zero.",
            details={"limit": limit},
            exit_code=2,
        )
    query_terms = _rules_query_terms(query)
    fts_query = build_rules_fts_query(query)
    if not fts_query:
        raise AppError(
            code="rules_query_invalid",
            message="Rules queries need at least one searchable term.",
            hint="Use a query containing letters or numbers.",
            details={"query": query},
            exit_code=2,
        )

    normalized_tags = normalize_scope_tags(scope_tags or [])
    excluded_chunks = _active_excluded_chunk_count(connection, book_id)
    exact_rows = _search_rule_chunks(
        connection,
        fts_query,
        book_id=book_id,
        scope_tags=normalized_tags,
        limit=max(limit * 4, 12),
    )
    semantic = _search_semantic_rule_chunks(
        connection,
        query,
        book_id=book_id,
        scope_tags=normalized_tags,
        limit=max(limit * 4, RULE_SEMANTIC_LIMIT),
    )
    rows = _merge_rule_candidates(
        exact_rows,
        semantic.candidates,
        scope_tags=normalized_tags,
        query_terms=query_terms,
        definition_query=_is_definition_rule_query(query),
    )
    if not rows:
        raise AppError(
            code="rules_query_empty",
            message="No ingested rule chunks matched the requested query.",
            hint="Adjust the query or ingest the relevant rulebook first.",
            details={
                "query": query,
                "book_id": book_id,
                "scope_tags": normalized_tags,
                "retrieval_mode": semantic.retrieval_mode,
                "semantic_error": semantic.error,
                "reviewed_exclusions": {"excluded_chunks": excluded_chunks},
            },
            exit_code=2,
        )
    primary_rows, fallback_rows, ambiguity = _apply_precedence(rows, scope_tags=normalized_tags, explicit_book_id=book_id)
    if ambiguity is not None:
        raise AppError(
            code="rules_query_ambiguous",
            message="Multiple supplement-specific rulebooks match this query with comparable precedence.",
            hint="Re-run the query with `--book-id` or narrower `--scope-tag` filters.",
            details=ambiguity,
            exit_code=2,
        )

    primary = [_row_to_rule_result(row) for row in primary_rows[:limit]]
    fallback = [_row_to_rule_result(row) for row in fallback_rows[:limit]]
    label = db_label or "rules.sqlite3"
    return CommandResult(
        message="Retrieved ingested rule chunks",
        data={
            data_key: label,
            "query": query,
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
            },
            "reviewed_exclusions": {"excluded_chunks": excluded_chunks},
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

    return CommandResult(
        message="Audited ingested rulebooks",
        data={
            "vault": str(vault_root),
            "book_id": book_id,
            "books": suspects,
            "semantic_index": semantic_index,
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


def _rules_audit_book_report(connection: sqlite3.Connection, book: sqlite3.Row) -> dict[str, Any]:
    current_book_id = str(book["book_id"])
    source_status = _inspect_rule_source_status(book)
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

    return {
        "book_id": current_book_id,
        "book_title": book["book_title"],
        "tier": book["tier"],
        "scope_tags": json.loads(book["scope_tags_json"]),
        "page_count": int(book["page_count"]),
        "chunk_count": int(chunk_count),
        "ocr_fallback_pages": [int(row["page_number"]) for row in ocr_pages],
        "source_status": source_status.to_dict(),
        "repair_eligible": source_status.repair_eligible,
        "review_summary": {
            "pending_pages": len(reviewable_pages),
            "pending_findings": sum(1 for finding in findings if not finding.resolved and finding.category in {"review", "blocked"}),
            "resolved_findings": resolved_count,
            "notices": category_counts.get("notice", 0),
            "blocked": category_counts.get("blocked", 0),
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
    if section_kind in {"art", "toc", "index", "sheet"}:
        return "notice"
    if not source_status.repair_eligible:
        return "blocked"
    return "review"


def _audit_page_reason(flags: list[str], section_kind: str, source_status: RuleSourceStatus) -> str:
    if section_kind in {"art", "toc", "index", "sheet"}:
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
        missing = int(semantic_index.get("missing_embeddings") or 0) + int(semantic_index.get("missing_metadata") or 0)
        stale = int(semantic_index.get("stale_embeddings") or 0) + int(semantic_index.get("stale_metadata") or 0)
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
            ["tesseract", str(image_path), "stdout", "--psm", psm],
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
            excerpt = summarize_text(chunk_text)
            content_hash = fingerprint_text(chunk_text)
            cursor = connection.execute(
                """
                INSERT INTO rule_chunks (
                    book_id, page_start, page_end, chunk_index, section_label, content,
                    excerpt, word_count, confidence, extraction_method, scope_tags_json, content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        SELECT rc.id, rc.book_id, b.book_title, b.tier, rc.scope_tags_json, rc.section_label, rc.content
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
            rc.section_label,
            rc.content,
            rc.excerpt,
            rc.word_count,
            rc.content_hash,
            rc.confidence,
            rc.extraction_method,
            m.section_kind,
            m.retrieval_flags_json,
            m.content_hash AS metadata_content_hash,
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
        "section_label": row.section_label,
        "excerpt": row.excerpt,
        "content": row.content,
        "confidence": row.confidence,
        "extraction_method": row.extraction_method,
        "score": round(row.score, 6),
        "exact_score": round(row.exact_score, 6),
        "semantic_score": round(row.semantic_score, 6),
        "lexical_score": round(row.lexical_score, 6),
        "quality_penalty": round(row.quality_penalty, 6),
        "match_reasons": sorted(set(row.match_reasons)),
        "section_kind": row.section_kind,
        "retrieval_flags": row.retrieval_flags,
    }


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
) -> SemanticRulesSearch:
    try:
        backend = resolve_embedding_backend()
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
            rc.section_label,
            rc.content,
            rc.excerpt,
            rc.word_count,
            rc.content_hash,
            rc.confidence,
            rc.extraction_method,
            e.embedding_json,
            m.section_kind,
            m.retrieval_flags_json,
            m.content_hash AS metadata_content_hash,
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
) -> list[RuleSearchCandidate]:
    candidates: dict[int, RuleSearchCandidate] = {}
    for row in exact_rows:
        candidate = candidates.setdefault(int(row["chunk_id"]), _candidate_from_row(row))
        candidate.exact_score = max(candidate.exact_score, fts_rank_to_score(float(row["rank"])))
        candidate.match_reasons.append("exact")

    for row, semantic_score in semantic_rows:
        candidate = candidates.setdefault(int(row["chunk_id"]), _candidate_from_row(row))
        candidate.semantic_score = max(candidate.semantic_score, semantic_score)
        candidate.match_reasons.append("semantic")

    for candidate in candidates.values():
        _score_rule_candidate(
            candidate,
            scope_tags=scope_tags,
            query_terms=query_terms,
            definition_query=definition_query,
        )
    return sorted(candidates.values(), key=_candidate_sort_key)


def _candidate_from_row(row: sqlite3.Row) -> RuleSearchCandidate:
    section_kind = _row_optional(row, "section_kind")
    retrieval_flags = _json_list(_row_optional(row, "retrieval_flags_json"))
    scope_assertions = _json_assertions(_row_optional(row, "scope_assertions_json"))
    book_scope_tags = _json_list(_row_optional(row, "book_scope_tags_json"))
    scope_tags = _json_list(_row_optional(row, "chunk_scope_tags_json"))
    if not scope_tags:
        scope_tags = book_scope_tags
    scope_fallback_used = not scope_assertions and bool(scope_tags and scope_tags == book_scope_tags)
    if not section_kind or _row_optional(row, "metadata_content_hash") != row["content_hash"]:
        section_kind, retrieval_flags = classify_rule_chunk(
            section_label=row["section_label"],
            content=row["content"],
            word_count=int(row["word_count"]),
            confidence=float(row["confidence"]),
            extraction_method=row["extraction_method"],
        )
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
        section_label=str(row["section_label"]),
        content=str(row["content"]),
        excerpt=str(row["excerpt"]),
        confidence=float(row["confidence"]),
        extraction_method=str(row["extraction_method"]),
        word_count=int(row["word_count"]),
        content_hash=str(row["content_hash"]),
        section_kind=str(section_kind or "unknown"),
        retrieval_flags=retrieval_flags,
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
    embedding_rows = [row for row in rows if full or _embedding_needs_refresh(row, backend)]
    metadata_rows = [row for row in rows if full or _metadata_needs_refresh(row)]

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
            "refreshed_embeddings": len(embedding_rows),
            "refreshed_metadata": len(metadata_rows),
            "full_reindex": full,
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
    needs_repair = (
        summary["missing_embeddings"] > 0
        or summary["stale_embeddings"] > 0
        or summary["missing_metadata"] > 0
        or summary["stale_metadata"] > 0
    )
    summary.update(
        {
            "available": summary["indexed_chunks"] > 0,
            "retrieval_mode": "hybrid" if summary["indexed_chunks"] > 0 else "exact_only",
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
    }


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
            rc.content,
            rc.excerpt,
            rc.word_count,
            rc.confidence,
            rc.extraction_method,
            rc.content_hash,
            e.backend AS embedding_backend,
            e.model AS embedding_model,
            e.dimensions AS embedding_dimensions,
            e.content_hash AS embedding_content_hash,
            m.content_hash AS metadata_content_hash,
            m.section_kind,
            m.retrieval_flags_json
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
    return _row_optional(row, "metadata_content_hash") != row["content_hash"]


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
    section_kind, flags = classify_rule_chunk(
        section_label=section_label,
        content=content,
        word_count=word_count,
        confidence=confidence,
        extraction_method=extraction_method,
    )
    connection.execute(
        """
        INSERT INTO rule_chunk_retrieval_metadata (
            chunk_id, content_hash, section_kind, retrieval_flags_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
            content_hash = excluded.content_hash,
            section_kind = excluded.section_kind,
            retrieval_flags_json = excluded.retrieval_flags_json,
            updated_at = excluded.updated_at
        """,
        (chunk_id, content_hash, section_kind, json.dumps(flags), timestamp_now()),
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
    elif "character sheet" in combined or "relationship map" in combined or "reference sheet" in combined:
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
    if section_kind in {"toc", "index", "sheet"}:
        flags.append("navigational")
    if section_kind == "art":
        flags.append("art_heavy")
    return section_kind, sorted(set(flags))


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


def _looks_art_heavy(content: str, word_count: int) -> bool:
    normalized = "".join(content.split())
    if not normalized:
        return True
    alpha_ratio = sum(1 for char in normalized if char.isalpha()) / len(normalized)
    return word_count < 25 and alpha_ratio < 0.45


def _row_optional(row: sqlite3.Row, key: str) -> Any | None:
    return row[key] if key in row.keys() else None


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
        return f"Run `backet rules index <vault> --book-id {book_id}` to refresh semantic rules retrieval."
    return "Run `backet rules index <vault>` to refresh semantic rules retrieval."


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
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        normalized = normalize_text(text)
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
    return normalized[: limit - 1].rstrip() + "…"


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


def has_tesseract() -> bool:
    return shutil_which("tesseract") is not None


def shutil_which(program: str) -> str | None:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path) / program
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def tesseract_install_hint() -> str:
    if sys.platform == "darwin":
        return "Install Tesseract first, for example with `brew install tesseract`, then rerun the command."
    if sys.platform.startswith("linux"):
        return "Install Tesseract first, for example with `sudo apt-get install tesseract-ocr`, then rerun the command."
    return "Install Tesseract on this machine and rerun the command."


def document_page_count(pdf_path: Path) -> int:
    fitz = _require_pymupdf()
    document = fitz.open(str(pdf_path))
    try:
        return document.page_count
    finally:
        document.close()
