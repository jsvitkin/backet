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
ANSWER_PACKET_SCHEMA_VERSION = 1
ANSWER_CLASS_ANSWER = "answer"
ANSWER_CLASS_INSUFFICIENT = "insufficient"
ANSWER_CLASS_AMBIGUOUS = "ambiguous"
ANSWER_CLASS_CONFLICTING = "conflicting"
ANSWER_CLASS_PERMISSION_DENIED = "permission-denied"
ANSWER_CLASS_RUNTIME_UNAVAILABLE = "runtime-unavailable"
SYSTEM_EXPLANATION_TEMPLATE_SOURCE_LIMIT = 4
SYSTEM_EXPLANATION_TEMPLATE_DETAIL_CHARS = 260
SYSTEM_EXPLANATION_PROMPT_SOURCE_LIMIT = 5
SYSTEM_EXPLANATION_PROMPT_SOURCE_CHARS = 900
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
    "whats",
    "when",
    "where",
    "who",
    "why",
    "with",
    "work",
    "working",
    "works",
}
SYSTEM_EXPLANATION_TERMS = {
    "combat",
    "conflict",
    "conflicts",
    "procedure",
    "resolution",
    "rules",
    "system",
    "systems",
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


@dataclass(slots=True)
class AnswerPacket:
    question: str
    response_class: str
    evidence_status: str
    selected_evidence: list[dict[str, Any]] = field(default_factory=list)
    fallback_context: list[dict[str, Any]] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    ambiguity: dict[str, Any] = field(default_factory=dict)
    answer_shape: str = "concise"
    diagnostics: dict[str, Any] = field(default_factory=dict)
    schema_version: int = ANSWER_PACKET_SCHEMA_VERSION

    @property
    def answerable(self) -> bool:
        return self.response_class == ANSWER_CLASS_ANSWER

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "question": self.question,
            "response_class": self.response_class,
            "evidence_status": self.evidence_status,
            "selected_evidence": self.selected_evidence,
            "fallback_context": self.fallback_context,
            "missing_evidence": self.missing_evidence,
            "ambiguity": self.ambiguity,
            "answer_shape": self.answer_shape,
            "diagnostics": self.diagnostics,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "response_class": self.response_class,
            "evidence_status": self.evidence_status,
            "selected_evidence_count": len(self.selected_evidence),
            "fallback_context_count": len(self.fallback_context),
            "missing_evidence": self.missing_evidence,
            "answer_shape": self.answer_shape,
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
        return self.generate_from_packet(build_answer_packet(question, sources))

    def generate_from_packet(self, packet: AnswerPacket) -> GeneratedAnswer:
        if packet.response_class != ANSWER_CLASS_ANSWER:
            return _non_answer_generated(packet, mode=self.mode)
        sources = packet.selected_evidence
        question = packet.question
        if not sources:
            return GeneratedAnswer(
                text="I do not have enough permitted source material to answer that.",
                mode=self.mode,
                diagnostics={"source_count": 0, "answer_packet": packet.summary()},
            )
        display_sources = _select_answer_sources(question, sources, limit=_template_source_limit(question))
        lines = _format_short_answer(question, display_sources)
        if lines:
            lines.append("")
            lines.append("**Source detail:**")
        else:
            lines = ["Relevant permitted rule text:"]
        for source in display_sources:
            snippet = _source_text_for_question(source, question, limit=_template_detail_chars(question))
            lines.append(f"**{format_bot_source_label(source)}**\n{_format_source_quote(snippet)}")
        labels = "; ".join(format_bot_source_label(source) for source in display_sources)
        lines.append(f"**Sources:** {labels}")
        return GeneratedAnswer(
            text="\n".join(lines),
            mode=self.mode,
            diagnostics={
                "source_count": len(sources),
                "question_fingerprint": _fingerprint_text(question),
                "answer_packet": packet.summary(),
            },
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
        return self.generate_from_packet(build_answer_packet(question, sources))

    def generate_from_packet(self, packet: AnswerPacket) -> GeneratedAnswer:
        if not packet.answerable:
            fallback = _generate_fallback_from_packet(self.fallback, packet)
            fallback.mode = self.mode
            fallback.diagnostics = {
                **fallback.diagnostics,
                "model_skipped_reason": f"evidence_status:{packet.evidence_status}",
            }
            return fallback
        sources = packet.selected_evidence
        if not sources:
            return _generate_fallback_from_packet(self.fallback, packet)
        prompt = build_llama_prompt(packet.question, sources, token_budget=self.token_budget, answer_packet=packet)
        try:
            text = self.client.complete(prompt, timeout_seconds=self.timeout_seconds, token_budget=self.token_budget).strip()
            validation_error = validate_generated_answer(
                text,
                sources,
                max_chars=self.max_response_chars,
                answer_packet=packet,
            )
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
                    "question_fingerprint": _fingerprint_text(packet.question),
                    "answer_packet": packet.summary(),
                },
            )
        except AppError as error:
            if not self.fallback_enabled:
                raise
            fallback = _generate_fallback_from_packet(self.fallback, packet)
            fallback.mode = self.mode
            fallback.fallback_used = True
            fallback.diagnostics = {**fallback.diagnostics, "fallback_reason": error.code}
            return fallback


def generate_answer_from_config(
    bot_config: dict[str, Any],
    question: str,
    sources: list[dict[str, Any]],
    client: ModelClient | None = None,
    answer_packet: AnswerPacket | dict[str, Any] | None = None,
) -> GeneratedAnswer:
    packet = coerce_answer_packet(question, sources, answer_packet=answer_packet)
    mode = str(bot_config.get("answer_mode") or "template")
    if mode == "llama-local":
        return LlamaLocalAnswerGenerator(model_config=bot_config.get("model", {}), client=client).generate_from_packet(packet)
    return TemplateAnswerGenerator().generate_from_packet(packet)


def build_answer_packet(
    question: str,
    sources: list[dict[str, Any]],
    retrieval_errors: list[dict[str, Any]] | None = None,
) -> AnswerPacket:
    error_packet = _answer_packet_from_retrieval_errors(question, retrieval_errors or [])
    source_packet = _answer_packet_from_sources(question, sources)
    if error_packet is not None and (source_packet is None or source_packet.response_class != ANSWER_CLASS_ANSWER):
        return error_packet
    if source_packet is not None:
        return source_packet
    if error_packet is not None:
        return error_packet
    return AnswerPacket(
        question=question,
        response_class=ANSWER_CLASS_INSUFFICIENT,
        evidence_status="insufficient",
        missing_evidence=["permitted_source"],
        answer_shape=_answer_shape_name(question),
        diagnostics={"source_count": 0},
    )


def coerce_answer_packet(
    question: str,
    sources: list[dict[str, Any]],
    *,
    answer_packet: AnswerPacket | dict[str, Any] | None = None,
) -> AnswerPacket:
    if isinstance(answer_packet, AnswerPacket):
        return answer_packet
    if isinstance(answer_packet, dict):
        return _answer_packet_from_dict(question, sources, answer_packet)
    return build_answer_packet(question, sources)


def _answer_packet_from_sources(question: str, sources: list[dict[str, Any]]) -> AnswerPacket | None:
    evidence_packet = next((source.get("evidence_packet") for source in sources if isinstance(source.get("evidence_packet"), dict)), None)
    if isinstance(evidence_packet, dict):
        status = str(evidence_packet.get("evidence_status") or "answerable")
        return AnswerPacket(
            question=question,
            response_class=_response_class_for_evidence_status(status),
            evidence_status=status,
            selected_evidence=sources if status == "answerable" else [],
            fallback_context=list(evidence_packet.get("fallback_context") or []),
            missing_evidence=[str(item) for item in evidence_packet.get("missing_evidence", []) or []],
            ambiguity=dict(evidence_packet.get("ambiguity", {}) or {}),
            answer_shape=_answer_shape_name(question),
            diagnostics={
                "source_count": len(sources),
                "packet_source": "retrieval_evidence_packet",
                "candidate_counts": evidence_packet.get("candidate_counts", {}),
            },
        )
    if sources:
        return AnswerPacket(
            question=question,
            response_class=ANSWER_CLASS_ANSWER,
            evidence_status="answerable",
            selected_evidence=sources,
            answer_shape=_answer_shape_name(question),
            diagnostics={"source_count": len(sources), "packet_source": "source_list_compatibility"},
        )
    return None


def _answer_packet_from_retrieval_errors(question: str, retrieval_errors: list[dict[str, Any]]) -> AnswerPacket | None:
    for error in retrieval_errors:
        if not isinstance(error, dict):
            continue
        details = error.get("details") if isinstance(error.get("details"), dict) else {}
        packet = details.get("evidence_packet") if isinstance(details, dict) else None
        if isinstance(packet, dict):
            return _answer_packet_from_dict(question, [], packet, diagnostics={"error_code": error.get("code")})
        if error.get("code") == "rules_query_ambiguous":
            return AnswerPacket(
                question=question,
                response_class=ANSWER_CLASS_AMBIGUOUS,
                evidence_status="ambiguous",
                ambiguity=dict(details or {}),
                answer_shape=_answer_shape_name(question),
                diagnostics={"error_code": error.get("code")},
            )
    if retrieval_errors:
        return AnswerPacket(
            question=question,
            response_class=ANSWER_CLASS_RUNTIME_UNAVAILABLE,
            evidence_status="runtime_unavailable",
            missing_evidence=["retrieval"],
            answer_shape=_answer_shape_name(question),
            diagnostics={"errors": retrieval_errors[:4]},
        )
    return None


def _answer_packet_from_dict(
    question: str,
    sources: list[dict[str, Any]],
    payload: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
) -> AnswerPacket:
    status = str(payload.get("evidence_status") or payload.get("status") or "answerable")
    response_class = str(payload.get("response_class") or _response_class_for_evidence_status(status))
    selected = sources if response_class == ANSWER_CLASS_ANSWER and sources else list(payload.get("selected_evidence") or [])
    return AnswerPacket(
        question=str(payload.get("question") or question),
        response_class=response_class,
        evidence_status=status,
        selected_evidence=selected,
        fallback_context=list(payload.get("fallback_context") or []),
        missing_evidence=[str(item) for item in payload.get("missing_evidence", []) or []],
        ambiguity=dict(payload.get("ambiguity", {}) or {}),
        answer_shape=str(payload.get("answer_shape") or _answer_shape_name(question)),
        diagnostics={**dict(payload.get("diagnostics", {}) or {}), **(diagnostics or {})},
    )


def _response_class_for_evidence_status(status: str) -> str:
    normalized = status.replace("_", "-").casefold()
    if normalized in {"answerable", "answer"}:
        return ANSWER_CLASS_ANSWER
    if normalized == "ambiguous":
        return ANSWER_CLASS_AMBIGUOUS
    if normalized == "conflicting":
        return ANSWER_CLASS_CONFLICTING
    if normalized in {"permission-denied", "denied"}:
        return ANSWER_CLASS_PERMISSION_DENIED
    if normalized in {"runtime-unavailable", "runtime unavailable", "unavailable"}:
        return ANSWER_CLASS_RUNTIME_UNAVAILABLE
    return ANSWER_CLASS_INSUFFICIENT


def _generate_fallback_from_packet(fallback: AnswerGenerator, packet: AnswerPacket) -> GeneratedAnswer:
    generator = getattr(fallback, "generate_from_packet", None)
    if callable(generator):
        return generator(packet)
    return fallback.generate(packet.question, packet.selected_evidence)


def _non_answer_generated(packet: AnswerPacket, *, mode: str) -> GeneratedAnswer:
    text = _non_answer_text(packet)
    return GeneratedAnswer(
        text=text,
        mode=mode,
        diagnostics={
            "source_count": len(packet.selected_evidence),
            "answer_packet": packet.summary(),
            "question_fingerprint": _fingerprint_text(packet.question),
        },
    )


def _non_answer_text(packet: AnswerPacket) -> str:
    if packet.response_class == ANSWER_CLASS_AMBIGUOUS:
        return (
            "I found multiple comparable permitted rule sources for that. "
            "Please narrow by book, scope, clan, discipline, or ask the Storyteller to choose."
        )
    if packet.response_class == ANSWER_CLASS_CONFLICTING:
        return "The permitted sources appear to conflict, so I cannot reconcile them safely."
    if packet.response_class == ANSWER_CLASS_PERMISSION_DENIED:
        return "Permission denied for that bot command."
    if packet.response_class == ANSWER_CLASS_RUNTIME_UNAVAILABLE:
        return "I could not retrieve enough permitted source material because retrieval is unavailable right now."
    if packet.missing_evidence:
        missing = ", ".join(packet.missing_evidence[:3])
        return f"I found related permitted material, but it is missing the evidence needed to answer safely: {missing}."
    return "I do not have enough permitted source material to answer that."


def _looks_like_substantive_answer(text: str) -> bool:
    lowered = " ".join(text.casefold().split())
    if "insufficient" in lowered or "do not have enough" in lowered or "cannot answer" in lowered:
        return False
    return len(lowered) > 80 or bool(re.search(r"\b(?:yes|no|you can|you cannot|must|requires?|costs?|roll)\b", lowered))


def _answer_shape_name(question: str) -> str:
    if _wants_consequence_list(question):
        return "consequence_bullets"
    if _wants_system_explanation(question):
        return "system_overview"
    return "concise"


def build_llama_prompt(
    question: str,
    sources: list[dict[str, Any]],
    token_budget: int,
    answer_packet: AnswerPacket | dict[str, Any] | None = None,
) -> str:
    packet = coerce_answer_packet(question, sources, answer_packet=answer_packet)
    char_budget = max(2200, min(6000, token_budget * 24))
    header = (
        "You are Backet-bot. Answer only from the SOURCE blocks below. "
        "Cite sources only once at the end as 'Sources: ...'. "
        "If the sources are insufficient, say that the permitted sources are insufficient. "
        "Start with the direct answer, not a list of sources. "
        "Do not put bracket labels like [R1] in the answer body, do not quote whole source blocks, "
        "do not print a 'closest sources' section, and do not invent beyond the sources. "
        f"EVIDENCE STATUS: {packet.evidence_status}. RESPONSE CLASS: {packet.response_class}. "
        f"{_answer_shape_instruction(question)}\n\n"
        f"QUESTION:\n{question.strip()}\n\n"
        "SOURCES:\n"
    )
    remaining = max(200, char_budget - len(header))
    blocks: list[str] = []
    prompt_sources = _select_answer_sources(question, packet.selected_evidence, limit=_prompt_source_limit(question))
    for source in prompt_sources:
        source_limit = min(_prompt_source_chars(question), max(240, remaining // max(1, len(prompt_sources))))
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


def validate_generated_answer(
    text: str,
    sources: list[dict[str, Any]],
    max_chars: int = DEFAULT_MAX_RESPONSE_CHARS,
    answer_packet: AnswerPacket | dict[str, Any] | None = None,
) -> str | None:
    if not text.strip():
        return "bot_llama_output_empty"
    if len(text) > max_chars:
        return "bot_llama_output_too_long"
    packet = coerce_answer_packet("", sources, answer_packet=answer_packet)
    if packet.response_class != ANSWER_CLASS_ANSWER:
        if _looks_like_substantive_answer(text):
            return "bot_llama_output_evidence_status_violation"
        return None
    citations = {f"[{source['citation']}]" for source in sources}
    emitted_citations = set(re.findall(r"\[[A-Z]\d+\]", text))
    unavailable = emitted_citations - citations
    if unavailable:
        return "bot_llama_output_unavailable_citation"
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
    max_bullets = _short_answer_bullet_limit(question)
    multi_source_answer = _wants_system_explanation(question) or _wants_consequence_list(question)
    for source in sources[:max(3, max_bullets)]:
        source_text = clean_bot_source_text(str(source.get("content") or source.get("excerpt") or ""))
        direct_answer_added = False
        for segment in _direct_rule_answer_segments(question, source_text, terms):
            if segment not in bullets:
                bullets.append(segment)
                direct_answer_added = True
            if len(bullets) >= max_bullets:
                return ["**Short answer:**", *(f"- {bullet}" for bullet in bullets)]
        if direct_answer_added and (_wants_consequence_list(question) or _asks_about_social_combat(question)):
            continue
        if bullets and not multi_source_answer:
            break
        segments = _answer_segments(source_text, terms, limit=_short_answer_segment_limit(question))
        if not segments:
            continue
        for segment in segments:
            if segment not in bullets:
                bullets.append(segment)
            if len(bullets) >= max_bullets:
                return ["**Short answer:**", *(f"- {bullet}" for bullet in bullets)]
        if bullets and not multi_source_answer:
            break
    if not bullets:
        return []
    return ["**Short answer:**", *(f"- {bullet}" for bullet in bullets)]


def _direct_rule_answer_segments(question: str, text: str, terms: list[str]) -> list[str]:
    direct_segments = [
        *_direct_werewolf_feeding_segments(question, text),
        *_direct_day_awake_segments(question, text),
        *_direct_social_combat_segments(question, text),
        *_direct_ritual_timing_segments(question, text),
        *_direct_blood_hunt_segments(question, text),
        *_direct_messy_critical_segments(question, text),
    ]
    if direct_segments:
        return direct_segments

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


def _direct_werewolf_feeding_segments(question: str, text: str) -> list[str]:
    if not _asks_about_werewolf_feeding(question):
        return []
    lower = text.lower()
    if not ("werewolf" in lower or "lupine" in lower):
        return []
    if "blood" not in lower or "slakes" not in lower:
        return []
    segments = [
        "Yes, a vampire can feed on werewolf blood; it is unusually potent and slakes twice the normal amount of Hunger.",
    ]
    if "draining a werewolf dry" in lower and "hunger to 0" in lower:
        segments.append("Draining a werewolf dry can reduce Hunger to 0, even for two vampires sharing the kill.")
    if "increases the difficulty to resist frenzy" in lower:
        segments.append("The danger is frenzy: each Hunger slaked with werewolf blood increases the Difficulty to resist frenzy by 1 while it remains in the vampire's system.")
    if "paranoid" in lower and "short-tempered" in lower:
        segments.append("Even if the vampire resists frenzy, the blood can leave them paranoid and short-tempered while it remains in their system.")
    return segments


def _direct_day_awake_segments(question: str, text: str) -> list[str]:
    if not _asks_about_day_awake(question):
        return []
    lower = text.lower()
    if "awakening during the day requires a humanity roll" not in lower:
        return []
    segments = [
        "Yes, but it is limited: awakening during the day requires a Humanity roll, with the Difficulty set by the crisis.",
    ]
    if "difficulty 3" in lower and "difficulty 4" in lower and "difficulty 5" in lower:
        segments.append("Examples from the rule are Difficulty 3 for life-threatening danger, Difficulty 4 for an urgent message or decision, and Difficulty 5 or higher for an inconvenience.")
    if "only act for a single scene" in lower:
        segments.append("Once awake, the vampire can act for one scene.")
    if "to remain awake longer" in lower and "difficulty 3" in lower:
        segments.append("To stay awake longer, they roll Humanity at Difficulty 3; a win grants another scene, and a critical win lets them stay awake as long as needed.")
    return segments


def _direct_social_combat_segments(question: str, text: str) -> list[str]:
    if not _asks_about_social_combat(question):
        return []
    lower = text.lower()
    if "social combat" not in lower:
        return []
    segments: list[str] = []
    if "social combat or conflict" in lower:
        segments.append("Social combat is for contested social conflict, from public humiliation to courtly intrigue.")
    if "three rounds and out" in lower or "one-roll conflict" in lower:
        segments.append("It works well as Three Rounds and Out or as a One-Roll Conflict, depending on how much focus the scene needs.")
    if "set the stakes" in lower or "requires an opponent" in lower:
        if "set the stakes" in lower and "requires an opponent" in lower:
            segments.append(
                "Set the stakes before rolling, and use it only when someone actively opposes the character on the same social ground."
            )
        elif "set the stakes" in lower:
            segments.append("Set the stakes before rolling: decide what the winner gets and what happens to the loser.")
        else:
            segments.append("Use social combat when someone actively opposes the character on the same social ground; otherwise use normal resolution.")
    if "build a dice pool" in lower or "social conflict pool" in lower:
        segments.append("Build the dice pool from the conflict type, arena, method, and audience.")
    if "compare numbers of successes" in lower and "damage to willpower" in lower:
        segments.append("Opposed rolls compare successes; the winner's margin is applied as Willpower damage.")
    if "concedes defeat" in lower and "achieves the stakes" in lower:
        segments.append("The conflict ends when someone concedes or breaks, and the winner achieves the agreed stakes.")
    return segments


def _direct_ritual_timing_segments(question: str, text: str) -> list[str]:
    if not _wants_ritual_timing(question):
        return []
    lower = text.lower()
    if "five minutes per level" not in lower:
        return []
    if not ("performing a ritual requires" in lower or "rituals unless otherwise noted" in lower):
        return []
    segments = ["Unless a ritual says otherwise, casting takes five minutes per ritual level."]
    if "rouse check" in lower and "intelligence + blood sorcery" in lower:
        segments.append("The general ritual procedure also calls for a Rouse Check and an Intelligence + Blood Sorcery test.")
    return segments


def _direct_blood_hunt_segments(question: str, text: str) -> list[str]:
    if not _asks_about_blood_hunt(question):
        return []
    lower = text.lower()
    if "blood hunt" not in lower:
        return []
    segments: list[str] = []
    if "ultimate punishment" in lower:
        segments.append(
            "A Blood Hunt is the ultimate punishment in vampire society: the target is named for lawful retaliation."
        )
    if "anyone can hunt and kill" in lower:
        segments.append("Once called, other Kindred may hunt and kill the named target.")
    if "anything goes" in lower or "murder party" in lower:
        segments.append("The sources frame it as a sanctioned free-for-all against the target, even involving diablerie in some cases.")
    return segments


def _direct_messy_critical_segments(question: str, text: str) -> list[str]:
    if not _wants_messy_critical_consequences(question):
        return []
    lower = text.lower()
    if "messy critical" not in lower and "simple mess" not in lower:
        return []
    segments: list[str] = []
    if "critical win" in lower and "hunger die" in lower:
        segments.append("A messy critical still succeeds, but the Beast shapes the success and makes the result uncontrolled.")
    if "stains" in lower:
        segments.append("One possible consequence is gaining one or more Stains from a monstrous action.")
    if "masquerade" in lower:
        segments.append("Another possible consequence is a Masquerade breach, such as obvious supernatural violence or visible feeding evidence.")
    if "loses one dot from an advantage" in lower:
        segments.append("The character can also lose a dot from an Advantage if the mess damages status, allies, resources, or similar assets.")
    if "simple mess" in lower and ("awareness" in question.casefold() or "stealth" in question.casefold()):
        segments.append(
            "For awareness or stealth tests, if the bigger messes do not fit, the result can become a simple mess: the test fails because the Beast ruins the quiet approach."
        )
    return segments


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


def _answer_segments(snippet: str, terms: list[str], limit: int = 2) -> list[str]:
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
    selected = sorted(scored[:limit], key=lambda item: item[4])
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
    if 0 < start < 900 and _looks_like_leading_table_noise(cleaned[:start]):
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
    if lower.startswith(("in social combat than", "in social combats than")):
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

    ranked: list[tuple[int, int, int, int, float, int, dict[str, Any]]] = []
    for index, source in enumerate(sources):
        text = str(source.get("content") or source.get("excerpt") or "").lower()
        phrase_hit = 1 if phrase and phrase in text else 0
        term_hits = sum(1 for term in terms if term in text)
        exact_match = 1 if "exact" in set(source.get("match_reasons", [])) else 0
        bonus = _source_question_bonus(question, text)
        score = float(source.get("score") or 0.0)
        ranked.append((bonus, phrase_hit, term_hits, exact_match, score, -index, source))

    relevant = [item for item in ranked if item[0] > 0 or item[1] > 0 or item[2] > 0 or item[3] > 0]
    if not relevant:
        return sources[:limit]
    if any(item[1] > 0 for item in relevant):
        relevant = [item for item in relevant if item[1] > 0 or item[0] > 0]
    relevant.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3], -item[4], -item[5]))
    selected = [item[6] for item in relevant[:limit]]
    if _wants_system_explanation(question):
        return _source_narrative_order(selected)
    return selected


def _source_narrative_order(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(source: dict[str, Any]) -> tuple[str, int, int, str, str]:
        return (
            str(source.get("book_title") or source.get("title") or ""),
            int(source.get("page_start") or 0),
            int(source.get("page_end") or source.get("page_start") or 0),
            str(source.get("relative_path") or ""),
            str(source.get("citation") or ""),
        )

    return sorted(sources, key=key)


def _answer_shape_instruction(question: str) -> str:
    if _wants_consequence_list(question):
        return (
            "This is asking for possible consequences. Write 3-5 concise bullets. Start with the "
            "most directly applicable consequence, then include other source-supported options."
        )
    if _wants_system_explanation(question):
        return (
            "This is a broad rules explanation request. Write a compact but complete overview in "
            "4-6 short bullets. Cover what the situation is, when to use the rule, how pools or "
            "resolution work, what consequences apply, and how the conflict ends when the sources "
            "support those points."
        )
    return "Write 2-4 concise Discord-friendly sentences, or 1-3 short bullets when the rule is procedural."


def _template_source_limit(question: str) -> int:
    if _wants_consequence_list(question):
        return 2
    if _wants_system_explanation(question):
        return SYSTEM_EXPLANATION_TEMPLATE_SOURCE_LIMIT
    return DEFAULT_TEMPLATE_SOURCE_LIMIT


def _template_detail_chars(question: str) -> int:
    if _wants_system_explanation(question):
        return SYSTEM_EXPLANATION_TEMPLATE_DETAIL_CHARS
    return DEFAULT_TEMPLATE_DETAIL_CHARS


def _prompt_source_limit(question: str) -> int:
    if _wants_consequence_list(question):
        return 4
    if _wants_system_explanation(question):
        return SYSTEM_EXPLANATION_PROMPT_SOURCE_LIMIT
    return DEFAULT_PROMPT_SOURCE_LIMIT


def _prompt_source_chars(question: str) -> int:
    if _wants_system_explanation(question):
        return SYSTEM_EXPLANATION_PROMPT_SOURCE_CHARS
    return DEFAULT_PROMPT_SOURCE_CHARS


def _short_answer_bullet_limit(question: str) -> int:
    if _wants_consequence_list(question):
        return 5
    if _wants_system_explanation(question):
        return 6
    if _asks_about_werewolf_feeding(question) or _asks_about_day_awake(question):
        return 4
    return 2


def _short_answer_segment_limit(question: str) -> int:
    if _wants_consequence_list(question):
        return 2
    if _wants_system_explanation(question):
        return 3
    return _short_answer_bullet_limit(question)


def _source_question_bonus(question: str, lower_text: str) -> int:
    bonus = 0
    if _wants_ritual_timing(question):
        if "five minutes per level" in lower_text and (
            "performing a ritual requires" in lower_text or "rituals unless otherwise noted" in lower_text
        ):
            bonus += 8
        if "performing a ritual requires" in lower_text:
            bonus += 3
    if _asks_about_blood_hunt(question):
        if "blood hunt is the ultimate punishment" in lower_text:
            bonus += 8
        elif "blood hunt" in lower_text:
            bonus += 4
        if "hunting vampires hunt" in lower_text or "hunting and feeding" in lower_text:
            bonus -= 2
    if _wants_messy_critical_consequences(question):
        if "messy critical a critical win" in lower_text:
            bonus += 6
        if "stains" in lower_text and "masquerade" in lower_text:
            bonus += 3
        if "simple mess" in lower_text and ("awareness" in question.casefold() or "stealth" in question.casefold()):
            bonus += 4
    if _asks_about_werewolf_feeding(question):
        if ("werewolf's blood" in lower_text or "werewolf’s blood" in lower_text or "lupine blood" in lower_text) and "slakes" in lower_text:
            bonus += 8
        if "difficulty to resist frenzy" in lower_text:
            bonus += 3
    if _asks_about_day_awake(question):
        if "awakening during the day requires a humanity roll" in lower_text:
            bonus += 8
        if "only act for a single scene" in lower_text and "to remain awake longer" in lower_text:
            bonus += 4
    return bonus


def _asks_about_werewolf_feeding(question: str) -> bool:
    lower = question.casefold()
    if not any(term in lower for term in ("werewolf", "werewolves", "lupine", "lupines", "garou", "werebeast")):
        return False
    return any(term in lower for term in ("eat", "feed", "drink", "blood", "bite", "drain", "slake"))


def _asks_about_day_awake(question: str) -> bool:
    lower = question.casefold()
    if "day" not in lower:
        return False
    return any(term in lower for term in ("awake", "awaken", "wake", "stay up", "day-sleep", "daysleep"))


def _wants_ritual_timing(question: str) -> bool:
    lower = question.casefold()
    return "ritual" in lower and any(term in lower for term in ("how long", "take", "time", "cast", "perform"))


def _asks_about_blood_hunt(question: str) -> bool:
    terms = _question_terms(question)
    return _question_phrase(terms) == "blood hunt" or "blood hunt" in question.casefold()


def _asks_about_social_combat(question: str) -> bool:
    return "social combat" in question.casefold()


def _wants_messy_critical_consequences(question: str) -> bool:
    lower = question.casefold()
    if "messy critical" not in lower:
        return False
    return any(term in lower for term in ("consequence", "consequences", "what happens", "potential", "result"))


def _wants_consequence_list(question: str) -> bool:
    return _wants_messy_critical_consequences(question)


def _wants_system_explanation(question: str) -> bool:
    normalized = " ".join(QUERY_TOKEN_PATTERN.findall(question.lower()))
    terms = set(_question_terms(question))
    if not terms.intersection(SYSTEM_EXPLANATION_TERMS):
        return False
    if re.search(r"\b(?:explain|overview|summarize|walk\s+me\s+through)\b", normalized):
        return True
    return bool(re.search(r"\bhow\s+(?:does|do|would|should)\b.+\b(?:work|works|run|resolve|resolved|handled)\b", normalized))


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
    joined = " ".join(terms)
    if any(term in joined for term in ("werewolf", "werewolves", "lupine", "lupines", "garou", "werebeast")) and any(
        term in joined for term in ("eat", "feed", "drink", "blood", "bite", "drain", "slake")
    ):
        for anchor_text in ("werewolf's blood", "werewolf’s blood", "lupine blood", "werewolf blood"):
            anchor_index = lower_text.find(anchor_text)
            if anchor_index >= 0:
                return anchor_index
    if "day" in joined and any(term in joined for term in ("awake", "awaken", "wake", "day-sleep", "daysleep")):
        for anchor_text in ("awakening during the day", "once awakened from day", "remain awake longer"):
            anchor_index = lower_text.find(anchor_text)
            if anchor_index >= 0:
                return anchor_index
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
