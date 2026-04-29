from __future__ import annotations

import json
from pathlib import Path

import fitz

from backet.cli import app


def test_skill_manifest_registers_workflow_skills() -> None:
    manifest_path = Path("skills/manifest.json")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    skills = {item["name"]: item["path"] for item in payload["skills"]}

    assert skills["workflow-authoring"] == "workflow-authoring"
    assert skills["city-foundation"] == "city-foundation"


def test_workflow_skills_encode_discuss_before_write_and_rules_aware_grounding() -> None:
    workflow_skill = Path("skills/workflow-authoring/SKILL.md").read_text(encoding="utf-8")
    city_skill = Path("skills/city-foundation/SKILL.md").read_text(encoding="utf-8")

    assert "Canon says" in workflow_skill
    assert "Rules suggest" in workflow_skill
    assert "Open choices" in workflow_skill
    assert "backet context" in workflow_skill
    assert "backet rules query" in workflow_skill

    assert "backet blueprint status" in city_skill
    assert "backet blueprint apply" in city_skill
    assert "backet context" in city_skill
    assert "backet rules query" in city_skill
    assert "Do not draft until the user explicitly says to proceed." in city_skill


def test_fixture_workflow_validation_combines_vault_context_and_ambiguous_rules(retrieval_vault: Path, runner, tmp_path: Path) -> None:
    apply_result = runner.invoke(app, ["--json", "blueprint", "apply", str(retrieval_vault), "city-by-night-v1"])
    assert apply_result.exit_code == 0

    index_result = runner.invoke(app, ["--json", "index", str(retrieval_vault)])
    assert index_result.exit_code == 0

    context_result = runner.invoke(
        app,
        [
            "--json",
            "context",
            str(retrieval_vault),
            "note",
            "1. City Identity & Thematic Structure/1.1 Aesthetic & Mood.md",
            "--query",
            "court secrecy hunger surveillance",
        ],
    )
    assert context_result.exit_code == 0
    context_payload = json.loads(context_result.stdout)
    assert context_payload["data"]["sources"]

    first_pdf = _create_text_pdf(
        tmp_path / "camarilla-a.pdf",
        [
            _rule_page(
                "Feeding Rights",
                "The Camarilla forbids feeding from blood dolls without approval. Permission must be explicit and tracked by local officers.",
            )
        ],
    )
    second_pdf = _create_text_pdf(
        tmp_path / "camarilla-b.pdf",
        [
            _rule_page(
                "Feeding Rights",
                "The Camarilla requires formal approval before blood doll feeding. Local officers keep records and may punish unlicensed access.",
            )
        ],
    )
    _ingest_book(runner, retrieval_vault, first_pdf, "camarilla-a", "Camarilla A", "supplement", ["camarilla"])
    _ingest_book(runner, retrieval_vault, second_pdf, "camarilla-b", "Camarilla B", "supplement", ["camarilla"])

    ambiguous_result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "query",
            str(retrieval_vault),
            "camarilla blood doll approval feeding",
            "--scope-tag",
            "camarilla",
        ],
    )
    assert ambiguous_result.exit_code == 2
    ambiguous_payload = json.loads(ambiguous_result.stdout)
    assert ambiguous_payload["error"]["code"] == "rules_query_ambiguous"


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


def _rule_page(title: str, body: str) -> str:
    return f"{title}\n{body}"
