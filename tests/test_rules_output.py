from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

import backet.output
from backet.models import CommandResult
from backet.rules_output import (
    RulesIngestProgressReporter,
    emit_rules_audit_report,
    emit_rules_ingest_report,
    emit_rules_scope_audit_report,
)


def test_rules_ingest_report_summarizes_long_page_lists_and_labels_human_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffer = StringIO()
    monkeypatch.setattr(backet.output, "console", Console(file=buffer, force_terminal=False, color_system=None, width=200))

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
    assert "backet rules audit /tmp/vault" in output
    assert "backet rules audit /tmp/vault --book-id" not in output
    assert "ocr_used_on_pages" not in output
    assert "suspect_pages" not in output
    assert "scope_tags" not in output
    assert "[]" not in output


def test_rules_ingest_report_omits_empty_optional_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = StringIO()
    monkeypatch.setattr(backet.output, "console", Console(file=buffer, force_terminal=False, color_system=None, width=200))

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


def test_rules_ingest_report_summarizes_generated_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = StringIO()
    monkeypatch.setattr(backet.output, "console", Console(file=buffer, force_terminal=False, color_system=None, width=200))

    emit_rules_ingest_report(
        CommandResult(
            message="Ingested rulebook PDF",
            data={
                "vault": "/tmp/vault",
                "rules_db": "/tmp/vault/.backet/rules/rules.sqlite3",
                "book_id": "camarilla-v5",
                "book_title": "Camarilla",
                "tier": "supplement",
                "scope_tags": [],
                "scope_assertions": {
                    "source_scope": ["sect:camarilla"],
                    "applied": 12,
                    "suggested": 1,
                    "review_needed": 1,
                    "notable": [
                        {
                            "pages": "159-168",
                            "tag": "clan:banu-haqim",
                            "role": "mechanical-authority",
                            "status": "applied",
                        }
                    ],
                },
                "pdf_path": "/tmp/camarilla.pdf",
                "pages_processed": 203,
                "ocr_used_on_pages": [],
                "suspect_pages": [],
                "chunk_count": 400,
            },
        )
    )

    output = buffer.getvalue()
    assert "Source scope: sect:camarilla" in output
    assert "Scopes:  12 applied" in output
    assert "Suggest: 1 scope assertions need review" in output
    assert "Scope preview:" in output
    assert "159-168: clan:banu-haqim" in output
    assert "backet rules scope audit /tmp/vault --book-id camarilla-v5" in output


def test_rules_audit_report_groups_human_work_without_raw_diagnostic_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = StringIO()
    monkeypatch.setattr(backet.output, "console", Console(file=buffer, force_terminal=False, color_system=None, width=200))

    emit_rules_audit_report(
        CommandResult(
            message="Audited ingested rulebooks",
            data={
                "vault": "/tmp/vault",
                "maintenance": [
                    {
                        "category": "maintenance",
                        "missing": 2,
                        "stale": 1,
                        "repair_hint": "Run `backet rules index <vault>`.",
                    }
                ],
                "corpus_health": {
                    "action": "reindex",
                    "books": [
                        {
                            "book_id": "cults",
                            "book_title": "Cults",
                            "action": "reindex",
                            "next_command": "backet rules index <vault> --book-id cults --full",
                            "reasons": ["stale_retrieval_index"],
                        }
                    ],
                },
                "books": [
                    {
                        "book_id": "cults",
                        "book_title": "Cults",
                        "tier": "supplement",
                        "page_count": 281,
                        "chunk_count": 952,
                        "ocr_fallback_pages": [1, 2],
                        "source_status": {
                            "status": "available",
                            "message": "The original source PDF is available for targeted repair.",
                        },
                        "review_summary": {
                            "pending_pages": 1,
                            "blocked": 0,
                            "notices": 1,
                            "excluded_chunks": 0,
                        },
                        "review_cards": [
                            {
                                "page_start": 37,
                                "category": "review",
                                "reasons": ["Extraction has very little readable text."],
                                "excerpt": "garbled OCR preview",
                            }
                        ],
                        "notices": [
                            {"page_start": 1, "reason": "Likely art material; review only if this page should answer rules queries."}
                        ],
                    }
                ],
            },
        )
    )

    rendered = buffer.getvalue()
    assert "Rules audit" in rendered
    assert "Maintenance" in rendered
    assert "Corpus health" in rendered
    assert "Overall action: reindex" in rendered
    assert "Cults (cults, supplement)" in rendered
    assert "Review: 1 pending pages" in rendered
    assert "Review queue" not in rendered
    assert "Page 37" not in rendered
    assert "Actions:" not in rendered
    assert "backet rules review" not in rendered
    assert "backet rules replace" not in rendered
    assert "backet rules repair" not in rendered
    assert "suspect_pages" not in rendered
    assert "quality_flags_json" not in rendered
    assert "review_cards" not in rendered


def test_rules_scope_audit_report_summarizes_reviewable_scope_assertions(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = StringIO()
    monkeypatch.setattr(backet.output, "console", Console(file=buffer, force_terminal=False, color_system=None, width=200))

    emit_rules_scope_audit_report(
        CommandResult(
            message="Audited rule scope assertions",
            data={
                "vault": "/tmp/vault",
                "books": [
                    {
                        "book_id": "camarilla-v5",
                        "book_title": "Camarilla",
                        "applied": 10,
                        "suggested": 2,
                        "rejected": 1,
                        "source_scope": ["sect:camarilla"],
                        "notable": [
                            {
                                "pages": "159-168",
                                "tag": "clan:banu-haqim",
                                "role": "mechanical-authority",
                                "status": "suggested",
                            }
                        ],
                    }
                ],
            },
        )
    )

    rendered = buffer.getvalue()
    assert "Rules scope audit" in rendered
    assert "Applied:   10" in rendered
    assert "Suggested: 2" in rendered
    assert "159-168: clan:banu-haqim" in rendered


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
