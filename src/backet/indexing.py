from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backet.embeddings import EmbeddingResult, resolve_embedding_backend
from backet.errors import AppError
from backet.index_ignore import IndexIgnorePolicy, load_index_ignore_policy
from backet.models import CommandResult
from backet.paths import index_db_path
from backet.vault import ensure_bootstrapped_vault

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
FRONTMATTER_DELIMITER = "---"
MAX_CHUNK_WORDS = 180
INDEX_SCHEMA_VERSION = 1


@dataclass(slots=True)
class ParsedChunk:
    chunk_index: int
    heading_path: str
    heading_level: int
    content: str
    excerpt: str
    word_count: int


@dataclass(slots=True)
class ParsedNote:
    relative_path: str
    title: str
    stem: str
    top_level: str
    parent_path: str
    content_hash: str
    modified_at: float
    size: int
    preview: str
    chunks: list[ParsedChunk]


@dataclass(slots=True)
class IndexState:
    has_index: bool
    needs_refresh: bool
    added_paths: list[str]
    changed_paths: list[str]
    deleted_paths: list[str]
    total_notes: int
    indexed_notes: int
    index_path: str
    last_indexed_at: str | None = None
    embedding_backend: str | None = None
    embedding_model: str | None = None
    index_ignore_path: str | None = None
    index_ignore_exists: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "has_index": self.has_index,
            "needs_refresh": self.needs_refresh,
            "added_paths": self.added_paths,
            "changed_paths": self.changed_paths,
            "deleted_paths": self.deleted_paths,
            "total_notes": self.total_notes,
            "indexed_notes": self.indexed_notes,
            "index_path": self.index_path,
            "last_indexed_at": self.last_indexed_at,
            "embedding_backend": self.embedding_backend,
            "embedding_model": self.embedding_model,
            "index_ignore_path": self.index_ignore_path,
            "index_ignore_exists": self.index_ignore_exists,
        }


def open_index_connection(vault_root: Path) -> sqlite3.Connection:
    ensure_bootstrapped_vault(vault_root)
    db_path = index_db_path(vault_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    ensure_index_schema(connection)
    return connection


def ensure_index_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY,
            relative_path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            stem TEXT NOT NULL,
            top_level TEXT NOT NULL,
            parent_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            modified_at REAL NOT NULL,
            size INTEGER NOT NULL,
            preview TEXT NOT NULL,
            chunk_count INTEGER NOT NULL,
            indexed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            heading_path TEXT NOT NULL,
            heading_level INTEGER NOT NULL,
            content TEXT NOT NULL,
            excerpt TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            embedding_json TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            UNIQUE(note_id, chunk_index)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
            chunk_id UNINDEXED,
            note_id UNINDEXED,
            title,
            relative_path,
            heading_path,
            content
        );

        CREATE TABLE IF NOT EXISTS index_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS index_runs (
            id INTEGER PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            notes_scanned INTEGER NOT NULL,
            notes_changed INTEGER NOT NULL,
            notes_deleted INTEGER NOT NULL,
            total_notes INTEGER NOT NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO index_meta (key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(INDEX_SCHEMA_VERSION),),
    )
    connection.commit()


def inspect_index_state(vault_root: Path) -> IndexState:
    ensure_bootstrapped_vault(vault_root)
    ignore_policy = load_index_ignore_policy(vault_root)
    current_notes = _scan_markdown_notes(vault_root, ignore_policy=ignore_policy)
    db_path = index_db_path(vault_root)
    if not db_path.exists():
        return IndexState(
            has_index=False,
            needs_refresh=bool(current_notes),
            added_paths=sorted(current_notes),
            changed_paths=[],
            deleted_paths=[],
            total_notes=len(current_notes),
            indexed_notes=0,
            index_path=str(db_path),
            index_ignore_path=str(ignore_policy.path),
            index_ignore_exists=ignore_policy.exists,
        )

    with closing(open_index_connection(vault_root)) as connection:
        stored_notes = {
            row["relative_path"]: row["content_hash"]
            for row in connection.execute("SELECT relative_path, content_hash FROM notes")
        }
        meta = _read_index_meta(connection)

    added_paths = sorted(path for path in current_notes if path not in stored_notes)
    deleted_paths = sorted(path for path in stored_notes if path not in current_notes)
    changed_paths = sorted(
        path for path, fingerprint in current_notes.items() if path in stored_notes and fingerprint != stored_notes[path]
    )

    return IndexState(
        has_index=True,
        needs_refresh=bool(added_paths or deleted_paths or changed_paths),
        added_paths=added_paths,
        changed_paths=changed_paths,
        deleted_paths=deleted_paths,
        total_notes=len(current_notes),
        indexed_notes=len(stored_notes),
        index_path=str(db_path),
        last_indexed_at=meta.get("last_indexed_at"),
        embedding_backend=meta.get("embedding_backend"),
        embedding_model=meta.get("embedding_model"),
        index_ignore_path=str(ignore_policy.path),
        index_ignore_exists=ignore_policy.exists,
    )


def index_vault(vault_root: Path, full: bool = False) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    state = inspect_index_state(vault_root)
    started_at = timestamp_now()
    backend = resolve_embedding_backend()
    created: list[str] = []

    db_path = index_db_path(vault_root)
    if not db_path.exists():
        created.append(str(db_path.relative_to(vault_root)))

    current_files = _scan_markdown_files(vault_root)
    if full:
        added_paths = sorted(current_files)
        changed_paths = []
        deleted_paths = state.deleted_paths
    else:
        added_paths = state.added_paths
        changed_paths = state.changed_paths
        deleted_paths = state.deleted_paths

    notes_to_process = sorted(set(added_paths + changed_paths))
    changed_count = len(notes_to_process)

    with closing(open_index_connection(vault_root)) as connection:
        for relative_path in deleted_paths:
            _delete_note(connection, relative_path)

        if notes_to_process:
            parsed_notes = [_parse_markdown_file(vault_root, current_files[path]) for path in notes_to_process]
            embeddings = _embed_parsed_notes(parsed_notes, backend)
            for parsed_note, embedding_result in zip(parsed_notes, embeddings, strict=False):
                _upsert_note(connection, parsed_note, embedding_result, timestamp_now())

        completed_at = timestamp_now()
        _write_index_meta(
            connection,
            {
                "last_indexed_at": completed_at,
                "embedding_backend": backend.name,
                "embedding_model": backend.model_name,
            },
        )
        connection.execute(
            """
            INSERT INTO index_runs (
                started_at, completed_at, notes_scanned, notes_changed, notes_deleted, total_notes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                started_at,
                completed_at,
                len(current_files),
                changed_count,
                len(deleted_paths),
                len(current_files),
            ),
        )
        connection.commit()

    if not notes_to_process and not deleted_paths and state.has_index and not full:
        return CommandResult(
            message="Vault index is already up to date",
            created=created,
            data={
                "vault": str(vault_root),
                "index_path": str(db_path),
                "notes_scanned": len(current_files),
                "notes_changed": 0,
                "notes_deleted": 0,
                "embedding_backend": backend.name,
                "embedding_model": backend.model_name,
                "last_indexed_at": state.last_indexed_at,
                "index_ignore_path": state.index_ignore_path,
                "index_ignore_exists": state.index_ignore_exists,
            },
        )

    return CommandResult(
        message="Indexed vault Markdown content",
        created=created,
        data={
            "vault": str(vault_root),
            "index_path": str(db_path),
            "notes_scanned": len(current_files),
            "notes_changed": changed_count,
            "notes_deleted": len(deleted_paths),
            "embedding_backend": backend.name,
            "embedding_model": backend.model_name,
            "index_ignore_path": state.index_ignore_path,
            "index_ignore_exists": state.index_ignore_exists,
            "full_reindex": full,
        },
    )


def require_current_index(vault_root: Path, refresh: bool = False) -> IndexState:
    state = inspect_index_state(vault_root)
    if not state.has_index:
        if refresh:
            index_vault(vault_root)
            return inspect_index_state(vault_root)
        raise AppError(
            code="index_missing",
            message="Vault retrieval state has not been built yet.",
            hint="Run `backet index <vault>` or re-run this command with `--refresh`.",
            details={"vault": str(vault_root), "index_path": state.index_path},
            exit_code=2,
        )

    if state.needs_refresh:
        if refresh:
            index_vault(vault_root)
            return inspect_index_state(vault_root)
        raise AppError(
            code="index_stale",
            message="Vault retrieval state is stale after external note edits.",
            hint="Run `backet index <vault>` or re-run this command with `--refresh`.",
            details=state.to_dict(),
            exit_code=2,
        )

    return state


def _scan_markdown_notes(vault_root: Path, ignore_policy: IndexIgnorePolicy | None = None) -> dict[str, str]:
    notes: dict[str, str] = {}
    for relative_path, absolute_path in _scan_markdown_files(vault_root, ignore_policy=ignore_policy).items():
        text = absolute_path.read_text(encoding="utf-8")
        notes[relative_path] = fingerprint_text(_strip_frontmatter(text))
    return notes


def _scan_markdown_files(vault_root: Path, ignore_policy: IndexIgnorePolicy | None = None) -> dict[str, Path]:
    policy = ignore_policy or load_index_ignore_policy(vault_root)
    notes: dict[str, Path] = {}
    for path in sorted(vault_root.rglob("*.md")):
        relative_path = path.relative_to(vault_root).as_posix()
        if policy.ignores(relative_path):
            continue
        notes[relative_path] = path
    return notes


def _parse_markdown_file(vault_root: Path, path: Path) -> ParsedNote:
    text = path.read_text(encoding="utf-8")
    stripped_text = _strip_frontmatter(text)
    title, chunks = _parse_markdown_chunks(path.stem, stripped_text)
    relative_path = path.relative_to(vault_root).as_posix()
    parent_path = path.relative_to(vault_root).parent.as_posix()
    if parent_path == ".":
        parent_path = ""
    top_level = relative_path.split("/", 1)[0]
    preview = chunks[0].excerpt if chunks else ""
    stat = path.stat()
    return ParsedNote(
        relative_path=relative_path,
        title=title,
        stem=path.stem,
        top_level=top_level,
        parent_path=parent_path,
        content_hash=fingerprint_text(stripped_text),
        modified_at=stat.st_mtime,
        size=stat.st_size,
        preview=preview,
        chunks=chunks,
    )


def _parse_markdown_chunks(stem: str, text: str) -> tuple[str, list[ParsedChunk]]:
    lines = text.splitlines()
    title = stem
    first_heading_found = False
    chunks: list[ParsedChunk] = []
    current_heading = stem
    current_heading_level = 0
    current_stack: list[str] = []
    buffer: list[str] = []
    chunk_index = 0

    def flush() -> None:
        nonlocal chunk_index
        raw_text = "\n".join(buffer).strip()
        if not raw_text:
            return
        for part in _split_section(raw_text):
            excerpt = summarize_excerpt(part)
            chunks.append(
                ParsedChunk(
                    chunk_index=chunk_index,
                    heading_path=current_heading,
                    heading_level=current_heading_level,
                    content=part,
                    excerpt=excerpt,
                    word_count=word_count(part),
                )
            )
            chunk_index += 1

    for line in lines:
        match = HEADING_PATTERN.match(line)
        if match:
            flush()
            buffer = []
            heading_level = len(match.group(1))
            heading_text = match.group(2).strip()
            if not first_heading_found and heading_level == 1:
                title = heading_text
                first_heading_found = True
            current_stack = current_stack[: max(heading_level - 1, 0)]
            current_stack.append(heading_text)
            current_heading = " > ".join(current_stack)
            current_heading_level = heading_level
            continue
        buffer.append(line)

    flush()
    if not chunks and text.strip():
        body = text.strip()
        chunks.append(
            ParsedChunk(
                chunk_index=0,
                heading_path=title,
                heading_level=0,
                content=body,
                excerpt=summarize_excerpt(body),
                word_count=word_count(body),
            )
        )
    return title, chunks


def _split_section(text: str) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current_lines: list[str] = []
    current_words = 0
    for paragraph in paragraphs:
        paragraph_words = word_count(paragraph)
        if paragraph_words > MAX_CHUNK_WORDS:
            if current_lines:
                chunks.append("\n\n".join(current_lines).strip())
                current_lines = []
                current_words = 0
            words = paragraph.split()
            for start in range(0, len(words), MAX_CHUNK_WORDS):
                chunks.append(" ".join(words[start : start + MAX_CHUNK_WORDS]).strip())
            continue
        if current_lines and current_words + paragraph_words > MAX_CHUNK_WORDS:
            chunks.append("\n\n".join(current_lines).strip())
            current_lines = []
            current_words = 0
        current_lines.append(paragraph)
        current_words += paragraph_words

    if current_lines:
        chunks.append("\n\n".join(current_lines).strip())

    return [chunk for chunk in chunks if chunk]


def _strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != FRONTMATTER_DELIMITER:
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            return "\n".join(lines[index + 1 :]).lstrip()
    return text


def _embed_parsed_notes(parsed_notes: list[ParsedNote], backend) -> list[EmbeddingResult]:
    results: list[EmbeddingResult] = []
    for parsed_note in parsed_notes:
        chunk_texts = [chunk.content for chunk in parsed_note.chunks]
        if not chunk_texts:
            results.append(EmbeddingResult(backend_name=backend.name, model_name=backend.model_name, vectors=[]))
            continue
        results.append(backend.encode_many(chunk_texts))
    return results


def _upsert_note(
    connection: sqlite3.Connection,
    parsed_note: ParsedNote,
    embedding_result: EmbeddingResult,
    indexed_at: str,
) -> None:
    existing_row = connection.execute(
        "SELECT id FROM notes WHERE relative_path = ?",
        (parsed_note.relative_path,),
    ).fetchone()
    if existing_row is not None:
        _delete_chunks_for_note(connection, existing_row["id"])

    connection.execute(
        """
        INSERT INTO notes (
            relative_path, title, stem, top_level, parent_path, content_hash, modified_at, size, preview, chunk_count, indexed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(relative_path) DO UPDATE SET
            title = excluded.title,
            stem = excluded.stem,
            top_level = excluded.top_level,
            parent_path = excluded.parent_path,
            content_hash = excluded.content_hash,
            modified_at = excluded.modified_at,
            size = excluded.size,
            preview = excluded.preview,
            chunk_count = excluded.chunk_count,
            indexed_at = excluded.indexed_at
        """,
        (
            parsed_note.relative_path,
            parsed_note.title,
            parsed_note.stem,
            parsed_note.top_level,
            parsed_note.parent_path,
            parsed_note.content_hash,
            parsed_note.modified_at,
            parsed_note.size,
            parsed_note.preview,
            len(parsed_note.chunks),
            indexed_at,
        ),
    )
    note_row = connection.execute(
        "SELECT id FROM notes WHERE relative_path = ?",
        (parsed_note.relative_path,),
    ).fetchone()
    if note_row is None:
        raise AppError(
            code="index_write_failed",
            message=f"Could not persist indexed note metadata for {parsed_note.relative_path}.",
            hint="Retry the indexing command.",
            details={"relative_path": parsed_note.relative_path},
            exit_code=1,
        )

    note_id = note_row["id"]
    for chunk, vector in zip(parsed_note.chunks, embedding_result.vectors, strict=False):
        chunk_cursor = connection.execute(
            """
            INSERT INTO chunks (
                note_id, chunk_index, heading_path, heading_level, content, excerpt, word_count, embedding_json, indexed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note_id,
                chunk.chunk_index,
                chunk.heading_path,
                chunk.heading_level,
                chunk.content,
                chunk.excerpt,
                chunk.word_count,
                json.dumps(vector),
                indexed_at,
            ),
        )
        chunk_id = chunk_cursor.lastrowid
        connection.execute(
            """
            INSERT INTO chunk_fts (chunk_id, note_id, title, relative_path, heading_path, content)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                note_id,
                parsed_note.title,
                parsed_note.relative_path,
                chunk.heading_path,
                chunk.content,
            ),
        )


def _delete_note(connection: sqlite3.Connection, relative_path: str) -> None:
    row = connection.execute("SELECT id FROM notes WHERE relative_path = ?", (relative_path,)).fetchone()
    if row is None:
        return
    _delete_chunks_for_note(connection, row["id"])
    connection.execute("DELETE FROM notes WHERE id = ?", (row["id"],))


def _delete_chunks_for_note(connection: sqlite3.Connection, note_id: int) -> None:
    chunk_ids = [row["id"] for row in connection.execute("SELECT id FROM chunks WHERE note_id = ?", (note_id,))]
    if chunk_ids:
        placeholders = ", ".join("?" for _ in chunk_ids)
        connection.execute(f"DELETE FROM chunk_fts WHERE chunk_id IN ({placeholders})", chunk_ids)
    connection.execute("DELETE FROM chunks WHERE note_id = ?", (note_id,))


def _read_index_meta(connection: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM index_meta")}


def _write_index_meta(connection: sqlite3.Connection, values: dict[str, str]) -> None:
    for key, value in values.items():
        connection.execute(
            """
            INSERT INTO index_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def fingerprint_file(path: Path) -> str:
    return fingerprint_text(path.read_text(encoding="utf-8"))


def fingerprint_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def summarize_excerpt(text: str, limit: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def timestamp_now() -> str:
    return datetime.now(UTC).isoformat()


def word_count(text: str) -> int:
    return len(text.split())
