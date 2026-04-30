from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

AUTO_APPLY_CONFIDENCE = 0.85
SUGGESTION_CONFIDENCE = 0.60
SCOPE_GENERATOR = "backet-rules-scope-v1"

SCOPE_STATUS_APPLIED = "applied"
SCOPE_STATUS_SUGGESTED = "suggested"
SCOPE_STATUS_REJECTED = "rejected"
SCOPE_STATUS_SUPERSEDED = "superseded"
SCOPE_STATUSES = {
    SCOPE_STATUS_APPLIED,
    SCOPE_STATUS_SUGGESTED,
    SCOPE_STATUS_REJECTED,
    SCOPE_STATUS_SUPERSEDED,
}

SCOPE_ROLE_SOURCE = "source"
SCOPE_ROLE_MECHANICAL = "mechanical-authority"
SCOPE_ROLE_SETTING = "setting-authority"
SCOPE_ROLE_PERSPECTIVE = "perspective"
SCOPE_ROLE_MENTION = "mention"
SCOPE_ROLES = {
    SCOPE_ROLE_SOURCE,
    SCOPE_ROLE_MECHANICAL,
    SCOPE_ROLE_SETTING,
    SCOPE_ROLE_PERSPECTIVE,
    SCOPE_ROLE_MENTION,
}
AUTHORITATIVE_SCOPE_ROLES = {SCOPE_ROLE_SOURCE, SCOPE_ROLE_MECHANICAL, SCOPE_ROLE_SETTING}


@dataclass(frozen=True, slots=True)
class ScopeTaxonomyEntry:
    tag: str
    aliases: tuple[str, ...]
    default_role: str = SCOPE_ROLE_SETTING


@dataclass(slots=True)
class RulePdfOutlineEntry:
    level: int
    title: str
    page: int


@dataclass(slots=True)
class ScopeAssertionDraft:
    tag: str
    role: str
    status: str
    confidence: float
    page_start: int | None = None
    page_end: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScopeGenerationResult:
    assertions: list[ScopeAssertionDraft]

    @property
    def generated_count(self) -> int:
        return len(self.assertions)

    @property
    def applied_count(self) -> int:
        return sum(1 for assertion in self.assertions if assertion.status == SCOPE_STATUS_APPLIED)

    @property
    def suggested_count(self) -> int:
        return sum(1 for assertion in self.assertions if assertion.status == SCOPE_STATUS_SUGGESTED)

    @property
    def review_needed_count(self) -> int:
        return self.suggested_count


TAXONOMY_ENTRIES: tuple[ScopeTaxonomyEntry, ...] = (
    ScopeTaxonomyEntry("sect:camarilla", ("camarilla", "ivory tower"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("sect:anarch", ("anarch", "anarchs", "anarch movement"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("sect:sabbat", ("sabbat", "black hand", "sword of caine"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("sect:ashirra", ("ashirra",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("sect:second-inquisition", ("second inquisition", "society of st. leopold"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:banu-haqim", ("banu haqim", "children of haqim", "child of haqim", "assamite", "assamites"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:brujah", ("brujah",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:gangrel", ("gangrel",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:hecata", ("hecata", "giovanni"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:lasombra", ("lasombra",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:malkavian", ("malkavian", "malkavians"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:ministry", ("ministry", "the ministry", "followers of set", "setite", "setites"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:nosferatu", ("nosferatu",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:ravnos", ("ravnos",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:salubri", ("salubri",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:toreador", ("toreador",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:tremere", ("tremere",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:tzimisce", ("tzimisce",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:ventrue", ("ventrue",), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:caitiff", ("caitiff", "clanless"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("clan:thin-blood", ("thin-blood", "thin blood", "thin-blooded", "thin blooded"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("discipline:animalism", ("animalism",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:auspex", ("auspex",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:blood-sorcery", ("blood sorcery", "quietus", "thaumaturgy"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:celerity", ("celerity",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:dominate", ("dominate",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:fortitude", ("fortitude",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:obfuscate", ("obfuscate",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:oblivion", ("oblivion",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:potence", ("potence",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:presence", ("presence",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:protean", ("protean",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("discipline:thin-blood-alchemy", ("thin-blood alchemy", "thin blood alchemy"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:ritual", ("ritual", "rituals"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:ceremony", ("ceremony", "ceremonies"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:bane", ("bane", "clan bane"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:clan-compulsion", ("clan compulsion", "compulsion"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:institutional-conflict", ("institutional conflict", "institutional scale", "institutional damage"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:domain", ("domain", "chasse", "portillon", "lien"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:blood-potency", ("blood potency",), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:hunger", ("hunger", "rouse check", "rouse checks"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:resonance", ("resonance", "dyscrasia"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:predator-type", ("predator type", "predator types"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("mechanic:advantage", ("advantage", "advantages", "merit", "merits", "flaw", "flaws"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("content:loresheet", ("loresheet", "lore sheet", "loresheets", "lore sheets"), SCOPE_ROLE_MECHANICAL),
    ScopeTaxonomyEntry("content:city", ("city", "cities", "domain city"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("topic:masquerade", ("masquerade", "the masquerade"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("topic:gehenna-war", ("gehenna war", "beckoning"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("topic:elysium", ("elysium", "elysia"), SCOPE_ROLE_SETTING),
    ScopeTaxonomyEntry("topic:court", ("court", "prince", "primogen", "sheriff", "harpy", "herald"), SCOPE_ROLE_SETTING),
)


def _normalize_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


TAXONOMY_BY_TAG = {entry.tag: entry for entry in TAXONOMY_ENTRIES}
ALIAS_TO_TAG: dict[str, str] = {}
for entry in TAXONOMY_ENTRIES:
    ALIAS_TO_TAG[_normalize_alias(entry.tag)] = entry.tag
    for alias in entry.aliases:
        ALIAS_TO_TAG[_normalize_alias(alias)] = entry.tag

MECHANICAL_MARKERS = (
    "system",
    "dice",
    "test",
    "roll",
    "pool",
    "difficulty",
    "rouse",
    "bane",
    "clan compulsion",
    "disciplines",
    "discipline",
    "rituals",
    "ritual",
    "loresheet",
    "lore sheet",
    "advantage",
    "merit",
    "flaw",
    "hunger",
)


def canonicalize_scope_tag(value: str) -> str:
    normalized = _normalize_alias(value)
    if normalized in ALIAS_TO_TAG:
        return ALIAS_TO_TAG[normalized]
    if ":" in value:
        prefix, name = value.split(":", 1)
        return f"{_slugify(prefix)}:{_slugify(name)}"
    return _slugify(value)


def normalize_scope_tags(scope_tags: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for tag in scope_tags:
        current = canonicalize_scope_tag(str(tag))
        if current and current not in normalized:
            normalized.append(current)
    return normalized


def is_known_scope_tag(tag: str) -> bool:
    return tag in TAXONOMY_BY_TAG


def status_for_confidence(confidence: float, tag: str) -> str:
    if not is_known_scope_tag(tag):
        return SCOPE_STATUS_SUGGESTED
    if confidence >= AUTO_APPLY_CONFIDENCE:
        return SCOPE_STATUS_APPLIED
    if confidence >= SUGGESTION_CONFIDENCE:
        return SCOPE_STATUS_SUGGESTED
    return SCOPE_STATUS_REJECTED


def generate_scope_assertions(
    *,
    book_id: str,
    title: str,
    tier: str,
    pdf_path: str,
    pages: Iterable[Any],
    outline: Iterable[RulePdfOutlineEntry],
) -> ScopeGenerationResult:
    outline_by_page: dict[int, list[str]] = {}
    for entry in outline:
        outline_by_page.setdefault(entry.page, []).append(entry.title)

    source_tags = _source_tags(book_id=book_id, title=title, pdf_path=pdf_path)
    assertions: list[ScopeAssertionDraft] = []
    for tag, evidence in source_tags:
        assertions.append(
            ScopeAssertionDraft(
                tag=tag,
                role=SCOPE_ROLE_SOURCE,
                status=SCOPE_STATUS_APPLIED,
                confidence=0.92,
                evidence=evidence,
            )
        )

    for page in pages:
        page_number = int(page.page_number)
        outline_titles = outline_by_page.get(page_number, [])
        assertions.extend(
            _page_assertions(
                page_number=page_number,
                section_label=str(page.section_label),
                text=str(page.text),
                outline_titles=outline_titles,
                source_tags=[tag for tag, _ in source_tags],
            )
        )

    return ScopeGenerationResult(assertions=_dedupe_assertions(assertions))


def parse_manifest_pages(value: Any) -> tuple[int | None, int | None]:
    if value in (None, "", "book"):
        return None, None
    if isinstance(value, int):
        return value, value
    text = str(value).strip()
    if "-" in text:
        start_text, end_text = text.split("-", 1)
        start = int(start_text.strip())
        end = int(end_text.strip())
        if start > end:
            raise ValueError("page range must increase")
        return start, end
    page = int(text)
    return page, page


def manifest_pages_label(page_start: int | None, page_end: int | None) -> str:
    if page_start is None or page_end is None:
        return "book"
    if page_start == page_end:
        return str(page_start)
    return f"{page_start}-{page_end}"


def _source_tags(book_id: str, title: str, pdf_path: str) -> list[tuple[str, dict[str, Any]]]:
    haystacks = {
        "book_id": book_id,
        "title": title,
        "pdf_stem": Path(pdf_path).stem,
    }
    matches: list[tuple[str, dict[str, Any]]] = []
    for source, text in haystacks.items():
        for tag, alias in _matches(text):
            entry = TAXONOMY_BY_TAG.get(tag)
            if entry is None:
                continue
            if tag.startswith(("sect:", "clan:", "discipline:", "mechanic:", "content:", "topic:")):
                matches.append((tag, {"source": source, "matched_alias": alias, "generator": SCOPE_GENERATOR}))
    return _dedupe_source_matches(matches)


def _page_assertions(
    *,
    page_number: int,
    section_label: str,
    text: str,
    outline_titles: list[str],
    source_tags: list[str],
) -> list[ScopeAssertionDraft]:
    heading_text = "\n".join([*outline_titles, section_label, *_first_lines(text, limit=4)])
    page_text = f"{heading_text}\n{text}"
    mechanical = _has_mechanical_markers(page_text)
    drafts: list[ScopeAssertionDraft] = []

    heading_matches = _matches(heading_text)
    content_matches = _matches(text)
    for tag, alias in heading_matches:
        role = _role_for_match(tag=tag, source_tags=source_tags, mechanical=mechanical, heading=True)
        confidence = _confidence_for_match(tag=tag, role=role, heading=True, mechanical=mechanical)
        drafts.append(
            ScopeAssertionDraft(
                tag=tag,
                role=role,
                status=status_for_confidence(confidence, tag),
                confidence=confidence,
                page_start=page_number,
                page_end=page_number,
                evidence={
                    "matched_alias": alias,
                    "section_label": section_label,
                    "outline_titles": outline_titles,
                    "match_source": "heading",
                    "mechanical_markers": mechanical,
                    "generator": SCOPE_GENERATOR,
                },
            )
        )

    heading_tags = {tag for tag, _ in heading_matches}
    for tag, alias in content_matches:
        if tag in heading_tags:
            continue
        role = _role_for_match(tag=tag, source_tags=source_tags, mechanical=mechanical, heading=False)
        confidence = _confidence_for_match(tag=tag, role=role, heading=False, mechanical=mechanical)
        if confidence < SUGGESTION_CONFIDENCE:
            continue
        drafts.append(
            ScopeAssertionDraft(
                tag=tag,
                role=role,
                status=status_for_confidence(confidence, tag),
                confidence=confidence,
                page_start=page_number,
                page_end=page_number,
                evidence={
                    "matched_alias": alias,
                    "section_label": section_label,
                    "match_source": "content",
                    "mechanical_markers": mechanical,
                    "generator": SCOPE_GENERATOR,
                },
            )
        )

    unknown = _unknown_heading_suggestion(section_label, known_tags={draft.tag for draft in drafts})
    if unknown is not None:
        drafts.append(unknown)
    return _dedupe_assertions(drafts)


def _role_for_match(tag: str, source_tags: list[str], mechanical: bool, heading: bool) -> str:
    entry = TAXONOMY_BY_TAG.get(tag)
    if entry is None:
        return SCOPE_ROLE_MENTION
    if entry.default_role == SCOPE_ROLE_MECHANICAL:
        return SCOPE_ROLE_MECHANICAL
    if tag.startswith("clan:"):
        return SCOPE_ROLE_MECHANICAL if mechanical else SCOPE_ROLE_SETTING
    if tag in source_tags:
        return SCOPE_ROLE_SETTING if heading else SCOPE_ROLE_MENTION
    if tag.startswith("sect:") and heading:
        return SCOPE_ROLE_PERSPECTIVE
    return SCOPE_ROLE_SETTING if heading else SCOPE_ROLE_MENTION


def _confidence_for_match(tag: str, role: str, heading: bool, mechanical: bool) -> float:
    entry = TAXONOMY_BY_TAG.get(tag)
    if entry is None:
        return 0.62
    if role == SCOPE_ROLE_MECHANICAL and mechanical:
        return 0.93 if heading else 0.86
    if heading:
        return 0.90 if role != SCOPE_ROLE_PERSPECTIVE else 0.82
    return 0.66 if role == SCOPE_ROLE_MENTION else 0.72


def _matches(text: str) -> list[tuple[str, str]]:
    folded = text.casefold()
    matches: list[tuple[str, str]] = []
    for entry in TAXONOMY_ENTRIES:
        for alias in entry.aliases:
            if _contains_phrase(folded, alias.casefold()):
                matches.append((entry.tag, alias))
                break
    return matches


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase).replace(r"\ ", r"[\s\-]+") + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _has_mechanical_markers(text: str) -> bool:
    folded = text.casefold()
    return any(marker in folded for marker in MECHANICAL_MARKERS)


def _first_lines(text: str, limit: int) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()][:limit]


def _unknown_heading_suggestion(section_label: str, known_tags: set[str]) -> ScopeAssertionDraft | None:
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", section_label)
    if len(words) < 2 or len(words) > 5:
        return None
    if any(tag in known_tags for tag in ("content:loresheet", "mechanic:institutional-conflict")):
        return None
    lowered = section_label.casefold()
    if any(term in lowered for term in ("page", "chapter", "contents", "index")):
        return None
    if not any(term in lowered for term in ("clan", "bloodline", "discipline", "ritual", "conflict", "loresheet")):
        return None
    tag = f"unknown:{_slugify(section_label)}"
    return ScopeAssertionDraft(
        tag=tag,
        role=SCOPE_ROLE_MENTION,
        status=SCOPE_STATUS_SUGGESTED,
        confidence=0.62,
        evidence={"section_label": section_label, "match_source": "unknown-heading", "generator": SCOPE_GENERATOR},
    )


def _dedupe_assertions(assertions: Iterable[ScopeAssertionDraft]) -> list[ScopeAssertionDraft]:
    by_key: dict[tuple[str, str, int | None, int | None], ScopeAssertionDraft] = {}
    for assertion in assertions:
        key = (assertion.tag, assertion.role, assertion.page_start, assertion.page_end)
        existing = by_key.get(key)
        if existing is None or assertion.confidence > existing.confidence:
            by_key[key] = assertion
    return sorted(
        by_key.values(),
        key=lambda item: (
            item.page_start if item.page_start is not None else -1,
            item.page_end if item.page_end is not None else -1,
            item.role,
            item.tag,
        ),
    )


def _dedupe_source_matches(matches: Iterable[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    by_tag: dict[str, dict[str, Any]] = {}
    for tag, evidence in matches:
        by_tag.setdefault(tag, evidence)
    return sorted(by_tag.items(), key=lambda item: item[0])
