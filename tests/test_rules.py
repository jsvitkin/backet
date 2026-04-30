from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

import fitz
import pytest

from backet.cli import app
from backet.errors import AppError
from backet.rules import ingest_rulebook, normalize_scope_tags, open_rules_connection, parse_pages_spec, split_rule_chunks


def test_parse_pages_spec_and_scope_tag_normalization() -> None:
    assert parse_pages_spec("1-3,5", 7) == [1, 2, 3, 5]
    assert normalize_scope_tags([" Camarilla ", "camarilla", " Discipline "]) == ["camarilla", "discipline"]
    with pytest.raises(AppError, match="whole page numbers"):
        parse_pages_spec("1-a", 7)


def test_split_rule_chunks_preserves_paragraph_boundaries() -> None:
    text = "\n\n".join(f"Paragraph {index} " + ("word " * 70) for index in range(1, 6))

    chunks = split_rule_chunks(text)

    assert len(chunks) >= 2
    assert chunks[0].startswith("Paragraph 1")


def test_rules_ingest_clean_pdf_and_query_metadata(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "core-rulebook.pdf",
        [
            _rule_page(
                "Feeding Rights",
                "Blood dolls suffer addiction and emotional dependence after repeated feeding. Repeated access to vitae can create an uneven bond, strained consent, and visible social fallout inside a domain.",
            ),
            _rule_page(
                "Elysium Etiquette",
                "Court etiquette enforces strict behavior in front of the Prince. Even minor breaches of protocol can trigger public punishment, political humiliation, or feeding restrictions inside Elysium.",
            ),
        ],
    )

    ingest_result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "ingest",
            str(vault),
            str(pdf_path),
            "--book-id",
            "core-v5",
            "--title",
            "Core Rulebook",
            "--tier",
            "core",
        ],
    )

    assert ingest_result.exit_code == 0
    assert "Ingesting Core Rulebook" not in ingest_result.stdout
    assert "[rules ingest]" not in ingest_result.stdout
    ingest_payload = json.loads(ingest_result.stdout)
    assert ingest_payload["data"]["book_id"] == "core-v5"
    assert ingest_payload["data"]["ocr_used_on_pages"] == []

    query_result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "blood doll addiction", "--limit", "3"],
    )
    assert query_result.exit_code == 0
    query_payload = json.loads(query_result.stdout)
    assert query_payload["data"]["primary_results"][0]["book_id"] == "core-v5"
    assert query_payload["data"]["primary_results"][0]["page_start"] == 1

    with closing(open_rules_connection(vault)) as connection:
        row = connection.execute("SELECT * FROM rule_chunks WHERE book_id = 'core-v5'").fetchone()

    assert row is not None
    assert row["section_label"] == "Feeding Rights"


def test_rules_ingest_uses_ocr_fallback_for_image_only_pdf(
    runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_image_only_pdf(
        tmp_path / "ocr-only.pdf",
        "Blood dolls are often controlled through coercion and secrecy.",
    )
    monkeypatch.setattr(
        "backet.rules._ocr_page",
        lambda page, pdf_path, page_number: "Blood dolls are often controlled through coercion and secrecy.",
    )

    result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "ingest",
            str(vault),
            str(pdf_path),
            "--book-id",
            "camarilla-guide",
            "--title",
            "Camarilla Guide",
            "--tier",
            "supplement",
            "--scope-tag",
            "camarilla",
        ],
    )

    assert result.exit_code == 0
    assert "Ingesting Camarilla Guide" not in result.stdout
    assert "[rules ingest]" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["data"]["ocr_used_on_pages"] == [1]


def test_rules_ingest_emits_progress_events(runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "progress.pdf",
        [
            _rule_page("First Page", "Direct text exists but OCR is forced for progress coverage."),
            _rule_page("Second Page", "This page will become suspect after OCR."),
        ],
    )
    monkeypatch.setattr(
        "backet.rules._ocr_page",
        lambda page, pdf_path, page_number: (
            "Readable OCR text with enough words and letters to pass the confidence checks. " * 3
            if page_number == 1
            else "bad"
        ),
    )
    events = []

    result = ingest_rulebook(
        vault_root=vault,
        pdf_path=pdf_path,
        book_id="progress-book",
        title="Progress Book",
        tier="core",
        scope_tags=[],
        force_ocr=True,
        progress=events.append,
    )

    phases = [event.phase for event in events]
    assert result.data["ocr_used_on_pages"] == [1, 2]
    assert phases[0] == "inspect"
    assert "start" in phases
    assert "fingerprint" in phases
    assert "store" in phases
    assert "index" in phases
    assert "audit" in phases
    assert any(event.phase == "ocr" and event.details["page_number"] == 1 for event in events)
    assert any(event.phase == "ocr" and event.details["page_number"] == 2 for event in events)

    extraction_complete = [event for event in events if event.phase == "extract" and event.current == 2][-1]
    assert extraction_complete.total == 2
    assert extraction_complete.counters["ocr_pages"] == 2
    assert extraction_complete.counters["review_pages"] == 1

    store_complete = [event for event in events if event.phase == "store" and event.current == 2][-1]
    assert store_complete.counters["chunks"] >= 1
    assert any(event.phase == "index" and event.current == event.total for event in events)
    assert any(event.phase == "audit" and event.current == 1 for event in events)


def test_rules_ingest_human_output_shows_progress_and_friendly_report(
    runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "human-progress.pdf",
        [
            _rule_page("First Page", "Direct text exists but OCR is forced."),
            _rule_page("Second Page", "This page will become suspect after OCR."),
        ],
    )
    monkeypatch.setattr(
        "backet.rules._ocr_page",
        lambda page, pdf_path, page_number: (
            "Readable OCR text with enough words and letters to pass the confidence checks. " * 3
            if page_number == 1
            else "bad"
        ),
    )

    result = runner.invoke(
        app,
        [
            "rules",
            "ingest",
            str(vault),
            str(pdf_path),
            "--book-id",
            "human-progress",
            "--title",
            "Human Progress",
            "--tier",
            "core",
            "--force-ocr",
        ],
    )

    assert result.exit_code == 0
    combined_output = result.stdout + getattr(result, "stderr", "")
    assert "Ingesting Human Progress" in combined_output
    assert "[rules ingest] Extracting pages" in combined_output
    assert "OCR fallback on page 1" in combined_output
    assert "Ingested Human Progress" in combined_output
    assert "OCR:     2 pages required OCR" in combined_output
    assert "Review:  1 page needs review" in combined_output
    assert "Pages requiring OCR: 1, 2" in combined_output
    assert "Review recommended" in combined_output
    assert "backet rules audit" in combined_output
    assert "ocr_used_on_pages" not in combined_output
    assert "suspect_pages" not in combined_output
    assert "\x1b[" not in combined_output


def test_rules_query_applies_supplement_precedence_and_core_fallback(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    core_pdf = _create_text_pdf(
        tmp_path / "core.pdf",
        [
            _rule_page(
                "Feeding Rights",
                "Core rules describe feeding rights in broad strokes. Domains may set customs, but the baseline text stays general and leaves room for local enforcement.",
            )
        ],
    )
    supplement_pdf = _create_text_pdf(
        tmp_path / "camarilla.pdf",
        [
            _rule_page(
                "Feeding Rights",
                "Camarilla domains restrict blood doll feeding through formal permission. Feeding access is treated as a privilege that must be granted and monitored by the local court.",
            )
        ],
    )
    _ingest_book(runner, vault, core_pdf, "core-v5", "Core Rulebook", "core")
    _ingest_book(runner, vault, supplement_pdf, "camarilla", "Camarilla", "supplement", ["camarilla"])

    result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "query",
            str(vault),
            "feeding rights blood doll permission",
            "--scope-tag",
            "camarilla",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["primary_results"][0]["book_id"] == "camarilla"
    assert payload["data"]["fallback_results"][0]["book_id"] == "core-v5"


def test_rules_query_surfaces_ambiguous_specific_sources(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    first_pdf = _create_text_pdf(
        tmp_path / "camarilla-a.pdf",
        [
            _rule_page(
                "Feeding Rights",
                "The Camarilla forbids feeding from blood dolls without approval. Permission must be explicit, public enough to verify, and revocable by local authority.",
            )
        ],
    )
    second_pdf = _create_text_pdf(
        tmp_path / "camarilla-b.pdf",
        [
            _rule_page(
                "Feeding Rights",
                "The Camarilla requires formal approval before blood doll feeding. Local officers maintain records and may punish any unlicensed access to blood dolls.",
            )
        ],
    )
    _ingest_book(runner, vault, first_pdf, "camarilla-a", "Camarilla A", "supplement", ["camarilla"])
    _ingest_book(runner, vault, second_pdf, "camarilla-b", "Camarilla B", "supplement", ["camarilla"])

    result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "query",
            str(vault),
            "camarilla blood doll approval feeding",
            "--scope-tag",
            "camarilla",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "rules_query_ambiguous"
    assert len(payload["error"]["details"]["conflicting_books"]) == 2


def test_rules_audit_and_targeted_repair(runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_image_only_pdf(
        tmp_path / "repair.pdf",
        "The first scan is unreadable without proper OCR repair.",
    )
    monkeypatch.setattr("backet.rules._ocr_page", lambda page, pdf_path, page_number: "bad")
    _ingest_book(runner, vault, pdf_path, "ocr-book", "OCR Book", "supplement", ["ritual"])

    audit_result = runner.invoke(app, ["--json", "rules", "audit", str(vault), "--book-id", "ocr-book"])
    assert audit_result.exit_code == 0
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["data"]["books"][0]["suspect_pages"][0]["page_number"] == 1

    monkeypatch.setattr(
        "backet.rules._ocr_page",
        lambda page, pdf_path, page_number: "Proper OCR repair restored the ritual text and page clarity.",
    )
    repair_result = runner.invoke(
        app,
        ["--json", "rules", "repair", str(vault), "ocr-book", "--pages", "1", "--force-ocr"],
    )
    assert repair_result.exit_code == 0

    query_result = runner.invoke(app, ["--json", "rules", "query", str(vault), "ritual text clarity", "--book-id", "ocr-book"])
    assert query_result.exit_code == 0
    query_payload = json.loads(query_result.stdout)
    assert "Proper OCR repair" in query_payload["data"]["primary_results"][0]["content"]


def _make_bootstrapped_vault(runner, tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    result = runner.invoke(app, ["init", str(vault)])
    assert result.exit_code == 0
    return vault


def _ingest_book(
    runner,
    vault: Path,
    pdf_path: Path,
    book_id: str,
    title: str,
    tier: str,
    scope_tags: list[str] | None = None,
) -> None:
    args = [
        "--json",
        "rules",
        "ingest",
        str(vault),
        str(pdf_path),
        "--book-id",
        book_id,
        "--title",
        title,
        "--tier",
        tier,
    ]
    for tag in scope_tags or []:
        args.extend(["--scope-tag", tag])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.stdout


def _create_text_pdf(path: Path, page_texts: list[str]) -> Path:
    document = fitz.open()
    try:
        for text in page_texts:
            page = document.new_page()
            box = fitz.Rect(36, 36, page.rect.width - 36, page.rect.height - 36)
            page.insert_textbox(box, text, fontsize=12)
        document.save(path)
    finally:
        document.close()
    return path


def _create_image_only_pdf(path: Path, text: str) -> Path:
    source = fitz.open()
    image_doc = fitz.open()
    try:
        page = source.new_page()
        box = fitz.Rect(36, 36, page.rect.width - 36, page.rect.height - 36)
        page.insert_textbox(box, text, fontsize=12)
        pixmap = page.get_pixmap(dpi=200, alpha=False)
        image_page = image_doc.new_page(width=page.rect.width, height=page.rect.height)
        image_page.insert_image(image_page.rect, stream=pixmap.tobytes("png"))
        image_doc.save(path)
    finally:
        source.close()
        image_doc.close()
    return path


def _rule_page(title: str, body: str) -> str:
    return f"{title}\n{body}"
