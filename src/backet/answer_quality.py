from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

ANSWER_QUALITY_CASE_SCHEMA_VERSION = 1
STAGE_PASSED = "passed"
STAGE_FAILED = "failed"
STAGE_NOT_APPLICABLE = "not_applicable"
FAILURE_STAGE_ORDER = ("runtime", "planner", "retrieval", "answerability", "synthesis", "citation", "output_policy")
CASE_REQUIRED_FIELDS = ("id", "question")


def load_answer_quality_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = int(payload.get("schema_version", 0))
    if schema_version != ANSWER_QUALITY_CASE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported answer quality case schema: {schema_version}")
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("Answer quality cases must be a list")
    validated: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"cases[{index}] must be an object")
        for field in CASE_REQUIRED_FIELDS:
            if not str(case.get(field) or "").strip():
                raise ValueError(f"cases[{index}].{field} is required")
        validated.append(dict(case))
    return validated


def evaluate_answer_quality_case(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _evaluate_runtime(answer, case)
    planner = _evaluate_planner(answer, case)
    retrieval = _evaluate_retrieval(answer, case)
    answerability = _evaluate_answerability(answer, case)
    synthesis = _evaluate_answer_text(answer, case)
    citation = _evaluate_citation(answer, case)
    output_policy = _evaluate_output_policy(answer, case)
    stages = {
        "runtime": runtime,
        "planner": planner,
        "retrieval": retrieval,
        "answerability": answerability,
        "synthesis": synthesis,
        "answer": synthesis,
        "citation": citation,
        "output_policy": output_policy,
    }
    first_failed = _first_failed_stage(stages)
    return {
        "case_id": case.get("id"),
        "question": case.get("question"),
        "difficulty": case.get("difficulty"),
        "passed": first_failed is None,
        "failure_stage": first_failed,
        "stages": stages,
        "trace_summary": summarize_answer_trace(answer),
    }


def summarize_answer_trace(answer: Mapping[str, Any]) -> dict[str, Any]:
    trace = _answer_trace(answer)
    retrieval = _mapping(trace.get("retrieval"))
    query_plan = _mapping(_mapping(trace.get("stages")).get("query_plan")).get("plan")
    if not isinstance(query_plan, Mapping):
        query_plan = {}
    answer_packet = _mapping(_mapping(trace.get("stages")).get("answer_packet"))
    synthesis = _mapping(_mapping(trace.get("stages")).get("synthesis"))
    generation = _mapping(trace.get("generation"))
    return {
        "response_class": answer_packet.get("response_class"),
        "evidence_status": answer_packet.get("evidence_status") or retrieval.get("rules_evidence_status"),
        "answer_mode": generation.get("mode"),
        "fallback_used": generation.get("fallback_used"),
        "fallback_reason": generation.get("fallback_reason"),
        "synthesis_mode": synthesis.get("mode"),
        "synthesis_validation_status": synthesis.get("validation_status"),
        "answer_shape": synthesis.get("answer_shape"),
        "stance": synthesis.get("stance"),
        "retrieval_mode": retrieval.get("rules_retrieval_mode"),
        "embedding_backend": retrieval.get("rules_embedding_backend"),
        "embedding_model": retrieval.get("rules_embedding_model"),
        "source_count": retrieval.get("source_count"),
        "planner_terms": _plan_terms(query_plan),
        "intents": list(query_plan.get("intents") or []),
        "selected_sources": [
            _bounded_source_summary(source)
            for source in _answer_sources(answer)[:8]
        ],
    }


def _evaluate_runtime(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    expected_profile = case.get("expected_runtime_profile")
    if expected_profile is None:
        return {"status": STAGE_NOT_APPLICABLE, "failures": []}
    trace = _answer_trace(answer)
    runtime = _mapping(trace.get("runtime"))
    profile = runtime.get("profile") or runtime.get("runtime_profile")
    if profile != expected_profile:
        return _stage_result([f"runtime profile {profile!r} did not match expected {expected_profile!r}"])
    return _stage_result([])


def _evaluate_planner(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    expected_plan = _mapping(case.get("expected_plan"))
    required_terms = _text_list(case.get("required_planner_terms")) + _text_list(expected_plan.get("required_terms"))
    expected_intents = _text_list(case.get("expected_intents")) + _text_list(expected_plan.get("intents"))
    if not required_terms and not expected_intents:
        return {"status": STAGE_NOT_APPLICABLE, "failures": []}

    trace = _answer_trace(answer)
    query_plan = _mapping(_mapping(_mapping(trace.get("stages")).get("query_plan")).get("plan"))
    plan_terms = _plan_terms(query_plan)
    aliases = _mapping(case.get("accepted_planner_aliases")) or _mapping(expected_plan.get("accepted_aliases"))
    failures: list[str] = []
    for term in required_terms:
        alternatives = [term, *_text_list(aliases.get(term))]
        if not any(_contains_term(plan_terms, alternative) for alternative in alternatives):
            failures.append(f"planner missing required term: {term}")
    intents = {str(intent) for intent in query_plan.get("intents") or []}
    for intent in expected_intents:
        if intent not in intents:
            failures.append(f"planner missing expected intent: {intent}")
    return _stage_result(failures)


def _evaluate_retrieval(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    sources = _answer_sources(answer)
    failures: list[str] = []
    expected_sources = list(case.get("expected_sources", []) or []) + list(case.get("required_source_anchors", []) or [])
    for index, predicate in enumerate(expected_sources, start=1):
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
    expected_class = case.get("expected_answer_class") or case.get("expected_response_class")
    expected_evidence = case.get("expected_evidence_status")
    trace = _answer_trace(answer)
    answer_packet = _mapping(_mapping(trace.get("stages")).get("answer_packet"))
    actual_class = answer_packet.get("response_class")
    actual_evidence = answer_packet.get("evidence_status")
    insufficient = _looks_insufficient(str(answer.get("text") or ""))
    if expects_insufficient and not insufficient:
        failures.append("answer did not report insufficient permitted sources")
    if expects_answerable and insufficient:
        failures.append("answer reported insufficiency for an answerable case")
    if expected_class is not None and actual_class != expected_class:
        failures.append(f"response_class {actual_class!r} did not match expected {expected_class!r}")
    if expected_evidence is not None and actual_evidence != expected_evidence:
        failures.append(f"evidence_status {actual_evidence!r} did not match expected {expected_evidence!r}")
    if not expects_insufficient and not expects_answerable and expected_class is None and expected_evidence is None:
        return {"status": STAGE_NOT_APPLICABLE, "failures": []}
    return _stage_result(failures)


def _evaluate_answer_text(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    text = str(answer.get("text") or "")
    folded = text.casefold()
    failures: list[str] = []
    expected_contains = list(case.get("expected_answer_contains", []) or []) + list(case.get("required_answer_contains", []) or [])
    forbidden_contains = list(case.get("forbidden_answer_contains", []) or [])
    for expected in expected_contains:
        if str(expected).casefold() not in folded:
            failures.append(f"answer does not contain expected text: {expected}")
    for pattern in case.get("required_answer_patterns", []) or []:
        if re.search(str(pattern), text, flags=re.IGNORECASE) is None:
            failures.append(f"answer does not match required pattern: {pattern}")
    for forbidden in forbidden_contains:
        if str(forbidden).casefold() in folded:
            failures.append(f"answer contains forbidden text: {forbidden}")
    for pattern in case.get("forbidden_answer_patterns", []) or []:
        if re.search(str(pattern), text, flags=re.IGNORECASE) is not None:
            failures.append(f"answer matches forbidden pattern: {pattern}")
    trace = _answer_trace(answer)
    synthesis = _mapping(_mapping(trace.get("stages")).get("synthesis"))
    expected_synthesis_mode = case.get("expected_synthesis_mode")
    expected_answer_shape = case.get("expected_answer_shape")
    expected_stance = case.get("expected_stance")
    expected_validation = case.get("expected_synthesis_validation_status")
    if expected_synthesis_mode is not None and synthesis.get("mode") != expected_synthesis_mode:
        failures.append(f"synthesis mode {synthesis.get('mode')!r} did not match expected {expected_synthesis_mode!r}")
    if expected_answer_shape is not None and synthesis.get("answer_shape") != expected_answer_shape:
        failures.append(f"answer_shape {synthesis.get('answer_shape')!r} did not match expected {expected_answer_shape!r}")
    if expected_stance is not None and synthesis.get("stance") != expected_stance:
        failures.append(f"stance {synthesis.get('stance')!r} did not match expected {expected_stance!r}")
    if expected_validation is not None and synthesis.get("validation_status") != expected_validation:
        failures.append(
            f"synthesis validation {synthesis.get('validation_status')!r} did not match expected {expected_validation!r}"
        )
    if bool(case.get("forbid_synthesis_fallback")):
        generation = _mapping(trace.get("generation"))
        if generation.get("fallback_used"):
            failures.append(f"synthesis fallback was used: {generation.get('fallback_reason')}")
    if (
        not expected_contains
        and not forbidden_contains
        and not case.get("required_answer_patterns")
        and not case.get("forbidden_answer_patterns")
        and expected_synthesis_mode is None
        and expected_answer_shape is None
        and expected_stance is None
        and expected_validation is None
        and not case.get("forbid_synthesis_fallback")
    ):
        return {"status": STAGE_NOT_APPLICABLE, "failures": []}
    return _stage_result(failures)


def _evaluate_citation(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    required = _text_list(case.get("required_citations"))
    citation_required = bool(case.get("citation_required"))
    if not required and not citation_required:
        return {"status": STAGE_NOT_APPLICABLE, "failures": []}
    text = str(answer.get("text") or "")
    sources = _answer_sources(answer)
    available = {str(source.get("citation") or "") for source in sources}
    failures: list[str] = []
    for citation in required:
        if citation not in text and citation not in available:
            failures.append(f"required citation missing: {citation}")
    if citation_required and "sources:" not in text.casefold() and not sources:
        failures.append("answer does not include source citation details")
    return _stage_result(failures)


def _evaluate_output_policy(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    text = str(answer.get("text") or "")
    max_chars = case.get("max_answer_chars")
    if max_chars is not None and len(text) > int(max_chars):
        failures.append(f"answer length {len(text)} exceeds max_answer_chars {max_chars}")
    for pattern in case.get("forbidden_output_patterns", []) or []:
        if re.search(str(pattern), text, flags=re.IGNORECASE) is not None:
            failures.append(f"answer matches forbidden output pattern: {pattern}")
    if not failures and max_chars is None and not case.get("forbidden_output_patterns"):
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
    for key in ("source_type", "citation", "book_id", "book_title", "title", "relative_path", "section_label"):
        expected = predicate.get(key)
        if expected is not None and str(source.get(key) or "") != str(expected):
            return False
    for key in ("page_start", "page_end"):
        expected = predicate.get(key)
        if expected is not None and source.get(key) != expected:
            return False
    page_start = source.get("page_start")
    if predicate.get("page_start_min") is not None and (page_start is None or int(page_start) < int(predicate["page_start_min"])):
        return False
    if predicate.get("page_start_max") is not None and (page_start is None or int(page_start) > int(predicate["page_start_max"])):
        return False
    contains_checks = {
        "book_id_contains": _source_field(source, "book_id"),
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
    all_text_contains = predicate.get("all_text_contains")
    if isinstance(all_text_contains, list):
        text = _source_text(source).casefold()
        if any(str(expected).casefold() not in text for expected in all_text_contains):
            return False
    any_text_contains = predicate.get("any_text_contains")
    if isinstance(any_text_contains, list):
        text = _source_text(source).casefold()
        if not any(str(expected).casefold() in text for expected in any_text_contains):
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


def _answer_trace(answer: Mapping[str, Any]) -> Mapping[str, Any]:
    trace = answer.get("answer_trace")
    return trace if isinstance(trace, Mapping) else {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _plan_terms(query_plan: Mapping[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in ("canonical_terms", "expanded_terms", "raw_unknown_terms", "required_evidence", "scoring_terms", "low_value_terms"):
        terms.extend(_text_list(query_plan.get(key)))
    entities = query_plan.get("entities")
    if isinstance(entities, Mapping):
        for values in entities.values():
            terms.extend(_text_list(values))
    for query in query_plan.get("retrieval_queries", []) or []:
        if isinstance(query, Mapping):
            terms.extend(_text_list(query.get("text")))
            terms.extend(_text_list(query.get("terms")))
            terms.extend(_text_list(query.get("evidence")))
    terms.extend(_text_list(query_plan.get("semantic_query")))
    terms.extend(_text_list(query_plan.get("scoring_query")))
    return _dedupe_text(terms)


def _contains_term(values: Iterable[str], term: str) -> bool:
    normalized = str(term).casefold()
    return any(normalized in str(value).casefold() for value in values)


def _first_failed_stage(stages: Mapping[str, Mapping[str, Any]]) -> str | None:
    for stage in FAILURE_STAGE_ORDER:
        current = stages.get(stage)
        if isinstance(current, Mapping) and current.get("status") == STAGE_FAILED:
            return stage
    return None


def _bounded_source_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    text = _source_text(source)
    return {
        "citation": source.get("citation"),
        "source_type": source.get("source_type"),
        "book_id": source.get("book_id"),
        "book_title": source.get("book_title") or source.get("title"),
        "page_start": source.get("page_start"),
        "page_end": source.get("page_end"),
        "section_label": source.get("section_label"),
        "retrieval_mode": source.get("retrieval_mode"),
        "evidence_status": source.get("evidence_status"),
        "snippet": text[:320],
    }


def _dedupe_text(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        current = str(value).strip()
        if not current or current in seen:
            continue
        seen.add(current)
        result.append(current)
    return result
