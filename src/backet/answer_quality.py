from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

ANSWER_QUALITY_CASE_SCHEMA_VERSION = 1
STAGE_PASSED = "passed"
STAGE_FAILED = "failed"
STAGE_NOT_APPLICABLE = "not_applicable"


def load_answer_quality_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = int(payload.get("schema_version", 0))
    if schema_version != ANSWER_QUALITY_CASE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported answer quality case schema: {schema_version}")
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("Answer quality cases must be a list")
    return [dict(case) for case in cases if isinstance(case, dict)]


def evaluate_answer_quality_case(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    retrieval = _evaluate_retrieval(answer, case)
    answerability = _evaluate_answerability(answer, case)
    answer_text = _evaluate_answer_text(answer, case)
    stages = {
        "retrieval": retrieval,
        "answerability": answerability,
        "answer": answer_text,
    }
    return {
        "case_id": case.get("id"),
        "passed": all(stage["status"] in {STAGE_PASSED, STAGE_NOT_APPLICABLE} for stage in stages.values()),
        "stages": stages,
    }


def _evaluate_retrieval(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    sources = _answer_sources(answer)
    failures: list[str] = []
    for index, predicate in enumerate(case.get("expected_sources", []) or [], start=1):
        if not isinstance(predicate, dict):
            continue
        if not any(_source_matches(source, predicate) for source in sources):
            failures.append(f"expected_sources[{index}] did not match any selected source")
    for index, predicate in enumerate(case.get("forbidden_sources", []) or [], start=1):
        if not isinstance(predicate, dict):
            continue
        if any(_source_matches(source, predicate) for source in sources):
            failures.append(f"forbidden_sources[{index}] matched a selected source")
    return _stage_result(failures)


def _evaluate_answerability(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    expects_insufficient = bool(case.get("expected_insufficient"))
    expects_answerable = bool(case.get("expected_answerable"))
    insufficient = _looks_insufficient(str(answer.get("text") or ""))
    if expects_insufficient and not insufficient:
        failures.append("answer did not report insufficient permitted sources")
    if expects_answerable and insufficient:
        failures.append("answer reported insufficiency for an answerable case")
    if not expects_insufficient and not expects_answerable:
        return {"status": STAGE_NOT_APPLICABLE, "failures": []}
    return _stage_result(failures)


def _evaluate_answer_text(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    text = str(answer.get("text") or "")
    folded = text.casefold()
    failures: list[str] = []
    for expected in case.get("expected_answer_contains", []) or []:
        if str(expected).casefold() not in folded:
            failures.append(f"answer does not contain expected text: {expected}")
    for forbidden in case.get("forbidden_answer_contains", []) or []:
        if str(forbidden).casefold() in folded:
            failures.append(f"answer contains forbidden text: {forbidden}")
    if not case.get("expected_answer_contains") and not case.get("forbidden_answer_contains"):
        return {"status": STAGE_NOT_APPLICABLE, "failures": []}
    return _stage_result(failures)


def _stage_result(failures: list[str]) -> dict[str, Any]:
    return {"status": STAGE_FAILED if failures else STAGE_PASSED, "failures": failures}


def _answer_sources(answer: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sources = answer.get("sources")
    if isinstance(sources, list) and sources:
        return [source for source in sources if isinstance(source, Mapping)]
    trace = answer.get("answer_trace")
    if not isinstance(trace, Mapping):
        return []
    retrieval = trace.get("retrieval")
    if not isinstance(retrieval, Mapping):
        return []
    selected = retrieval.get("selected_sources")
    if not isinstance(selected, list):
        return []
    return [source for source in selected if isinstance(source, Mapping)]


def _source_matches(source: Mapping[str, Any], predicate: Mapping[str, Any]) -> bool:
    for key in ("source_type", "citation", "book_title", "title", "relative_path", "section_label"):
        expected = predicate.get(key)
        if expected is not None and str(source.get(key) or "") != str(expected):
            return False
    for key in ("page_start", "page_end"):
        expected = predicate.get(key)
        if expected is not None and source.get(key) != expected:
            return False
    contains_checks = {
        "book_title_contains": _source_field(source, "book_title"),
        "title_contains": _source_field(source, "title"),
        "relative_path_contains": _source_field(source, "relative_path"),
        "section_label_contains": _source_field(source, "section_label"),
        "text_contains": _source_text(source),
    }
    for predicate_key, haystack in contains_checks.items():
        expected = predicate.get(predicate_key)
        if expected is not None and str(expected).casefold() not in haystack.casefold():
            return False
    forbidden = predicate.get("text_not_contains")
    if forbidden is not None and str(forbidden).casefold() in _source_text(source).casefold():
        return False
    return True


def _source_field(source: Mapping[str, Any], key: str) -> str:
    return str(source.get(key) or "")


def _source_text(source: Mapping[str, Any]) -> str:
    return " ".join(
        str(source.get(key) or "")
        for key in ("content", "excerpt", "snippet", "label", "section_label", "book_title", "title", "relative_path")
    )


def _looks_insufficient(text: str) -> bool:
    folded = text.casefold()
    return any(
        marker in folded
        for marker in (
            "insufficient",
            "not enough permitted source",
            "do not have enough permitted source",
            "don't have enough permitted source",
        )
    )
