from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from backet.errors import AppError
from backet.models import CommandResult
from backet.paths import rules_db_path
from backet.vault import ensure_bootstrapped_vault

RULES_SCHEMA_VERSION = 1
DEFAULT_PAGE_MIN_CHARS = 80
DEFAULT_CHUNK_WORDS = 220
SUPPORTED_TIERS = {"core", "supplement"}
SUSPECT_CONFIDENCE_THRESHOLD = 0.7
FTS_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")


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
class BookRegistryEntry:
    book_id: str
    title: str
    pdf_path: str
    tier: str
    scope_tags: list[str]
    page_count: int
    pdf_fingerprint: str


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

    fitz = _require_pymupdf()
    document = fitz.open(str(pdf_path))
    try:
        page_numbers = parse_pages_spec(pages_spec, document.page_count)
        extracted_pages = _extract_pages(document, pdf_path, page_numbers, force_ocr=force_ocr)
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

    pdf_fingerprint = fingerprint_bytes(pdf_path.read_bytes())
    resolved_title = title or pdf_path.stem
    entry = BookRegistryEntry(
        book_id=book_id,
        title=resolved_title,
        pdf_path=str(pdf_path.resolve()),
        tier=normalized_tier,
        scope_tags=normalized_tags,
        page_count=document_page_count(pdf_path),
        pdf_fingerprint=pdf_fingerprint,
    )

    db_created = not rules_db_path(vault_root).exists()
    created: list[str] = []
    if db_created:
        created.append(str(rules_db_path(vault_root).relative_to(vault_root)))

    with closing(open_rules_connection(vault_root)) as connection:
        _upsert_book(connection, entry)
        _replace_pages(connection, entry, extracted_pages, pages_spec=pages_spec)
        audit_summary = _audit_summary(connection, book_id)
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
        rows = _search_rule_chunks(connection, fts_query, book_id=book_id, scope_tags=normalized_tags, limit=max(limit * 4, 12))
        if not rows:
            raise AppError(
                code="rules_query_empty",
                message="No ingested rule chunks matched the requested query.",
                hint="Adjust the query or ingest the relevant rulebook first.",
                details={"query": query, "book_id": book_id, "scope_tags": normalized_tags},
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
            "primary_results": primary,
            "fallback_results": fallback,
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

    return CommandResult(
        message="Audited ingested rulebooks",
        data={
            "vault": str(vault_root),
            "book_id": book_id,
            "books": suspects,
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


def _extract_pages(document, pdf_path: Path, page_numbers: list[int], force_ocr: bool) -> list[ExtractedPage]:
    extracted: list[ExtractedPage] = []
    for page_number in page_numbers:
        page = document.load_page(page_number - 1)
        direct_text = normalize_text(page.get_text("text"))
        direct_result = _build_page_result(page_number, direct_text, extraction_method="direct")
        if force_ocr or direct_result.suspect:
            ocr_text = _ocr_page(page, pdf_path=pdf_path, page_number=page_number)
            ocr_result = _build_page_result(page_number, ocr_text, extraction_method="ocr")
            extracted.append(ocr_result)
            continue
        extracted.append(direct_result)
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
    for page in pages:
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
        for chunk_index, chunk_text in enumerate(split_rule_chunks(page.text), start=1):
            excerpt = summarize_text(chunk_text)
            content_hash = fingerprint_text(chunk_text)
            connection.execute(
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
    for row in chunk_rows:
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
            rc.confidence,
            rc.extraction_method,
            bm25(rule_chunks_fts) AS rank
        FROM rule_chunks_fts
        JOIN rule_chunks rc ON rc.id = rule_chunks_fts.chunk_id
        JOIN books b ON b.book_id = rc.book_id
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
    rows: list[sqlite3.Row],
    scope_tags: list[str],
    explicit_book_id: str | None,
) -> tuple[list[sqlite3.Row], list[sqlite3.Row], dict[str, Any] | None]:
    supplements = [row for row in rows if row["tier"] == "supplement"]
    cores = [row for row in rows if row["tier"] == "core"]
    if explicit_book_id:
        return rows, [], None
    if not supplements:
        return cores, [], None

    by_book: dict[str, list[sqlite3.Row]] = {}
    for row in supplements:
        by_book.setdefault(str(row["book_id"]), []).append(row)

    book_scores = []
    for current_book_id, current_rows in by_book.items():
        best_rank = min(float(row["rank"]) for row in current_rows)
        score = fts_rank_to_score(best_rank)
        row_tags = json.loads(current_rows[0]["book_scope_tags_json"])
        overlap = len(set(row_tags) & set(scope_tags)) if scope_tags else len(row_tags)
        book_scores.append((current_book_id, score, overlap, current_rows))

    book_scores.sort(key=lambda item: (-item[1], -item[2], item[0]))
    primary_book_id, primary_score, _, primary_rows = book_scores[0]
    competing = [
        {
            "book_id": book_id,
            "book_title": rows_for_book[0]["book_title"],
            "score": round(score, 6),
            "scope_tags": json.loads(rows_for_book[0]["book_scope_tags_json"]),
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
                    "book_title": primary_rows[0]["book_title"],
                    "score": round(primary_score, 6),
                    "scope_tags": json.loads(primary_rows[0]["book_scope_tags_json"]),
                },
                *competing,
            ],
        }

    primary = [row for row in supplements if row["book_id"] == primary_book_id]
    fallback = cores
    return primary, fallback, None


def _row_to_rule_result(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "book_id": row["book_id"],
        "book_title": row["book_title"],
        "tier": row["tier"],
        "scope_tags": json.loads(row["book_scope_tags_json"]),
        "page_start": row["page_start"],
        "page_end": row["page_end"],
        "section_label": row["section_label"],
        "excerpt": row["excerpt"],
        "content": row["content"],
        "confidence": row["confidence"],
        "extraction_method": row["extraction_method"],
        "score": round(fts_rank_to_score(float(row["rank"])), 6),
    }


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
