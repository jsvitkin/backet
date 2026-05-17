from __future__ import annotations

from backet.rules_query_planner import (
    CONTRACT_DEFINITION,
    CONTRACT_RESTRICTION,
    CONTRACT_TARGETING,
    INTENT_ADVANCEMENT,
    INTENT_BROAD_EXPLANATION,
    INTENT_DEFINITION,
    INTENT_DICE_POOL,
    INTENT_COST,
    INTENT_TARGETING,
    plan_rules_query,
)


def test_rules_query_plan_normalizes_bloodbond_compounds() -> None:
    plan = plan_rules_query("what are bloodbonds and how do I make use of it")

    assert INTENT_DEFINITION in plan.intents
    assert INTENT_BROAD_EXPLANATION in plan.intents
    assert "blood bond" in plan.canonical_terms
    assert "blood bonds" in plan.expanded_terms
    assert "mechanic:blood-bond" in plan.scope_tags
    assert {"make", "use", "it"}.issubset(set(plan.low_value_terms))
    assert any(query.role == "raw_fallback" for query in plan.retrieval_queries)


def test_rules_query_plan_detects_discipline_advancement() -> None:
    plan = plan_rules_query("how do I learn obfuscate")

    assert INTENT_ADVANCEMENT in plan.intents
    assert "discipline:obfuscate" in plan.scope_tags
    assert "obfuscate" in plan.entities["disciplines"]
    assert "experience" in plan.required_evidence
    assert "learn" in plan.low_value_terms
    assert any(query.role == "advancement_evidence" for query in plan.retrieval_queries)


def test_rules_query_plan_warns_for_dementation_alias() -> None:
    plan = plan_rules_query("can malkavians use dementation on other vampires")

    assert INTENT_TARGETING in plan.intents
    assert "clan:malkavian" in plan.scope_tags
    assert "discipline:dominate" in plan.scope_tags
    assert "malkavian" in plan.entities["clans"]
    assert "Dementation" in plan.entities["powers"]
    assert {"use", "other"}.issubset(set(plan.low_value_terms))
    assert any("ambiguous_power_alias:dementation" in warning for warning in plan.warnings)
    assert any(query.role == "targeting_evidence" for query in plan.retrieval_queries)


def test_rules_query_plan_serializes_diagnostics() -> None:
    payload = plan_rules_query("what are bloodbonds").to_dict()

    assert payload["schema_version"] == 3
    assert payload["raw_question"] == "what are bloodbonds"
    assert payload["normalized_question"] == "what are blood bonds"
    assert payload["entities"]["mechanics"] == ["blood bond"]
    assert payload["resolved_entities"][0]["canonical_name"] == "blood bond"
    assert payload["scenario_frame"]["question_archetype"] == "definition"
    assert payload["scenario_frame"]["requires_scenario"] is False
    assert payload["evidence_contract"]["contract_id"] == CONTRACT_DEFINITION
    assert payload["retrieval_queries"][-1]["role"] == "raw_fallback"


def test_rules_query_plan_resolves_common_entity_first_targets() -> None:
    blush = plan_rules_query("do I need blush of life to pass as human?")
    dominate = plan_rules_query("can I use Dominate without eye contact on another vampire?")
    hunger = plan_rules_query("what happens when I am at hunger 5 and must rouse?")

    assert blush.resolved_entities[0]["canonical_name"] == "blush of life"
    assert any(query.role == "entity_anchor" for query in blush.retrieval_queries)
    assert dominate.target_groups == ["vampire"]
    assert "eye_contact" in dominate.situational_constraints
    assert any(entity["canonical_name"] == "Dominate" for entity in dominate.resolved_entities)
    assert "hunger_5" in hunger.situational_constraints
    assert any(entity["canonical_name"] == "hunger" for entity in hunger.resolved_entities)


def test_rules_query_plan_treats_rouse_check_definition_as_definition() -> None:
    plan = plan_rules_query("What does a Rouse Check do in play?")

    assert INTENT_DEFINITION in plan.intents
    assert INTENT_COST not in plan.intents
    assert INTENT_DICE_POOL not in plan.intents
    assert "rouse check" in plan.canonical_terms


def test_rules_query_plan_keeps_raw_terms_when_entities_are_present() -> None:
    plan = plan_rules_query("Can I use Auspex Sense the Unseen to spot someone using Obfuscate, and what roll is involved?")
    raw_terms = next(query for query in plan.retrieval_queries if query.role == "raw_terms").terms

    assert "auspex" in raw_terms
    assert "obfuscate" in raw_terms
    assert "sense" in raw_terms
    assert "unseen" in raw_terms


def test_rules_query_plan_adds_base_mending_damage_query() -> None:
    plan = plan_rules_query("How does a vampire mend superficial Health damage?")

    query = next(item for item in plan.retrieval_queries if item.role == "mending_damage_evidence")

    assert "mending damage" in query.terms
    assert "rouse check" in query.terms


def test_rules_query_plan_frames_targeting_contract() -> None:
    payload = plan_rules_query("can malkavians use dementation on other vampires").to_dict()

    frame = payload["scenario_frame"]
    contract = payload["evidence_contract"]
    assert frame["question_archetype"] == "targeting"
    assert frame["requested_answer_shape"] == "yes_no"
    assert frame["actor"] == "malkavian"
    assert frame["target"] == "vampire"
    assert frame["mechanic"] == "Dementation"
    assert frame["requires_scenario"] is True
    assert any(item["code"] == "ambiguous_power_alias" for item in frame["ambiguity_warnings"])
    assert contract["contract_id"] == CONTRACT_TARGETING
    assert {"target", "effect", "source_reference"}.issubset(set(contract["required_facets"]))


def test_rules_query_plan_frames_negative_restriction_contract() -> None:
    payload = plan_rules_query("can I use Dominate on another vampire without eye contact").to_dict()

    frame = payload["scenario_frame"]
    contract = payload["evidence_contract"]
    assert frame["question_archetype"] == "restriction"
    assert frame["polarity"] == "negative"
    assert "eye_contact" in frame["conditions"]
    assert contract["contract_id"] == CONTRACT_RESTRICTION
    assert contract["requires_explicit_negative_evidence"] is True
