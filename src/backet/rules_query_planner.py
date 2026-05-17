from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from backet.rules_scope import TAXONOMY_ENTRIES, ScopeTaxonomyEntry, canonicalize_scope_tag

RULES_QUERY_PLAN_SCHEMA_VERSION = 2

INTENT_DEFINITION = "definition"
INTENT_ADVANCEMENT = "advancement"
INTENT_TARGETING = "targeting"
INTENT_COST = "cost"
INTENT_TIMING = "timing"
INTENT_DICE_POOL = "dice_pool"
INTENT_CONSEQUENCE = "consequence"
INTENT_BROAD_EXPLANATION = "broad_explanation"

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
        resolution_confidence=1.0 if resolved_entities else 0.0,
    )


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
    timing_or_casting_query = bool(
        re.search(r"\bhow\s+long\b.*\b(?:take|cast|perform)\b", normalized)
        or re.search(r"\b(?:time|duration)\b.*\b(?:cast|perform)\b", normalized)
    )

    if re.search(r"\b(?:what\s+(?:is|are)|define|definition|meaning)\b", normalized):
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
    if re.search(r"\b(?:cost|costs|rouse|xp|experience|spend|spent|pay)\b", normalized):
        _add(intents, INTENT_COST)
    if re.search(r"\b(?:dice\s+pool|pool|roll|test|check)\b", normalized):
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

    if required_evidence and entity_terms:
        queries.append(_retrieval_query("required_evidence", [*entity_terms, *required_evidence], evidence=required_evidence, weight=0.8))

    unknown_terms = [term for term in raw_unknown_terms if term not in LOW_VALUE_TERMS]
    if unknown_terms and not entity_terms:
        queries.append(_retrieval_query("raw_terms", unknown_terms, evidence=[], weight=0.7))

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
