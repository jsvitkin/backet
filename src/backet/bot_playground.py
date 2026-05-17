from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from backet.bot_answers import TemplateAnswerGenerator, clean_bot_source_text
from backet.bot_export import export_bot_bundle
from backet.bot_runtime import BotBundle, answer_bot_query, sanitize_discord_mentions
from backet.errors import AppError
from backet.models import CommandResult


def run_bot_playground(
    vault_root: Path,
    questions: list[str],
    command: str = "rules.ask",
    user_id: str | None = None,
    role_ids: list[str] | None = None,
    private: bool | None = None,
    limit: int = 4,
    use_model: bool = False,
    bundle_output: Path | None = None,
    force: bool = False,
) -> CommandResult:
    cleaned_questions = [question.strip() for question in questions if question.strip()]
    if not cleaned_questions:
        raise AppError(
            code="bot_playground_question_missing",
            message="No playground question was provided.",
            hint="Pass a question argument, or repeat --question for several runs.",
            exit_code=2,
        )

    if bundle_output is None:
        with tempfile.TemporaryDirectory(prefix="backet-bot-playground-") as temp_dir:
            return _run_playground_with_bundle(
                vault_root=vault_root,
                bundle_output=Path(temp_dir) / "bundle",
                questions=cleaned_questions,
                command=command,
                user_id=user_id,
                role_ids=role_ids or [],
                private=private,
                limit=limit,
                use_model=use_model,
                force=True,
                temporary_bundle=True,
            )

    output = bundle_output.expanduser().resolve()
    return _run_playground_with_bundle(
        vault_root=vault_root,
        bundle_output=output,
        questions=cleaned_questions,
        command=command,
        user_id=user_id,
        role_ids=role_ids or [],
        private=private,
        limit=limit,
        use_model=use_model,
        force=force,
        temporary_bundle=False,
    )


def _run_playground_with_bundle(
    *,
    vault_root: Path,
    bundle_output: Path,
    questions: list[str],
    command: str,
    user_id: str | None,
    role_ids: list[str],
    private: bool | None,
    limit: int,
    use_model: bool,
    force: bool,
    temporary_bundle: bool,
) -> CommandResult:
    if force and bundle_output.exists():
        if bundle_output.is_dir():
            shutil.rmtree(bundle_output)
        else:
            bundle_output.unlink()
    export = export_bot_bundle(vault_root.expanduser().resolve(), output_path=bundle_output, force=force)
    bundle = BotBundle.load(bundle_output)
    answer_generator = None if use_model else TemplateAnswerGenerator()
    runs: list[dict[str, Any]] = []
    for question in questions:
        started = time.monotonic()
        answer = answer_bot_query(
            bundle,
            command=command,
            question=question,
            user_id=user_id,
            role_ids=role_ids,
            private=private,
            limit=limit,
            answer_generator=answer_generator,
        )
        elapsed = time.monotonic() - started
        runs.append(
            {
                "question": question,
                "elapsed_seconds": round(elapsed, 3),
                "answer": answer.to_dict(),
                "source_debug": [_source_debug(source) for source in answer.sources],
            }
        )

    return CommandResult(
        message="Bot playground run complete",
        issues=export.issues,
        data={
            "vault": str(vault_root.expanduser().resolve()),
            "bundle": "temporary" if temporary_bundle else str(bundle_output),
            "temporary_bundle": temporary_bundle,
            "command": command,
            "mode": "configured model" if use_model else "template-only",
            "limit": limit,
            "export_summary": export.data.get("summary", {}),
            "runs": runs,
        },
    )


def _source_debug(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "citation": source.get("citation"),
        "source_type": source.get("source_type"),
        "title": source.get("title") or source.get("book_title"),
        "relative_path": source.get("relative_path"),
        "page_start": source.get("page_start"),
        "page_end": source.get("page_end"),
        "section_label": source.get("section_label"),
        "score": source.get("score"),
        "match_reasons": source.get("match_reasons", []),
        "retrieval_mode": source.get("retrieval_mode"),
        "embedding_backend": source.get("embedding_backend"),
        "embedding_model": source.get("embedding_model"),
        "evidence_status": source.get("evidence_status"),
        "evidence_cues": source.get("evidence_cues", []),
        "retrieval_channels": source.get("retrieval_channels", []),
        "excerpt": sanitize_discord_mentions(clean_bot_source_text(str(source.get("excerpt") or source.get("content") or "")))[:500],
    }
