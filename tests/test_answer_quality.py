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


def test_answer_quality_evaluator_checks_planner_and_answerability() -> None:
    case = {
        "id": "dementation-targeting",
        "question": "can malkavians use dementation on other vampires",
        "required_planner_terms": ["dementation", "vampire"],
        "accepted_planner_aliases": {"vampire": ["vampires", "kindred"]},
        "expected_intents": ["targeting"],
        "expected_response_class": "answer",
        "expected_evidence_status": "answerable",
    }
    answer = {
        "text": "Yes. Sources: Core Rulebook p. 258",
        "sources": [],
        "answer_trace": {
            "stages": {
                "query_plan": {
                    "plan": {
                        "canonical_terms": ["Dementation"],
                        "expanded_terms": ["dominate"],
                        "raw_unknown_terms": ["vampires"],
                        "intents": ["targeting"],
                    }
                },
                "answer_packet": {"response_class": "answer", "evidence_status": "answerable"},
            },
            "retrieval": {"source_count": 1},
            "generation": {"mode": "template"},
        },
    }

    result = evaluate_answer_quality_case(answer, case)

    assert result["passed"] is True
    assert result["trace_summary"]["planner_terms"]


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
