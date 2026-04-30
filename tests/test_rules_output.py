from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

import backet.output
from backet.models import CommandResult
from backet.rules_output import RulesIngestProgressReporter, emit_rules_ingest_report


def test_rules_ingest_report_summarizes_long_page_lists_and_labels_human_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffer = StringIO()
    monkeypatch.setattr(backet.output, "console", Console(file=buffer, force_terminal=False, color_system=None))

    emit_rules_ingest_report(
        CommandResult(
            message="Ingested rulebook PDF",
            created=[".backet/rules/rules.sqlite3"],
            data={
                "vault": "/tmp/vault",
                "rules_db": "/tmp/vault/.backet/rules/rules.sqlite3",
                "book_id": "core-v5",
                "book_title": "Core Rulebook",
                "tier": "core",
                "scope_tags": [],
                "pdf_path": "/tmp/core.pdf",
                "pages_processed": 431,
                "ocr_used_on_pages": list(range(1, 13)),
                "suspect_pages": list(range(20, 33)),
                "chunk_count": 1169,
            },
        )
    )

    output = buffer.getvalue()
    assert "Ingested Core Rulebook" in output
    assert "Pages:   431 processed" in output
    assert "Chunks:  1,169 stored" in output
    assert "OCR:     12 pages required OCR" in output
    assert "Review:  13 pages need review" in output
    assert "Pages requiring OCR: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, +2 more" in output
    assert "Pages needing review: 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, +3 more" in output
    assert "backet rules audit /tmp/vault --book-id core-v5" in output
    assert "ocr_used_on_pages" not in output
    assert "suspect_pages" not in output
    assert "scope_tags" not in output
    assert "[]" not in output


def test_rules_ingest_report_omits_empty_optional_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = StringIO()
    monkeypatch.setattr(backet.output, "console", Console(file=buffer, force_terminal=False, color_system=None))

    emit_rules_ingest_report(
        CommandResult(
            message="Ingested rulebook PDF",
            data={
                "vault": "/tmp/vault",
                "rules_db": "/tmp/vault/.backet/rules/rules.sqlite3",
                "book_id": "core-v5",
                "book_title": "Core Rulebook",
                "tier": "core",
                "scope_tags": [],
                "pdf_path": "/tmp/core.pdf",
                "pages_processed": 2,
                "ocr_used_on_pages": [],
                "suspect_pages": [],
                "chunk_count": 4,
            },
        )
    )

    output = buffer.getvalue()
    assert "Scope:" not in output
    assert "OCR:" not in output
    assert "Review:" not in output
    assert "Pages requiring OCR" not in output
    assert "Review recommended" not in output
    assert "[]" not in output


def test_progress_reporter_uses_plain_lines_for_non_interactive_output() -> None:
    buffer = StringIO()
    reporter = RulesIngestProgressReporter(console=Console(file=buffer, force_terminal=False, color_system=None))

    with reporter:
        reporter(
            _event(
                "start",
                "Starting rulebook ingestion",
                current=0,
                total=2,
                details={
                    "book_id": "core-v5",
                    "book_title": "Core Rulebook",
                    "tier": "core",
                    "pdf_path": "/tmp/core.pdf",
                    "rules_db": "/tmp/vault/.backet/rules/rules.sqlite3",
                    "selected_pages": 2,
                    "page_count": 2,
                },
            )
        )
        reporter(_event("extract", "Extracting pages", current=0, total=2))
        reporter(_event("ocr", "OCR fallback on page 1", current=0, total=2))
        reporter(_event("extract", "Extracted page 2", current=2, total=2, counters={"ocr_pages": 1}))

    output = buffer.getvalue()
    assert "Ingesting Core Rulebook" in output
    assert "[rules ingest] Extracting pages 0/2" in output
    assert "[rules ingest] OCR fallback on page 1 0/2" in output
    assert "[rules ingest] Extracting pages 2/2 (OCR: 1)" in output
    assert "\x1b[" not in output


def _event(
    phase: str,
    message: str,
    *,
    current: int | None = None,
    total: int | None = None,
    counters: dict[str, int] | None = None,
    details: dict[str, object] | None = None,
):
    from backet.rules import RulesIngestProgressEvent

    return RulesIngestProgressEvent(
        phase=phase,
        message=message,
        current=current,
        total=total,
        counters=counters or {},
        details=details or {},
    )
