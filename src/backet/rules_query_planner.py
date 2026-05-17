from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from backet.rules_scope import TAXONOMY_ENTRIES, ScopeTaxonomyEntry, canonicalize_scope_tag

RULES_QUERY_PLAN_SCHEMA_VERSION = 3

INTENT_DEFINITION = "definition"
INTENT_ADVANCEMENT = "advancement"
INTENT_TARGETING = "targeting"
INTENT_COST = "cost"
INTENT_TIMING = "timing"
INTENT_DICE_POOL = "dice_pool"
INTENT_CONSEQUENCE = "consequence"
INTENT_BROAD_EXPLANATION = "broad_explanation"

QUESTION_ARCHETYPE_DEFINITION = "definition"
QUESTION_ARCHETYPE_PROCEDURE = "procedure"
QUESTION_ARCHETYPE_COST = "cost"
QUESTION_ARCHETYPE_RESOURCE_QUANTITY = "resource_quantity"
QUESTION_ARCHETYPE_TARGETING = "targeting"
QUESTION_ARCHETYPE_RESTRICTION = "restriction"
QUESTION_ARCHETYPE_INTERACTION = "interaction"
QUESTION_ARCHETYPE_EXCEPTION = "exception"
QUESTION_ARCHETYPE_CONFLICT = "conflict"
QUESTION_ARCHETYPE_BROAD_EXPLANATION = "broad_explanation"
QUESTION_ARCHETYPE_INSUFFICIENCY = "insufficiency"

CONTRACT_DEFINITION = "definition"
CONTRACT_PROCEDURE = "procedure"
CONTRACT_COST = "cost"
CONTRACT_RESOURCE_QUANTITY = "resource_quantity"
CONTRACT_TARGETING = "targeting"
CONTRACT_RESTRICTION = "restriction"
CONTRACT_INTERACTION = "interaction"
CONTRACT_EXCEPTION = "exception"
CONTRACT_CONFLICT = "conflict"
CONTRACT_INSUFFICIENCY = "insufficiency"

ANSWERABILITY_ENOUGH = "enough"
ANSWERABILITY_PARTIAL = "partial"
ANSWERABILITY_CONFLICTING = "conflicting"
ANSWERABILITY_INSUFFICIENT = "insufficient"

INTENT_ORDER = (
    INTENT_DEFINITION,
    INTENT_ADVANCEMENT,
    INTENT_TARGETING,
    INTENT_COST,
    INTENT_TIMING,
    INTENT_DICE_POOL,
    INTENT_CONSEQUENCE,
    INTENT_BROAD_EXPLANATION,
)

LOW_VALUE_TERMS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "be",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "its",
    "learn",
    "make",
    "makes",
    "making",
    "me",
    "my",
    "of",
    "on",
    "or",
    "other",
    "others",
    "please",
    "should",
    "that",
    "the",
    "them",
    "to",
    "use",
    "used",
    "uses",
    "using",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "would",
}

COMPOUND_REPLACEMENTS = {
    "bloodbond": "blood bond",
    "bloodbonds": "blood bonds",
    "bloodbonded": "blood bonded",
    "dicepool": "dice pool",
    "dicepools": "dice pools",
    "outofclan": "out of clan",
    "rousecheck": "rouse check",
    "rousechecks": "rouse checks",
    "bloodpotency": "blood potency",
    "thinblood": "thin blood",
    "thinbloods": "thin bloods",
}

TARGETED_MECHANIC_ALIASES = {
    "blush of life": {
        "aliases": ("blush of life", "blush", "look alive", "pass as human"),
        "expanded": ("blush of life", "rouse check", "simulate life", "food", "sex", "breathing"),
        "scope_tags": ("mechanic:blush-of-life",),
    },
    "rouse check": {
        "aliases": ("rouse check", "rouse checks", "rousecheck", "rousechecks"),
        "expanded": ("rouse check", "hunger", "rouse", "check"),
        "scope_tags": ("mechanic:rouse-check",),
    },
    "hunger": {
        "aliases": ("hunger", "hunger 5", "hunger five", "hunger frenzy"),
        "expanded": ("hunger", "hunger 5", "hunger frenzy", "rouse check"),
        "scope_tags": ("mechanic:hunger",),
    },
    "blood bond": {
        "aliases": ("blood bond", "blood bonds", "bloodbond", "bloodbonds", "blood bonded"),
        "expanded": ("blood bond", "blood bonds", "bond", "bonds", "vitae"),
        "scope_tags": ("mechanic:blood-bond",),
    },
    "out of clan discipline": {
        "aliases": (
            "out of clan",
            "out of clan discipline",
            "discipline acquisition",
            "discipline advancement",
            "learn discipline",
            "learn power",
        ),
        "expanded": (
            "out of clan",
            "discipline",
            "discipline acquisition",
            "discipline advancement",
            "experience",
            "teacher",
        ),
        "scope_tags": ("mechanic:advancement",),
    },
}

TARGETED_POWER_ALIASES = {
    "Dominate": {
        "aliases": ("dominate", "domination"),
        "expanded": ("dominate", "discipline", "command", "mesmerize", "eye contact"),
        "scope_tags": ("discipline:dominate",),
    },
    "Dementation": {
        "aliases": ("dementation", "dementia"),
        "expanded": ("dementation", "dominate", "malkavian", "power"),
        "scope_tags": ("discipline:dominate",),
        "warning": (
            "ambiguous_power_alias:dementation may refer to a legacy discipline or a Dominate "
            "variant/power; retaining Dementation and Dominate in the query plan"
        ),
    },
}

REQUIRED_EVIDENCE_BY_INTENT = {
    INTENT_DEFINITION: ("definition", "overview"),
    INTENT_ADVANCEMENT: (
        "advancement",
        "acquisition",
        "experience",
        "cost",
        "teacher",
        "out of clan",
        "discipline access",
    ),
    INTENT_TARGETING: ("system", "target", "targets", "restrictions", "applicability", "affect"),
    INTENT_COST: ("cost", "rouse check", "experience", "spend"),
    INTENT_TIMING: ("duration", "time", "minutes", "cast", "perform"),
    INTENT_DICE_POOL: ("dice pool", "test", "roll", "attribute", "skill"),
    INTENT_CONSEQUENCE: ("success", "failure", "consequence", "result"),
    INTENT_BROAD_EXPLANATION: ("overview", "system", "example"),
}


@dataclass(frozen=True, slots=True)
class RulesRetrievalQuery:
    role: str
    text: str
    terms: list[str]
    evidence: list[str] = field(default_factory=list)
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "text": self.text,
            "terms": self.terms,
            "evidence": self.evidence,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class ScenarioFrame:
    actor: str | None
    action: str | None
    target: str | None
    mechanic: str | None
    entities: list[str]
    conditions: list[str]
    polarity: str
    requested_answer_shape: str
    question_archetype: str
    requires_scenario: bool
    confidence: float
    ambiguity_warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "mechanic": self.mechanic,
            "entities": self.entities,
            "conditions": self.conditions,
            "polarity": self.polarity,
            "requested_answer_shape": self.requested_answer_shape,
            "question_archetype": self.question_archetype,
            "requires_scenario": self.requires_scenario,
            "confidence": self.confidence,
            "ambiguity_warnings": self.ambiguity_warnings,
        }


@dataclass(frozen=True, slots=True)
class EvidenceContract:
    contract_id: str
    archetype: str
    required_facets: list[str]
    acceptable_source_roles: list[str]
    fallback_source_roles: list[str]
    missing_facet_policy: str
    answerability_statuses: list[str]
    requires_explicit_negative_evidence: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "archetype": self.archetype,
            "required_facets": self.required_facets,
            "acceptable_source_roles": self.acceptable_source_roles,
            "fallback_source_roles": self.fallback_source_roles,
            "missing_facet_policy": self.missing_facet_policy,
            "answerability_statuses": self.answerability_statuses,
            "requires_explicit_negative_evidence": self.requires_explicit_negative_evidence,
            "diagnostics": self.diagnostics,
        }


CONTRACT_DEFINITIONS: dict[str, EvidenceContract] = {
    CONTRACT_DEFINITION: EvidenceContract(
        contract_id=CONTRACT_DEFINITION,
        archetype=QUESTION_ARCHETYPE_DEFINITION,
        required_facets=["effect", "source_reference"],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional", "example"],
        missing_facet_policy=ANSWERABILITY_PARTIAL,
        answerability_statuses=[ANSWERABILITY_ENOUGH, ANSWERABILITY_PARTIAL, ANSWERABILITY_INSUFFICIENT],
    ),
    CONTRACT_PROCEDURE: EvidenceContract(
        contract_id=CONTRACT_PROCEDURE,
        archetype=QUESTION_ARCHETYPE_PROCEDURE,
        required_facets=["effect", "source_reference"],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional", "example"],
        missing_facet_policy=ANSWERABILITY_PARTIAL,
        answerability_statuses=[ANSWERABILITY_ENOUGH, ANSWERABILITY_PARTIAL, ANSWERABILITY_INSUFFICIENT],
    ),
    CONTRACT_COST: EvidenceContract(
        contract_id=CONTRACT_COST,
        archetype=QUESTION_ARCHETYPE_COST,
        required_facets=["cost", "source_reference"],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional", "example"],
        missing_facet_policy=ANSWERABILITY_PARTIAL,
        answerability_statuses=[ANSWERABILITY_ENOUGH, ANSWERABILITY_PARTIAL, ANSWERABILITY_INSUFFICIENT],
    ),
    CONTRACT_RESOURCE_QUANTITY: EvidenceContract(
        contract_id=CONTRACT_RESOURCE_QUANTITY,
        archetype=QUESTION_ARCHETYPE_RESOURCE_QUANTITY,
        required_facets=["resource", "cost", "source_reference"],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional", "example"],
        missing_facet_policy=ANSWERABILITY_PARTIAL,
        answerability_statuses=[ANSWERABILITY_ENOUGH, ANSWERABILITY_PARTIAL, ANSWERABILITY_INSUFFICIENT],
    ),
    CONTRACT_TARGETING: EvidenceContract(
        contract_id=CONTRACT_TARGETING,
        archetype=QUESTION_ARCHETYPE_TARGETING,
        required_facets=["target", "effect", "source_reference"],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional", "example"],
        missing_facet_policy=ANSWERABILITY_PARTIAL,
        answerability_statuses=[ANSWERABILITY_ENOUGH, ANSWERABILITY_PARTIAL, ANSWERABILITY_INSUFFICIENT],
    ),
    CONTRACT_RESTRICTION: EvidenceContract(
        contract_id=CONTRACT_RESTRICTION,
        archetype=QUESTION_ARCHETYPE_RESTRICTION,
        required_facets=["limit", "target", "source_reference"],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional"],
        missing_facet_policy=ANSWERABILITY_INSUFFICIENT,
        answerability_statuses=[ANSWERABILITY_ENOUGH, ANSWERABILITY_PARTIAL, ANSWERABILITY_INSUFFICIENT],
        requires_explicit_negative_evidence=True,
    ),
    CONTRACT_INTERACTION: EvidenceContract(
        contract_id=CONTRACT_INTERACTION,
        archetype=QUESTION_ARCHETYPE_INTERACTION,
        required_facets=["effect", "target", "limit", "source_reference"],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional", "example"],
        missing_facet_policy=ANSWERABILITY_PARTIAL,
        answerability_statuses=[ANSWERABILITY_ENOUGH, ANSWERABILITY_PARTIAL, ANSWERABILITY_INSUFFICIENT],
    ),
    CONTRACT_EXCEPTION: EvidenceContract(
        contract_id=CONTRACT_EXCEPTION,
        archetype=QUESTION_ARCHETYPE_EXCEPTION,
        required_facets=["limit", "source_reference"],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional", "example"],
        missing_facet_policy=ANSWERABILITY_PARTIAL,
        answerability_statuses=[ANSWERABILITY_ENOUGH, ANSWERABILITY_PARTIAL, ANSWERABILITY_INSUFFICIENT],
    ),
    CONTRACT_CONFLICT: EvidenceContract(
        contract_id=CONTRACT_CONFLICT,
        archetype=QUESTION_ARCHETYPE_CONFLICT,
        required_facets=["effect", "source_reference"],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional", "example"],
        missing_facet_policy=ANSWERABILITY_CONFLICTING,
        answerability_statuses=[ANSWERABILITY_ENOUGH, ANSWERABILITY_CONFLICTING, ANSWERABILITY_INSUFFICIENT],
    ),
    CONTRACT_INSUFFICIENCY: EvidenceContract(
        contract_id=CONTRACT_INSUFFICIENCY,
        archetype=QUESTION_ARCHETYPE_INSUFFICIENCY,
        required_facets=[],
        acceptable_source_roles=["base", "specific", "exception", "chunk"],
        fallback_source_roles=["optional", "example", "flavor"],
        missing_facet_policy=ANSWERABILITY_INSUFFICIENT,
        answerability_statuses=[ANSWERABILITY_INSUFFICIENT],
        diagnostics={"reason": "contract_selection_unavailable"},
    ),
}


@dataclass(frozen=True, slots=True)
class RulesQueryPlan:
    raw_question: str
    normalized_question: str
    intents: list[str]
    entities: dict[str, list[str]]
    scope_tags: list[str]
    canonical_terms: list[str]
    expanded_terms: list[str]
    retrieval_queries: list[RulesRetrievalQuery]
    required_evidence: list[str]
    low_value_terms: list[str]
    raw_unknown_terms: list[str]
    warnings: list[str]
    scoring_terms: list[str]
    semantic_query: str
    raw_fallback_query: str
    resolved_entities: list[dict[str, Any]] = field(default_factory=list)
    unresolved_high_value_terms: list[str] = field(default_factory=list)
    target_groups: list[str] = field(default_factory=list)
    situational_constraints: list[str] = field(default_factory=list)
    ambiguity_warnings: list[dict[str, Any]] = field(default_factory=list)
    scenario_frame: ScenarioFrame | None = None
    evidence_contract: EvidenceContract | None = None
    resolution_confidence: float = 0.0
    schema_version: int = RULES_QUERY_PLAN_SCHEMA_VERSION

    @property
    def scoring_query(self) -> str:
        return " ".join(self.scoring_terms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "raw_question": self.raw_question,
            "normalized_question": self.normalized_question,
            "intents": self.intents,
            "entities": self.entities,
            "scope_tags": self.scope_tags,
            "canonical_terms": self.canonical_terms,
            "expanded_terms": self.expanded_terms,
            "retrieval_queries": [query.to_dict() for query in self.retrieval_queries],
            "required_evidence": self.required_evidence,
            "low_value_terms": self.low_value_terms,
            "raw_unknown_terms": self.raw_unknown_terms,
            "warnings": self.warnings,
            "scoring_terms": self.scoring_terms,
            "scoring_query": self.scoring_query,
            "semantic_query": self.semantic_query,
            "raw_fallback_query": self.raw_fallback_query,
            "resolved_entities": self.resolved_entities,
            "unresolved_high_value_terms": self.unresolved_high_value_terms,
            "target_groups": self.target_groups,
            "situational_constraints": self.situational_constraints,
            "ambiguity_warnings": self.ambiguity_warnings,
            "scenario_frame": self.scenario_frame.to_dict() if self.scenario_frame else None,
            "evidence_contract": self.evidence_contract.to_dict() if self.evidence_contract else None,
            "resolution_confidence": self.resolution_confidence,
        }


def plan_rules_query(question: str) -> RulesQueryPlan:
    raw_question = str(question or "")
    normalized = normalize_rules_query_text(raw_question)
    tokens = _tokens(normalized)
    low_value_terms = _dedupe(token for token in tokens if token in LOW_VALUE_TERMS)

    entities = _empty_entities()
    scope_tags: list[str] = []
    canonical_terms: list[str] = []
    expanded_terms: list[str] = []
    warnings: list[str] = []

    for entry, alias in _taxonomy_matches(normalized):
        tag = canonicalize_scope_tag(entry.tag)
        _add(scope_tags, tag)
        canonical = _canonical_term_for_entry(entry, matched_alias=alias)
        _add(canonical_terms, canonical)
        _add_entity(entities, tag, canonical)
        _extend(expanded_terms, _expanded_terms_for_taxonomy_entry(entry, matched_alias=alias))

    for canonical, meta in TARGETED_MECHANIC_ALIASES.items():
        if _any_alias_matches(normalized, meta["aliases"]):
            _add(entities["mechanics"], canonical)
            _add(canonical_terms, canonical)
            _extend(expanded_terms, meta["expanded"])
            _extend(scope_tags, meta["scope_tags"])

    for canonical, meta in TARGETED_POWER_ALIASES.items():
        if _any_alias_matches(normalized, meta["aliases"]):
            _add(entities["powers"], canonical)
            _add(canonical_terms, canonical)
            _extend(expanded_terms, meta["expanded"])
            _extend(scope_tags, meta["scope_tags"])
            if meta.get("warning"):
                _add(warnings, str(meta["warning"]))

    intents = _detect_intents(normalized, entities)
    required_evidence = _required_evidence_for_intents(intents)
    raw_unknown_terms = _raw_unknown_terms(tokens, canonical_terms, expanded_terms, low_value_terms)
    entities["raw_unknown_terms"] = raw_unknown_terms
    if not canonical_terms and raw_unknown_terms:
        _add(warnings, "no_canonical_entities_detected; retaining raw searchable terms")
    resolved_entities = _seed_resolved_entities(normalized)
    target_groups = _target_groups(normalized)
    situational_constraints = _situational_constraints(normalized)
    ambiguity_warnings = _ambiguity_warnings(
        normalized=normalized,
        warnings=warnings,
        canonical_terms=canonical_terms,
        entities=entities,
        resolved_entities=resolved_entities,
    )
    unresolved_high_value_terms = _unresolved_high_value_terms(
        normalized=normalized,
        raw_unknown_terms=raw_unknown_terms,
        resolved_entities=resolved_entities,
    )
    if unresolved_high_value_terms:
        _add(warnings, "unresolved_high_value_terms; broad fallback cannot prove answerability")

    scoring_terms = _scoring_terms(
        intents=intents,
        canonical_terms=canonical_terms,
        expanded_terms=expanded_terms,
        required_evidence=required_evidence,
        raw_unknown_terms=raw_unknown_terms,
    )
    semantic_query = " ".join(_dedupe([*canonical_terms, *expanded_terms, *required_evidence, *raw_unknown_terms]))
    retrieval_queries = _build_retrieval_queries(
        raw_question=raw_question,
        normalized_question=normalized,
        intents=intents,
        entities=entities,
        canonical_terms=canonical_terms,
        expanded_terms=expanded_terms,
        required_evidence=required_evidence,
        raw_unknown_terms=raw_unknown_terms,
    )
    scenario_frame = _build_scenario_frame(
        normalized=normalized,
        intents=intents,
        entities=entities,
        canonical_terms=canonical_terms,
        resolved_entities=resolved_entities,
        target_groups=target_groups,
        situational_constraints=situational_constraints,
        ambiguity_warnings=ambiguity_warnings,
    )
    evidence_contract = _select_evidence_contract(intents=intents, scenario_frame=scenario_frame)

    return RulesQueryPlan(
        raw_question=raw_question,
        normalized_question=normalized,
        intents=intents,
        entities={key: _dedupe(value) for key, value in entities.items()},
        scope_tags=_dedupe(scope_tags),
        canonical_terms=_dedupe(canonical_terms),
        expanded_terms=_dedupe(expanded_terms),
        retrieval_queries=retrieval_queries,
        required_evidence=required_evidence,
        low_value_terms=low_value_terms,
        raw_unknown_terms=raw_unknown_terms,
        warnings=warnings,
        scoring_terms=scoring_terms,
        semantic_query=semantic_query or normalized,
        raw_fallback_query=raw_question,
        resolved_entities=resolved_entities,
        unresolved_high_value_terms=unresolved_high_value_terms,
        target_groups=target_groups,
        situational_constraints=situational_constraints,
        ambiguity_warnings=ambiguity_warnings,
        scenario_frame=scenario_frame,
        evidence_contract=evidence_contract,
        resolution_confidence=scenario_frame.confidence if scenario_frame else (1.0 if resolved_entities else 0.0),
    )


def _build_scenario_frame(
    *,
    normalized: str,
    intents: list[str],
    entities: dict[str, list[str]],
    canonical_terms: list[str],
    resolved_entities: list[dict[str, Any]],
    target_groups: list[str],
    situational_constraints: list[str],
    ambiguity_warnings: list[dict[str, Any]],
) -> ScenarioFrame:
    requested_shape = _requested_answer_shape(normalized, intents)
    archetype = _question_archetype(normalized, intents, requested_shape, entities, target_groups)
    mechanic = _scenario_mechanic(entities, canonical_terms, resolved_entities)
    actor = _scenario_actor(normalized, entities)
    target = _scenario_target(normalized, actor=actor, target_groups=target_groups)
    conditions = _scenario_conditions(normalized, situational_constraints)
    requires_scenario = _scenario_required(archetype, intents)
    confidence = _scenario_confidence(
        mechanic=mechanic,
        actor=actor,
        target=target,
        requested_shape=requested_shape,
        requires_scenario=requires_scenario,
        ambiguity_warnings=ambiguity_warnings,
    )
    return ScenarioFrame(
        actor=actor,
        action=_scenario_action(normalized, intents, requested_shape),
        target=target,
        mechanic=mechanic,
        entities=_scenario_entities(entities, canonical_terms, resolved_entities),
        conditions=conditions,
        polarity=_question_polarity(normalized),
        requested_answer_shape=requested_shape,
        question_archetype=archetype,
        requires_scenario=requires_scenario,
        confidence=confidence,
        ambiguity_warnings=ambiguity_warnings,
    )


def _select_evidence_contract(*, intents: list[str], scenario_frame: ScenarioFrame) -> EvidenceContract:
    archetype = scenario_frame.question_archetype
    mapping = {
        QUESTION_ARCHETYPE_DEFINITION: CONTRACT_DEFINITION,
        QUESTION_ARCHETYPE_PROCEDURE: CONTRACT_PROCEDURE,
        QUESTION_ARCHETYPE_COST: CONTRACT_COST,
        QUESTION_ARCHETYPE_RESOURCE_QUANTITY: CONTRACT_RESOURCE_QUANTITY,
        QUESTION_ARCHETYPE_TARGETING: CONTRACT_TARGETING,
        QUESTION_ARCHETYPE_RESTRICTION: CONTRACT_RESTRICTION,
        QUESTION_ARCHETYPE_INTERACTION: CONTRACT_INTERACTION,
        QUESTION_ARCHETYPE_EXCEPTION: CONTRACT_EXCEPTION,
        QUESTION_ARCHETYPE_CONFLICT: CONTRACT_CONFLICT,
        QUESTION_ARCHETYPE_BROAD_EXPLANATION: CONTRACT_PROCEDURE,
    }
    contract_id = mapping.get(archetype)
    if not contract_id:
        return CONTRACT_DEFINITIONS[CONTRACT_INSUFFICIENCY]
    if scenario_frame.requires_scenario and not scenario_frame.mechanic and INTENT_TARGETING in intents:
        return EvidenceContract(
            **{
                **CONTRACT_DEFINITIONS[CONTRACT_INSUFFICIENCY].to_dict(),
                "diagnostics": {
                    "reason": "missing_scenario_mechanic",
                    "candidate_archetype": archetype,
                },
            }
        )
    return CONTRACT_DEFINITIONS[contract_id]


def _requested_answer_shape(normalized: str, intents: list[str]) -> str:
    if re.search(r"^(?:can|could|does|do|is|are|should|would|will|did)\b", normalized):
        return "yes_no"
    if INTENT_COST in intents or re.search(r"\b(?:how\s+much|cost|costs|spend|spent|pay|rouse)\b", normalized):
        return "cost"
    if INTENT_TIMING in intents:
        return "timing"
    if INTENT_DICE_POOL in intents:
        return "dice_pool"
    if INTENT_CONSEQUENCE in intents:
        return "consequence"
    if INTENT_DEFINITION in intents and not re.search(r"\bhow\s+(?:do|does|can)\b", normalized):
        return "definition"
    if INTENT_ADVANCEMENT in intents or re.search(r"\bhow\s+(?:do|does|can)\b", normalized):
        return "procedure"
    return "explanation"


def _question_archetype(
    normalized: str,
    intents: list[str],
    requested_shape: str,
    entities: dict[str, list[str]],
    target_groups: list[str],
) -> str:
    known_entities = sum(len(values) for key, values in entities.items() if key != "raw_unknown_terms")
    if re.search(r"\b(?:conflict|contradict|which\s+rule|takes\s+precedence|override|overrides)\b", normalized):
        return QUESTION_ARCHETYPE_CONFLICT
    if re.search(r"\b(?:unless|except|exception|exceptions|special\s+case)\b", normalized):
        return QUESTION_ARCHETYPE_EXCEPTION
    if re.search(r"\b(?:cannot|cant|can't|without|not|no|prohibited|forbidden|must\s+not)\b", normalized):
        return QUESTION_ARCHETYPE_RESTRICTION
    if re.search(r"\b(?:interact|combine|stack|versus|vs|against|while|during|spot\s+someone\s+using)\b", normalized) and (
        known_entities > 1 or target_groups
    ):
        return QUESTION_ARCHETYPE_INTERACTION
    if INTENT_TARGETING in intents:
        return QUESTION_ARCHETYPE_TARGETING
    if INTENT_COST in intents and re.search(r"\b(?:how\s+much|amount|quantity|many|blood|vitae|hunger|rouse|xp|experience)\b", normalized):
        return QUESTION_ARCHETYPE_RESOURCE_QUANTITY
    if INTENT_COST in intents:
        return QUESTION_ARCHETYPE_COST
    if INTENT_CONSEQUENCE in intents:
        return QUESTION_ARCHETYPE_PROCEDURE
    if requested_shape in {"timing", "dice_pool", "procedure"} or INTENT_ADVANCEMENT in intents:
        return QUESTION_ARCHETYPE_PROCEDURE
    if INTENT_DEFINITION in intents:
        return QUESTION_ARCHETYPE_DEFINITION
    if INTENT_BROAD_EXPLANATION in intents:
        return QUESTION_ARCHETYPE_BROAD_EXPLANATION
    return QUESTION_ARCHETYPE_INSUFFICIENCY


def _scenario_required(archetype: str, intents: list[str]) -> bool:
    if archetype == QUESTION_ARCHETYPE_DEFINITION and intents == [INTENT_DEFINITION]:
        return False
    return archetype not in {QUESTION_ARCHETYPE_DEFINITION, QUESTION_ARCHETYPE_INSUFFICIENCY}


def _scenario_mechanic(
    entities: dict[str, list[str]],
    canonical_terms: list[str],
    resolved_entities: list[dict[str, Any]],
) -> str | None:
    for entity in resolved_entities:
        name = str(entity.get("canonical_name") or "").strip()
        if name:
            return name
    for key in ("powers", "disciplines", "mechanics", "clans"):
        values = entities.get(key) or []
        if values:
            return values[0]
    return canonical_terms[0] if canonical_terms else None


def _scenario_entities(
    entities: dict[str, list[str]],
    canonical_terms: list[str],
    resolved_entities: list[dict[str, Any]],
) -> list[str]:
    values: list[str] = []
    for entity in resolved_entities:
        _add(values, str(entity.get("canonical_name") or ""))
    for key in ("powers", "disciplines", "mechanics", "clans", "sects"):
        _extend(values, entities.get(key) or [])
    _extend(values, canonical_terms)
    return _dedupe(values)


def _scenario_actor(normalized: str, entities: dict[str, list[str]]) -> str | None:
    if entities.get("clans"):
        return entities["clans"][0]
    if _contains_phrase(normalized, "my character") or re.search(r"\b(?:i|me|my)\b", normalized):
        return "player_character"
    if re.search(r"\b(?:vampire|vampires|kindred)\b", normalized):
        return "vampire"
    if re.search(r"\b(?:mortal|human|kine)\b", normalized):
        return "mortal"
    return None


def _scenario_action(normalized: str, intents: list[str], requested_shape: str) -> str | None:
    patterns = (
        ("learn", r"\b(?:learn|acquire|buy|purchase|gain|get)\b"),
        ("use", r"\b(?:use|activate|employ)\b"),
        ("target", r"\b(?:target|affect|apply)\b"),
        ("perform", r"\b(?:perform|cast|make|do)\b"),
        ("roll", r"\b(?:roll|test|check)\b"),
        ("pay", r"\b(?:cost|spend|pay|rouse)\b"),
    )
    for action, pattern in patterns:
        if re.search(pattern, normalized):
            return action
    if INTENT_DEFINITION in intents:
        return "define"
    if requested_shape != "explanation":
        return requested_shape
    return None


def _scenario_target(normalized: str, *, actor: str | None, target_groups: list[str]) -> str | None:
    explicit = _explicit_target_group(normalized)
    if explicit:
        return explicit
    textual = _target_from_question_text(normalized)
    if textual:
        return _canonical_target_group(textual) or textual
    for group in target_groups:
        if actor == "player_character" and group == "vampire" and len(target_groups) > 1:
            continue
        if actor in {"vampire", "mortal", "ghoul", "animal"} and group == actor:
            continue
        return group
    return None


def _explicit_target_group(normalized: str) -> str | None:
    target_patterns = (
        r"\b(?:on|against|to|affect|affects|include|includes|target|targets)\s+(?:another|other|a|an|the|some)?\s*(vampires?|kindred|mortals?|humans?|kine|ghouls?|animals?)\b",
        r"\b(?:with|around|near|before)\s+(?:another|other|a|an|the|some)?\s*(vampires?|kindred|mortals?|humans?|kine|ghouls?|animals?)\b",
        r"\bpass(?:ing)?\s+as\s+(humans?|mortals?|kine)\b",
        r"\blook(?:ing)?\s+alive\b.*\b(?:with|around|near|before)\s+(mortals?|humans?|kine)\b",
    )
    for pattern in target_patterns:
        match = re.search(pattern, normalized)
        if match:
            canonical = _canonical_target_group(match.group(1))
            if canonical:
                return canonical
    return None


def _canonical_target_group(value: str) -> str | None:
    normalized = normalize_rules_query_text(value)
    aliases = {
        "vampire": ("vampire", "vampires", "kindred"),
        "mortal": ("mortal", "mortals", "human", "humans", "kine"),
        "ghoul": ("ghoul", "ghouls"),
        "animal": ("animal", "animals"),
    }
    for canonical, values in aliases.items():
        if normalized in values:
            return canonical
    return None


def _target_from_question_text(normalized: str) -> str | None:
    target_match = re.search(r"\b(?:on|against|to|affect)\s+(?:another|other|a|an|the)?\s*([a-z][a-z0-9 ]{2,40})$", normalized)
    if not target_match:
        return None
    target = target_match.group(1).strip()
    if not target:
        return None
    return " ".join(token for token in target.split() if token not in LOW_VALUE_TERMS) or target


def _scenario_conditions(normalized: str, situational_constraints: list[str]) -> list[str]:
    conditions = list(situational_constraints)
    if re.search(r"\b(?:without|no|not)\b", normalized):
        _add(conditions, "negative_condition")
    if re.search(r"\b(?:during|while|in combat|scene)\b", normalized):
        _add(conditions, "scene_context")
    return _dedupe(conditions)


def _question_polarity(normalized: str) -> str:
    if re.search(r"\b(?:cannot|cant|can't|without|not|no|prohibited|forbidden|must\s+not)\b", normalized):
        return "negative"
    return "positive"


def _scenario_confidence(
    *,
    mechanic: str | None,
    actor: str | None,
    target: str | None,
    requested_shape: str,
    requires_scenario: bool,
    ambiguity_warnings: list[dict[str, Any]],
) -> float:
    confidence = 0.45
    if mechanic:
        confidence += 0.25
    if actor:
        confidence += 0.08
    if target:
        confidence += 0.08
    if requested_shape != "explanation":
        confidence += 0.12
    if not requires_scenario:
        confidence += 0.12
    if ambiguity_warnings:
        confidence -= 0.12
    if requires_scenario and not mechanic:
        confidence -= 0.18
    return round(max(0.1, min(confidence, 0.95)), 2)


def _ambiguity_warnings(
    *,
    normalized: str,
    warnings: list[str],
    canonical_terms: list[str],
    entities: dict[str, list[str]],
    resolved_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ambiguity: list[dict[str, Any]] = []
    for warning in warnings:
        if "ambiguous_power_alias" in warning:
            ambiguity.append(
                {
                    "code": "ambiguous_power_alias",
                    "term": "dementation" if "dementation" in warning else None,
                    "message": warning,
                }
            )
    mechanic_like = _dedupe(
        [
            *entities.get("powers", []),
            *entities.get("disciplines", []),
            *entities.get("mechanics", []),
            *canonical_terms,
        ]
    )
    if len(mechanic_like) > 3:
        ambiguity.append(
            {
                "code": "multiple_plausible_mechanics",
                "candidates": mechanic_like[:6],
                "message": "Multiple mechanics or entities are plausible for this question.",
            }
        )
    if not mechanic_like and not resolved_entities and re.search(r"\b(?:can|could|how|use|target|affect|cost)\b", normalized):
        ambiguity.append(
            {
                "code": "missing_mechanic",
                "message": "No named mechanic or entity was detected for a scenario-shaped question.",
            }
        )
    return ambiguity


def normalize_rules_query_text(text: str) -> str:
    normalized = str(text or "").casefold()
    normalized = normalized.replace("'", "").replace("'", "")
    for compact, expanded in COMPOUND_REPLACEMENTS.items():
        normalized = re.sub(rf"\b{re.escape(compact)}\b", expanded, normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    for compact, expanded in COMPOUND_REPLACEMENTS.items():
        normalized = re.sub(rf"\b{re.escape(compact)}\b", expanded, normalized)
    return " ".join(normalized.split())


def _seed_resolved_entities(normalized: str) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for canonical, meta in TARGETED_MECHANIC_ALIASES.items():
        matched = [alias for alias in meta["aliases"] if _contains_phrase(normalized, normalize_rules_query_text(str(alias)))]
        if not matched:
            continue
        resolved.append(
            {
                "entity_id": "seed:mechanic:" + normalize_rules_query_text(canonical).replace(" ", "-"),
                "canonical_name": canonical,
                "entity_type": "mechanic",
                "accepted_aliases": _dedupe(str(alias) for alias in meta["aliases"]),
                "matched_aliases": _dedupe(matched),
                "source_anchors": [],
                "scope_tags": _dedupe(str(tag) for tag in meta.get("scope_tags", ())),
                "alias_provenance": "curated_seed",
                "confidence": 0.9,
            }
        )
    for canonical, meta in TARGETED_POWER_ALIASES.items():
        matched = [alias for alias in meta["aliases"] if _contains_phrase(normalized, normalize_rules_query_text(str(alias)))]
        if not matched:
            continue
        entity_type = "discipline" if str(canonical).casefold() == "dominate" else "power"
        resolved.append(
            {
                "entity_id": "seed:" + entity_type + ":" + normalize_rules_query_text(canonical).replace(" ", "-"),
                "canonical_name": canonical,
                "entity_type": entity_type,
                "accepted_aliases": _dedupe(str(alias) for alias in meta["aliases"]),
                "matched_aliases": _dedupe(matched),
                "source_anchors": [],
                "scope_tags": _dedupe(str(tag) for tag in meta.get("scope_tags", ())),
                "alias_provenance": "curated_seed",
                "confidence": 0.9,
            }
        )
    return resolved


def _target_groups(normalized: str) -> list[str]:
    groups: list[str] = []
    aliases = {
        "vampire": ("vampire", "vampires", "kindred", "other vampire", "other vampires"),
        "mortal": ("mortal", "mortals", "human", "humans", "kine"),
        "ghoul": ("ghoul", "ghouls"),
        "animal": ("animal", "animals"),
    }
    for canonical, values in aliases.items():
        if any(_contains_phrase(normalized, normalize_rules_query_text(value)) for value in values):
            _add(groups, canonical)
    return groups


def _situational_constraints(normalized: str) -> list[str]:
    constraints: list[str] = []
    patterns = {
        "eye_contact": r"\b(?:eye\s+contact|look(?:ing)?\s+into\s+(?:their|the)\s+eyes?|meet(?:ing)?\s+eyes?)\b",
        "touch": r"\b(?:touch|touching|physical\s+contact)\b",
        "scene_duration": r"\b(?:scene|one\s+scene|until\s+the\s+scene)\b",
        "hunger_5": r"\b(?:hunger\s+(?:5|five)|at\s+(?:5|five)\s+hunger)\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, normalized):
            _add(constraints, label)
    return constraints


def _unresolved_high_value_terms(
    *,
    normalized: str,
    raw_unknown_terms: list[str],
    resolved_entities: list[dict[str, Any]],
) -> list[str]:
    if resolved_entities:
        return []
    return []


def _detect_intents(normalized: str, entities: dict[str, list[str]]) -> list[str]:
    intents: list[str] = []
    has_named_rule_entity = any(entities[key] for key in ("disciplines", "mechanics", "powers"))
    rouse_check_definition = "rouse check" in normalized and bool(
        re.search(r"\b(?:what\s+(?:is|are|does)|define|definition|meaning|do\s+in\s+play)\b", normalized)
    )
    timing_or_casting_query = bool(
        re.search(r"\bhow\s+long\b.*\b(?:take|cast|perform)\b", normalized)
        or re.search(r"\b(?:time|duration)\b.*\b(?:cast|perform)\b", normalized)
    )

    if re.search(r"\b(?:what\s+(?:is|are)|define|definition|meaning)\b", normalized) or rouse_check_definition:
        _add(intents, INTENT_DEFINITION)
    if not timing_or_casting_query and re.search(r"\b(?:learn|acquire|buy|purchase|take|get|gain)\b", normalized) and (
        has_named_rule_entity or re.search(r"\b(?:discipline|power)\b", normalized)
    ):
        _add(intents, INTENT_ADVANCEMENT)
    if timing_or_casting_query:
        _add(intents, INTENT_TIMING)
    if re.search(
        r"\b(?:can|could|does|do)\b.*\b(?:use|affect|target|apply|work)\b.*\b(?:on|against|to)\b",
        normalized,
    ) or re.search(r"\b(?:target|targets|affect|affects|applicability|restriction|restrictions)\b", normalized):
        _add(intents, INTENT_TARGETING)
    if not rouse_check_definition and re.search(r"\b(?:cost|costs|rouse|xp|experience|spend|spent|pay)\b", normalized):
        _add(intents, INTENT_COST)
    if not rouse_check_definition and re.search(r"\b(?:dice\s+pool|pool|roll|test|check)\b", normalized):
        _add(intents, INTENT_DICE_POOL)
    if re.search(r"\b(?:what\s+happens|consequence|result|success|failure|fail|succeed)\b", normalized):
        _add(intents, INTENT_CONSEQUENCE)
    if re.search(r"\b(?:how\s+(?:do|does|can)|explain|overview|work|works|make\s+use)\b", normalized):
        _add(intents, INTENT_BROAD_EXPLANATION)

    return [intent for intent in INTENT_ORDER if intent in intents] or [INTENT_BROAD_EXPLANATION]


def _build_retrieval_queries(
    *,
    raw_question: str,
    normalized_question: str,
    intents: list[str],
    entities: dict[str, list[str]],
    canonical_terms: list[str],
    expanded_terms: list[str],
    required_evidence: list[str],
    raw_unknown_terms: list[str],
) -> list[RulesRetrievalQuery]:
    queries: list[RulesRetrievalQuery] = []
    entity_terms = _dedupe([*canonical_terms, *_high_value_expanded_terms(expanded_terms)])
    if entity_terms:
        queries.append(_retrieval_query("entity_anchor", entity_terms, evidence=[], weight=1.25))
        queries.append(_retrieval_query("canonical_entities", entity_terms, evidence=[]))

    for intent in intents:
        evidence = list(REQUIRED_EVIDENCE_BY_INTENT.get(intent, ()))
        terms = _dedupe([*entity_terms, *evidence])
        if intent == INTENT_ADVANCEMENT:
            terms = _dedupe(
                [
                    *entities.get("disciplines", []),
                    *entities.get("powers", []),
                    "discipline",
                    "power",
                    "advancement",
                    "acquisition",
                    "experience",
                    "cost",
                    "teacher",
                    "out of clan",
                ]
            )
        elif intent == INTENT_TARGETING:
            terms = _dedupe(
                [
                    *entities.get("powers", []),
                    *entities.get("disciplines", []),
                    *entities.get("mechanics", []),
                    "system",
                    "target",
                    "targets",
                    "affect",
                    "vampire",
                    "kindred",
                    "restriction",
                ]
            )
        elif intent == INTENT_DEFINITION:
            terms = _dedupe([*entities.get("mechanics", []), *entities.get("powers", []), *entity_terms, "definition", "rules"])
        elif intent == INTENT_TIMING:
            terms = _dedupe([*entity_terms, "duration", "time", "minutes", "per level", "cast", "performing", "requires"])
        if terms:
            queries.append(_retrieval_query(f"{intent}_evidence", terms, evidence=evidence, weight=0.9))

    if "mend" in normalized_question and "superficial" in normalized_question and "damage" in normalized_question:
        queries.append(
            _retrieval_query(
                "mending_damage_evidence",
                ["mending damage", "superficial damage", "rouse check", "blood potency"],
                evidence=["system", "cost"],
                weight=1.0,
            )
        )

    if required_evidence and entity_terms:
        queries.append(_retrieval_query("required_evidence", [*entity_terms, *required_evidence], evidence=required_evidence, weight=0.8))

    unknown_terms = [term for term in raw_unknown_terms if term not in LOW_VALUE_TERMS]
    if unknown_terms:
        raw_terms = unknown_terms if not entity_terms else _dedupe([*entity_terms, *unknown_terms])
        queries.append(_retrieval_query("raw_terms", raw_terms, evidence=[], weight=0.7))

    fallback_text = raw_question.strip() or normalized_question
    if fallback_text:
        queries.append(
            RulesRetrievalQuery(
                role="raw_fallback",
                text=fallback_text,
                terms=_tokens(normalize_rules_query_text(fallback_text)),
                evidence=[],
                weight=0.25,
            )
        )
    return _dedupe_retrieval_queries(queries)


def _retrieval_query(role: str, terms: Iterable[str], *, evidence: list[str], weight: float = 1.0) -> RulesRetrievalQuery:
    normalized_terms = _dedupe(_normalize_query_term(term) for term in terms if _normalize_query_term(term))
    return RulesRetrievalQuery(
        role=role,
        text=" ".join(normalized_terms),
        terms=normalized_terms,
        evidence=evidence,
        weight=weight,
    )


def _required_evidence_for_intents(intents: list[str]) -> list[str]:
    evidence: list[str] = []
    for intent in intents:
        _extend(evidence, REQUIRED_EVIDENCE_BY_INTENT.get(intent, ()))
    return _dedupe(evidence)


def _scoring_terms(
    *,
    intents: list[str],
    canonical_terms: list[str],
    expanded_terms: list[str],
    required_evidence: list[str],
    raw_unknown_terms: list[str],
) -> list[str]:
    if INTENT_ADVANCEMENT in intents or INTENT_TARGETING in intents:
        terms = _dedupe([*canonical_terms, *_high_value_expanded_terms(expanded_terms), *required_evidence])
    else:
        terms = _dedupe(canonical_terms)
    if not terms:
        terms = raw_unknown_terms
    token_terms: list[str] = []
    for term in terms:
        for token in _tokens(normalize_rules_query_text(term)):
            if token not in LOW_VALUE_TERMS:
                _add(token_terms, token)
    return token_terms


def _high_value_expanded_terms(expanded_terms: list[str]) -> list[str]:
    high_value: list[str] = []
    for term in expanded_terms:
        tokens = _tokens(normalize_rules_query_text(term))
        if not tokens or all(token in LOW_VALUE_TERMS for token in tokens):
            continue
        if len(tokens) == 1 and tokens[0] in {"bond", "bonds", "power", "vampire", "kindred"}:
            continue
        _add(high_value, term)
    return high_value


def _taxonomy_matches(normalized: str) -> list[tuple[ScopeTaxonomyEntry, str]]:
    matches: list[tuple[ScopeTaxonomyEntry, str]] = []
    matched_tags: set[str] = set()
    for entry in TAXONOMY_ENTRIES:
        aliases = sorted({*entry.aliases, entry.tag.replace(":", " ")}, key=len, reverse=True)
        for alias in aliases:
            normalized_alias = normalize_rules_query_text(alias)
            if normalized_alias and _contains_phrase(normalized, normalized_alias):
                if entry.tag not in matched_tags:
                    matches.append((entry, alias))
                    matched_tags.add(entry.tag)
                break
    return matches


def _expanded_terms_for_taxonomy_entry(entry: ScopeTaxonomyEntry, *, matched_alias: str) -> list[str]:
    terms = [matched_alias, *entry.aliases, entry.tag.split(":", 1)[-1].replace("-", " ")]
    return _dedupe(_normalize_query_term(term) for term in terms)


def _canonical_term_for_entry(entry: ScopeTaxonomyEntry, *, matched_alias: str) -> str:
    if entry.tag.startswith(("mechanic:", "content:", "topic:")):
        return _normalize_query_term(matched_alias)
    return _normalize_query_term(entry.aliases[0] if entry.aliases else entry.tag.split(":", 1)[-1])


def _add_entity(entities: dict[str, list[str]], tag: str, canonical: str) -> None:
    if tag.startswith("clan:"):
        _add(entities["clans"], canonical)
    elif tag.startswith("discipline:"):
        _add(entities["disciplines"], canonical)
    elif tag.startswith("sect:"):
        _add(entities["sects"], canonical)
    elif tag.startswith(("mechanic:", "content:", "topic:")):
        _add(entities["mechanics"], canonical)


def _raw_unknown_terms(
    tokens: list[str],
    canonical_terms: list[str],
    expanded_terms: list[str],
    low_value_terms: list[str],
) -> list[str]:
    known_tokens: set[str] = set(low_value_terms)
    for term in [*canonical_terms, *expanded_terms]:
        known_tokens.update(_tokens(normalize_rules_query_text(term)))
    return _dedupe(token for token in tokens if token not in known_tokens and token not in LOW_VALUE_TERMS)


def _any_alias_matches(normalized: str, aliases: Iterable[str]) -> bool:
    return any(_contains_phrase(normalized, normalize_rules_query_text(alias)) for alias in aliases)


def _contains_phrase(normalized: str, phrase: str) -> bool:
    if not phrase:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized) is not None


def _normalize_query_term(term: str) -> str:
    return normalize_rules_query_text(term)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text)


def _empty_entities() -> dict[str, list[str]]:
    return {
        "clans": [],
        "disciplines": [],
        "sects": [],
        "mechanics": [],
        "powers": [],
        "raw_unknown_terms": [],
    }


def _dedupe_retrieval_queries(queries: list[RulesRetrievalQuery]) -> list[RulesRetrievalQuery]:
    seen: set[tuple[str, str]] = set()
    deduped: list[RulesRetrievalQuery] = []
    for query in queries:
        key = (query.role, query.text)
        if not query.text or key in seen:
            continue
        seen.add(key)
        deduped.append(query)
    return deduped


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _add(items: list[str], item: str) -> None:
    if item and item not in items:
        items.append(item)


def _extend(items: list[str], values: Iterable[str]) -> None:
    for value in values:
        _add(items, str(value))
