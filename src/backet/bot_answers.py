from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from backet.errors import AppError
from backet.models import CommandResult, Issue

DEFAULT_LLAMA_ENDPOINT = "http://127.0.0.1:8080/completion"
DEFAULT_LLAMA_TIMEOUT_SECONDS = 20.0
DEFAULT_LLAMA_TOKEN_BUDGET = 900
DEFAULT_MAX_RESPONSE_CHARS = 1900
DEFAULT_PROMPT_SOURCE_CHARS = 720
DEFAULT_TEMPLATE_SOURCE_LIMIT = 1
DEFAULT_TEMPLATE_DETAIL_CHARS = 420
DEFAULT_PROMPT_SOURCE_LIMIT = 3
SOURCE_QUOTE_WIDTH = 90
QUERY_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")
QUERY_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "ask",
    "at",
    "be",
    "by",
    "can",
    "do",
    "does",
    "explain",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "tell",
    "that",
    "the",
    "to",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "work",
    "working",
    "works",
}


@dataclass(slots=True)
class GeneratedAnswer:
    text: str
    mode: str
    fallback_used: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "mode": self.mode,
            "fallback_used": self.fallback_used,
            "diagnostics": self.diagnostics,
        }


class AnswerGenerator(Protocol):
    def generate(self, question: str, sources: list[dict[str, Any]]) -> GeneratedAnswer:
        ...


class ModelClient(Protocol):
    def complete(self, prompt: str, timeout_seconds: float, token_budget: int) -> str:
        ...


class TemplateAnswerGenerator:
    mode = "template"

    def generate(self, question: str, sources: list[dict[str, Any]]) -> GeneratedAnswer:
        if not sources:
            return GeneratedAnswer(
                text="I do not have enough permitted source material to answer that.",
                mode=self.mode,
                diagnostics={"source_count": 0},
            )
        display_sources = _select_answer_sources(question, sources, limit=DEFAULT_TEMPLATE_SOURCE_LIMIT)
        lines = _format_short_answer(question, display_sources)
        if lines:
            lines.append("")
            lines.append("**Source detail:**")
        else:
            lines = ["Relevant permitted rule text:"]
        for source in display_sources:
            snippet = _source_text_for_question(source, question, limit=DEFAULT_TEMPLATE_DETAIL_CHARS)
            lines.append(f"**{format_bot_source_label(source)}**\n{_format_source_quote(snippet)}")
        labels = "; ".join(format_bot_source_label(source) for source in display_sources)
        lines.append(f"**Sources:** {labels}")
        return GeneratedAnswer(
            text="\n".join(lines),
            mode=self.mode,
            diagnostics={"source_count": len(sources), "question_fingerprint": _fingerprint_text(question)},
        )


class LlamaHttpClient:
    def __init__(self, endpoint: str = DEFAULT_LLAMA_ENDPOINT) -> None:
        self.endpoint = endpoint

    def complete(self, prompt: str, timeout_seconds: float, token_budget: int) -> str:
        payload = {
            "prompt": prompt,
            "n_predict": token_budget,
            "temperature": 0.2,
            "stream": False,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as exc:
            raise AppError(
                code="bot_llama_timeout",
                message="Local Llama service timed out.",
                hint="Increase the timeout or use template fallback.",
                details={"endpoint": self.endpoint, "timeout_seconds": timeout_seconds},
                exit_code=2,
            ) from exc
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise AppError(
                code="bot_llama_unavailable",
                message="Local Llama service is unavailable or returned invalid JSON.",
                hint="Check the llama.cpp server and endpoint configuration.",
                details={"endpoint": self.endpoint, "error": str(exc)},
                exit_code=2,
            ) from exc
        return _extract_llama_text(data)


class LlamaLocalAnswerGenerator:
    mode = "llama-local"

    def __init__(
        self,
        model_config: dict[str, Any] | None = None,
        client: ModelClient | None = None,
        fallback: AnswerGenerator | None = None,
    ) -> None:
        config = dict(model_config or {})
        self.endpoint = str(config.get("endpoint") or os.environ.get("BACKET_LLAMA_ENDPOINT") or DEFAULT_LLAMA_ENDPOINT)
        self.timeout_seconds = float(config.get("timeout_seconds") or config.get("timeout") or DEFAULT_LLAMA_TIMEOUT_SECONDS)
        self.token_budget = int(config.get("token_budget") or DEFAULT_LLAMA_TOKEN_BUDGET)
        self.max_response_chars = int(config.get("max_response_chars") or DEFAULT_MAX_RESPONSE_CHARS)
        self.fallback_enabled = str(config.get("fallback", "template")).lower() != "disabled"
        self.client = client or LlamaHttpClient(endpoint=self.endpoint)
        self.fallback = fallback or TemplateAnswerGenerator()

    def generate(self, question: str, sources: list[dict[str, Any]]) -> GeneratedAnswer:
        if not sources:
            return self.fallback.generate(question, sources)
        prompt = build_llama_prompt(question, sources, token_budget=self.token_budget)
        try:
            text = self.client.complete(prompt, timeout_seconds=self.timeout_seconds, token_budget=self.token_budget).strip()
            validation_error = validate_generated_answer(text, sources, max_chars=self.max_response_chars)
            if validation_error is not None:
                raise AppError(
                    code=validation_error,
                    message="Local Llama output was not source-grounded enough for Discord.",
                    hint="Template fallback will be used when enabled.",
                    details={"mode": self.mode},
                    exit_code=2,
                )
            return GeneratedAnswer(
                text=text,
                mode=self.mode,
                diagnostics={
                    "source_count": len(sources),
                    "endpoint": self.endpoint,
                    "question_fingerprint": _fingerprint_text(question),
                },
            )
        except AppError as error:
            if not self.fallback_enabled:
                raise
            fallback = self.fallback.generate(question, sources)
            fallback.mode = self.mode
            fallback.fallback_used = True
            fallback.diagnostics = {**fallback.diagnostics, "fallback_reason": error.code}
            return fallback


def generate_answer_from_config(
    bot_config: dict[str, Any],
    question: str,
    sources: list[dict[str, Any]],
    client: ModelClient | None = None,
) -> GeneratedAnswer:
    mode = str(bot_config.get("answer_mode") or "template")
    if mode == "llama-local":
        return LlamaLocalAnswerGenerator(model_config=bot_config.get("model", {}), client=client).generate(question, sources)
    return TemplateAnswerGenerator().generate(question, sources)


def build_llama_prompt(question: str, sources: list[dict[str, Any]], token_budget: int) -> str:
    char_budget = max(2200, min(6000, token_budget * 24))
    header = (
        "You are Backet-bot. Answer only from the SOURCE blocks below. "
        "Cite sources only once at the end as 'Sources: ...'. "
        "If the sources are insufficient, say that the permitted sources are insufficient. "
        "Start with the direct answer, not a list of sources. "
        "Do not put bracket labels like [R1] in the answer body, do not quote whole source blocks, "
        "do not print a 'closest sources' section, and do not invent beyond the sources. "
        "Write 2-4 concise Discord-friendly sentences, or 1-3 short bullets when the rule is procedural.\n\n"
        f"QUESTION:\n{question.strip()}\n\n"
        "SOURCES:\n"
    )
    remaining = max(200, char_budget - len(header))
    blocks: list[str] = []
    prompt_sources = _select_answer_sources(question, sources, limit=DEFAULT_PROMPT_SOURCE_LIMIT)
    for source in prompt_sources:
        source_limit = min(DEFAULT_PROMPT_SOURCE_CHARS, max(240, remaining // max(1, len(prompt_sources))))
        excerpt = _source_text_for_question(source, question, limit=source_limit)
        if not excerpt:
            continue
        label = f"[{source['citation']}] {format_bot_source_label(source)}"
        block = f"{label}\n{excerpt}"
        blocks.append(block)
        remaining -= len(block)
        if remaining <= 0:
            break
    return f"{header}{chr(10).join(blocks)}\n\nANSWER:"


def validate_generated_answer(text: str, sources: list[dict[str, Any]], max_chars: int = DEFAULT_MAX_RESPONSE_CHARS) -> str | None:
    if not text.strip():
        return "bot_llama_output_empty"
    if len(text) > max_chars:
        return "bot_llama_output_too_long"
    citations = {f"[{source['citation']}]" for source in sources}
    source_labels = {format_bot_source_label(source).casefold() for source in sources}
    lowered = text.casefold()
    has_source_label = "sources:" in lowered and any(label in lowered for label in source_labels)
    if citations and not any(citation in text for citation in citations) and not has_source_label:
        return "bot_llama_output_missing_citation"
    return None


def validate_llama_model_files(bundle_root: Path, models_root: Path | None = None) -> CommandResult:
    manifest_path = bundle_root.expanduser().resolve() / "manifest.json"
    if not manifest_path.exists():
        raise AppError(
            code="bot_bundle_manifest_missing",
            message="Bot bundle manifest is missing.",
            hint="Export a bot bundle before checking model files.",
            details={"bundle_root": str(bundle_root)},
            exit_code=2,
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bot = manifest.get("bot", {})
    if bot.get("answer_mode") != "llama-local":
        return CommandResult(
            message="Local Llama model check skipped",
            data={"required": False, "answer_mode": bot.get("answer_mode", "template")},
        )
    model = dict(bot.get("model", {}) or {})
    model_path = str(model.get("path") or model.get("model_path") or "")
    if not model_path:
        raise AppError(
            code="bot_llama_model_path_missing",
            message="Local Llama mode requires a configured model path.",
            hint="Set model.path in bot-config.yaml.",
            exit_code=2,
        )
    path = Path(model_path).expanduser()
    if not path.is_absolute():
        root = models_root.expanduser().resolve() if models_root is not None else Path("/srv/backet-bot/models")
        path = root / path
    issues: list[Issue] = []
    if not path.exists():
        issues.append(
            Issue(
                code="bot_llama_model_missing",
                severity="error",
                message="Configured local Llama model file is missing",
                path=str(path),
                hint="Run the VM model bootstrap script or fix model.path.",
                safe_to_fix=False,
            )
        )
    expected_sha256 = str(model.get("sha256") or "").strip().lower()
    actual_sha256 = _fingerprint_file(path) if path.exists() else None
    if path.exists() and expected_sha256 and actual_sha256 != expected_sha256:
        issues.append(
            Issue(
                code="bot_llama_model_checksum_mismatch",
                severity="error",
                message="Configured local Llama model checksum does not match",
                path=str(path),
                hint="Re-download the model or update the expected checksum.",
                safe_to_fix=False,
            )
        )
    if path.exists() and not expected_sha256:
        issues.append(
            Issue(
                code="bot_llama_model_checksum_missing",
                severity="warning",
                message="Configured local Llama model has no expected checksum",
                path=str(path),
                hint="Add model.sha256 to bot-config.yaml.",
                safe_to_fix=False,
            )
        )
    return CommandResult(
        message="Local Llama model check complete",
        issues=issues,
        data={
            "required": True,
            "model_path": str(path),
            "expected_sha256": expected_sha256 or None,
            "actual_sha256": actual_sha256,
            "ok": not any(issue.severity == "error" for issue in issues),
        },
    )


def _extract_llama_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("content"), str):
        return data["content"]
    if isinstance(data.get("response"), str):
        return data["response"]
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            if isinstance(first.get("text"), str):
                return first["text"]
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    raise AppError(
        code="bot_llama_output_malformed",
        message="Local Llama service response did not contain generated text.",
        hint="Use a llama.cpp-compatible completion endpoint.",
        details={"keys": sorted(data.keys())},
        exit_code=2,
    )


def format_bot_source_label(source: dict[str, Any]) -> str:
    if source["source_type"] == "vault":
        return f"{source['title']} ({source['relative_path']})"
    page = source["page_start"]
    if source.get("page_end") and source["page_end"] != source["page_start"]:
        page = f"{source['page_start']}-{source['page_end']}"
    section = _clean_section_label(str(source.get("section_label") or ""))
    suffix = f" ({section})" if section else ""
    return f"{source['book_title']} p. {page}{suffix}"


def _source_text_for_question(source: dict[str, Any], question: str, limit: int) -> str:
    text = str(source.get("content") or source.get("excerpt") or "").strip()
    return _question_window(text, question, limit=limit)


def _format_source_quote(snippet: str) -> str:
    lines = textwrap.wrap(snippet, width=SOURCE_QUOTE_WIDTH, break_long_words=False, break_on_hyphens=False) or [snippet]
    return "\n".join(f"> {line}" for line in lines)


def _format_short_answer(question: str, sources: list[dict[str, Any]]) -> list[str]:
    terms = _question_terms(question)
    if not terms:
        return []
    bullets: list[str] = []
    for source in sources[:3]:
        source_text = clean_bot_source_text(str(source.get("content") or source.get("excerpt") or ""))
        for segment in _direct_rule_answer_segments(question, source_text, terms):
            if segment not in bullets:
                bullets.append(segment)
            if len(bullets) >= 2:
                return ["**Short answer:**", *(f"- {bullet}" for bullet in bullets)]
        if bullets:
            break
        segments = _answer_segments(source_text, terms)
        if not segments:
            continue
        for segment in segments:
            if segment not in bullets:
                bullets.append(segment)
            if len(bullets) >= 2:
                return ["**Short answer:**", *(f"- {bullet}" for bullet in bullets)]
        if bullets:
            break
    if not bullets:
        return []
    return ["**Short answer:**", *(f"- {bullet}" for bullet in bullets)]


def _direct_rule_answer_segments(question: str, text: str, terms: list[str]) -> list[str]:
    lowered_question = question.casefold()
    if not ("dicepool" in lowered_question or "dice pool" in lowered_question or "pool" in lowered_question):
        return []
    if "hunt" not in lowered_question and "predator" not in lowered_question:
        return []

    wanted_keys = _question_key_aliases(terms)
    if not wanted_keys:
        return []

    matches = re.finditer(
        r"\b(?P<key>[A-Za-z][A-Za-z '\-]{1,45}?)\s*:\s*(?P<pool>[A-Z][A-Za-z]+(?:\s*\+\s*[A-Z][A-Za-z]+)+)\s*:",
        text,
    )
    for match in matches:
        key = match.group("key").strip()
        normalized_key = _compact_key(key)
        if normalized_key not in wanted_keys:
            continue
        pool = re.sub(r"\s*\+\s*", " + ", match.group("pool").strip())
        return [f"{_display_rule_key(key)} hunting dice pool: {pool}."]
    return []


def _question_key_aliases(terms: list[str]) -> set[str]:
    aliases: set[str] = set()
    for term in terms:
        aliases.add(_compact_key(term))
    for left, right in zip(terms, terms[1:]):
        aliases.add(_compact_key(left + right))
        aliases.add(_compact_key(f"{left} {right}"))
    return {alias for alias in aliases if len(alias) >= 4}


def _compact_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _display_rule_key(text: str) -> str:
    compact = _compact_key(text)
    overrides = {
        "alleycat": "Alley Cat",
    }
    return overrides.get(compact, _title_answer_heading(text))


def _answer_segments(snippet: str, terms: list[str]) -> list[str]:
    prepared = _prepare_sentence_boundaries(snippet)
    raw_segments = [segment.strip(" -") for segment in re.split(r"(?<=[.!?])\s+", prepared) if segment.strip(" -")]
    if not raw_segments:
        raw_segments = [prepared]
    phrase = _question_phrase(terms)
    scored: list[tuple[int, int, int, int, int, str]] = []
    for index, segment in enumerate(raw_segments):
        cleaned = _clean_answer_segment(segment, terms)
        if len(cleaned) < 24 or _looks_like_bad_answer_segment(cleaned):
            continue
        lower = cleaned.lower()
        term_hits = sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", lower))
        if term_hits == 0:
            continue
        phrase_hit = 1 if phrase and phrase in lower else 0
        ordered = 1 if _first_ordered_term_start(lower, terms) >= 0 else 0
        cue = 1 if any(value in lower for value in ("system:", "cost:", "dice pool", "dice pools", "on a success", "on a failure", "to make")) else 0
        scored.append((phrase_hit, term_hits, cue, ordered, index, cleaned))
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3], item[4]))
    selected = sorted(scored[:2], key=lambda item: item[4])
    segments = [_limit_sentence(_merge_following_rule_outcomes(item[5], raw_segments, item[4], terms)) for item in selected]
    if segments and _looks_like_complete_definition(segments[0]):
        return [segments[0]]
    return segments


def _prepare_sentence_boundaries(text: str) -> str:
    text = re.sub(r"\bp\.\s*(\d+)", r"page \1", text)
    text = re.sub(r"\bp\.", "page", text)
    prepared = re.sub(r"\s+(Cost|Dice Pools?|System|Duration|Prerequisite|Level \d)\s*:", r". \1:", text)
    prepared = re.sub(r"\s+(Cost|Dice Pools?|System|Duration|Prerequisite|Level \d)\b", r". \1", prepared)
    return prepared


def _clean_answer_segment(segment: str, terms: list[str]) -> str:
    cleaned = segment.strip()
    cleaned = re.sub(r"^(?:\.\s*)+", "", cleaned).strip()
    cleaned = re.sub(r"^\([^)]{0,220}\)\s*", "", cleaned).strip()
    start = _first_ordered_term_start(cleaned.lower(), terms)
    if 0 < start < 300 and _looks_like_leading_table_noise(cleaned[:start]):
        cleaned = cleaned[start:].lstrip(" :;-")
        start = _first_ordered_term_start(cleaned.lower(), terms)
    if 0 < start < 120 and re.match(r"^(Cost|Dice Pools?|System|Duration|Prerequisite):", cleaned, flags=re.IGNORECASE):
        cleaned = cleaned[start:].lstrip(" :;-")
    cleaned = re.sub(r"^(Cost|Dice Pools?|System|Duration|Prerequisite):\s*", r"\1: ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(Committing\s+.+?)\s+(To begin\b)", r"\1: \2", cleaned)
    cleaned = cleaned.rstrip(" ,;:")
    phrase = _question_phrase(terms)
    if phrase:
        match = re.match(rf"({re.escape(phrase)})\s+([A-Z])", cleaned, flags=re.IGNORECASE)
        if match:
            prefix = match.group(1)
            if prefix.islower():
                prefix = prefix.title()
            cleaned = f"{prefix}: {cleaned[match.start(2):]}"
    term_span = _ordered_terms_span(cleaned.lower(), terms)
    if term_span and term_span[0] == 0 and term_span[1] < 90:
        tail = cleaned[term_span[1] :].lstrip()
        if tail and tail[0].isupper():
            heading = _title_answer_heading(cleaned[: term_span[1]].strip())
            cleaned = f"{heading}: {tail}"
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _merge_following_rule_outcomes(segment: str, raw_segments: list[str], index: int, terms: list[str]) -> str:
    lower = segment.lower()
    if not (lower.startswith("to make ") or "player rolls" in lower):
        return segment
    merged = [segment]
    for raw in raw_segments[index + 1 : index + 4]:
        cleaned = _clean_answer_segment(raw, terms)
        next_lower = cleaned.lower()
        if not next_lower.startswith(("as always", "on a success", "on a failure")):
            break
        merged.append(cleaned)
    return " ".join(merged)


def _looks_like_complete_definition(segment: str) -> bool:
    lower = segment.lower()
    return lower.startswith("to make ") and ("on a success" in lower or "on a failure" in lower)


def _ordered_terms_span(text: str, terms: list[str]) -> tuple[int, int] | None:
    if not terms:
        return None
    first = re.search(rf"\b{re.escape(terms[0])}\b", text)
    if first is None:
        return None
    start = first.start()
    end = first.end()
    previous = end
    for term in terms[1:]:
        match = re.search(rf"\b{re.escape(term)}\b", text[previous:])
        if match is None:
            return None
        end = previous + match.end()
        previous = end
    return start, end


def _title_answer_heading(text: str) -> str:
    small_words = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
    words = text.split()
    titled: list[str] = []
    for index, word in enumerate(words):
        lower = word.lower()
        if index > 0 and lower in small_words:
            titled.append(lower)
        else:
            titled.append(lower.capitalize())
    return " ".join(titled)


def _looks_like_bad_answer_segment(segment: str) -> bool:
    lower = segment.lower()
    if "..." in segment:
        return True
    if re.search(r"[\ue000-\uf8ff]", segment):
        return True
    if lower.startswith(("for example, this represents", "for example, this tracker")):
        return True
    if segment.count("(") != segment.count(")"):
        return True
    if re.search(r"\b(?:page|p)\s*$", segment, flags=re.IGNORECASE):
        return True
    return False


def _looks_like_leading_table_noise(text: str) -> bool:
    lower = text.lower()
    if "difficulty" in lower or lower.startswith("sample "):
        return True
    return len(re.findall(r"\b\d+\b", text)) >= 3


def _first_ordered_term_start(text: str, terms: list[str]) -> int:
    if not terms:
        return -1
    first = re.search(rf"\b{re.escape(terms[0])}\b", text)
    if first is None:
        return -1
    previous = first.start()
    for term in terms[1:]:
        match = re.search(rf"\b{re.escape(term)}\b", text[previous + 1 :])
        if match is None:
            return first.start()
        previous = previous + 1 + match.start()
    return first.start()


def _limit_sentence(sentence: str, limit: int = 320) -> str:
    sentence = " ".join(sentence.split())
    if len(sentence) <= limit:
        return sentence
    end = sentence.rfind(" ", 0, limit - 4)
    if end < 80:
        end = limit - 4
    return sentence[:end].rstrip(" ,;:") + " ..."


def _select_answer_sources(question: str, sources: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not sources or limit <= 0:
        return []
    terms = _question_terms(question)
    if not terms:
        return sources[:limit]
    phrase = _question_phrase(terms)

    ranked: list[tuple[int, int, int, float, int, dict[str, Any]]] = []
    for index, source in enumerate(sources):
        text = str(source.get("content") or source.get("excerpt") or "").lower()
        phrase_hit = 1 if phrase and phrase in text else 0
        term_hits = sum(1 for term in terms if term in text)
        exact_match = 1 if "exact" in set(source.get("match_reasons", [])) else 0
        score = float(source.get("score") or 0.0)
        ranked.append((phrase_hit, term_hits, exact_match, score, -index, source))

    relevant = [item for item in ranked if item[0] > 0 or item[1] > 0 or item[2] > 0]
    if not relevant:
        return sources[:limit]
    if any(item[0] > 0 for item in relevant):
        relevant = [item for item in relevant if item[0] > 0]
    relevant.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3], -item[4]))
    return [item[5] for item in relevant[:limit]]


def _question_window(text: str, question: str, limit: int) -> str:
    normalized = clean_bot_source_text(text)
    if not normalized or len(normalized) <= limit:
        return normalized

    terms = _question_terms(question)
    lower = normalized.lower()
    start = _best_window_start(lower, terms, limit)
    end = min(len(normalized), start + limit)
    if start > 0 and not normalized[start - 1].isspace():
        next_space = normalized.find(" ", start)
        if 0 <= next_space < start + 40:
            start = next_space + 1
    if end < len(normalized):
        previous_space = normalized.rfind(" ", start, end)
        if previous_space > start + int(limit * 0.6):
            end = previous_space
    snippet = normalized[start:end].strip()
    if start > 0:
        snippet = f"... {snippet}"
    if end < len(normalized):
        snippet = f"{snippet} ..."
    return snippet


def _best_window_start(lower_text: str, terms: list[str], limit: int) -> int:
    if not terms:
        return 0
    phrase = _question_phrase(terms)
    anchors: list[int] = []
    for alias in _question_key_aliases(terms):
        alias_match = re.search(rf"\b{re.escape(alias)}\s*:", lower_text)
        if alias_match:
            return alias_match.start()
    if len(terms) > 1:
        phrase_index = lower_text.find(phrase)
        if phrase_index >= 0:
            return phrase_index
        ordered_span = _ordered_terms_span(lower_text, terms)
        if ordered_span and ordered_span[1] - ordered_span[0] <= 140:
            return ordered_span[0]
    for term in terms:
        index = lower_text.find(term)
        while index >= 0 and len(anchors) < 40:
            anchors.append(index)
            index = lower_text.find(term, index + len(term))
    if not anchors:
        return 0

    best_start = 0
    best_score = -1
    for anchor in anchors:
        current_start = max(0, anchor - limit // 4)
        window = lower_text[current_start : current_start + limit]
        score = sum(window.count(term) for term in terms)
        if phrase and phrase in window:
            score += 5
        if score > best_score or (score == best_score and current_start < best_start):
            best_score = score
            best_start = current_start
    return best_start


def _question_terms(question: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for term in QUERY_TOKEN_PATTERN.findall(question.lower()):
        if len(term) <= 1 or term in QUERY_STOPWORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _question_phrase(terms: list[str]) -> str:
    return " ".join(terms) if len(terms) > 1 else ""


def clean_bot_source_text(text: str) -> str:
    text = re.sub(r"\u00ad\s*", "", text)
    cleaned = (
        text.replace("\u0083", "-")
        .replace("■", "-")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    cleaned = re.sub(r"[\ue000-\uf8ff]+", "", cleaned)
    return " ".join(cleaned.split())


def _clean_section_label(label: str) -> str:
    cleaned = clean_bot_source_text(label)
    if not cleaned:
        return ""
    compact = cleaned.replace(" ", "")
    if len(compact) >= 4 and cleaned.count(" ") >= max(2, len(compact) // 2):
        return ""
    if compact.isdigit():
        return ""
    return cleaned


def _fingerprint_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fingerprint_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
