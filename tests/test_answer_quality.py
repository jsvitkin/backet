from __future__ import annotations

from pathlib import Path

import json

import pytest

from backet.answer_quality import evaluate_answer_quality_case, load_answer_quality_cases


def test_answer_quality_fixture_cases_load() -> None:
    cases = load_answer_quality_cases(Path("tests/fixtures/answer-quality/cases.json"))

    assert {case["id"] for case in cases} == {
        "learn-obfuscate-advancement",
        "malkavian-dementation-targeting",
        "blood-bond-definition",
    }
    assert all(case["suite"] == "standard" for case in cases)
    assert all(case["severity"] == "required" for case in cases)
    assert all(case["required"] is True for case in cases)


def test_answer_quality_evaluator_reports_stage_failures() -> None:
    cases = load_answer_quality_cases(Path("tests/fixtures/answer-quality/cases.json"))
    case = next(case for case in cases if case["id"] == "blood-bond-definition")
    answer = {
        "text": "A prince thought the Second Inquisition could be used to destroy the Anarchs.",
        "sources": [
            {
                "source_type": "rules",
                "book_title": "Core Rulebook",
                "section_label": "Second Inquisition",
                "content": "Second Inquisition paranoia is enough.",
            }
        ],
    }

    result = evaluate_answer_quality_case(answer, case)

    assert result["passed"] is False
    assert result["failure_stage"] == "retrieval"
    assert result["stages"]["retrieval"]["status"] == "failed"
    assert result["stages"]["answer"]["status"] == "failed"
    assert result["stages"]["synthesis"]["status"] == "failed"


def test_answer_quality_evaluator_accepts_expected_sources_and_insufficiency() -> None:
    answerable_case = {
        "id": "blood-bond-ok",
        "expected_answerable": True,
        "expected_sources": [{"source_type": "rules", "text_contains": "Blood Bond"}],
        "expected_answer_contains": ["Blood Bond"],
    }
    answerable = {
        "text": "Blood Bond rules describe the bond. Sources: Core Rulebook p. 1",
        "sources": [{"source_type": "rules", "content": "Blood Bond definition text."}],
    }
    insufficient_case = {"id": "insufficient", "expected_insufficient": True}
    insufficient = {"text": "I do not have enough permitted source material to answer that.", "sources": []}

    assert evaluate_answer_quality_case(answerable, answerable_case)["passed"] is True
    assert evaluate_answer_quality_case(insufficient, insufficient_case)["passed"] is True


def test_answer_quality_case_file_reports_invalid_field_path(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema_version": 1, "cases": [{"id": "missing-question"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match=r"cases\[0\]\.question"):
        load_answer_quality_cases(path)


def test_answer_quality_case_file_validates_new_fields(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite": "pipeline-smoke",
                "severity": "exploratory",
                "cases": [
                    {
                        "id": "direct-answer",
                        "question": "what is a rouse check?",
                        "category": "definition",
                        "archetype": "definition",
                        "difficulty": "very-easy",
                        "evidence_contract_id": "definition",
                        "required_facets": ["effect"],
                        "accepted_source_roles": ["base", "chunk"],
                        "expected_first_failure_stage": "claim-support",
                        "required_direct_answer_patterns": ["rouse"],
                        "required_claim_patterns": ["hunger"],
                        "variants": [
                            {
                                "id": "table-wording",
                                "question": "at the table, what does a rouse check do?",
                                "metadata": {"style": "table"},
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_answer_quality_cases(path)

    assert cases[0]["suite"] == "pipeline-smoke"
    assert cases[0]["severity"] == "exploratory"
    assert cases[0]["required"] is False
    assert cases[0]["expected_failure_stage"] == "claim_support"
    assert cases[0]["expected_contract_id"] == "definition"
    variant = next(case for case in cases if case["id"] == "direct-answer::table-wording")
    assert variant["base_case_id"] == "direct-answer"
    assert variant["question"].startswith("at the table")
    assert variant["variant_metadata"]["style"] == "table"


def test_answer_quality_case_file_rejects_bad_archetype_fields(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "bad-archetype",
                        "question": "what is a rouse check?",
                        "archetype": "magic",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"cases\[0\]\.archetype"):
        load_answer_quality_cases(path)


def test_answer_quality_case_file_rejects_bad_stage(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "bad-stage",
                        "question": "what is a rouse check?",
                        "expected_failure_stage": "magic",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"cases\[0\]\.expected_failure_stage"):
        load_answer_quality_cases(path)


def test_answer_quality_evaluator_checks_planner_and_answerability() -> None:
    case = {
        "id": "dementation-targeting",
        "question": "can malkavians use dementation on other vampires",
        "required_planner_terms": ["dementation", "vampire"],
        "accepted_planner_aliases": {"vampire": ["vampires", "kindred"]},
        "expected_intents": ["targeting"],
        "expected_response_class": "answer",
        "expected_evidence_status": "answerable",
        "expected_scenario_archetype": "targeting",
        "expected_contract_id": "targeting",
        "expected_answerability_status": "enough",
        "required_facets": ["target", "effect"],
        "accepted_source_roles": ["base", "chunk"],
    }
    answer = {
        "text": "Yes. Sources: Core Rulebook p. 258",
        "sources": [{"source_type": "rules", "rule_unit_authority_roles": ["base"], "content": "Dementation targets vampires."}],
        "answer_trace": {
            "stages": {
                "query_plan": {
                    "plan": {
                        "canonical_terms": ["Dementation"],
                        "expanded_terms": ["dominate"],
                        "raw_unknown_terms": ["vampires"],
                        "intents": ["targeting"],
                        "scenario_frame": {"question_archetype": "targeting"},
                        "evidence_contract": {"contract_id": "targeting"},
                    }
                },
                "answer_packet": {"response_class": "answer", "evidence_status": "answerable"},
                "answerability": {
                    "answerability_status": "enough",
                    "satisfied_facets": ["target", "effect", "source_reference"],
                    "missing_facets": [],
                },
            },
            "retrieval": {"source_count": 1},
            "generation": {"mode": "template"},
        },
    }

    result = evaluate_answer_quality_case(answer, case)

    assert result["passed"] is True
    assert result["trace_summary"]["planner_terms"]


def test_answer_quality_evaluator_rejects_forbidden_source_roles() -> None:
    case = {
        "id": "base-rule",
        "question": "what is the base rule?",
        "required_facets": ["effect"],
        "forbidden_source_roles": ["example"],
        "expected_answerability_status": "enough",
    }
    answer = {
        "text": "The rule works this way.",
        "sources": [{"source_type": "rules", "content": "Example only.", "rule_unit_authority_roles": ["example"]}],
        "answer_trace": {
            "stages": {
                "answer_packet": {"response_class": "answer", "evidence_status": "answerable"},
                "answerability": {"answerability_status": "enough", "satisfied_facets": ["effect"], "missing_facets": []},
            }
        },
    }

    result = evaluate_answer_quality_case(answer, case)

    assert result["passed"] is False
    assert result["failure_stage"] == "answerability"
    assert "forbidden" in result["stages"]["answerability"]["failures"][0]


def test_answer_quality_evaluator_checks_direct_answer_and_claims() -> None:
    case = {
        "id": "claim-case",
        "question": "what happens at hunger 5?",
        "required_direct_answer_patterns": ["hunger frenzy"],
        "required_claim_patterns": ["Difficulty 4"],
        "expected_claim_stance": "consequence",
    }
    answer = {
        "text": "**Short answer:**\n- At Hunger 5, a forced Rouse Check triggers a hunger frenzy test.\n\nSources: Core Rulebook p. 213",
        "answer_trace": {
            "stages": {
                "claim_support": {
                    "claims": [
                        {
                            "text": "At Hunger 5, a forced Rouse Check triggers a Difficulty 4 hunger frenzy test.",
                            "stance": "consequence",
                        }
                    ]
                }
            }
        },
    }

    result = evaluate_answer_quality_case(answer, case)

    assert result["passed"] is True
    assert result["stages"]["claim_support"]["status"] == "passed"


def test_answer_quality_evaluator_accepts_expected_failure_stage() -> None:
    case = {
        "id": "expected-claim-failure",
        "question": "what happens at hunger 5?",
        "expected_failure_stage": "claim_support",
        "required_claim_patterns": ["Difficulty 4"],
    }
    answer = {"text": "At Hunger 5, something happens."}

    result = evaluate_answer_quality_case(answer, case)

    assert result["passed"] is True
    assert result["failure_stage"] == "claim_support"


def test_answer_quality_evaluator_classifies_planner_first() -> None:
    case = {
        "id": "planner-miss",
        "question": "can malkavians use dementation on other vampires",
        "required_planner_terms": ["dementation"],
        "expected_sources": [{"source_type": "rules", "text_contains": "Dementation"}],
    }
    answer = {
        "text": "No useful answer.",
        "sources": [],
        "answer_trace": {"stages": {"query_plan": {"plan": {"canonical_terms": ["malkavian"]}}}},
    }

    result = evaluate_answer_quality_case(answer, case)

    assert result["passed"] is False
    assert result["failure_stage"] == "planner"
