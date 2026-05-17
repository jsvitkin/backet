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
    assert "External research" in workflow_skill
    assert "Open choices" in workflow_skill
    assert "backet context" in workflow_skill
    assert "backet rules query" in workflow_skill
    assert "cited support material" in workflow_skill
    assert "backet.visibility: player" in workflow_skill
    assert "backet.bot_topics" in workflow_skill
    assert "backet bot visibility audit" in workflow_skill
    assert len(workflow_skill.splitlines()) < 80

    assert "backet blueprint status" in city_skill
    assert "backet blueprint apply" in city_skill
    assert "backet context" in city_skill
    assert "backet rules query" in city_skill
    assert "External research" in city_skill
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
    _ingest_book(runner, retrieval_vault, first_pdf, "camarilla-a", "Camarilla A", "supplement")
    _ingest_book(runner, retrieval_vault, second_pdf, "camarilla-b", "Camarilla B", "supplement")

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


def test_private_discord_bot_docs_cover_setup_and_troubleshooting() -> None:
    docs = Path("docs/private-discord-bot.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "Private Discord Bot Bundles" in readme
    assert "backet bot export" in readme
    assert "Discord Developer Portal" in docs
    assert "GitHub Actions" in docs
    assert "ORACLE_VM_SSH_KEY" in docs
    assert "DISCORD_TOKEN" in docs
    assert "Llama 3.2 3B" in docs
    assert "Missing player-visible notes" in docs
    assert "Incompatible bundle" in docs


def test_rule_ingestion_docs_cover_system_dependency_setup() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    installation = Path("docs/wiki/Installation.md").read_text(encoding="utf-8")
    rules_guide = Path("docs/wiki/Adding-Rules-to-a-Vault.md").read_text(encoding="utf-8")

    combined = "\n".join([readme, installation, rules_guide])
    assert "backet setup check" in combined
    assert "backet setup install --yes" in combined
    assert "UB-Mannheim.TesseractOCR" in combined
    assert "brew install tesseract" in combined
    assert "OCR fallback is required for this PDF" in rules_guide


def test_installation_wiki_covers_platform_specific_installs() -> None:
    installation = Path("docs/wiki/Installation.md").read_text(encoding="utf-8")

    assert "The current release is `v0.1.28`." in installation
    assert "## Recommended Install on macOS or Linux" in installation
    assert "curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/install.sh | bash" in installation
    assert "## Recommended Install on Windows PowerShell" in installation
    assert "py -3 -m pipx install https://github.com/jsvitkin/backet/releases/download/v0.1.28/backet-0.1.28-py3-none-any.whl" in installation
    assert "The Windows install path does not use the macOS/Linux `curl ... | bash` installer." in installation


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
