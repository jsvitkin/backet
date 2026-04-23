from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from backet.embeddings import cosine_similarity, resolve_embedding_backend
from backet.errors import AppError
from backet.indexing import index_vault, inspect_index_state, open_index_connection
from backet.models import CommandResult

SUPPORTED_SCOPES = {"vault", "note", "path", "subtree"}
FTS_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")


@dataclass(slots=True)
class ScopeAnchor:
    scope: str
    target: str
    note_rows: list[sqlite3.Row]

    @property
    def note_ids(self) -> list[int]:
        return [int(row["id"]) for row in self.note_rows]

    @property
    def relative_paths(self) -> list[str]:
        return [str(row["relative_path"]) for row in self.note_rows]


@dataclass(slots=True)
class ScoredChunk:
    chunk_id: int
    score: float
    reasons: list[str]


def build_context_bundle(
    vault_root: Path,
    scope: str,
    target: str,
    query: str | None,
    limit: int,
    refresh: bool,
) -> CommandResult:
    scope_key = scope.strip().lower()
    if scope_key not in SUPPORTED_SCOPES:
        raise AppError(
            code="context_scope_unknown",
            message=f"Unsupported context scope: {scope}",
            hint="Use one of: vault, note, path, subtree.",
            details={"scope": scope},
            exit_code=2,
        )
    if limit <= 0:
        raise AppError(
            code="context_limit_invalid",
            message="Context bundle limits must be positive.",
            hint="Use a limit greater than zero.",
            details={"limit": limit},
            exit_code=2,
        )

    initial_state = inspect_index_state(vault_root)
    refresh_performed = False
    if not initial_state.has_index or initial_state.needs_refresh:
        if refresh:
            index_vault(vault_root)
            refresh_performed = True
        else:
            if not initial_state.has_index:
                raise AppError(
                    code="index_missing",
                    message="Vault retrieval state has not been built yet.",
                    hint="Run `backet index <vault>` or re-run this command with `--refresh`.",
                    details=initial_state.to_dict(),
                    exit_code=2,
                )
            raise AppError(
                code="index_stale",
                message="Vault retrieval state is stale after external note edits.",
                hint="Run `backet index <vault>` or re-run this command with `--refresh`.",
                details=initial_state.to_dict(),
                exit_code=2,
            )

    state = inspect_index_state(vault_root)
    with closing(open_index_connection(vault_root)) as connection:
        anchor = resolve_scope_anchor(connection, scope_key, target)
        selected_chunks = assemble_context_chunks(connection, anchor, query=query, limit=limit)

    sources = [
        {
            "relative_path": chunk["relative_path"],
            "title": chunk["title"],
            "heading_path": chunk["heading_path"],
            "excerpt": chunk["excerpt"],
            "score": round(float(chunk["score"]), 6),
            "match_reasons": chunk["match_reasons"],
        }
        for chunk in selected_chunks
    ]

    return CommandResult(
        message="Assembled vault context bundle",
        data={
            "vault": str(vault_root),
            "scope": scope_key,
            "target": anchor.target,
            "query": query,
            "limit": limit,
            "refresh_performed": refresh_performed,
            "index": state.to_dict(),
            "scope_note_count": len(anchor.note_rows),
            "scope_paths": anchor.relative_paths,
            "sources": sources,
        },
    )


def resolve_scope_anchor(connection: sqlite3.Connection, scope: str, target: str) -> ScopeAnchor:
    normalized_target = normalize_target(target)
    if scope == "vault":
        rows = connection.execute(
            "SELECT * FROM notes ORDER BY top_level, relative_path"
        ).fetchall()
        return ScopeAnchor(scope=scope, target=normalized_target or ".", note_rows=rows)

    if scope == "note":
        rows = _resolve_note_rows(connection, normalized_target)
        return ScopeAnchor(scope=scope, target=normalized_target, note_rows=rows)

    if scope in {"path", "subtree"}:
        rows = _resolve_path_rows(connection, normalized_target)
        return ScopeAnchor(scope=scope, target=normalized_target, note_rows=rows)

    raise AppError(
        code="context_scope_unknown",
        message=f"Unsupported context scope: {scope}",
        hint="Use one of: vault, note, path, subtree.",
        exit_code=2,
    )


def assemble_context_chunks(
    connection: sqlite3.Connection,
    anchor: ScopeAnchor,
    query: str | None,
    limit: int,
) -> list[dict[str, object]]:
    anchor_chunks = _fetch_anchor_chunks(connection, anchor.note_ids)
    if not query:
        if anchor.scope == "vault":
            grouped: dict[str, sqlite3.Row] = {}
            for row in anchor_chunks:
                grouped.setdefault(str(row["top_level"]), row)
            selected_rows = list(grouped.values())[:limit]
        else:
            selected_rows = anchor_chunks[:limit]
        return [_row_to_source(row, score=1.0, reasons=["scope-anchor"]) for row in selected_rows]

    exact_scores = _query_exact_scores(connection, anchor.note_ids, query)
    semantic_scores = _query_semantic_scores(connection, anchor.note_ids, query)
    candidate_ids = set(exact_scores) | set(semantic_scores) | {int(row["chunk_id"]) for row in anchor_chunks}
    if not candidate_ids:
        return [_row_to_source(row, score=1.0, reasons=["scope-anchor"]) for row in anchor_chunks[:limit]]

    rows = _fetch_chunks_by_ids(connection, sorted(candidate_ids))
    scored: list[ScoredChunk] = []
    anchor_note_ids = set(anchor.note_ids)
    anchor_target = anchor.target.casefold()
    query_casefold = query.casefold()

    for row in rows:
        chunk_id = int(row["chunk_id"])
        reasons: list[str] = []
        score = 0.0

        if chunk_id in exact_scores:
            score += exact_scores[chunk_id]
            reasons.append("exact")
        if chunk_id in semantic_scores:
            score += semantic_scores[chunk_id]
            reasons.append("semantic")
        if int(row["note_id"]) in anchor_note_ids:
            score += 0.3
            reasons.append("scope-anchor")
        if anchor.scope in {"path", "subtree"} and anchor_target and row["relative_path"].casefold().startswith(anchor_target):
            score += 0.15
            reasons.append("path-filter")
        if row["title"].casefold() == query_casefold:
            score += 0.25
            reasons.append("title-match")
        if anchor_target and anchor_target in row["relative_path"].casefold():
            score += 0.1
            reasons.append("hierarchy")
        if not reasons:
            reasons.append("scope-anchor")
        scored.append(ScoredChunk(chunk_id=chunk_id, score=score, reasons=sorted(set(reasons))))

    scored.sort(key=lambda item: (-item.score, item.chunk_id))
    selected: list[dict[str, object]] = []
    seen_chunk_ids: set[int] = set()

    scored_by_id = {item.chunk_id: item for item in scored}

    for row in anchor_chunks:
        chunk_id = int(row["chunk_id"])
        anchor_item = scored_by_id.get(chunk_id)
        if anchor_item is not None:
            selected.append(_row_to_source(row, score=anchor_item.score, reasons=anchor_item.reasons))
        else:
            selected.append(_row_to_source(row, score=1.0, reasons=["scope-anchor"]))
        seen_chunk_ids.add(chunk_id)
        if len(selected) >= limit:
            return selected[:limit]

    row_by_chunk_id = {int(row["chunk_id"]): row for row in rows}
    for item in scored:
        if item.chunk_id in seen_chunk_ids:
            continue
        selected.append(_row_to_source(row_by_chunk_id[item.chunk_id], score=item.score, reasons=item.reasons))
        seen_chunk_ids.add(item.chunk_id)
        if len(selected) >= limit:
            break

    return selected[:limit]


def _resolve_note_rows(connection: sqlite3.Connection, target: str) -> list[sqlite3.Row]:
    stem_target = target[:-3] if target.lower().endswith(".md") else target
    candidates = connection.execute(
        """
        SELECT * FROM notes
        WHERE relative_path = ?
           OR lower(title) = lower(?)
           OR lower(stem) = lower(?)
        ORDER BY relative_path
        """,
        (target, target, stem_target),
    ).fetchall()
    if not candidates and not target.endswith(".md"):
        candidates = connection.execute(
            "SELECT * FROM notes WHERE relative_path = ? ORDER BY relative_path",
            (f"{target}.md",),
        ).fetchall()
    if not candidates:
        raise AppError(
            code="context_target_missing",
            message="No indexed note matches the requested context target.",
            hint="Check the note path or title, or run `backet index <vault>` if the vault changed.",
            details={"scope": "note", "target": target},
            exit_code=2,
        )
    if len(candidates) > 1:
        raise AppError(
            code="context_target_ambiguous",
            message="Multiple indexed notes match the requested note target.",
            hint="Use the exact relative note path to disambiguate.",
            details={"scope": "note", "target": target, "matches": [row["relative_path"] for row in candidates]},
            exit_code=2,
        )
    return candidates


def _resolve_path_rows(connection: sqlite3.Connection, target: str) -> list[sqlite3.Row]:
    prefix = target.rstrip("/")
    if prefix in {"", "."}:
        return connection.execute("SELECT * FROM notes ORDER BY relative_path").fetchall()
    rows = connection.execute(
        """
        SELECT * FROM notes
        WHERE relative_path = ?
           OR relative_path LIKE ? ESCAPE '\\'
           OR parent_path = ?
        ORDER BY relative_path
        """,
        (prefix, f"{prefix}/%", prefix),
    ).fetchall()
    if not rows:
        raise AppError(
            code="context_target_missing",
            message="No indexed notes were found for the requested path scope.",
            hint="Check the relative path, or run `backet index <vault>` if the vault changed.",
            details={"scope": "path", "target": target},
            exit_code=2,
        )
    return rows


def _fetch_anchor_chunks(connection: sqlite3.Connection, note_ids: list[int]) -> list[sqlite3.Row]:
    if not note_ids:
        return []
    placeholders = ", ".join("?" for _ in note_ids)
    return connection.execute(
        f"""
        SELECT
            c.id AS chunk_id,
            c.note_id,
            c.heading_path,
            c.excerpt,
            c.content,
            n.relative_path,
            n.title,
            n.top_level
        FROM chunks c
        JOIN notes n ON n.id = c.note_id
        WHERE c.chunk_index = 0 AND c.note_id IN ({placeholders})
        ORDER BY n.top_level, n.relative_path
        """,
        note_ids,
    ).fetchall()


def _query_exact_scores(connection: sqlite3.Connection, note_ids: list[int], query: str) -> dict[int, float]:
    if not note_ids:
        return {}
    fts_query = build_fts_query(query)
    if not fts_query:
        return {}
    placeholders = ", ".join("?" for _ in note_ids)
    rows = connection.execute(
        f"""
        SELECT
            chunk_fts.chunk_id,
            bm25(chunk_fts) AS rank
        FROM chunk_fts
        JOIN chunks c ON c.id = chunk_fts.chunk_id
        WHERE chunk_fts MATCH ? AND c.note_id IN ({placeholders})
        ORDER BY rank
        LIMIT 20
        """,
        [fts_query, *note_ids],
    ).fetchall()
    scores: dict[int, float] = {}
    for row in rows:
        rank = float(row["rank"])
        scores[int(row["chunk_id"])] = fts_rank_to_score(rank)
    return scores


def _query_semantic_scores(connection: sqlite3.Connection, note_ids: list[int], query: str) -> dict[int, float]:
    if not note_ids:
        return {}
    placeholders = ", ".join("?" for _ in note_ids)
    rows = connection.execute(
        f"""
        SELECT
            c.id AS chunk_id,
            c.embedding_json
        FROM chunks c
        WHERE c.note_id IN ({placeholders})
        """,
        note_ids,
    ).fetchall()
    if not rows:
        return {}

    backend = resolve_embedding_backend()
    query_vector = backend.encode_many([query]).vectors[0]
    scored = []
    for row in rows:
        score = cosine_similarity(query_vector, json.loads(row["embedding_json"]))
        scored.append((int(row["chunk_id"]), max(score, 0.0)))

    scored.sort(key=lambda item: (-item[1], item[0]))
    return {chunk_id: score for chunk_id, score in scored[:20] if score > 0}


def _fetch_chunks_by_ids(connection: sqlite3.Connection, chunk_ids: list[int]) -> list[sqlite3.Row]:
    if not chunk_ids:
        return []
    placeholders = ", ".join("?" for _ in chunk_ids)
    return connection.execute(
        f"""
        SELECT
            c.id AS chunk_id,
            c.note_id,
            c.heading_path,
            c.excerpt,
            n.relative_path,
            n.title
        FROM chunks c
        JOIN notes n ON n.id = c.note_id
        WHERE c.id IN ({placeholders})
        """,
        chunk_ids,
    ).fetchall()


def _row_to_source(row: sqlite3.Row, score: float, reasons: list[str]) -> dict[str, object]:
    return {
        "relative_path": row["relative_path"],
        "title": row["title"],
        "heading_path": row["heading_path"],
        "excerpt": row["excerpt"],
        "score": score,
        "match_reasons": sorted(set(reasons)),
    }


def build_fts_query(text: str) -> str:
    terms = [term for term in FTS_TOKEN_PATTERN.findall(text.lower()) if len(term) > 1]
    return " OR ".join(f'"{term}"' for term in terms)


def fts_rank_to_score(rank: float) -> float:
    positive_rank = abs(rank)
    return 1.0 / (1.0 + positive_rank)


def normalize_target(target: str) -> str:
    normalized = target.replace("\\", "/").strip()
    if normalized in {"", "."}:
        return "."
    return normalized.strip("/")
