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
