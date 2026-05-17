from __future__ import annotations

import json
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from backet.answer_quality import evaluate_answer_quality_case, load_answer_quality_cases
from backet.bot_answers import TemplateAnswerGenerator
from backet.bot_export import export_bot_bundle
from backet.bot_runtime import BotBundle, answer_bot_query
from backet.errors import AppError
from backet.models import CommandResult

DEFAULT_QA_RESOURCE_PACKAGE = "backet.resources.answer_quality"
DEFAULT_QA_RESOURCE_NAME = "standard-rules-cases.json"


def run_bot_qa(
    target: Path,
    *,
    case_files: list[Path] | None = None,
    questions: list[str] | None = None,
    suites: list[str] | None = None,
    archetypes: list[str] | None = None,
    difficulties: list[str] | None = None,
    command: str = "rules.ask",
    user_id: str | None = None,
    role_ids: list[str] | None = None,
    private: bool | None = None,
    limit: int = 4,
    use_model: bool = False,
    bundle: bool = False,
    report_output: Path | None = None,
    force: bool = False,
) -> CommandResult:
    cases = _load_cases(
        case_files,
        questions=questions or [],
        suites=suites or [],
        archetypes=archetypes or [],
        difficulties=difficulties or [],
    )
    resolved_target = target.expanduser().resolve()
    if bundle or _looks_like_bundle(resolved_target):
        return _run_qa_with_bundle(
            bundle_root=resolved_target,
            cases=cases,
            command=command,
            user_id=user_id,
            role_ids=role_ids or [],
            private=private,
            limit=limit,
            use_model=use_model,
            report_output=report_output,
            target_kind="bundle",
            active_filters={
                "suites": suites or [],
                "archetypes": archetypes or [],
                "difficulties": difficulties or [],
            },
        )

    if not resolved_target.exists() or not resolved_target.is_dir():
        raise AppError(
            code="bot_qa_target_missing",
            message="Bot QA target must be a vault directory or exported bundle.",
            hint="Pass a vault path, or pass --bundle for an exported bot bundle.",
            details={"target": str(resolved_target)},
            exit_code=2,
        )
    with tempfile.TemporaryDirectory(prefix="backet-bot-qa-") as temp_dir:
        bundle_root = Path(temp_dir) / "bundle"
        export = export_bot_bundle(resolved_target, output_path=bundle_root, force=True)
        result = _run_qa_with_bundle(
            bundle_root=bundle_root,
            cases=cases,
            command=command,
            user_id=user_id,
            role_ids=role_ids or [],
            private=private,
            limit=limit,
            use_model=use_model,
            report_output=report_output,
            target_kind="vault",
            vault_root=resolved_target,
            active_filters={
                "suites": suites or [],
                "archetypes": archetypes or [],
                "difficulties": difficulties or [],
            },
        )
        result.issues.extend(export.issues)
        result.data["export_summary"] = export.data.get("summary", {})
        return result


def default_answer_quality_case_file() -> Path:
    resource = resources.files(DEFAULT_QA_RESOURCE_PACKAGE).joinpath(DEFAULT_QA_RESOURCE_NAME)
    with resources.as_file(resource) as path:
        return Path(path)


def _run_qa_with_bundle(
    *,
    bundle_root: Path,
    cases: list[dict[str, Any]],
    command: str,
    user_id: str | None,
    role_ids: list[str],
    private: bool | None,
    limit: int,
    use_model: bool,
    report_output: Path | None,
    target_kind: str,
    active_filters: dict[str, list[str]],
    vault_root: Path | None = None,
) -> CommandResult:
    bundle_obj = BotBundle.load(bundle_root)
    answer_generator = None if use_model else TemplateAnswerGenerator()
    case_results: list[dict[str, Any]] = []
    for case in cases:
        skip_reason = _skip_reason(case)
        if skip_reason is not None:
            case_results.append(
            {
                "case_id": case.get("id"),
                "base_case_id": case.get("base_case_id"),
                "variant_id": case.get("variant_id"),
                "variant_metadata": case.get("variant_metadata", {}),
                "question": case.get("question"),
                "suite": case.get("suite"),
                "category": case.get("category"),
                "archetype": case.get("archetype"),
                "evidence_contract_id": case.get("expected_contract_id") or case.get("evidence_contract_id"),
                "severity": case.get("severity"),
                "difficulty": case.get("difficulty"),
                    "required": _case_required(case),
                    "skipped": True,
                    "skip_reason": skip_reason,
                    "passed": True,
                    "failure_stage": None,
                }
            )
            continue
        case_command = str(case.get("command") or command)
        answer = answer_bot_query(
            bundle_obj,
            command=case_command,
            question=str(case["question"]),
            user_id=str(case.get("user_id") or user_id or "") or None,
            role_ids=[str(role) for role in case.get("role_ids", role_ids) or []],
            private=private,
            limit=int(case.get("limit") or limit),
            answer_generator=answer_generator,
        )
        evaluation = evaluate_answer_quality_case(answer.to_dict(), case)
        case_results.append(
            {
                **evaluation,
                "suite": case.get("suite"),
                "category": case.get("category"),
                "archetype": case.get("archetype"),
                "evidence_contract_id": case.get("expected_contract_id") or case.get("evidence_contract_id"),
                "required_facets": case.get("required_facets", []),
                "answerability_status": (evaluation.get("trace_summary") or {}).get("answerability_status"),
                "base_case_id": case.get("base_case_id"),
                "variant_id": case.get("variant_id"),
                "variant_metadata": case.get("variant_metadata", {}),
                "severity": case.get("severity"),
                "required": _case_required(case),
                "skipped": False,
                "command": case_command,
                "answer": _answer_summary(answer.to_dict()),
                "next_debug_command": _next_debug_command(target_kind, vault_root or bundle_root, case),
            }
        )

    passed = sum(1 for item in case_results if item.get("passed") and not item.get("skipped"))
    failed = [item for item in case_results if not item.get("passed")]
    failed_required = [item for item in failed if item.get("required", True)]
    skipped = [item for item in case_results if item.get("skipped")]
    data = {
        "target": str(vault_root or bundle_root),
        "target_kind": target_kind,
        "bundle": str(bundle_root),
        "mode": "configured model" if use_model else "template-only",
        "case_count": len(case_results),
        "passed_count": passed,
        "failed_count": len(failed),
        "failed_required_count": len(failed_required),
        "skipped_count": len(skipped),
        "by_suite": _summary_counts(case_results, "suite"),
        "by_category": _summary_counts(case_results, "category"),
        "by_archetype": _summary_counts(case_results, "archetype"),
        "by_difficulty": _summary_counts(case_results, "difficulty"),
        "by_contract": _summary_counts(case_results, "evidence_contract_id"),
        "by_answerability": _summary_counts(case_results, "answerability_status"),
        "by_failure_stage": _summary_counts(case_results, "failure_stage"),
        "active_filters": {
            "suites": active_filters.get("suites", []),
            "archetypes": active_filters.get("archetypes", []),
            "difficulties": active_filters.get("difficulties", []),
        },
        "ok": not failed_required,
        "cases": case_results,
    }
    created: list[str] = []
    if report_output is not None:
        created = _write_reports(report_output.expanduser().resolve(), data)
    return CommandResult(
        message="Bot answer QA complete",
        data=data,
        created=created,
    )


def _load_cases(
    case_files: list[Path] | None,
    *,
    questions: list[str],
    suites: list[str],
    archetypes: list[str],
    difficulties: list[str],
) -> list[dict[str, Any]]:
    paths = case_files or ([] if questions else [default_answer_quality_case_file()])
    cases: list[dict[str, Any]] = []
    for path in paths:
        try:
            cases.extend(load_answer_quality_cases(path.expanduser().resolve()))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise AppError(
                code="bot_qa_case_file_invalid",
                message="Bot QA case file could not be loaded.",
                hint="Check the case file path and schema.",
                details={"case_file": str(path), "error": str(exc)},
                exit_code=2,
            ) from exc
    for index, question in enumerate(questions, start=1):
        text = str(question).strip()
        if not text:
            continue
        cases.append(
            {
                "id": f"ad-hoc-{index}",
                "suite": "ad-hoc",
                "category": "ad-hoc",
                "archetype": "ad-hoc",
                "severity": "exploratory",
                "required": False,
                "difficulty": "ungraded",
                "command": "rules.ask",
                "question": text,
            }
        )
    suite_filter = {str(suite) for suite in suites if str(suite)}
    if suite_filter:
        cases = [case for case in cases if str(case.get("suite") or "") in suite_filter]
    archetype_filter = {str(archetype) for archetype in archetypes if str(archetype)}
    if archetype_filter:
        cases = [case for case in cases if str(case.get("archetype") or "") in archetype_filter]
    difficulty_filter = {str(difficulty) for difficulty in difficulties if str(difficulty)}
    if difficulty_filter:
        cases = [case for case in cases if str(case.get("difficulty") or "") in difficulty_filter]
    return cases


def _looks_like_bundle(path: Path) -> bool:
    return path.is_dir() and (path / "manifest.json").exists() and (path / "access-policy.json").exists()


def _skip_reason(case: dict[str, Any]) -> str | None:
    vault_path = case.get("vault_path")
    if vault_path and not Path(str(vault_path)).expanduser().exists():
        return f"vault_path_missing:{vault_path}"
    bundle_path = case.get("bundle_path")
    if bundle_path and not Path(str(bundle_path)).expanduser().exists():
        return f"bundle_path_missing:{bundle_path}"
    return None


def _case_required(case: dict[str, Any]) -> bool:
    if "required" in case:
        return bool(case.get("required"))
    return str(case.get("severity") or "required") == "required"


def _next_debug_command(target_kind: str, target: Path, case: dict[str, Any]) -> str:
    parts = ["backet", "bot", "qa", str(target)]
    if target_kind == "bundle":
        parts.append("--bundle")
    if case.get("suite"):
        parts.extend(["--suite", str(case.get("suite"))])
    if case.get("archetype"):
        parts.extend(["--archetype", str(case.get("archetype"))])
    if case.get("difficulty"):
        parts.extend(["--difficulty", str(case.get("difficulty"))])
    parts.append("--no-fail-on-failure")
    return " ".join(_shell_quote(part) for part in parts)


def _shell_quote(value: str) -> str:
    text = str(value)
    if not text or any(char.isspace() for char in text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _answer_summary(answer: dict[str, Any]) -> dict[str, Any]:
    trace = answer.get("answer_trace") if isinstance(answer.get("answer_trace"), dict) else {}
    generation = trace.get("generation") if isinstance(trace.get("generation"), dict) else {}
    retrieval = trace.get("retrieval") if isinstance(trace.get("retrieval"), dict) else {}
    stages = trace.get("stages") if isinstance(trace.get("stages"), dict) else {}
    synthesis = stages.get("synthesis") if isinstance(stages.get("synthesis"), dict) else {}
    answerability = stages.get("answerability") if isinstance(stages.get("answerability"), dict) else {}
    return {
        "text": str(answer.get("text") or "")[:900],
        "answer_mode": generation.get("mode"),
        "fallback_used": generation.get("fallback_used"),
        "synthesis_mode": synthesis.get("mode"),
        "synthesis_validation_status": synthesis.get("validation_status"),
        "answer_shape": synthesis.get("answer_shape"),
        "answerability_status": answerability.get("answerability_status"),
        "missing_facets": list(answerability.get("missing_facets") or []),
        "satisfied_facets": list(answerability.get("satisfied_facets") or []),
        "failure_stage": answerability.get("failure_stage"),
        "source_count": retrieval.get("source_count"),
        "rules_retrieval_mode": retrieval.get("rules_retrieval_mode"),
        "rules_evidence_status": retrieval.get("rules_evidence_status"),
        "selected_sources": [
            {
                "citation": source.get("citation"),
                "source_type": source.get("source_type"),
                "book_id": source.get("book_id"),
                "book_title": source.get("book_title") or source.get("title"),
                "page_start": source.get("page_start"),
                "page_end": source.get("page_end"),
                "section_label": source.get("section_label"),
                "rule_unit_authority_roles": source.get("rule_unit_authority_roles", []),
                "rule_unit_answer_facets": source.get("rule_unit_answer_facets", []),
            }
            for source in list(answer.get("sources") or [])[:6]
            if isinstance(source, dict)
        ],
    }


def _summary_counts(case_results: list[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for item in case_results:
        label = str(item.get(key) or "unspecified")
        bucket = counts.setdefault(label, {"total": 0, "passed": 0, "failed": 0, "skipped": 0})
        bucket["total"] += 1
        if item.get("skipped"):
            bucket["skipped"] += 1
        elif item.get("passed"):
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
    return counts


def _write_reports(output: Path, data: dict[str, Any]) -> list[str]:
    if output.suffix.lower() == ".json":
        json_path = output
        markdown_path = output.with_suffix(".md")
    else:
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "answer-quality.json"
        markdown_path = output / "answer-quality.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_report(data), encoding="utf-8")
    return [str(json_path), str(markdown_path)]


def _markdown_report(data: dict[str, Any]) -> str:
    lines = [
        "# Bot Answer QA",
        "",
        f"- Target: {data.get('target')}",
        f"- Mode: {data.get('mode')}",
        f"- Cases: {data.get('case_count')}",
        f"- Passed: {data.get('passed_count')}",
        f"- Failed: {data.get('failed_count')}",
        f"- Skipped: {data.get('skipped_count')}",
        "",
        "## Summary",
        "",
    ]
    for title, key in (
        ("Suite", "by_suite"),
        ("Archetype", "by_archetype"),
        ("Difficulty", "by_difficulty"),
        ("Contract", "by_contract"),
        ("Failure stage", "by_failure_stage"),
    ):
        for label, payload in sorted(dict(data.get(key, {}) or {}).items()):
            if isinstance(payload, dict):
                lines.append(
                    f"- {title} `{label}`: {payload.get('passed', 0)} passed, {payload.get('failed', 0)} failed, {payload.get('skipped', 0)} skipped"
                )
    lines.extend(
        [
            "",
            "## Cases",
            "",
        ]
    )
    for case in data.get("cases", []):
        if not isinstance(case, dict):
            continue
        status = "skipped" if case.get("skipped") else ("passed" if case.get("passed") else "failed")
        meta = ", ".join(
            str(value)
            for value in (
                case.get("suite"),
                case.get("category"),
                case.get("archetype"),
                case.get("difficulty"),
                case.get("evidence_contract_id"),
                case.get("severity"),
            )
            if value
        )
        suffix = f" ({meta})" if meta else ""
        lines.append(f"- {case.get('case_id')}: {status}{suffix}")
        if case.get("failure_stage"):
            lines.append(f"  - Stage: {case.get('failure_stage')}")
        if case.get("skip_reason"):
            lines.append(f"  - Skip: {case.get('skip_reason')}")
        answer = case.get("answer") if isinstance(case.get("answer"), dict) else {}
        missing_facets = ", ".join(str(item) for item in answer.get("missing_facets", []) or [])
        if missing_facets:
            lines.append(f"  - Missing facets: {missing_facets}")
        if case.get("next_debug_command") and not case.get("passed"):
            lines.append(f"  - Debug: `{case.get('next_debug_command')}`")
    lines.append("")
    return "\n".join(lines)
