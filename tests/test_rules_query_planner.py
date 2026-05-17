from __future__ import annotations

from backet.rules_query_planner import (
    INTENT_ADVANCEMENT,
    INTENT_BROAD_EXPLANATION,
    INTENT_DEFINITION,
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

    assert payload["schema_version"] == 1
    assert payload["raw_question"] == "what are bloodbonds"
    assert payload["normalized_question"] == "what are blood bonds"
    assert payload["entities"]["mechanics"] == ["blood bond"]
    assert payload["retrieval_queries"][-1]["role"] == "raw_fallback"
