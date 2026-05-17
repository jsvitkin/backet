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
    cases = _load_cases(case_files)
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
                    "question": case.get("question"),
                    "difficulty": case.get("difficulty"),
                    "required": bool(case.get("required", True)),
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
                "required": bool(case.get("required", True)),
                "skipped": False,
                "command": case_command,
                "answer": _answer_summary(answer.to_dict()),
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


def _load_cases(case_files: list[Path] | None) -> list[dict[str, Any]]:
    paths = case_files or [default_answer_quality_case_file()]
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


def _answer_summary(answer: dict[str, Any]) -> dict[str, Any]:
    trace = answer.get("answer_trace") if isinstance(answer.get("answer_trace"), dict) else {}
    generation = trace.get("generation") if isinstance(trace.get("generation"), dict) else {}
    retrieval = trace.get("retrieval") if isinstance(trace.get("retrieval"), dict) else {}
    stages = trace.get("stages") if isinstance(trace.get("stages"), dict) else {}
    synthesis = stages.get("synthesis") if isinstance(stages.get("synthesis"), dict) else {}
    return {
        "text": str(answer.get("text") or "")[:900],
        "answer_mode": generation.get("mode"),
        "fallback_used": generation.get("fallback_used"),
        "synthesis_mode": synthesis.get("mode"),
        "synthesis_validation_status": synthesis.get("validation_status"),
        "answer_shape": synthesis.get("answer_shape"),
        "source_count": retrieval.get("source_count"),
        "rules_retrieval_mode": retrieval.get("rules_retrieval_mode"),
        "rules_evidence_status": retrieval.get("rules_evidence_status"),
    }


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
        "## Cases",
        "",
    ]
    for case in data.get("cases", []):
        if not isinstance(case, dict):
            continue
        status = "skipped" if case.get("skipped") else ("passed" if case.get("passed") else "failed")
        lines.append(f"- {case.get('case_id')}: {status}")
        if case.get("failure_stage"):
            lines.append(f"  - Stage: {case.get('failure_stage')}")
        if case.get("skip_reason"):
            lines.append(f"  - Skip: {case.get('skip_reason')}")
    lines.append("")
    return "\n".join(lines)
