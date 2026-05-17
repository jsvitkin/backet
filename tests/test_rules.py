from __future__ import annotations

import json
import shutil
from contextlib import closing
from pathlib import Path

import fitz
import pytest

from backet.cli import app
from backet.embeddings import EmbeddingResult
from backet.errors import AppError
from backet.rules import (
    RULE_BLOCK_STRUCTURE_SCHEMA_VERSION,
    RULE_UNIT_SCHEMA_VERSION,
    _rules_corpus_action_for_book,
    build_rules_fts_query,
    classify_rule_chunk,
    classify_rule_chunk_rag_metadata,
    derive_rule_units_from_chunk,
    derive_rule_block_structure,
    ingest_rulebook,
    normalize_scope_tags,
    open_rules_connection,
    parse_pages_spec,
    split_rule_chunks,
)


def test_parse_pages_spec_and_scope_tag_normalization() -> None:
    assert parse_pages_spec("1-3,5", 7) == [1, 2, 3, 5]
    assert normalize_scope_tags([" Camarilla ", "camarilla", " Discipline "]) == ["sect:camarilla", "discipline"]
    with pytest.raises(AppError, match="whole page numbers"):
        parse_pages_spec("1-a", 7)


def test_split_rule_chunks_preserves_paragraph_boundaries() -> None:
    text = "\n\n".join(f"Paragraph {index} " + ("word " * 70) for index in range(1, 6))

    chunks = split_rule_chunks(text)

    assert len(chunks) >= 2
    assert chunks[0].startswith("Paragraph 1")


def test_rules_fts_query_drops_question_stopwords() -> None:
    assert build_rules_fts_query("What is a hunger check?") == '"hunger" OR "check"'


def test_rule_block_structure_cleans_page_furniture_and_preserves_stat_block_fields() -> None:
    structure = derive_rule_block_structure(
        book_id="core-v5",
        section_label="V A M P I R E",
        page_start=205,
        chunk_index=1,
        content=(
            "2 0 5\n"
            "V A M P I R E : T H E M A S Q U E R A D E 2 0 5 Blood Surge\n"
            "Cost: One Rouse Check\n"
            "System: Add dice to one test.\n"
            "Duration: One test"
        ),
    )

    assert structure.schema_version == RULE_BLOCK_STRUCTURE_SCHEMA_VERSION
    assert structure.block_id.startswith("core-v5:p205:c1")
    assert structure.block_kind == "rules"
    assert "Cost: One Rouse Check" in structure.clean_content
    assert "System: Add dice" in structure.clean_content
    assert not structure.source_window.startswith("V A M P I R E")
    assert "page_furniture_removed" in structure.structure_flags


def test_rule_unit_derivation_classifies_specific_mechanics_and_facets() -> None:
    units = derive_rule_units_from_chunk(
        {
            "chunk_id": 7,
            "book_id": "core-v5",
            "page_start": 214,
            "page_end": 214,
            "chunk_index": 2,
            "section_label": "Blood Sorcery Ritual",
            "content": (
                "Ward Against Kindred\n"
                "Cost: One Rouse Check. Dice Pool: Intelligence + Blood Sorcery. "
                "System: The vampire marks a ward that affects Kindred who cross it. "
                "Duration: Until the next sunset."
            ),
            "excerpt": "Ward Against Kindred. Cost: One Rouse Check.",
            "source_window": "Ward Against Kindred. Cost: One Rouse Check. System: The vampire marks a ward.",
            "word_count": 36,
            "confidence": 0.93,
            "extraction_method": "direct",
            "content_hash": "abc123",
            "block_kind": "ritual",
            "block_heading_path_json": json.dumps(["Blood Sorcery Ritual", "Ward Against Kindred"]),
            "structure_flags_json": "[]",
            "chunk_scope_tags_json": json.dumps(["discipline:blood-sorcery"]),
            "metadata_content_hash": "abc123",
            "rag_schema_version": 2,
            "section_kind": "rules",
            "heading_path_json": json.dumps(["Blood Sorcery Ritual", "Ward Against Kindred"]),
            "aliases_json": json.dumps(["blood sorcery"]),
            "entity_locations_json": json.dumps(
                [{"alias": "blood sorcery", "canonical": "blood sorcery", "scope_tag": "discipline:blood-sorcery"}]
            ),
            "evidence_cues_json": json.dumps(["system", "cost", "dice_pool", "duration", "targeting"]),
        }
    )

    assert len(units) == 1
    unit = units[0]
    assert unit.schema_version == RULE_UNIT_SCHEMA_VERSION
    assert unit.unit_kind == "ritual"
    assert unit.authority_role == "specific"
    assert {"cost", "dice_pool", "duration", "target", "effect"}.issubset(set(unit.answer_facets))
    assert "discipline:blood-sorcery" in unit.entity_tags
    assert unit.source_chunk_ids == [7]


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


def test_rules_ingest_derives_rule_units_and_query_uses_rule_unit_channel(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "rule-units.pdf",
        [
            _rule_page(
                "Blood Surge",
                "Cost: One Rouse Check. System: A vampire can add dice to a test using Blood Surge. Duration: One test.",
            ),
            _rule_page(
                "Example Chronicle",
                "For example, an elder might brag about Blood Surge at court without explaining the rules.",
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    with closing(open_rules_connection(vault)) as connection:
        units = connection.execute("SELECT * FROM rule_units ORDER BY page_start").fetchall()

    assert units
    assert units[0]["schema_version"] == RULE_UNIT_SCHEMA_VERSION
    assert units[0]["source_content_hash"]
    assert "cost" in json.loads(units[0]["answer_facets_json"])

    query_result = runner.invoke(app, ["--json", "rules", "query", str(vault), "what is the cost of blood surge", "--limit", "1"])
    assert query_result.exit_code == 0, query_result.stdout
    payload = json.loads(query_result.stdout)
    first = payload["data"]["primary_results"][0]
    assert "rule_unit" in first["retrieval_channels"]
    assert first["rule_units"]
    assert "cost" in first["rule_unit_answer_facets"]
    assert payload["data"]["evidence_packet"]["candidate_counts"]["rule_unit"] >= 1


def test_rules_units_human_output_is_concise(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "units-human.pdf",
        [_rule_page("Rouse Checks", "A Rouse Check is a single die roll. System: On a failure, Hunger increases by one.")],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    result = runner.invoke(app, ["rules", "units", str(vault)])

    assert result.exit_code == 0, result.stdout
    assert "Derived rule units" in result.stdout
    assert "Units:" in result.stdout
    assert "{" not in result.stdout
    assert "source_content_hash" not in result.stdout


def test_rules_index_reports_semantic_schema_and_refreshes_stale_chunks(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "core-index.pdf",
        [
            _rule_page(
                "Domain Traits",
                "Chasse, Portillon, and Lien describe domain reach, access, and mortal awareness for hunting territory.",
            )
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    with closing(open_rules_connection(vault)) as connection:
        embedding_count = connection.execute("SELECT COUNT(*) AS count FROM rule_chunk_embeddings").fetchone()["count"]
        metadata_count = connection.execute("SELECT COUNT(*) AS count FROM rule_chunk_retrieval_metadata").fetchone()["count"]
        connection.execute("UPDATE rule_chunks SET content_hash = 'changed-hash' WHERE book_id = 'core-v5'")
        connection.commit()

    assert embedding_count > 0
    assert metadata_count > 0

    audit_result = runner.invoke(app, ["--json", "rules", "audit", str(vault), "--book-id", "core-v5"])
    assert audit_result.exit_code == 0
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["data"]["semantic_index"]["stale_embeddings"] > 0
    assert audit_payload["data"]["semantic_index"]["stale_metadata"] > 0
    assert "backet rules index" in audit_payload["data"]["semantic_index"]["repair_hint"]

    index_result = runner.invoke(app, ["--json", "rules", "index", str(vault), "--book-id", "core-v5"])
    assert index_result.exit_code == 0
    index_payload = json.loads(index_result.stdout)
    assert index_payload["data"]["embedding_backend"] == "hash"
    assert index_payload["data"]["indexed_chunks"] == index_payload["data"]["total_chunks"]
    assert index_payload["data"]["missing_count"] == 0
    assert index_payload["data"]["stale_count"] == 0
    assert index_payload["data"]["stale_embeddings_before"] > 0
    assert index_payload["data"]["stale_metadata_before"] > 0
    assert index_payload["data"]["refreshed_embeddings"] > 0
    assert index_payload["data"]["refreshed_metadata"] > 0
    assert index_payload["data"]["source_pdf_required"] is False
    assert index_payload["data"]["source_operation"] == "stored_chunk_text"


def test_rules_index_full_rebuilds_missing_rule_block_structure(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "structure-index.pdf",
        [
            _rule_page(
                "Blood Bonds",
                "A Blood Bond forms from repeated drinks of vitae. System: The bond creates emotional dependence and obedience pressure.",
            )
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    with closing(open_rules_connection(vault)) as connection:
        connection.execute(
            """
            UPDATE rule_chunks
            SET rule_block_id = '',
                clean_content = '',
                source_window = '',
                structure_flags_json = '[]',
                structure_schema_version = 0
            WHERE book_id = 'core-v5'
            """
        )
        connection.commit()

    audit_result = runner.invoke(app, ["--json", "rules", "audit", str(vault), "--book-id", "core-v5"])
    assert audit_result.exit_code == 0
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["data"]["books"][0]["structure_health"]["missing_structure"] > 0
    assert "missing_rule_block_structure" in audit_payload["data"]["corpus_health"]["books"][0]["reasons"]

    index_result = runner.invoke(app, ["--json", "rules", "index", str(vault), "--book-id", "core-v5", "--full"])
    assert index_result.exit_code == 0
    index_payload = json.loads(index_result.stdout)
    assert index_payload["data"]["refreshed_structure"] > 0
    assert index_payload["data"]["missing_structure"] == 0
    assert index_payload["data"]["source_pdf_required"] is False

    query_result = runner.invoke(app, ["--json", "rules", "query", str(vault), "what is a blood bond", "--limit", "1"])
    assert query_result.exit_code == 0
    result = json.loads(query_result.stdout)["data"]["primary_results"][0]
    assert result["rule_block_id"].startswith("core-v5:p1:c1")
    assert result["structure_schema_version"] == RULE_BLOCK_STRUCTURE_SCHEMA_VERSION
    assert "Blood Bond" in result["excerpt"]


def test_rules_corpus_health_action_categories() -> None:
    base_book = {
        "book_id": "core-v5",
        "book_title": "Core",
        "page_count": 10,
        "chunk_count": 20,
        "source_status": {"status": "available", "pdf_path": "core.pdf", "stored_fingerprint": "abc"},
        "review_summary": {"pending_pages": 0, "blocked": 0},
        "suspect_pages": [],
        "suspect_chunks": [],
    }
    clean_index = {"missing_embeddings": 0, "missing_metadata": 0, "stale_embeddings": 0, "stale_metadata": 0}
    stale_index = {"missing_embeddings": 1, "missing_metadata": 0, "stale_embeddings": 0, "stale_metadata": 1}

    assert _rules_corpus_action_for_book(base_book, semantic_index=clean_index, vault_label="/vault")["action"] == "none"
    assert _rules_corpus_action_for_book(base_book, semantic_index=stale_index, vault_label="/vault")["action"] == "reindex"

    repair_book = {**base_book, "review_summary": {"pending_pages": 1, "blocked": 0}}
    repair = _rules_corpus_action_for_book(repair_book, semantic_index=clean_index, vault_label="/vault")
    assert repair["action"] == "repair"
    assert repair["source_pdf_required"] is True

    resolved_noise_book = {
        **base_book,
        "review_summary": {"pending_pages": 0, "blocked": 8, "pending_blocked": 0},
        "suspect_pages": [{"review_state": "excluded"} for _ in range(8)],
    }
    assert _rules_corpus_action_for_book(resolved_noise_book, semantic_index=stale_index, vault_label="/vault")[
        "action"
    ] == "reindex"

    unresolved_noise_book = {
        **base_book,
        "source_status": {"status": "missing", "pdf_path": "core.pdf"},
        "review_summary": {"pending_pages": 1, "blocked": 8, "pending_blocked": 1},
        "suspect_pages": [{"review_state": "pending"} for _ in range(8)],
    }
    unresolved = _rules_corpus_action_for_book(unresolved_noise_book, semantic_index=clean_index, vault_label="/vault")
    assert unresolved["action"] == "reingest"
    assert unresolved["source_pdf_required"] is True

    reingest_book = {**base_book, "chunk_count": 0, "source_status": {"status": "missing", "pdf_path": "core.pdf"}}
    reingest = _rules_corpus_action_for_book(reingest_book, semantic_index=clean_index, vault_label="/vault")
    assert reingest["action"] == "reingest"
    assert reingest["source_pdf_required"] is True


def test_rules_query_can_return_semantic_only_matches_with_diagnostics(
    runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _StubRuleEmbeddingBackend()
    monkeypatch.setattr("backet.rules.resolve_embedding_backend", lambda: backend)
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "semantic-core.pdf",
        [
            _rule_page(
                "Domain Traits",
                "Chasse, Portillon, and Lien describe domain reach, access, and mortal awareness for feeding territory.",
            ),
            _rule_page(
                "Feeding Rights",
                "Blood dolls suffer addiction and dependence after repeated feeding from a vampire.",
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    semantic_result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "neighborhood control", "--limit", "2"],
    )
    assert semantic_result.exit_code == 0
    semantic_payload = json.loads(semantic_result.stdout)
    semantic_first = semantic_payload["data"]["primary_results"][0]
    assert semantic_payload["data"]["retrieval_mode"] == "hybrid"
    assert semantic_payload["data"]["embedding_backend"] == "stub"
    assert semantic_payload["data"]["candidate_counts"]["exact"] == 0
    assert semantic_first["section_label"] == "Domain Traits"
    assert "semantic" in semantic_first["match_reasons"]
    assert semantic_first["exact_score"] == 0

    exact_result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "blood doll feeding", "--limit", "2"],
    )
    assert exact_result.exit_code == 0
    exact_payload = json.loads(exact_result.stdout)
    exact_first = exact_payload["data"]["primary_results"][0]
    assert exact_first["section_label"] == "Feeding Rights"
    assert "exact" in exact_first["match_reasons"]


def test_rules_query_falls_back_to_exact_when_semantic_backend_is_unavailable(
    runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "exact-only.pdf",
        [
            _rule_page(
                "Feeding Rights",
                "Feeding rights govern blood doll access, permission, punishment, and court accountability inside a contested domain.",
            )
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    def unavailable_backend():
        raise AppError(
            code="embedding_backend_unavailable",
            message="No semantic backend is available.",
            hint="Use the hash backend for tests.",
            exit_code=2,
        )

    monkeypatch.setattr("backet.rules.resolve_embedding_backend", unavailable_backend)
    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "feeding rights", "--limit", "1"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["retrieval_mode"] == "semantic_unavailable"
    assert payload["data"]["semantic_error"]["code"] == "embedding_backend_unavailable"
    assert payload["data"]["primary_results"][0]["section_label"] == "Feeding Rights"
    assert "exact" in payload["data"]["primary_results"][0]["match_reasons"]
    assert "retrieval-metadata" in payload["data"]["primary_results"][0]["match_reasons"]


def test_rules_query_prefers_definition_over_incidental_cost_mentions(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "definitions.pdf",
        [
            _rule_page(
                "Discipline Power",
                "Cost: One Rouse Check. System: This power mentions a Rouse Check only as an activation cost.",
            ),
            _rule_page(
                "Rousing the Blood",
                (
                    "The rules call for a Rouse Check when vampiric blood is stirred. "
                    "To make a Rouse Check, the player rolls a single die. "
                    "On a success Hunger remains unchanged; on a failure Hunger increases by one."
                ),
            ),
            _rule_page(
                "Damage Types",
                "Aggravated damage: causes severe wounds and lasting injuries. Superficial damage is tracked separately.",
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    rouse = runner.invoke(app, ["--json", "rules", "query", str(vault), "What is a rouse check?", "--limit", "1"])
    damage = runner.invoke(app, ["--json", "rules", "query", str(vault), "What is aggravated damage?", "--limit", "1"])

    assert rouse.exit_code == 0, rouse.stdout
    assert damage.exit_code == 0, damage.stdout
    rouse_first = json.loads(rouse.stdout)["data"]["primary_results"][0]
    damage_first = json.loads(damage.stdout)["data"]["primary_results"][0]
    assert rouse_first["section_label"] == "Rousing the Blood"
    assert damage_first["section_label"] == "Damage Types"
    assert "definition-match" in rouse_first["match_reasons"]
    assert "definition-match" in damage_first["match_reasons"]


def test_rules_query_planner_prefers_blood_bond_definition(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "blood-bond.pdf",
        [
            _rule_page(
                "Second Inquisition",
                (
                    "A prince thought they could use it as a pawn in his own schemes. "
                    "This chapter discusses agencies, hunters, paranoia, and indirect threats."
                ),
            ),
            _rule_page(
                "Blood Bonds",
                (
                    "A Blood Bond is a supernatural emotional dependence created by repeated tastes of vitae. "
                    "Blood bonds bind the drinker to the vampire whose vitae they consume."
                ),
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "what are bloodbonds and how do I make use of it", "--limit", "1"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["data"]["query_plan"]["entities"]["mechanics"] == ["blood bond"]
    assert payload["data"]["query_plan"]["scope_tags"] == ["mechanic:blood-bond"]
    assert payload["data"]["evidence_status"] == "answerable"
    assert payload["data"]["evidence_packet"]["candidate_counts"]["selected_evidence"] == 1
    assert payload["data"]["semantic_quality"]["status"] == "degraded"
    assert payload["data"]["primary_results"][0]["section_label"] == "Blood Bonds"


def test_rules_query_planner_prefers_advancement_for_learning_obfuscate(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "advancement.pdf",
        [
            _rule_page(
                "Example Character",
                (
                    "They wanted me to learn a lesson about myself, but I am not ready for it. "
                    "Clan: Nosferatu. Disciplines and Powers: Obfuscate 1 Silence of Death, "
                    "Obfuscate 2 Unseen Passage, Animalism 1 Bond Famulus."
                ),
            ),
            _rule_page(
                "Advancement",
                (
                    "Characters learn new Discipline powers by spending experience during advancement. "
                    "Out of clan Discipline powers such as Obfuscate require access to a teacher, "
                    "story permission, and the listed experience cost."
                ),
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "how do I learn obfuscate", "--limit", "1"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "advancement" in payload["data"]["query_plan"]["intents"]
    assert "discipline:obfuscate" in payload["data"]["query_plan"]["scope_tags"]
    assert payload["data"]["scope_tags"] == []
    assert payload["data"]["evidence_status"] == "answerable"
    assert "advancement" in payload["data"]["evidence_packet"]["selected_evidence"][0]["evidence_cues"]
    assert payload["data"]["primary_results"][0]["section_label"] == "Advancement"


def test_rules_query_planner_does_not_treat_casting_time_as_advancement(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "ritual-time.pdf",
        [
            _rule_page(
                "Rituals",
                "Rituals Unless otherwise noted, performing a ritual requires a Rouse Check, five minutes per level to cast.",
            )
        ],
    )
    _ingest_book(runner, vault, pdf_path, "ritual-time", "Ritual Time", "core")

    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "how long does it take to cast a ritual"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "advancement" not in payload["data"]["query_plan"]["intents"]
    assert "five minutes per level" in payload["data"]["evidence_packet"]["selected_evidence"][0]["content"]


def test_rules_query_planner_prefers_ritual_timing_over_ceremony_timing(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "ritual-vs-ceremony-time.pdf",
        [
            _rule_page(
                "Oblivion Ceremonies",
                (
                    "Ceremonies are Oblivion's equivalent to Blood Sorcery Rituals. "
                    "Unless otherwise noted, performing a Ceremony requires a Rouse Check, five minutes per level to cast."
                ),
            ),
            _rule_page(
                "D I S C I P L I N E S",
                (
                    "D I S C I P L I N E S 2 7 5 Rituals Unless otherwise noted, performing a ritual requires a Rouse Check, "
                    "five minutes per level to cast, and a winning Intelligence + Blood Sorcery test."
                ),
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "ritual-time", "Ritual Time", "core")

    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "how long does it take to cast a ritual", "--limit", "1"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["data"]["primary_results"][0]["section_label"] == "D I S C I P L I N E S"
    assert "performing a ritual requires" in payload["data"]["evidence_packet"]["selected_evidence"][0]["content"]


def test_rules_query_planner_prefers_dementation_targeting_system(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "dementation.pdf",
        [
            _rule_page(
                "Malkavian Clan",
                (
                    "Some Malkavians use Dominate to distract a victim's mind. "
                    "Others rely on Obfuscate and unusual clan traditions in social scenes."
                ),
            ),
            _rule_page(
                "Dementation System",
                (
                    "Dementation is a Dominate power associated with Malkavians. "
                    "System: choose a target vampire or other Kindred within conversation range. "
                    "The power affects the target if the user's roll succeeds."
                ),
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "can malkavians use dementation on other vampires", "--limit", "1"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "targeting" in payload["data"]["query_plan"]["intents"]
    assert any("ambiguous_power_alias:dementation" in warning for warning in payload["data"]["query_plan"]["warnings"])
    assert payload["data"]["evidence_status"] == "answerable"
    assert "targeting" in payload["data"]["evidence_packet"]["selected_evidence"][0]["evidence_cues"]
    assert payload["data"]["primary_results"][0]["section_label"] == "Dementation System"

    typo_result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "can malkavians use dementia on other vampires", "--limit", "1"],
    )
    assert typo_result.exit_code == 0, typo_result.stdout
    typo_payload = json.loads(typo_result.stdout)
    assert typo_payload["data"]["query_plan"]["entities"]["powers"] == ["Dementation"]
    assert typo_payload["data"]["evidence_status"] == "answerable"
    assert typo_payload["data"]["primary_results"][0]["section_label"] == "Dementation System"


def test_rules_rag_v2_requires_entity_and_intent_cooccurrence(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "targeting-without-entity.pdf",
        [
            _rule_page(
                "Malkavian Clan",
                "Malkavians sometimes unsettle a victim's mind, but this clan text gives no procedure.",
            ),
            _rule_page(
                "Generic Targeting System",
                "System: choose a target vampire or other Kindred within conversation range. The roll affects that target on a win.",
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "can malkavians use dementation on other vampires", "--limit", "1"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    packet = payload["data"]["evidence_packet"]
    assert payload["data"]["evidence_status"] == "insufficient"
    assert packet["selected_evidence"] == []
    assert "entity_anchor" in packet["missing_evidence"] or "targeting" in packet["missing_evidence"]
    rejected_reasons = {reason for candidate in packet["rejected_candidates"] for reason in candidate["rejection_reasons"]}
    assert "missing_entity_anchor" in rejected_reasons
    assert "missing_intent_evidence" in rejected_reasons


def test_rules_rag_v2_uses_bounded_neighbor_expansion_for_split_system_text(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    anchor_paragraph = "Dementation is a Malkavian Dominate power. " + ("Malkavian memory " * 105)
    system_paragraph = (
        "System: choose a target vampire or other Kindred within conversation range. "
        "The power affects that target if the user's roll succeeds."
    )
    pdf_path = _create_text_pdf(
        tmp_path / "split-system.pdf",
        [_rule_page("Dementation", f"{anchor_paragraph}\n\n{system_paragraph}")],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "can malkavians use dementation on other vampires", "--limit", "1"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    packet = payload["data"]["evidence_packet"]
    assert payload["data"]["evidence_status"] == "answerable"
    assert packet["candidate_counts"]["selected_evidence"] >= 1
    assert "neighbor_expansion" in packet["retrieval_diagnostics"]
    if packet["retrieval_diagnostics"]["neighbor_expansion"]["candidate_count"]:
        assert any("neighbor_expansion" in result["retrieval_channels"] for result in packet["selected_evidence"])


def test_rules_rag_v2_selects_cost_and_consequence_evidence(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "cost-consequence.pdf",
        [
            _rule_page(
                "Blood Surge Cost",
                "Cost: One Rouse Check. A Blood Surge adds dice to a roll for the current test.",
            ),
            _rule_page(
                "Messy Critical Consequence",
                "On a messy critical, the character succeeds but suffers a Beast-driven consequence or complication.",
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    cost = runner.invoke(app, ["--json", "rules", "query", str(vault), "what does blood surge cost", "--limit", "1"])
    consequence = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "what happens on a messy critical", "--limit", "1"],
    )

    assert cost.exit_code == 0, cost.stdout
    assert consequence.exit_code == 0, consequence.stdout
    cost_payload = json.loads(cost.stdout)
    consequence_payload = json.loads(consequence.stdout)
    assert cost_payload["data"]["evidence_status"] == "answerable"
    assert cost_payload["data"]["primary_results"][0]["section_label"] == "Blood Surge Cost"
    assert "cost" in cost_payload["data"]["evidence_packet"]["selected_evidence"][0]["evidence_cues"]
    assert consequence_payload["data"]["evidence_status"] == "answerable"
    assert consequence_payload["data"]["primary_results"][0]["section_label"] == "Messy Critical Consequence"
    assert "consequence" in consequence_payload["data"]["evidence_packet"]["selected_evidence"][0]["evidence_cues"]


def test_rules_rag_v2_marks_mere_mentions_insufficient(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "mere-mention.pdf",
        [
            _rule_page(
                "Example Character",
                (
                    "They wanted me to learn a lesson about myself, but I am not ready for it. "
                    "Clan: Nosferatu. Disciplines and Powers: Obfuscate 1 Silence of Death, "
                    "Obfuscate 2 Unseen Passage."
                ),
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "how do I learn obfuscate", "--limit", "1"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["data"]["evidence_status"] == "insufficient"
    assert payload["data"]["evidence_packet"]["selected_evidence"] == []
    assert "advancement" in payload["data"]["evidence_packet"]["missing_evidence"]
    rejected = payload["data"]["evidence_packet"]["rejected_candidates"]
    assert rejected
    assert "mere_mention" in rejected[0]["rejection_reasons"]


def test_rules_query_downranks_non_answer_sections(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "noisy-core.pdf",
        [
            _rule_page(
                "Table of Contents",
                "Domain rules, feeding rules, combat rules, character rules, and storyteller rules are listed here for navigation only.",
            ),
            _rule_page(
                "Domain Systems",
                "Domain rules explain how Chasse, Portillon, and Lien shape hunting pressure, mortal access, and Kindred control.",
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "domain rules", "--limit", "2"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    results = payload["data"]["primary_results"]
    assert results[0]["section_label"] == "Domain Systems"
    assert results[1]["section_label"] == "Table of Contents"
    assert "quality-penalty" in results[1]["match_reasons"]
    assert results[1]["section_kind"] == "toc"


def test_rules_query_downranks_suspect_ocr_when_clean_text_also_matches(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    repeated_text = _rule_page(
        "Domain Systems",
        "Domain rules explain hunting access, feeding control, mortal awareness, and coterie pressure in contested territory.",
    )
    pdf_path = _create_text_pdf(tmp_path / "ocr-penalty.pdf", [repeated_text, repeated_text])
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")
    with closing(open_rules_connection(vault)) as connection:
        chunk_id = connection.execute(
            "SELECT id FROM rule_chunks WHERE book_id = 'core-v5' AND page_start = 1"
        ).fetchone()["id"]
        connection.execute(
            "UPDATE rule_chunks SET confidence = 0.65, extraction_method = 'ocr' WHERE id = ?",
            (chunk_id,),
        )
        connection.execute(
            """
            UPDATE rule_chunk_retrieval_metadata
            SET retrieval_flags_json = ?, section_kind = 'rules'
            WHERE chunk_id = ?
            """,
            (json.dumps(["suspect_ocr"]), chunk_id),
        )
        connection.commit()

    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "domain hunting access", "--limit", "2"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    results = payload["data"]["primary_results"]
    assert results[0]["page_start"] == 2
    assert results[1]["page_start"] == 1
    assert "quality-penalty" in results[1]["match_reasons"]
    assert "suspect_ocr" in results[1]["retrieval_flags"]


def test_rules_query_excerpt_window_skips_page_furniture(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "window.pdf",
        [
            _rule_page(
                "Core Book",
                (
                    "V A M P I R E : T H E M A S Q U E R A D E 2 0 5 " * 6
                    + "Blood Surge. Cost: One Rouse Check. System: add dice to a single test for the scene."
                ),
            )
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")

    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "what does blood surge cost", "--limit", "1"])

    assert result.exit_code == 0, result.stdout
    excerpt = json.loads(result.stdout)["data"]["primary_results"][0]["excerpt"]
    assert "Blood Surge" in excerpt
    assert not excerpt.startswith("V A M P I R E")


def test_rules_entity_first_retrieval_keeps_blush_of_life_on_target(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "blush.pdf",
        [
            _rule_page(
                "Blush of Life",
                "A vampire can make a Rouse Check to send blood through dead flesh. System: Blush of Life lets the vampire breathe, warm their skin, and pass as human for the scene.",
            ),
            _rule_page(
                "Shadow Cloak",
                "Duration: One scene. System: This unrelated power hides the vampire in a patch of darkness but says nothing about appearing alive.",
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")
    runner.invoke(app, ["--json", "rules", "index", str(vault), "--book-id", "core-v5", "--full"])

    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "how does Blush of Life work?", "--limit", "1"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)["data"]
    selected = payload["evidence_packet"]["selected_evidence"]
    assert selected
    assert selected[0]["section_label"] == "Blush of Life"
    assert payload["query_plan"]["resolved_entities"][0]["canonical_name"] == "blush of life"
    assert payload["evidence_packet"]["retrieval_diagnostics"]["entity_first"]["mode"] == "entity_first"


def test_rules_entity_first_retrieval_prefers_base_dominate_targeting(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "dominate.pdf",
        [
            _rule_page(
                "Dominate",
                "System: Dominate powers require the vampire to catch the victim's eye and issue a command. The discipline can affect mortals and Kindred when the individual power permits it.",
            ),
            _rule_page(
                "Famulus Delivery",
                "System: This special animal delivery power lets a vampire transmit a command through a famulus without direct eye contact. It is a narrow exception and not the base Dominate rule.",
            ),
        ],
    )
    _ingest_book(runner, vault, pdf_path, "core-v5", "Core Rulebook", "core")
    runner.invoke(app, ["--json", "rules", "index", str(vault), "--book-id", "core-v5", "--full"])

    result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "query",
            str(vault),
            "can I use Dominate on another vampire without eye contact?",
            "--limit",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)["data"]
    selected = payload["evidence_packet"]["selected_evidence"]
    assert selected
    assert selected[0]["section_label"] == "Dominate"
    assert payload["query_plan"]["target_groups"] == ["vampire"]
    assert "eye_contact" in payload["query_plan"]["situational_constraints"]


def test_rule_retrieval_metadata_classifies_common_non_answer_chunks() -> None:
    assert classify_rule_chunk("Index", "Index domain feeding page references", 5, 0.95, "direct") == (
        "index",
        ["navigational", "very_short"],
    )
    assert classify_rule_chunk("Character Sheet", "Name clan predator ambition desire health willpower", 7, 0.95, "direct") == (
        "sheet",
        ["navigational", "very_short"],
    )
    assert classify_rule_chunk("V A M P I R E", "Core Book 2 0 5", 4, 0.95, "direct") == (
        "furniture",
        ["navigational", "page_furniture", "very_short"],
    )
    assert classify_rule_chunk("Page 4", "12 13 -- ..", 3, 0.4, "ocr") == (
        "art",
        ["art_heavy", "suspect_ocr", "very_short"],
    )


def test_rag_v2_metadata_detects_aliases_locations_and_evidence_cues() -> None:
    metadata = classify_rule_chunk_rag_metadata(
        "Advancement",
        (
            "Characters learn new Discipline powers by spending experience. "
            "Out of clan Discipline powers such as Obfuscate require access to a teacher."
        ),
        18,
        0.98,
        "direct",
    )

    assert metadata.rag_schema_version == 2
    assert "Advancement" in metadata.heading_path
    assert "obfuscate" in metadata.aliases
    assert {"advancement", "cost", "prerequisite"}.issubset(set(metadata.evidence_cues))
    assert any(entity["scope_tag"] == "discipline:obfuscate" for entity in metadata.entity_locations)


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
    _ingest_book(runner, vault, supplement_pdf, "camarilla", "Camarilla", "supplement")

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


def test_rules_query_without_scope_prefers_core_and_keeps_supplements_as_fallback(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    core_pdf = _create_text_pdf(
        tmp_path / "core.pdf",
        [
            _rule_page(
                "Blood Potency",
                "Core rules explain Blood Potency for all vampires. Blood Potency controls blood surge, mending, and feeding limitations.",
            )
        ],
    )
    supplement_pdf = _create_text_pdf(
        tmp_path / "supplement.pdf",
        [
            _rule_page(
                "Ancient Icon",
                "This supplement relic affects vampires with Blood Potency five or greater and changes how their Hunger can be reduced.",
            )
        ],
    )
    _ingest_book(runner, vault, core_pdf, "core-v5", "Core Rulebook", "core")
    _ingest_book(runner, vault, supplement_pdf, "icon-book", "Icon Book", "supplement")

    result = runner.invoke(app, ["--json", "rules", "query", str(vault), "blood potency", "--limit", "2"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["primary_results"][0]["book_id"] == "core-v5"
    assert payload["data"]["fallback_results"][0]["book_id"] == "icon-book"


def test_rules_ingest_generates_scope_assertions_and_review_commands(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "camarilla-scopes.pdf",
        [
            _rule_page(
                "Banu Haqim",
                "Disciplines include Blood Sorcery. Bane, Clan Compulsion, and Rituals define the mechanical play surface for the clan.",
            ),
            _rule_page(
                "Institutional Conflict",
                "Institutional Conflict pools, Institutional Scale, and Institutional Damage resolve boardroom struggles between mortal institutions.",
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
            "camarilla-v5",
            "--title",
            "Camarilla",
            "--tier",
            "supplement",
        ],
    )
    assert ingest_result.exit_code == 0
    ingest_payload = json.loads(ingest_result.stdout)
    scopes = ingest_payload["data"]["scope_assertions"]
    assert "sect:camarilla" in scopes["source_scope"]
    assert scopes["applied"] >= 4

    audit_result = runner.invoke(app, ["--json", "rules", "scope", "audit", str(vault), "--book-id", "camarilla-v5"])
    assert audit_result.exit_code == 0
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["data"]["books"][0]["source_scope"] == ["sect:camarilla"]

    export_result = runner.invoke(app, ["--json", "rules", "scope", "export", str(vault), "--book-id", "camarilla-v5"])
    assert export_result.exit_code == 0
    export_payload = json.loads(export_result.stdout)
    manifest = export_payload["data"]["manifest"]
    exported_tags = {tag for scope in manifest["scopes"] for tag in [scope["tag"]]}
    assert "clan:banu-haqim" in exported_tags
    assert "mechanic:institutional-conflict" in exported_tags

    query_result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "query",
            str(vault),
            "blood sorcery rituals",
            "--scope-tag",
            "banu-haqim",
        ],
    )
    assert query_result.exit_code == 0
    query_payload = json.loads(query_result.stdout)
    first = query_payload["data"]["primary_results"][0]
    assert first["book_id"] == "camarilla-v5"
    assert "clan:banu-haqim" in first["scope_tags"]
    assert "scope-assertion" in first["match_reasons"]
    assert any(assertion["tag"] == "clan:banu-haqim" for assertion in first["scope_assertions"])


def test_rules_scope_apply_validates_and_refreshes_query_scopes(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "custom-scope.pdf",
        [
            _rule_page(
                "Strange Bloodline",
                "This page describes a custom ritual mystery that should be reviewable through an applied manifest.",
            )
        ],
    )
    _ingest_book(runner, vault, pdf_path, "custom-book", "Custom Book", "supplement")
    manifest_path = tmp_path / "custom-scopes.json"
    manifest_path.write_text(
        json.dumps(
            {
                "book_id": "custom-book",
                "source_scope": ["sect:camarilla"],
                "scopes": [
                    {
                        "pages": "1",
                        "tags": ["mechanic:ritual"],
                        "role": "mechanical-authority",
                        "status": "applied",
                        "confidence": 1.0,
                    }
                ],
            }
        )
    )

    apply_result = runner.invoke(app, ["--json", "rules", "scope", "apply", str(vault), str(manifest_path)])
    assert apply_result.exit_code == 0

    query_result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "custom ritual mystery", "--scope-tag", "ritual"],
    )
    assert query_result.exit_code == 0
    query_payload = json.loads(query_result.stdout)
    assert query_payload["data"]["primary_results"][0]["book_id"] == "custom-book"
    assert "mechanic:ritual" in query_payload["data"]["primary_results"][0]["scope_tags"]

    invalid_manifest = tmp_path / "invalid-scopes.json"
    invalid_manifest.write_text(json.dumps({"book_id": "custom-book", "scopes": [{"pages": "1", "tags": ["ritual"], "role": "bad"}]}))
    invalid_result = runner.invoke(app, ["--json", "rules", "scope", "apply", str(vault), str(invalid_manifest)])
    assert invalid_result.exit_code == 2
    invalid_payload = json.loads(invalid_result.stdout)
    assert invalid_payload["error"]["code"] == "rules_scope_manifest_invalid"


def test_perspective_scope_does_not_override_authoritative_core(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    core_pdf = _create_text_pdf(
        tmp_path / "sabbat-core.pdf",
        [
            _rule_page(
                "Sabbat Mechanics",
                "Sabbat vaulderie mechanics define a system test and dice pool for sect rituals.",
            )
        ],
    )
    perspective_pdf = _create_text_pdf(
        tmp_path / "camarilla-perspective.pdf",
        [
            _rule_page(
                "The Sabbat",
                "The Camarilla regards the Sabbat as a dangerous enemy and warns neonates away from their ideology.",
            )
        ],
    )
    _ingest_book(runner, vault, core_pdf, "core-v5", "Core Rulebook", "core")
    _ingest_book(runner, vault, perspective_pdf, "camarilla-v5", "Camarilla", "supplement")

    result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "sabbat vaulderie mechanics", "--scope-tag", "sabbat"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["primary_results"][0]["book_id"] == "core-v5"


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
    _ingest_book(runner, vault, first_pdf, "camarilla-a", "Camarilla A", "supplement")
    _ingest_book(runner, vault, second_pdf, "camarilla-b", "Camarilla B", "supplement")

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
    _ingest_book(runner, vault, pdf_path, "ocr-book", "OCR Book", "supplement")

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


def test_rules_audit_review_decisions_hide_only_unchanged_findings_and_exclude_query_results(
    runner,
    tmp_path: Path,
) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "review.pdf",
        [
            _rule_page(
                "Feeding Permits",
                "Blood doll feeding permits require a court record and a named officer before repeated access is allowed.",
            )
        ],
    )
    _ingest_book(runner, vault, pdf_path, "review-book", "Review Book", "supplement")
    with closing(open_rules_connection(vault)) as connection:
        page_hash = connection.execute(
            "SELECT content_hash FROM page_audit WHERE book_id = 'review-book' AND page_number = 1"
        ).fetchone()["content_hash"]
        connection.execute(
            """
            UPDATE page_audit
            SET suspect = 1, confidence = 0.4, quality_flags_json = ?
            WHERE book_id = 'review-book' AND page_number = 1
            """,
            (json.dumps(["low_text_density"]),),
        )
        connection.execute("UPDATE rule_chunks SET confidence = 0.4 WHERE book_id = 'review-book'")
        connection.commit()

    audit_result = runner.invoke(app, ["--json", "rules", "audit", str(vault), "--book-id", "review-book"])
    assert audit_result.exit_code == 0
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["data"]["books"][0]["review_cards"][0]["page_start"] == 1

    ignored = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "review",
            str(vault),
            "--book-id",
            "review-book",
            "--page",
            "1",
            "--decision",
            "ignored",
            "--reason",
            "art-heavy false positive",
        ],
    )
    assert ignored.exit_code == 0, ignored.stdout
    audit_result = runner.invoke(app, ["--json", "rules", "audit", str(vault), "--book-id", "review-book"])
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["data"]["books"][0]["review_cards"] == []
    assert audit_payload["data"]["books"][0]["suspect_pages"][0]["review_state"] == "ignored"

    with closing(open_rules_connection(vault)) as connection:
        connection.execute(
            "UPDATE page_audit SET content_hash = 'changed-after-review' WHERE book_id = 'review-book' AND page_number = 1"
        )
        connection.commit()
    audit_result = runner.invoke(app, ["--json", "rules", "audit", str(vault), "--book-id", "review-book"])
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["data"]["books"][0]["review_cards"][0]["page_start"] == 1
    assert audit_payload["data"]["books"][0]["suspect_pages"][0]["review_state"] == "pending"

    excluded = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "review",
            str(vault),
            "--book-id",
            "review-book",
            "--page",
            "1",
            "--decision",
            "excluded",
        ],
    )
    assert excluded.exit_code == 0, excluded.stdout
    query_result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "blood doll feeding permits", "--book-id", "review-book"],
    )
    assert query_result.exit_code == 2
    query_payload = json.loads(query_result.stdout)
    assert query_payload["error"]["details"]["reviewed_exclusions"]["excluded_chunks"] == 1

    with closing(open_rules_connection(vault)) as connection:
        connection.execute(
            "UPDATE page_audit SET content_hash = ? WHERE book_id = 'review-book' AND page_number = 1",
            (page_hash,),
        )
        connection.commit()
    skipped = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "review",
            str(vault),
            "--book-id",
            "review-book",
            "--page",
            "1",
            "--chunk-index",
            "1",
            "--decision",
            "skipped",
        ],
    )
    assert skipped.exit_code == 0, skipped.stdout
    assert json.loads(skipped.stdout)["data"]["resolved"] is False


def test_rules_audit_guided_review_walks_all_books_without_book_id_commands(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    first_pdf = _create_text_pdf(
        tmp_path / "first-review.pdf",
        [
            _rule_page(
                "First Page",
                "First reviewable feeding rule text needs a human audit decision, and this direct text is long enough to avoid OCR fallback during ingestion.",
            )
        ],
    )
    second_pdf = _create_text_pdf(
        tmp_path / "second-review.pdf",
        [
            _rule_page(
                "Second Page",
                "Second reviewable court rule text needs a human audit decision, and this direct text is long enough to avoid OCR fallback during ingestion.",
            )
        ],
    )
    _ingest_book(runner, vault, first_pdf, "first-review", "First Review", "core")
    _ingest_book(runner, vault, second_pdf, "second-review", "Second Review", "supplement")
    with closing(open_rules_connection(vault)) as connection:
        for current_book_id in ("first-review", "second-review"):
            connection.execute(
                """
                UPDATE page_audit
                SET suspect = 1, confidence = 0.4, quality_flags_json = ?
                WHERE book_id = ? AND page_number = 1
                """,
                (json.dumps(["low_text_density"]), current_book_id),
            )
        connection.commit()

    result = runner.invoke(app, ["rules", "audit", str(vault), "--review"], input="a\na\n")

    assert result.exit_code == 0, result.stdout
    assert "Guided review: 2 pending card(s)" in result.stdout
    assert "Review 1/2" in result.stdout
    assert "Review 2/2" in result.stdout
    assert "backet rules review" not in result.stdout
    assert "--book-id" not in result.stdout
    with closing(open_rules_connection(vault)) as connection:
        rows = connection.execute(
            """
            SELECT book_id, decision
            FROM rule_audit_reviews
            WHERE decision = 'accepted'
            ORDER BY book_id
            """
        ).fetchall()
    assert [(row["book_id"], row["decision"]) for row in rows] == [
        ("first-review", "accepted"),
        ("second-review", "accepted"),
    ]


def test_rules_manual_replacement_refreshes_page_chunks_metadata_and_query_results(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "replace.pdf",
        [_rule_page("Broken Page", "This older extraction is going to be replaced by human corrected text.")],
    )
    _ingest_book(runner, vault, pdf_path, "replace-book", "Replace Book", "core")

    replacement = (
        "Corrected ritual text says vitae witnesses must record the feeding license before the scene can continue. "
        "The corrected passage includes enough words to be stored as useful rules text."
    )
    result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "replace",
            str(vault),
            "--book-id",
            "replace-book",
            "--page",
            "1",
            "--text",
            replacement,
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["data"]["chunk_count"] >= 1

    with closing(open_rules_connection(vault)) as connection:
        page = connection.execute("SELECT * FROM page_audit WHERE book_id = 'replace-book' AND page_number = 1").fetchone()
        override_count = connection.execute("SELECT COUNT(*) AS count FROM rule_page_text_overrides").fetchone()["count"]
        metadata_count = connection.execute("SELECT COUNT(*) AS count FROM rule_chunk_retrieval_metadata").fetchone()["count"]
        fts_count = connection.execute("SELECT COUNT(*) AS count FROM rule_chunks_fts WHERE book_id = 'replace-book'").fetchone()["count"]
    assert page["extraction_method"] == "manual"
    assert page["suspect"] == 0
    assert override_count == 1
    assert metadata_count >= 1
    assert fts_count >= 1

    query_result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "corrected ritual witnesses license", "--book-id", "replace-book"],
    )
    assert query_result.exit_code == 0, query_result.stdout
    query_payload = json.loads(query_result.stdout)
    assert "Corrected ritual text" in query_payload["data"]["primary_results"][0]["content"]


def test_rules_source_status_relink_and_missing_source_repair_block(runner, tmp_path: Path) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_text_pdf(
        tmp_path / "source.pdf",
        [_rule_page("Source Page", "Domain officers track blood doll permissions through a local court ledger.")],
    )
    _ingest_book(runner, vault, pdf_path, "source-book", "Source Book", "core")

    matching_pdf = tmp_path / "source-copy.pdf"
    shutil.copyfile(pdf_path, matching_pdf)
    relink_result = runner.invoke(
        app,
        ["--json", "rules", "relink-source", str(vault), str(matching_pdf), "--book-id", "source-book"],
    )
    assert relink_result.exit_code == 0, relink_result.stdout
    assert json.loads(relink_result.stdout)["data"]["source_status"]["status"] == "available"

    different_pdf = _create_text_pdf(
        tmp_path / "different.pdf",
        [_rule_page("Different Source", "A different source PDF should require explicit force before repair trust changes.")],
    )
    mismatch_result = runner.invoke(
        app,
        ["--json", "rules", "relink-source", str(vault), str(different_pdf), "--book-id", "source-book"],
    )
    assert mismatch_result.exit_code == 2
    assert json.loads(mismatch_result.stdout)["error"]["code"] == "rules_source_fingerprint_mismatch"

    forced_result = runner.invoke(
        app,
        [
            "--json",
            "rules",
            "relink-source",
            str(vault),
            str(different_pdf),
            "--book-id",
            "source-book",
            "--force",
        ],
    )
    assert forced_result.exit_code == 0, forced_result.stdout
    assert json.loads(forced_result.stdout)["data"]["status"] == "forced_mismatch"
    with closing(open_rules_connection(vault)) as connection:
        history_count = connection.execute("SELECT COUNT(*) AS count FROM rule_source_relinks").fetchone()["count"]
    assert history_count == 2

    different_pdf.unlink()
    repair_result = runner.invoke(app, ["--json", "rules", "repair", str(vault), "source-book", "--pages", "1"])
    assert repair_result.exit_code == 2
    assert json.loads(repair_result.stdout)["error"]["code"] == "rules_repair_source_unavailable"


def test_rules_automatic_ocr_candidate_scoring_selects_best_local_candidate(
    runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = _make_bootstrapped_vault(runner, tmp_path)
    pdf_path = _create_image_only_pdf(tmp_path / "ocr-candidates.pdf", "Unreadable scan")
    monkeypatch.setattr(
        "backet.rules._ocr_text_candidates",
        lambda page, pdf_path, page_number: [
            "bad",
            "Corrected OCR candidate explains blood sorcery rituals, dice tests, and vitae costs for the scene.",
        ],
    )
    _ingest_book(runner, vault, pdf_path, "candidate-book", "Candidate Book", "supplement")

    query_result = runner.invoke(
        app,
        ["--json", "rules", "query", str(vault), "blood sorcery dice vitae", "--book-id", "candidate-book"],
    )
    assert query_result.exit_code == 0, query_result.stdout
    query_payload = json.loads(query_result.stdout)
    assert "Corrected OCR candidate" in query_payload["data"]["primary_results"][0]["content"]


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


class _StubRuleEmbeddingBackend:
    name = "stub"
    model_name = "stub-rules-v1"

    def encode_many(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            backend_name=self.name,
            model_name=self.model_name,
            vectors=[self._encode(text) for text in texts],
        )

    def _encode(self, text: str) -> list[float]:
        lowered = text.casefold()
        if "neighborhood control" in lowered or "chasse" in lowered or "portillon" in lowered or "lien" in lowered:
            return [1.0, 0.0]
        if "blood doll" in lowered or "blood dolls" in lowered:
            return [0.0, 1.0]
        return [0.0, 0.0]
