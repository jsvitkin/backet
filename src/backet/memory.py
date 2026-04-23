from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

from backet.errors import AppError
from backet.indexing import index_vault, inspect_index_state, open_index_connection, timestamp_now
from backet.models import CommandResult
from backet.paths import memory_dir

SUPPORTED_MEMORY_FAMILIES = {"all", "city", "subtree"}
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def build_memory_capsules(vault_root: Path, family: str = "all", refresh: bool = False) -> CommandResult:
    family_key = family.strip().lower()
    if family_key not in SUPPORTED_MEMORY_FAMILIES:
        raise AppError(
            code="memory_family_unknown",
            message=f"Unsupported memory family: {family}",
            hint="Use one of: all, city, subtree.",
            details={"family": family},
            exit_code=2,
        )

    state = inspect_index_state(vault_root)
    if not state.has_index or state.needs_refresh:
        if refresh:
            index_vault(vault_root)
            state = inspect_index_state(vault_root)
        else:
            raise AppError(
                code="memory_index_unavailable",
                message="Derived memory needs a current vault index before it can be rebuilt.",
                hint="Run `backet index <vault>` or re-run this command with `--refresh`.",
                details=state.to_dict(),
                exit_code=2,
            )

    memory_root = memory_dir(vault_root)
    memory_root.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    with closing(open_index_connection(vault_root)) as connection:
        note_rows = connection.execute(
            "SELECT title, relative_path, top_level, preview FROM notes ORDER BY top_level, relative_path"
        ).fetchall()
        if family_key in {"all", "city"}:
            created.extend(_write_city_capsule(memory_root, note_rows, vault_root))
        if family_key in {"all", "subtree"}:
            created.extend(_write_subtree_capsules(memory_root, note_rows, vault_root))

    return CommandResult(
        message="Rebuilt derived memory capsules",
        created=created,
        data={
            "vault": str(vault_root),
            "memory_root": str(memory_root),
            "families_built": family_key,
            "capsules_written": len(created),
            "indexed_notes": state.indexed_notes,
        },
    )


def _write_city_capsule(memory_root: Path, note_rows: list[sqlite3.Row], vault_root: Path) -> list[str]:
    capsule_path = memory_root / "city" / "overview.md"
    capsule_path.parent.mkdir(parents=True, exist_ok=True)

    top_levels: dict[str, list[sqlite3.Row]] = {}
    for row in note_rows:
        top_levels.setdefault(str(row["top_level"]), []).append(row)

    lines = [
        "# City Overview Memory",
        "",
        f"- Generated: {timestamp_now()}",
        f"- Scope: vault",
        f"- Indexed notes: {len(note_rows)}",
        "",
        "## Top-Level Groups",
    ]
    for top_level, rows in top_levels.items():
        lines.append(f"- `{top_level}`: {len(rows)} notes")

    lines.extend(
        [
            "",
            "## Highlighted Notes",
        ]
    )
    for row in note_rows[: min(len(note_rows), 8)]:
        lines.extend(
            [
                f"### {row['title']}",
                f"Source: `{row['relative_path']}`",
                row["preview"] or "No preview available.",
                "",
            ]
        )

    lines.extend(
        [
            "## Source References",
            *_source_reference_lines(note_rows),
            "",
        ]
    )
    capsule_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return [str(capsule_path.relative_to(vault_root))]


def _write_subtree_capsules(memory_root: Path, note_rows: list[sqlite3.Row], vault_root: Path) -> list[str]:
    created: list[str] = []
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in note_rows:
        grouped.setdefault(str(row["top_level"]), []).append(row)

    subtree_root = memory_root / "subtrees"
    subtree_root.mkdir(parents=True, exist_ok=True)

    for top_level, rows in grouped.items():
        capsule_path = subtree_root / f"{slugify(top_level)}.md"
        lines = [
            f"# Subtree Memory: {top_level}",
            "",
            f"- Generated: {timestamp_now()}",
            f"- Scope: subtree",
            f"- Target: `{top_level}`",
            f"- Indexed notes: {len(rows)}",
            "",
            "## Notes",
        ]
        for row in rows:
            lines.append(f"- {row['title']} — `{row['relative_path']}`")

        lines.extend(
            [
                "",
                "## Excerpts",
            ]
        )
        for row in rows[: min(len(rows), 8)]:
            lines.extend(
                [
                    f"### {row['title']}",
                    row["preview"] or "No preview available.",
                    "",
                ]
            )

        lines.extend(
            [
                "## Source References",
                *_source_reference_lines(rows),
                "",
            ]
        )
        capsule_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        created.append(str(capsule_path.relative_to(vault_root)))

    return created


def _source_reference_lines(note_rows: list[sqlite3.Row]) -> list[str]:
    return [f"- `{row['relative_path']}` ({row['title']})" for row in note_rows]


def slugify(value: str) -> str:
    lowered = value.lower()
    slug = SLUG_PATTERN.sub("-", lowered).strip("-")
    return slug or "subtree"
