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

from backet.embeddings import EmbeddingBackend, cosine_similarity, resolve_embedding_backend
from backet.errors import AppError
from backet.models import CommandResult
from backet.paths import rules_db_path
from backet.vault import ensure_bootstrapped_vault

RULES_SCHEMA_VERSION = 2
DEFAULT_PAGE_MIN_CHARS = 80
DEFAULT_CHUNK_WORDS = 220
SUPPORTED_TIERS = {"core", "supplement"}
SUSPECT_CONFIDENCE_THRESHOLD = 0.7
FTS_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")
SEMANTIC_WEIGHT = 0.75
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
    connection.commit()


def ingest_rulebook(
    vault_root: Path,
    pdf_path: Path,
    book_id: str,
    title: str | None,
    tier: str,
    scope_tags: list[str],
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
    normalized_tags = normalize_scope_tags(scope_tags)
    if normalized_tier == "supplement" and not normalized_tags:
        raise AppError(
            code="rules_scope_tags_missing",
            message="Supplement rulebooks need at least one scope tag for precedence handling.",
            hint="Re-run the command with one or more `--scope-tag` values.",
            details={"book_id": book_id},
            exit_code=2,
        )
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
    if limit <= 0:
        raise AppError(
            code="rules_limit_invalid",
            message="Rules query limits must be positive.",
            hint="Use a limit greater than zero.",
            details={"limit": limit},
            exit_code=2,
        )
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
    with closing(open_rules_connection(vault_root)) as connection:
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
        rows = _merge_rule_candidates(exact_rows, semantic.candidates, scope_tags=normalized_tags)
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
    return CommandResult(
        message="Retrieved ingested rule chunks",
        data={
            "vault": str(vault_root),
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
            },
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
            pages = connection.execute(
                """
                SELECT * FROM page_audit
                WHERE book_id = ? AND suspect = 1
                ORDER BY page_number
                """,
                (book["book_id"],),
            ).fetchall()
            suspect_chunks = connection.execute(
                """
                SELECT * FROM rule_chunks
                WHERE book_id = ? AND confidence < ?
                ORDER BY page_start, chunk_index
                """,
                (book["book_id"], SUSPECT_CONFIDENCE_THRESHOLD),
            ).fetchall()
            suspects.append(
                {
                    "book_id": book["book_id"],
                    "book_title": book["book_title"],
                    "tier": book["tier"],
                    "scope_tags": json.loads(book["scope_tags_json"]),
                    "suspect_pages": [
                        {
                            "page_number": page["page_number"],
                            "extraction_method": page["extraction_method"],
                            "confidence": page["confidence"],
                            "quality_flags": json.loads(page["quality_flags_json"]),
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
                            "excerpt": row["excerpt"],
                        }
                        for row in suspect_chunks
                    ],
                }
            )
        semantic_index = _inspect_rule_semantic_index_for_current_backend(connection, book_id=book_id)

    return CommandResult(
        message="Audited ingested rulebooks",
        data={
            "vault": str(vault_root),
            "book_id": book_id,
            "books": suspects,
            "semantic_index": semantic_index,
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
            ocr_text = _ocr_page(page, pdf_path=pdf_path, page_number=page_number)
            ocr_result = _build_page_result(page_number, ocr_text, extraction_method="ocr")
            ocr_pages += 1
            if ocr_result.suspect:
                review_pages += 1
            extracted.append(ocr_result)
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
    confidence = 0.95 if extraction_method == "direct" and not suspect else 0.65 if extraction_method == "ocr" else 0.4
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


def _ocr_page(page, pdf_path: Path, page_number: int) -> str:
    if not has_tesseract():
        raise AppError(
            code="rules_ocr_unavailable",
            message="OCR fallback is required for this PDF, but Tesseract is not available.",
            hint=tesseract_install_hint(),
            details={"pdf_path": str(pdf_path), "page_number": page_number},
            exit_code=2,
        )
    with TemporaryDirectory(prefix="backet-rules-ocr-") as temp_dir:
        image_path = Path(temp_dir) / f"page-{page_number}.png"
        pixmap = page.get_pixmap(dpi=200, alpha=False)
        pixmap.save(str(image_path))
        process = subprocess.run(
            ["tesseract", str(image_path), "stdout", "--psm", "6"],
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            raise AppError(
                code="rules_ocr_failed",
                message="Tesseract failed while OCR-processing the requested rulebook page.",
                hint=tesseract_install_hint(),
                details={"stderr": process.stderr.strip(), "page_number": page_number},
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
            f"DELETE FROM page_audit WHERE book_id = ? AND page_number IN ({placeholders})",
            [entry.book_id, *page_numbers],
        )
        connection.execute(
            f"DELETE FROM rule_chunks WHERE book_id = ? AND page_start IN ({placeholders})",
            [entry.book_id, *page_numbers],
        )
    connection.execute("DELETE FROM rule_chunks_fts WHERE book_id = ?", (entry.book_id,))

    # FTS gets rebuilt for the whole book after inserts to keep it consistent.
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
    chunk_rows = connection.execute(
        """
        SELECT rc.id, rc.book_id, b.book_title, b.tier, rc.scope_tags_json, rc.section_label, rc.content
        FROM rule_chunks rc
        JOIN books b ON b.book_id = rc.book_id
        WHERE rc.book_id = ?
        ORDER BY rc.page_start, rc.chunk_index
        """,
        (entry.book_id,),
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
            bm25(rule_chunks_fts) AS rank
        FROM rule_chunks_fts
        JOIN rule_chunks rc ON rc.id = rule_chunks_fts.chunk_id
        JOIN books b ON b.book_id = rc.book_id
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        WHERE rule_chunks_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (fts_query, limit),
    ).fetchall()
    filtered: list[sqlite3.Row] = []
    for row in rows:
        if book_id and row["book_id"] != book_id:
            continue
        row_tags = json.loads(row["book_scope_tags_json"])
        if row["tier"] == "supplement" and scope_tags and not set(scope_tags).issubset(set(row_tags)):
            continue
        filtered.append(row)
    return filtered


def _apply_precedence(
    rows: list[RuleSearchCandidate],
    scope_tags: list[str],
    explicit_book_id: str | None,
) -> tuple[list[RuleSearchCandidate], list[RuleSearchCandidate], dict[str, Any] | None]:
    rows = sorted(rows, key=_candidate_sort_key)
    supplements = [row for row in rows if row.tier == "supplement"]
    cores = [row for row in rows if row.tier == "core"]
    if explicit_book_id:
        return rows, [], None
    if not supplements:
        return cores, [], None

    by_book: dict[str, list[RuleSearchCandidate]] = {}
    for row in supplements:
        by_book.setdefault(row.book_id, []).append(row)

    book_scores = []
    for current_book_id, current_rows in by_book.items():
        score = max(row.score for row in current_rows)
        row_tags = current_rows[0].book_scope_tags
        overlap = len(set(row_tags) & set(scope_tags)) if scope_tags else len(row_tags)
        book_scores.append((current_book_id, score, overlap, current_rows))

    book_scores.sort(key=lambda item: (-item[1], -item[2], item[0]))
    primary_book_id, primary_score, _, primary_rows = book_scores[0]
    competing = [
        {
            "book_id": book_id,
            "book_title": rows_for_book[0].book_title,
            "score": round(score, 6),
            "scope_tags": rows_for_book[0].book_scope_tags,
        }
        for book_id, score, _, rows_for_book in book_scores[1:]
        if abs(score - primary_score) <= 0.05
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
                    "scope_tags": primary_rows[0].book_scope_tags,
                },
                *competing,
            ],
        }

    primary = [row for row in supplements if row.book_id == primary_book_id]
    fallback = cores
    return primary, fallback, None


def _row_to_rule_result(row: RuleSearchCandidate) -> dict[str, Any]:
    return {
        "book_id": row.book_id,
        "book_title": row.book_title,
        "tier": row.tier,
        "scope_tags": row.book_scope_tags,
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
        "quality_penalty": round(row.quality_penalty, 6),
        "match_reasons": sorted(set(row.match_reasons)),
        "section_kind": row.section_kind,
        "retrieval_flags": row.retrieval_flags,
    }


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
            m.content_hash AS metadata_content_hash
        FROM rule_chunks rc
        JOIN books b ON b.book_id = rc.book_id
        JOIN rule_chunk_embeddings e ON e.chunk_id = rc.id
        LEFT JOIN rule_chunk_retrieval_metadata m ON m.chunk_id = rc.id
        WHERE e.backend = ? AND e.model = ? AND e.content_hash = rc.content_hash
        ORDER BY rc.book_id, rc.page_start, rc.chunk_index
        """,
        (backend.name, backend.model_name),
    ).fetchall()

    filtered: list[sqlite3.Row] = []
    for row in rows:
        if book_id and row["book_id"] != book_id:
            continue
        row_tags = json.loads(row["book_scope_tags_json"])
        if row["tier"] == "supplement" and scope_tags and not set(scope_tags).issubset(set(row_tags)):
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
        _score_rule_candidate(candidate, scope_tags=scope_tags)
    return sorted(candidates.values(), key=_candidate_sort_key)


def _candidate_from_row(row: sqlite3.Row) -> RuleSearchCandidate:
    section_kind = _row_optional(row, "section_kind")
    retrieval_flags = _json_list(_row_optional(row, "retrieval_flags_json"))
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
        book_scope_tags=json.loads(row["book_scope_tags_json"]),
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


def _score_rule_candidate(candidate: RuleSearchCandidate, scope_tags: list[str]) -> None:
    score = candidate.exact_score + (candidate.semantic_score * SEMANTIC_WEIGHT)
    reasons = set(candidate.match_reasons)

    if candidate.section_kind != "unknown" or candidate.retrieval_flags:
        reasons.add("retrieval-metadata")

    if candidate.tier == "supplement":
        reasons.add("supplement-precedence")
        overlap = len(set(candidate.book_scope_tags) & set(scope_tags)) if scope_tags else 0
        if overlap:
            score += SUPPLEMENT_SCOPE_BOOST + (0.03 * overlap)
            reasons.add("scope-tag")
    elif scope_tags:
        reasons.add("core-fallback")

    penalty = _rule_quality_penalty(candidate)
    if penalty > 0:
        reasons.add("quality-penalty")
    candidate.quality_penalty = penalty
    candidate.score = max(score - penalty, 0.0)
    candidate.match_reasons = sorted(reasons)


def _rule_quality_penalty(candidate: RuleSearchCandidate) -> float:
    penalty = NON_ANSWER_SECTION_PENALTIES.get(candidate.section_kind, 0.0)
    for flag in candidate.retrieval_flags:
        penalty += RETRIEVAL_FLAG_PENALTIES.get(flag, 0.0)
    if candidate.confidence < SUSPECT_CONFIDENCE_THRESHOLD:
        penalty += 0.1
    return min(penalty, 0.9)


def _candidate_sort_key(candidate: RuleSearchCandidate) -> tuple[float, int, int]:
    return (-candidate.score, candidate.page_start, candidate.chunk_id)


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
    terms = [term for term in FTS_TOKEN_PATTERN.findall(text.lower()) if len(term) > 1]
    return " OR ".join(f'"{term}"' for term in terms)


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
    normalized = []
    for tag in scope_tags:
        current = tag.strip().lower()
        if not current:
            continue
        if current not in normalized:
            normalized.append(current)
    return normalized


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
    return 1.0 / (1.0 + positive_rank)


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
