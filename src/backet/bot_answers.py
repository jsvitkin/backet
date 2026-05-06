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
DEFAULT_TEMPLATE_SOURCE_LIMIT = 2
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
        lines = ["Relevant permitted rule text:"]
        for source in display_sources:
            snippet = _source_text_for_question(source, question, limit=DEFAULT_PROMPT_SOURCE_CHARS)
            lines.append(f"**[{source['citation']}] {format_bot_source_label(source)}**\n{_format_source_quote(snippet)}")
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
        "Every sentence must cite one or more source labels like [V1] or [R1]. "
        "If the sources are insufficient, say that the permitted sources are insufficient. "
        "Write 2-4 concise sentences and do not invent beyond the sources.\n\n"
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
    if citations and not any(citation in text for citation in citations):
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
    if len(terms) > 1:
        phrase_index = lower_text.find(phrase)
        if phrase_index >= 0:
            return phrase_index
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
