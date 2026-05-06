from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backet.bot_answers import LlamaLocalAnswerGenerator, validate_llama_model_files
from backet.bot_runtime import BotBundle, answer_bot_query
from backet.cli import app
from backet.errors import AppError
from backet.vault import initialize_vault


def test_llama_runtime_prompt_receives_only_permitted_player_sources(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_llama_config(vault)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs are public.")
    _write(vault / "Plot.md", "storyteller", ["plotline"], "# Plot\n\nHidden betrayal by Sabine.")
    output = _export_bundle(runner, vault, tmp_path)
    client = _FakeModelClient("Court customs are public. [V1]")
    bundle = BotBundle.load(output)

    answer = answer_bot_query(
        bundle,
        command="canon.ask",
        question="What customs are public?",
        role_ids=["player-role"],
        model_client=client,
    )

    assert answer.text == "Court customs are public. [V1]"
    assert answer.diagnostics["answer_generation"]["mode"] == "llama-local"
    assert answer.diagnostics["answer_generation"]["fallback_used"] is False
    assert "Court customs are public" in client.prompts[0]
    assert "Hidden betrayal" not in client.prompts[0]
    assert "Sabine" not in client.prompts[0]


def test_llama_generator_falls_back_on_timeout_and_missing_citations() -> None:
    sources = [
        {
            "source_type": "vault",
            "citation": "V1",
            "title": "Player Primer",
            "relative_path": "Player Primer.md",
            "excerpt": "Court customs are public.",
        }
    ]

    timeout = LlamaLocalAnswerGenerator(client=_FailingModelClient("bot_llama_timeout")).generate("customs?", sources)
    missing_citation = LlamaLocalAnswerGenerator(client=_FakeModelClient("Court customs are public.")).generate(
        "customs?",
        sources,
    )

    assert timeout.fallback_used is True
    assert timeout.diagnostics["fallback_reason"] == "bot_llama_timeout"
    assert "[V1]" in timeout.text
    assert missing_citation.fallback_used is True
    assert missing_citation.diagnostics["fallback_reason"] == "bot_llama_output_missing_citation"


def test_llama_generator_uses_endpoint_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKET_LLAMA_ENDPOINT", "http://llama:8080/completion")

    generator = LlamaLocalAnswerGenerator(model_config={})

    assert generator.endpoint == "http://llama:8080/completion"


def test_llama_model_check_validates_vm_local_path_and_checksum(runner, tmp_path: Path) -> None:
    model_bytes = b"fake gguf bytes"
    model_sha = hashlib.sha256(model_bytes).hexdigest()
    vault = _make_vault(tmp_path)
    _write_llama_config(vault, model_sha=model_sha)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs.")
    output = _export_bundle(runner, vault, tmp_path)
    models_root = tmp_path / "models"
    model_path = models_root / "llama-3.2-3b-instruct-q4" / "model.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(model_bytes)

    result = validate_llama_model_files(output, models_root=models_root)
    cli = runner.invoke(app, ["--json", "bot", "model-check", str(output), "--models-root", str(models_root)])

    assert result.data["ok"] is True
    assert result.data["actual_sha256"] == model_sha
    assert cli.exit_code == 0
    assert json.loads(cli.stdout)["data"]["ok"] is True


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    initialize_vault(vault, cli_version="0.1.0")
    return vault


def _export_bundle(runner, vault: Path, tmp_path: Path) -> Path:
    output = tmp_path / "bundle"
    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])
    assert result.exit_code == 0, result.stdout
    return output


def _write_llama_config(vault: Path, model_sha: str = "abc123") -> None:
    (vault / ".backet" / "state" / "bot-config.yaml").write_text(
        "schema_version: 1\n"
        "roles:\n"
        "  player:\n"
        "    - player-role\n"
        "answer_mode: llama-local\n"
        "model:\n"
        "  endpoint: http://127.0.0.1:8080/completion\n"
        "  timeout_seconds: 1\n"
        "  token_budget: 256\n"
        "  fallback: template\n"
        "  path: llama-3.2-3b-instruct-q4/model.gguf\n"
        f"  sha256: {model_sha}\n",
        encoding="utf-8",
    )


def _write(path: Path, visibility: str, topics: list[str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    topic_lines = "".join(f"    - {topic}\n" for topic in topics)
    topics_block = f"  bot_topics:\n{topic_lines}" if topics else ""
    path.write_text(f"---\nbacket:\n  visibility: {visibility}\n{topics_block}---\n\n{body}\n", encoding="utf-8")


class _FakeModelClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str, timeout_seconds: float, token_budget: int) -> str:
        self.prompts.append(prompt)
        return self.response


class _FailingModelClient:
    def __init__(self, code: str) -> None:
        self.code = code

    def complete(self, prompt: str, timeout_seconds: float, token_budget: int) -> str:
        raise AppError(code=self.code, message="fake failure", exit_code=2)
