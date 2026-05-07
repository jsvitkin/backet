from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backet.bot_answers import LlamaLocalAnswerGenerator, TemplateAnswerGenerator, build_llama_prompt, validate_llama_model_files
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
        },
    ]

    timeout = LlamaLocalAnswerGenerator(client=_FailingModelClient("bot_llama_timeout")).generate("customs?", sources)
    missing_citation = LlamaLocalAnswerGenerator(client=_FakeModelClient("Court customs are public.")).generate(
        "customs?",
        sources,
    )

    assert timeout.fallback_used is True
    assert timeout.diagnostics["fallback_reason"] == "bot_llama_timeout"
    assert "Player Primer" in timeout.text
    assert "[V1]" not in timeout.text
    assert missing_citation.fallback_used is True
    assert missing_citation.diagnostics["fallback_reason"] == "bot_llama_output_missing_citation"


def test_answer_context_windows_use_full_source_content_near_question_terms() -> None:
    sources = [
        {
            "source_type": "rules",
            "citation": "R1",
            "book_title": "Core Rulebook",
            "page_start": 222,
            "page_end": 222,
            "section_label": "Frenzy",
            "excerpt": "Fury frenzy and table fragments before the useful answer.",
            "content": (
                "Fury frenzy and unrelated table fragments. "
                "Many filler words appear before the useful rule text. " * 8
                + "Hunger frenzy: temptation causes hunger frenzy; the Beast always craves more blood. "
                "Every time a vampire fails a Rouse Check while at Hunger 5, they must make a hunger frenzy test. "
                "During a hunger frenzy, the vampire seeks fresh human blood from the closest source."
            ),
        },
        {
            "source_type": "rules",
            "citation": "R2",
            "book_title": "Noisy Supplement",
            "page_start": 99,
            "page_end": 99,
            "section_label": "Unrelated",
            "excerpt": "A semantic-only source that does not contain the actual query terms.",
            "content": "A semantic-only source about debts, privacy, and unrelated table fragments.",
            "match_reasons": ["semantic"],
            "score": 0.42,
        },
    ]

    template = TemplateAnswerGenerator().generate("What is a hunger frenzy?", sources)
    prompt = build_llama_prompt("What is a hunger frenzy?", sources, token_budget=64)
    normalized_template = " ".join(template.text.replace("> ", "").split())

    assert "**Short answer:**" in template.text
    assert "Hunger frenzy: temptation causes hunger frenzy" in template.text
    assert "fresh human blood from the closest source" in normalized_template
    assert "Noisy Supplement" not in template.text
    assert "temptation causes hunger frenzy" in prompt.lower()
    assert "Noisy Supplement" not in prompt
    assert "Fury frenzy and unrelated table fragments. Many filler words" not in prompt


def test_template_answer_cleans_pdf_heading_noise() -> None:
    sources = [
        {
            "source_type": "rules",
            "citation": "R1",
            "book_title": "Core Rulebook",
            "page_start": 265,
            "page_end": 265,
            "section_label": "D I S C I P L I N E S",
            "content": "Mask of a Thousand Faces lets the vampire mimic a studied human appearance.",
        }
    ]

    template = TemplateAnswerGenerator().generate("How does mask of a thousand faces work?", sources)

    assert "D I S C I P L I N E S" not in template.text
    assert "Core Rulebook p. 265" in template.text
    assert "> Mask of a Thousand Faces lets" in template.text


def test_template_answer_skips_pdf_tracker_glyph_fragments() -> None:
    sources = [
        {
            "source_type": "rules",
            "citation": "R1",
            "book_title": "Core Rulebook",
            "page_start": 241,
            "page_end": 241,
            "section_label": "Humanity",
            "content": (
                "For example, this represents a rating of Humanity 6: \ue0ee\ue0ee\ue0ef\ue0ef "
                "Stains can mark corruption on the Humanity track. "
                "If too many Stains build up without repentance or redress, Humanity might drop."
            ),
        }
    ]

    template = TemplateAnswerGenerator().generate("How do stains work?", sources)

    assert "\ue0ee" not in template.text
    assert "If too many Stains build up" in template.text


def test_template_answer_extracts_predator_pool_rows_without_source_codes() -> None:
    sources = [
        {
            "source_type": "rules",
            "citation": "R1",
            "book_title": "Core Rulebook",
            "page_start": 309,
            "page_end": 309,
            "section_label": "Predator Pools",
            "content": (
                "Predator Pools explain the hunting approach. "
                "alleycat: Strength + Brawl: You take blood by force or threat."
            ),
        }
    ]

    template = TemplateAnswerGenerator().generate(
        "Whats the hunting dicepool for an alley cat predator type vampire",
        sources,
    )

    assert "Alley Cat hunting dice pool: Strength + Brawl." in template.text
    assert "[R1]" not in template.text
    assert "**Core Rulebook p. 309 (Predator Pools)**" in template.text


def test_broad_rules_explanation_uses_fuller_answer_shape() -> None:
    sources = [
        _rule_source(
            citation="R1",
            page=307,
            content=(
                "Order of operations seldom matters in social combat. "
                "Combatants roll their respective dice pools and compare numbers of successes. "
                "The combatant with more successes applies the result as damage to Willpower."
            ),
        ),
        _rule_source(
            citation="R2",
            page=306,
            content=(
                "Advanced Conflict: Social Combat can occur anywhere and take many forms. "
                "These rules operate at a slightly higher degree of abstraction than physical conflict. "
                "Social combat responds well to the Three Rounds and Out structure or the One-Roll Conflict system."
            ),
        ),
        _rule_source(
            citation="R3",
            page=306,
            content=(
                "As in One-Roll Conflict, set the stakes ahead of time. "
                "Social combat requires an opponent: someone who actively does not want you to succeed. "
                "Social Conflict Pool: depending on the conflict type, arena, and audience, build a dice pool."
            ),
        ),
        _rule_source(
            citation="R4",
            page=307,
            content=(
                "Winning Social Combat: Social combat ends when one party concedes defeat. "
                "The winner achieves the stakes agreed to at the beginning of the conflict."
            ),
        ),
    ]

    template = TemplateAnswerGenerator().generate("How does social combat work?", sources)
    prompt = build_llama_prompt("How does social combat work?", sources, token_budget=256)

    assert template.text.count("- ") >= 4
    assert "set the stakes" in template.text
    assert "damage to Willpower" in template.text
    assert "winner achieves the agreed stakes" in template.text
    assert "Core Rulebook p. 306" in template.text
    assert "Core Rulebook p. 307" in template.text
    assert "4-6 short bullets" in prompt
    assert prompt.index("Core Rulebook p. 306") < prompt.index("Core Rulebook p. 307")


def test_ritual_timing_question_prefers_casting_rule_over_intro_text() -> None:
    sources = [
        _rule_source(
            citation="R1",
            page=274,
            content=(
                "Blood Sorcery unlocks the ability to perform Rituals. "
                "Learning new Rituals during play requires both experience and time."
            ),
            score=1.0,
        ),
        _rule_source(
            citation="R2",
            page=93,
            content=(
                "Ceremonies are Oblivion's equivalent to Blood Sorcery's Rituals. "
                "Unless otherwise noted, performing a Ceremony requires a Rouse Check, five minutes per level to cast."
            ),
            score=1.1,
        ),
        _rule_source(
            citation="R3",
            page=277,
            content=(
                "Rituals Unless otherwise noted, performing a ritual requires a Rouse Check, "
                "five minutes per level to cast, and a winning Intelligence + Blood Sorcery test."
            ),
            score=0.5,
        ),
    ]

    template = TemplateAnswerGenerator().generate("How long does it take to perform rituals in general?", sources)

    assert "five minutes per ritual level" in template.text
    assert "Core Rulebook p. 277" in template.text
    assert "Core Rulebook p. 274" not in template.text
    assert "Core Rulebook p. 93" not in template.text


def test_blood_hunt_question_prefers_blood_hunt_over_ordinary_hunting() -> None:
    sources = [
        _rule_source(
            citation="R1",
            page=308,
            content="Systems of the Blood. Hunting and feeding are central activities for vampires.",
            score=1.0,
        ),
        _rule_source(
            citation="R2",
            page=54,
            content=(
                "The Blood Hunt is the ultimate punishment in Vampire society. "
                "Anyone can hunt and kill those named as targets."
            ),
            score=0.5,
        ),
    ]

    template = TemplateAnswerGenerator().generate("Whats a blood hunt?", sources)

    assert "ultimate punishment" in template.text
    assert "hunt and kill" in template.text
    assert "Core Rulebook p. 54" in template.text
    assert "Core Rulebook p. 308" not in template.text


def test_messy_critical_awareness_question_lists_relevant_consequences() -> None:
    sources = [
        _rule_source(
            citation="R1",
            page=209,
            content=(
                "Messy Critical A critical win in which one or more 10s appears on a Hunger die is a messy critical. "
                "The character succeeds as in a regular critical but the Beast shapes the result. "
                "The character gains one or more Stains from their monstrous action. "
                "The character breaches the Masquerade through obvious supernatural violence."
            ),
        ),
        _rule_source(
            citation="R2",
            page=209,
            content=(
                "The character loses one dot from an Advantage. "
                "If none of the above conditions fit the narrative, such as on stealth or awareness tests, "
                "the messy critical turns into a simple mess, and the test fails."
            ),
        ),
    ]

    template = TemplateAnswerGenerator().generate(
        "My character rolled a messy critical on their wits + awareness roll. what are the potential messy consequences?",
        sources,
    )

    assert "simple mess" in template.text
    assert "Stains" in template.text
    assert "Masquerade breach" in template.text
    assert template.text.count("- ") >= 4


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


def _rule_source(citation: str, page: int, content: str, score: float = 1.0) -> dict[str, object]:
    return {
        "source_type": "rules",
        "citation": citation,
        "book_id": "core",
        "book_title": "Core Rulebook",
        "page_start": page,
        "page_end": page,
        "section_label": "Advanced Systems",
        "content": content,
        "excerpt": content[:180],
        "score": score,
        "match_reasons": ["exact"],
    }


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
