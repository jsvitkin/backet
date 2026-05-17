from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backet import bot_qa
from backet.cli import app


class FakeAnswer:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, Any]:
        return self.payload


def test_bot_qa_runs_cases_against_bundle_and_writes_reports(tmp_path: Path, monkeypatch) -> None:
    bundle = _fake_bundle(tmp_path)
    case_file = _case_file(tmp_path, required_term="blood bond")
    report_dir = tmp_path / "reports"
    monkeypatch.setattr(bot_qa.BotBundle, "load", lambda _path: object())
    monkeypatch.setattr(bot_qa, "answer_bot_query", lambda *_args, **_kwargs: FakeAnswer(_answer_payload("Blood Bond rules.")))

    result = bot_qa.run_bot_qa(bundle, case_files=[case_file], bundle=True, report_output=report_dir)

    assert result.data["ok"] is True
    assert result.data["passed_count"] == 1
    assert (report_dir / "answer-quality.json").exists()
    assert (report_dir / "answer-quality.md").exists()


def test_bot_qa_skips_missing_private_vault_case(tmp_path: Path, monkeypatch) -> None:
    bundle = _fake_bundle(tmp_path)
    case_file = tmp_path / "cases.json"
    case_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "private-case",
                        "question": "secret local vault question",
                        "vault_path": str(tmp_path / "missing-vault"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_qa.BotBundle, "load", lambda _path: object())

    result = bot_qa.run_bot_qa(bundle, case_files=[case_file], bundle=True)

    assert result.data["ok"] is True
    assert result.data["skipped_count"] == 1
    assert result.data["cases"][0]["skip_reason"].startswith("vault_path_missing")
    assert result.data["by_suite"]["standard"]["skipped"] == 1


def test_bot_qa_exploratory_failures_do_not_fail_run(tmp_path: Path, monkeypatch) -> None:
    bundle = _fake_bundle(tmp_path)
    case_file = tmp_path / "cases.json"
    case_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite": "exploratory",
                "severity": "exploratory",
                "cases": [
                    {
                        "id": "future-case",
                        "question": "can I use blush of life?",
                        "required_answer_contains": ["Blush of Life"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_qa.BotBundle, "load", lambda _path: object())
    monkeypatch.setattr(bot_qa, "answer_bot_query", lambda *_args, **_kwargs: FakeAnswer(_answer_payload("unrelated text")))

    result = bot_qa.run_bot_qa(bundle, case_files=[case_file], bundle=True)

    assert result.data["ok"] is True
    assert result.data["failed_count"] == 1
    assert result.data["failed_required_count"] == 0
    assert result.data["cases"][0]["severity"] == "exploratory"


def test_bot_qa_runs_ad_hoc_questions_without_default_cases(tmp_path: Path, monkeypatch) -> None:
    bundle = _fake_bundle(tmp_path)
    monkeypatch.setattr(bot_qa.BotBundle, "load", lambda _path: object())
    monkeypatch.setattr(bot_qa, "answer_bot_query", lambda *_args, **_kwargs: FakeAnswer(_answer_payload("Rouse Check rules.")))

    result = bot_qa.run_bot_qa(bundle, questions=["what is a rouse check?"], bundle=True)

    assert result.data["case_count"] == 1
    assert result.data["cases"][0]["case_id"] == "ad-hoc-1"
    assert result.data["cases"][0]["suite"] == "ad-hoc"
    assert result.data["ok"] is True


def test_bot_qa_cli_json_exits_nonzero_on_required_failure(tmp_path: Path, monkeypatch, runner) -> None:
    bundle = _fake_bundle(tmp_path)
    case_file = _case_file(tmp_path, required_term="dementation")
    monkeypatch.setattr(bot_qa.BotBundle, "load", lambda _path: object())
    monkeypatch.setattr(bot_qa, "answer_bot_query", lambda *_args, **_kwargs: FakeAnswer(_answer_payload("unrelated text")))

    result = runner.invoke(app, ["--json", "bot", "qa", str(bundle), "--bundle", "--case-file", str(case_file)])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["data"]["ok"] is False
    assert payload["data"]["cases"][0]["failure_stage"] in {"planner", "retrieval", "synthesis"}


def test_bot_qa_cli_accepts_question_and_suite_filter(tmp_path: Path, monkeypatch, runner) -> None:
    bundle = _fake_bundle(tmp_path)
    monkeypatch.setattr(bot_qa.BotBundle, "load", lambda _path: object())
    monkeypatch.setattr(bot_qa, "answer_bot_query", lambda *_args, **_kwargs: FakeAnswer(_answer_payload("Rouse Check rules.")))

    result = runner.invoke(
        app,
        [
            "--json",
            "bot",
            "qa",
            str(bundle),
            "--bundle",
            "--question",
            "what is a rouse check?",
            "--suite",
            "ad-hoc",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["case_count"] == 1
    assert payload["data"]["cases"][0]["suite"] == "ad-hoc"


def test_bot_qa_human_output_groups_archetypes_without_raw_payloads(tmp_path: Path, monkeypatch, runner) -> None:
    bundle = _fake_bundle(tmp_path)
    case_file = _case_file(tmp_path, required_term="dementation")
    monkeypatch.setattr(bot_qa.BotBundle, "load", lambda _path: object())
    monkeypatch.setattr(bot_qa, "answer_bot_query", lambda *_args, **_kwargs: FakeAnswer(_answer_payload("unrelated text")))

    result = runner.invoke(
        app,
        [
            "bot",
            "qa",
            str(bundle),
            "--bundle",
            "--case-file",
            str(case_file),
            "--no-fail-on-failure",
        ],
    )

    assert result.exit_code == 0
    assert "Archetypes:" in result.stdout
    assert "Difficulties:" in result.stdout
    assert "debug:" in result.stdout
    assert "{" not in result.stdout
    assert "trace_summary" not in result.stdout
    assert "answer_trace" not in result.stdout
    assert "source_pdf" not in result.stdout


def test_bot_qa_filters_by_archetype_and_difficulty(tmp_path: Path, monkeypatch) -> None:
    bundle = _fake_bundle(tmp_path)
    case_file = tmp_path / "archetypes.json"
    case_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite": "archetype-smoke",
                "severity": "exploratory",
                "cases": [
                    {
                        "id": "definition-case",
                        "question": "what is a rouse check?",
                        "archetype": "definition",
                        "difficulty": "very-easy",
                    },
                    {
                        "id": "targeting-case",
                        "question": "can I use dominate on a vampire?",
                        "archetype": "targeting",
                        "difficulty": "hard",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_qa.BotBundle, "load", lambda _path: object())
    monkeypatch.setattr(bot_qa, "answer_bot_query", lambda *_args, **_kwargs: FakeAnswer(_answer_payload("Rouse Check rules.")))

    result = bot_qa.run_bot_qa(
        bundle,
        case_files=[case_file],
        archetypes=["targeting"],
        difficulties=["hard"],
        bundle=True,
    )

    assert result.data["case_count"] == 1
    assert result.data["cases"][0]["case_id"] == "targeting-case"
    assert result.data["cases"][0]["archetype"] == "targeting"
    assert result.data["active_filters"]["archetypes"] == ["targeting"]
    assert result.data["by_archetype"]["targeting"]["total"] == 1


def test_packaged_standard_cases_avoid_long_source_excerpts() -> None:
    cases = bot_qa.default_answer_quality_case_file()
    payload = json.loads(cases.read_text(encoding="utf-8"))

    for case in payload["cases"]:
        text = json.dumps(case)
        assert len(max(text.split(), key=len)) < 80
        assert "They wanted me to learn a lesson about myself, but I" not in text


def _fake_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_text("{}", encoding="utf-8")
    (bundle / "access-policy.json").write_text("{}", encoding="utf-8")
    return bundle


def _case_file(tmp_path: Path, *, required_term: str) -> Path:
    path = tmp_path / f"{required_term.replace(' ', '-')}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "case-1",
                        "question": "what is this rule?",
                        "archetype": "definition",
                        "difficulty": "easy",
                        "required_planner_terms": [required_term],
                        "expected_sources": [{"source_type": "rules", "text_contains": required_term}],
                        "required_answer_contains": [required_term],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _answer_payload(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "sources": [{"source_type": "rules", "citation": "R1", "content": text}],
        "answer_trace": {
            "stages": {
                "query_plan": {"plan": {"canonical_terms": [text], "intents": ["definition"]}},
                "answer_packet": {"response_class": "answer", "evidence_status": "answerable"},
            },
            "retrieval": {
                "source_count": 1,
                "selected_sources": [{"source_type": "rules", "citation": "R1", "snippet": text}],
                "rules_retrieval_mode": "exact_only",
                "rules_evidence_status": "answerable",
            },
            "generation": {"mode": "template", "fallback_used": False},
        },
    }
