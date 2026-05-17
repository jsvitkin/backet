from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

ANSWER_QUALITY_CASE_SCHEMA_VERSION = 1
STAGE_PASSED = "passed"
STAGE_FAILED = "failed"
STAGE_NOT_APPLICABLE = "not_applicable"
FAILURE_STAGE_ORDER = (
    "runtime",
    "planner",
    "retrieval",
    "answerability",
    "claim_support",
    "synthesis",
    "citation",
    "output_policy",
)
CASE_REQUIRED_FIELDS = ("id", "question")
CASE_SEVERITIES = ("required", "exploratory", "calibration", "private")
CASE_FIELD_TYPES = {
    "suite": str,
    "category": str,
    "severity": str,
    "expected_failure_stage": str,
    "expected_first_failure_stage": str,
    "direct_answer_contains": list,
    "required_direct_answer_contains": list,
    "direct_answer_patterns": list,
    "required_direct_answer_patterns": list,
    "required_claim_patterns": list,
    "forbidden_claim_patterns": list,
}
STAGE_ALIASES = {
    "answer": "synthesis",
    "claim-support": "claim_support",
    "claim_support": "claim_support",
    "output-policy": "output_policy",
    "output_policy": "output_policy",
}


def load_answer_quality_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = int(payload.get("schema_version", 0))
    if schema_version != ANSWER_QUALITY_CASE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported answer quality case schema: {schema_version}")
    suite_name = str(payload.get("suite") or payload.get("name") or "standard")
    default_category = str(payload.get("category") or "uncategorized")
    default_severity = str(payload.get("severity") or "required")
    _validate_severity(default_severity, "severity")
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
        current = dict(case)
        _validate_case_shape(current, index)
        current.setdefault("suite", suite_name)
        current.setdefault("category", default_category)
        if "severity" in current and current.get("severity") is not None:
            severity = str(current.get("severity"))
        elif "required" in current:
            severity = "required" if bool(current.get("required")) else "exploratory"
        else:
            severity = default_severity
        _validate_severity(severity, f"cases[{index}].severity")
        current["severity"] = severity
        current["required"] = bool(current.get("required")) if "required" in current else severity == "required"
        if stage := current.get("expected_first_failure_stage"):
            current["expected_failure_stage"] = _normalize_stage_name(str(stage), f"cases[{index}].expected_first_failure_stage")
        if stage := current.get("expected_failure_stage"):
            current["expected_failure_stage"] = _normalize_stage_name(str(stage), f"cases[{index}].expected_failure_stage")
        validated.append(current)
    return validated


def evaluate_answer_quality_case(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _evaluate_runtime(answer, case)
    planner = _evaluate_planner(answer, case)
    retrieval = _evaluate_retrieval(answer, case)
    answerability = _evaluate_answerability(answer, case)
    claim_support = _evaluate_claim_support(answer, case)
    synthesis = _evaluate_answer_text(answer, case)
    citation = _evaluate_citation(answer, case)
    output_policy = _evaluate_output_policy(answer, case)
    stages = {
        "runtime": runtime,
        "planner": planner,
        "retrieval": retrieval,
        "answerability": answerability,
        "claim_support": claim_support,
        "synthesis": synthesis,
        "answer": synthesis,
        "citation": citation,
        "output_policy": output_policy,
    }
    first_failed = _first_failed_stage(stages)
    expected_failure_stage = case.get("expected_failure_stage")
    expected_failure_matched = expected_failure_stage is not None and first_failed == expected_failure_stage
    passed = first_failed is None if expected_failure_stage is None else expected_failure_matched
    return {
        "case_id": case.get("id"),
        "question": case.get("question"),
        "suite": case.get("suite"),
        "category": case.get("category"),
        "severity": case.get("severity"),
        "difficulty": case.get("difficulty"),
        "required": bool(case.get("required", case.get("severity") == "required")),
        "passed": passed,
        "failure_stage": first_failed,
        "expected_failure_stage": expected_failure_stage,
        "expected_failure_matched": expected_failure_matched,
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
        "selected_source_count": len(_answer_sources(answer)),
        "fallback_reason": generation.get("fallback_reason"),
        "planner_terms": _plan_terms(query_plan),
        "intents": list(query_plan.get("intents") or []),
        "resolved_entities": _resolved_entity_names(query_plan.get("resolved_entities")),
        "unresolved_terms": _text_list(query_plan.get("unresolved_high_value_terms")),
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
    direct_text = _direct_answer_text(text)
    folded = text.casefold()
    direct_folded = direct_text.casefold()
    failures: list[str] = []
    expected_contains = list(case.get("expected_answer_contains", []) or []) + list(case.get("required_answer_contains", []) or [])
    forbidden_contains = list(case.get("forbidden_answer_contains", []) or [])
    for expected in expected_contains:
        if str(expected).casefold() not in folded:
            failures.append(f"answer does not contain expected text: {expected}")
    direct_contains = list(case.get("direct_answer_contains", []) or []) + list(case.get("required_direct_answer_contains", []) or [])
    for expected in direct_contains:
        if str(expected).casefold() not in direct_folded:
            failures.append(f"direct answer does not contain expected text: {expected}")
    for pattern in case.get("required_answer_patterns", []) or []:
        if re.search(str(pattern), text, flags=re.IGNORECASE) is None:
            failures.append(f"answer does not match required pattern: {pattern}")
    direct_patterns = list(case.get("direct_answer_patterns", []) or []) + list(case.get("required_direct_answer_patterns", []) or [])
    for pattern in direct_patterns:
        if re.search(str(pattern), direct_text, flags=re.IGNORECASE) is None:
            failures.append(f"direct answer does not match required pattern: {pattern}")
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
        and not direct_contains
        and not direct_patterns
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
    if citation_required and "sources:" not in text.casefold() and "source:" not in text.casefold():
        failures.append("answer does not include source citation details")
    return _stage_result(failures)


def _evaluate_claim_support(answer: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    required_patterns = _text_list(case.get("required_claim_patterns"))
    forbidden_patterns = _text_list(case.get("forbidden_claim_patterns"))
    expected_stance = case.get("expected_claim_stance")
    forbid_unsupported = bool(case.get("forbid_unsupported_final_text"))
    if not required_patterns and not forbidden_patterns and expected_stance is None and not forbid_unsupported:
        return {"status": STAGE_NOT_APPLICABLE, "failures": []}
    claims = _answer_claims(answer)
    claim_text = "\n".join(str(claim.get("text") or claim.get("claim") or "") for claim in claims)
    failures: list[str] = []
    if required_patterns and not claims:
        failures.append("no claim diagnostics available")
    for pattern in required_patterns:
        if re.search(str(pattern), claim_text, flags=re.IGNORECASE) is None:
            failures.append(f"validated claims do not match required pattern: {pattern}")
    for pattern in forbidden_patterns:
        if re.search(str(pattern), claim_text, flags=re.IGNORECASE) is not None:
            failures.append(f"validated claims match forbidden pattern: {pattern}")
    if expected_stance is not None:
        stances = {str(claim.get("stance") or "") for claim in claims}
        if str(expected_stance) not in stances:
            failures.append(f"claim stance {sorted(stances)!r} did not include expected {expected_stance!r}")
    if forbid_unsupported:
        support = _mapping(_mapping(_answer_trace(answer).get("stages")).get("claim_support"))
        unsupported = support.get("unsupported_final_text")
        if unsupported:
            failures.append("final answer includes unsupported text")
        if not support and not claims:
            failures.append("no final answer support mapping available")
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


def _answer_claims(answer: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    trace = _answer_trace(answer)
    stages = _mapping(trace.get("stages"))
    claim_stage = _mapping(stages.get("claim_support")) or _mapping(stages.get("claims"))
    raw_claims = claim_stage.get("claims") or claim_stage.get("validated_claims") or trace.get("claims")
    if not isinstance(raw_claims, list):
        return []
    return [claim for claim in raw_claims if isinstance(claim, Mapping)]


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


def _resolved_entity_names(value: Any) -> list[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, bytearray, Mapping)):
        return _text_list(value)
    names: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            name = item.get("canonical_name") or item.get("entity_id")
            if name:
                names.append(str(name))
        elif str(item):
            names.append(str(item))
    return names


def _direct_answer_text(text: str) -> str:
    lines: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        lowered = stripped.casefold().strip("*: ")
        if lowered.startswith("sources") or lowered.startswith("source detail") or lowered.startswith("evidence"):
            break
        if lowered in {"short answer", "answer"}:
            continue
        lines.append(stripped)
        if len(lines) >= 4:
            break
    return " ".join(lines) if lines else str(text or "")


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


def _validate_case_shape(case: Mapping[str, Any], index: int) -> None:
    for field, expected_type in CASE_FIELD_TYPES.items():
        if field not in case or case[field] is None:
            continue
        value = case[field]
        if expected_type is list and isinstance(value, str):
            continue
        if not isinstance(value, expected_type):
            raise ValueError(f"cases[{index}].{field} must be {expected_type.__name__}")


def _validate_severity(severity: str, field_path: str) -> None:
    if severity not in CASE_SEVERITIES:
        raise ValueError(f"{field_path} must be one of {', '.join(CASE_SEVERITIES)}")


def _normalize_stage_name(stage: str, field_path: str) -> str:
    normalized = STAGE_ALIASES.get(stage, stage)
    valid = set(FAILURE_STAGE_ORDER)
    if normalized not in valid:
        raise ValueError(f"{field_path} must be one of {', '.join(FAILURE_STAGE_ORDER)}")
    return normalized


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
