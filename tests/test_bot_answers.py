from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backet.bot_answers import (
    ANSWER_CLASS_ANSWER,
    ANSWER_CLASS_AMBIGUOUS,
    ANSWER_CLASS_CONFLICTING,
    ANSWER_CLASS_INSUFFICIENT,
    ANSWER_CLASS_RUNTIME_UNAVAILABLE,
    AnswerPacket,
    LlamaLocalAnswerGenerator,
    OllamaLocalAnswerGenerator,
    TemplateAnswerGenerator,
    build_answer_outline,
    build_llama_prompt,
    generate_answer_from_config,
    validate_generated_answer,
    validate_llama_model_files,
)
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
    client = _FakeModelClient("Court customs are public.\n\nSources: Player Primer (Player Primer.md)")
    bundle = BotBundle.load(output)

    answer = answer_bot_query(
        bundle,
        command="canon.ask",
        question="What customs are public?",
        role_ids=["player-role"],
        model_client=client,
    )

    assert answer.text == "Court customs are public.\n\nSources: Player Primer (Player Primer.md)"
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


def test_template_answer_packet_response_classes_are_evidence_aware() -> None:
    generator = TemplateAnswerGenerator()
    insufficient = generator.generate_from_packet(
        AnswerPacket(
            question="how do I learn obfuscate",
            response_class=ANSWER_CLASS_INSUFFICIENT,
            evidence_status="insufficient",
            missing_evidence=["advancement"],
        )
    )
    ambiguous = generator.generate_from_packet(
        AnswerPacket(
            question="which rule applies?",
            response_class=ANSWER_CLASS_AMBIGUOUS,
            evidence_status="ambiguous",
        )
    )
    conflicting = generator.generate_from_packet(
        AnswerPacket(
            question="which source wins?",
            response_class=ANSWER_CLASS_CONFLICTING,
            evidence_status="conflicting",
        )
    )
    unavailable = generator.generate_from_packet(
        AnswerPacket(
            question="rules?",
            response_class=ANSWER_CLASS_RUNTIME_UNAVAILABLE,
            evidence_status="runtime_unavailable",
        )
    )

    assert "missing the evidence" in insufficient.text
    assert "advancement" in insufficient.text
    assert "narrow" in ambiguous.text
    assert "conflict" in conflicting.text
    assert "retrieval is unavailable" in unavailable.text
    assert insufficient.diagnostics["answer_packet"]["response_class"] == "insufficient"


def test_llama_prompt_consumes_answer_packet_selected_evidence_only() -> None:
    selected = [
        _rule_source(
            citation="R1",
            page=70,
            content="Advancement rules say learning a new Discipline power costs experience and may require a teacher.",
        )
    ]
    packet = AnswerPacket(
        question="how do I learn obfuscate",
        response_class="answer",
        evidence_status="answerable",
        selected_evidence=selected,
        fallback_context=[
            _rule_source(
                citation="R2",
                page=71,
                content="Obfuscate appears on this character sheet but the chunk does not answer advancement.",
            )
        ],
    )

    prompt = build_llama_prompt(packet.question, selected, token_budget=96, answer_packet=packet)

    assert "EVIDENCE STATUS: answerable" in prompt
    assert "Never output bracket labels" in prompt
    assert "costs experience" in prompt
    assert "character sheet" not in prompt


def test_answer_outline_claim_contract_validates_selected_evidence_only() -> None:
    selected = _rule_source(
        citation="R1",
        page=67,
        content="Blood Bonds create a supernatural tie between a regnant and a thrall through repeated drinks.",
    )
    selected["rule_block_id"] = "core:p67:c1:blood-bonds"
    packet = AnswerPacket(
        question="what are blood bonds?",
        response_class=ANSWER_CLASS_ANSWER,
        evidence_status="answerable",
        selected_evidence=[selected],
        fallback_context=[
            _rule_source(
                citation="R2",
                page=368,
                content="A prince tried to use the Second Inquisition as a pawn in his own schemes.",
            )
        ],
        answer_shape="definition",
        diagnostics={
            "query_plan": {
                "intents": ["definition"],
                "resolved_entities": [
                    {
                        "entity_id": "seed:mechanic:blood-bond",
                        "canonical_name": "blood bond",
                        "accepted_aliases": ["blood bond", "blood bonds"],
                        "source_anchors": [],
                    }
                ],
                "target_groups": [],
                "situational_constraints": [],
            }
        },
    )

    outline = build_answer_outline(packet)
    claim = outline.claims[0]
    answer = TemplateAnswerGenerator().generate_from_packet(packet)

    assert outline.response_class == ANSWER_CLASS_ANSWER
    assert claim.validation_status == "validated"
    assert claim.source_ids == ["R1"]
    assert claim.covered_entities == ["seed:mechanic:blood-bond"]
    assert claim.support_windows[0]["source_id"] == "R1"
    assert "Second Inquisition" not in answer.text
    assert answer.diagnostics["synthesis"]["claim_contract"]["validated_claims"] == 1
    assert answer.diagnostics["synthesis"]["final_answer_support"][0]["claim_id"] == claim.claim_id


def test_llama_validation_blocks_unavailable_citations_and_status_violations() -> None:
    sources = [_rule_source(citation="R1", page=70, content="Blood Bond definition text.")]
    insufficient_packet = AnswerPacket(
        question="what are blood bonds?",
        response_class=ANSWER_CLASS_INSUFFICIENT,
        evidence_status="insufficient",
        missing_evidence=["definition"],
    )

    assert validate_generated_answer("Blood Bonds work like this. [R2]", sources) == "bot_llama_output_unavailable_citation"
    assert validate_generated_answer("Blood Bonds work like this. [R1]", sources) == "bot_llama_output_internal_citation"
    assert validate_generated_answer("Blood Bonds work like this.\n\nSources: Core Rulebook p. 70 (Advanced Systems)", sources) is None
    assert (
        validate_generated_answer(
            "Yes, you can learn it by spending experience and finding a teacher. [R1]",
            sources,
            answer_packet=insufficient_packet,
        )
        == "bot_llama_output_internal_citation"
    )
    assert validate_generated_answer("The permitted sources are insufficient.", sources, answer_packet=insufficient_packet) is None


def test_llama_validation_requires_outline_supporting_claim() -> None:
    sources = [
        _rule_source(
            citation="R1",
            page=208,
            content=(
                "Messy Critical A critical win with Hunger can become a messy critical. "
                "The player may accept a Masquerade breach or a Stain as the messy consequence."
            ),
        )
    ]
    packet = AnswerPacket(
        question="does a messy critical on a feeding roll cause a masquerade breach",
        response_class=ANSWER_CLASS_ANSWER,
        evidence_status="answerable",
        selected_evidence=sources,
        answer_shape="yes_no",
    )

    assert (
        validate_generated_answer("Yes.\n\nSources: Core Rulebook p. 208 (Advanced Systems)", sources, answer_packet=packet)
        == "bot_llama_output_missing_outline_support"
    )
    assert (
        validate_generated_answer(
            "Yes, a messy critical can become a Masquerade breach when that consequence fits the scene.\n\n"
            "Sources: Core Rulebook p. 208 (Advanced Systems)",
            sources,
            answer_packet=packet,
        )
        is None
    )


def test_llama_generator_does_not_call_model_for_insufficient_packet() -> None:
    client = _FakeModelClient("You can learn it by spending XP. [R1]")
    packet = AnswerPacket(
        question="how do I learn obfuscate",
        response_class=ANSWER_CLASS_INSUFFICIENT,
        evidence_status="insufficient",
        missing_evidence=["advancement"],
    )

    answer = LlamaLocalAnswerGenerator(client=client).generate_from_packet(packet)

    assert client.prompts == []
    assert "missing the evidence" in answer.text
    assert answer.diagnostics["model_skipped_reason"] == "evidence_status:insufficient"


@pytest.mark.parametrize(
    ("question", "source_text", "shape", "stance", "expected"),
    [
        (
            "can vampires feed on werewolf blood",
            "A werewolf's blood is so rich that every drink from its veins slakes twice the normal amount of Hunger.",
            "yes_no",
            "yes",
            "can feed on werewolf blood",
        ),
        (
            "what are Blood Bonds?",
            "Blood Bonds create a supernatural tie between a regnant and a thrall through repeated draughts.",
            "definition",
            "definition",
            "supernatural tie",
        ),
        (
            "how do I roll a frenzy test?",
            "Frenzy test. System: The vampire rolls Willpower against a Difficulty set by the provocation.",
            "procedure",
            "procedure",
            "rolls Willpower",
        ),
        (
            "how long does it take to cast a ritual",
            "Rituals Unless otherwise noted, performing a ritual requires a Rouse Check, five minutes per level to cast.",
            "timing",
            "timing",
            "five minutes per ritual level",
        ),
        (
            "what does this power cost?",
            "Cost: One Rouse Check. System: The vampire rolls Resolve + Blood Sorcery.",
            "cost",
            "cost",
            "Cost: One Rouse Check",
        ),
        (
            "what happens on a messy critical?",
            "Messy Critical: The character gains one or more Stains from their monstrous action.",
            "consequence_bullets",
            "consequence_bullets",
            "Stains",
        ),
    ],
)
def test_answer_outline_shapes(question: str, source_text: str, shape: str, stance: str, expected: str) -> None:
    outline = build_answer_outline(
        AnswerPacket(
            question=question,
            response_class="answer",
            evidence_status="answerable",
            selected_evidence=[_rule_source(citation="R1", page=1, content=source_text)],
            answer_shape=shape,
        )
    )

    assert outline.response_class == "answer"
    assert outline.answer_shape == shape
    assert outline.stance == stance
    assert outline.source_ids == ["R1"]
    assert expected in " ".join(claim.text for claim in outline.claims)


def test_answer_outline_abstains_when_selected_evidence_lacks_required_anchor() -> None:
    outline = build_answer_outline(
        AnswerPacket(
            question="can malkavians use dementation on other vampires",
            response_class="answer",
            evidence_status="answerable",
            selected_evidence=[
                _rule_source(
                    citation="R1",
                    page=185,
                    content="Social interaction can be demanding for the Malkavians and their coterie.",
                )
            ],
            answer_shape="yes_no",
        )
    )

    assert outline.response_class == ANSWER_CLASS_INSUFFICIENT
    assert "dementation" in outline.missing_evidence


def test_answer_outline_answers_rouse_check_definition_not_random_roll_fragment() -> None:
    outline = build_answer_outline(
        AnswerPacket(
            question="What does a Rouse Check do in play?",
            response_class="answer",
            evidence_status="answerable",
            selected_evidence=[
                _rule_source(
                    citation="R1",
                    page=213,
                    content=(
                        "Some conditions allow the player to roll two dice on some Rouse Checks and pick the highest. "
                        "One success (6+) on either die prevents Hunger from increasing. "
                        "If the Rouse Check fails, Hunger increases by 1."
                    ),
                )
            ],
            answer_shape="definition",
        )
    )

    claims = " ".join(claim.text for claim in outline.claims)

    assert outline.response_class == ANSWER_CLASS_ANSWER
    assert "prevents Hunger from increasing" in claims
    assert "failure increases Hunger by 1" in claims


def test_answer_outline_prefers_blood_surge_pool_bonus_over_nearby_rouse_bonus() -> None:
    answer = TemplateAnswerGenerator().generate(
        "How does Blood Surge help a roll?",
        [
            _rule_source(
                citation="R1",
                page=219,
                content=(
                    "Add one Attribute die to your dice pool when performing a Blood Surge. "
                    "Roll two dice and pick the highest when rolling a Rouse Check for discipline powers of level 3 and below."
                ),
            )
        ],
    )

    assert "adding one Attribute die" in answer.text
    assert "discipline powers" not in answer.text.split("**Evidence:**", 1)[0]


def test_answer_outline_prefers_base_mending_damage_over_power_specific_heal() -> None:
    answer = TemplateAnswerGenerator().generate(
        "How does a vampire mend superficial Health damage?",
        [
            _rule_source(
                citation="R1",
                page=77,
                content=(
                    "Intelligence + Fortitude System: The vampire rolls Intelligence + Fortitude against Difficulty 2 "
                    "and mends a number of superficial Health damage levels equal to the margin on the roll. "
                    "Use of this power takes a whole turn."
                ),
                score=1.2,
            ),
            _rule_source(
                citation="R2",
                page=219,
                content=(
                    "When Mending Damage, you can remove 1 point of Superficial damage per Rouse Check. "
                    "Blood Potency 1."
                ),
            ),
        ],
    )

    assert "Mending Damage" in answer.text
    assert "Rouse Check" in answer.text
    assert "Intelligence + Fortitude" not in answer.text.split("**Evidence:**", 1)[0]


def test_answer_outline_rejects_irrelevant_rule_fragments_with_incidental_terms() -> None:
    outline = build_answer_outline(
        AnswerPacket(
            question="Can I spend Willpower to reroll Hunger dice?",
            response_class="answer",
            evidence_status="answerable",
            selected_evidence=[
                _rule_source(
                    citation="R1",
                    page=61,
                    content="Tzimisce using this Bane cannot take the corresponding Folkloric Block.",
                )
            ],
            answer_shape="yes_no",
        )
    )

    assert outline.response_class == ANSWER_CLASS_INSUFFICIENT
    assert "question_anchor" in outline.missing_evidence


def test_answer_outline_rejects_generic_hunger_text_for_vampire_feeding_question() -> None:
    outline = build_answer_outline(
        AnswerPacket(
            question="If my vampire feeds from another vampire, how much Hunger can they slake and what risks come with repeated feeding?",
            response_class="answer",
            evidence_status="answerable",
            selected_evidence=[
                _rule_source(
                    citation="R1",
                    page=293,
                    content=(
                        "If the roll led to a failed Rouse Check or otherwise increased their Hunger, "
                        "they play up their hunger and its consequences."
                    ),
                )
            ],
            answer_shape="concise",
        )
    )

    assert outline.response_class == ANSWER_CLASS_INSUFFICIENT
    assert "question_anchor" in outline.missing_evidence


def test_answer_outline_prefers_predator_type_build_rule_over_example_flavor() -> None:
    answer = TemplateAnswerGenerator().generate(
        "How do Predator Types change starting character choices?",
        [
            _rule_source(
                citation="R1",
                page=109,
                content=(
                    "PREDATOR DISCIPLINE NOTES Remember, your Predator type can grant an out-of-clan Discipline dot. "
                    "Hunger can be stronger than bloodline. "
                    "Extortionist The extortionist acquires blood in exchange for services such as security or surveillance."
                ),
            )
        ],
    )

    assert "out-of-clan Discipline dot" in answer.text
    assert "security or surveillance" not in answer.text.split("**Evidence:**", 1)[0]


def test_model_validation_requires_all_short_outline_claims() -> None:
    source = _rule_source(
        citation="R1",
        page=307,
        content=(
            "Social combat uses opposed pressure to settle agreed stakes. "
            "Combatants roll their respective dice pools and compare numbers of successes. "
            "The combatant with more successes applies the result as damage to Willpower."
        ),
    )
    packet = AnswerPacket(
        question="How does social combat work?",
        response_class="answer",
        evidence_status="answerable",
        selected_evidence=[source],
        answer_shape="system_overview",
    )

    assert (
        validate_generated_answer(
            "Combatants roll their dice pools.\n\nSources: Core Rulebook p. 307 (Advanced Systems)",
            [source],
            answer_packet=packet,
        )
        == "bot_llama_output_missing_outline_support"
    )


def test_model_validation_rejects_blood_surge_adjacent_rule_leakage() -> None:
    source = _rule_source(
        citation="R1",
        page=219,
        content=(
            "Add one Attribute die to your dice pool when performing a Blood Surge. "
            "Roll two dice and pick the highest when rolling a Rouse Check for discipline powers of level 3 and below."
        ),
    )
    packet = AnswerPacket(
        question="How does Blood Surge help a roll?",
        response_class="answer",
        evidence_status="answerable",
        selected_evidence=[source],
        answer_shape="procedure",
    )

    assert (
        validate_generated_answer(
            "To perform a Blood Surge, roll two dice and pick the highest result. Sources: Core Rulebook p. 219 (Advanced Systems)",
            [source],
            answer_packet=packet,
        )
        == "bot_llama_output_adjacent_rule_leakage"
    )


def test_template_advancement_answer_uses_trait_costs_table() -> None:
    answer = TemplateAnswerGenerator().generate(
        "how do I learn obfuscate",
        [
            _rule_source(
                citation="R1",
                page=67,
                content=(
                    "TRAIT COSTS: EXPERIENCE TRAIT EXPERIENCE POINTS "
                    "Clan Discipline New level x 5 Other Discipline New level x 7 "
                    "Caitiff Discipline New level x 6"
                ),
            )
        ],
    )

    assert "Other Discipline: new level x 7 experience" in answer.text
    assert "Core Rulebook p. 67" in answer.text


def test_advancement_answer_prefers_trait_cost_table_over_learning_distractor() -> None:
    answer = TemplateAnswerGenerator().generate(
        "how do I learn obfuscate",
        [
            _rule_source(
                citation="R1",
                page=67,
                content=(
                    "TRAIT COSTS: EXPERIENCE TRAIT EXPERIENCE POINTS "
                    "Clan Discipline New level x 5 Other Discipline New level x 7 "
                    "Caitiff Discipline New level x 6. "
                    "Pick one power from each Discipline level you have."
                ),
                score=0.8,
            ),
            _rule_source(
                citation="R2",
                page=94,
                content=(
                    "Learning new Ceremonies during play requires both experience and time, "
                    "as well as a teacher who knows the Ceremony already."
                ),
                score=1.2,
            ),
        ],
    )

    assert "Learn Obfuscate as a Discipline advancement" in answer.text
    assert "Other Discipline: new level x 7 experience" in answer.text
    assert "Core Rulebook p. 67" in answer.text
    assert "Core Rulebook p. 94" not in answer.text


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


def test_werewolf_feeding_question_answers_mechanics_not_lore() -> None:
    sources = [
        _rule_source(
            citation="R1",
            page=378,
            content=(
                "Werewolf: Lupines are enemies of vampires and dangerous in the wild. "
                "A werewolf's blood is so rich that every drink from its veins slakes twice the normal amount of Hunger. "
                "Draining a werewolf dry can reduce Hunger to 0. "
                "Every point of Hunger slaked with werewolf blood increases the Difficulty to resist frenzy by one. "
                "Even if the vampire resists, they become paranoid and short-tempered while the blood remains in their system."
            ),
            score=0.6,
        ),
        _rule_source(
            citation="R2",
            page=203,
            content="A quote about eating blood uses the word eat but says nothing about werewolves.",
            score=0.9,
        ),
    ]

    template = TemplateAnswerGenerator().generate("can I eat a werewolf", sources)

    assert "can feed on werewolf blood" in template.text
    assert "slakes twice" in template.text
    assert "Difficulty to resist frenzy" in template.text
    assert "Core Rulebook p. 378" in template.text
    assert "Core Rulebook p. 203" not in template.text
    assert "Lupines are enemies" not in template.text


def test_day_awake_question_answers_humanity_roll_procedure() -> None:
    sources = [
        _rule_source(
            citation="R1",
            page=221,
            content=(
                "Awakening during the day requires a Humanity roll at a Difficulty depending on the level of crisis. "
                "A fire or other life-threatening situation is Difficulty 3; an urgent message or decision is Difficulty 4; "
                "an inconvenience to deal with is Difficulty 5 or higher. "
                "Once awakened from day-sleep, a vampire can only act for a single scene. "
                "At the end of that period, to remain awake longer, they must make a Humanity roll at Difficulty 3; "
                "a win permits an additional scene. A critical win lets them stay awake for as long as needed."
            ),
        ),
        _rule_source(
            citation="R2",
            page=249,
            content="An animal possession power mentions staying awake during the day but does not give the base procedure.",
            score=1.2,
        ),
    ]

    template = TemplateAnswerGenerator().generate("can a vampire stay awake during the day", sources)

    assert "requires a Humanity roll" in template.text
    assert "Difficulty 3 for life-threatening danger" in template.text
    assert "one scene" in template.text
    assert "stay awake as long as needed" in template.text
    assert "Core Rulebook p. 221" in template.text
    assert "Core Rulebook p. 249" not in template.text


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


def test_ollama_generator_records_model_timing_and_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backet.bot_answers.ollama_generate",
        lambda prompt, model, endpoint, timeout_seconds, token_budget, stream: {
            "response": "Blood Bonds create a supernatural tie through repeated draughts.\n\nSources: Core Rulebook p. 1 (Blood Bonds)",
            "total_duration": 2_000_000_000,
            "load_duration": 100_000_000,
            "eval_count": 12,
            "eval_duration": 300_000_000,
        },
    )
    generator = OllamaLocalAnswerGenerator(model_config={"model": "llama3.2:3b", "endpoint": "http://ollama:11434"})

    answer = generator.generate(
        "What are Blood Bonds?",
        [
            {
                "source_type": "rules",
                "citation": "R1",
                "book_title": "Core Rulebook",
                "page_start": 1,
                "page_end": 1,
                "section_label": "Blood Bonds",
                "content": "Blood Bonds create a supernatural tie through repeated draughts.",
                "excerpt": "Blood Bonds create a supernatural tie through repeated draughts.",
                "score": 1.0,
                "match_reasons": ["exact"],
            }
        ],
    )

    assert answer.mode == "ollama-local"
    assert answer.fallback_used is False
    assert answer.diagnostics["model"] == "llama3.2:3b"
    assert answer.diagnostics["runtime_provider"] == "ollama"
    assert answer.diagnostics["timing"]["eval_count"] == 12


def test_model_service_answer_can_use_llama_cpp_endpoint() -> None:
    answer = generate_answer_from_config(
        {
            "model_services": {
                "answer": {
                    "provider": "llama.cpp",
                    "endpoint": "http://127.0.0.1:8080/completion",
                    "timeout_seconds": 30,
                }
            }
        },
        "How do Blood Bonds work?",
        [
            {
                "source_type": "rules",
                "citation": "R1",
                "book_title": "Core Rulebook",
                "page_start": 1,
                "page_end": 1,
                "section_label": "Blood Bonds",
                "content": "Blood Bonds create a supernatural tie through repeated draughts.",
                "excerpt": "Blood Bonds create a supernatural tie through repeated draughts.",
                "score": 1.0,
                "match_reasons": ["exact"],
            }
        ],
        client=_FakeModelClient("Blood Bonds create a supernatural tie through repeated draughts.\n\nSources: Core Rulebook p. 1 (Blood Bonds)"),
    )

    assert answer.mode == "llama-local"
    assert answer.text == "Blood Bonds create a supernatural tie through repeated draughts.\n\nSources: Core Rulebook p. 1 (Blood Bonds)"
    assert answer.diagnostics["endpoint"] == "http://127.0.0.1:8080/completion"


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
