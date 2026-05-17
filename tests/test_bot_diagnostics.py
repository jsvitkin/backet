from __future__ import annotations

from backet.bot_runtime import (
    ANSWER_TRACE_SNIPPET_CHARS,
    BotCommandRoute,
    ResolvedBotAccess,
    build_answer_trace,
)


def test_answer_trace_bounds_source_text_and_marks_future_stages_unavailable() -> None:
    source_text = ("Blood Bond rules text. " * 80) + "@everyone"
    trace = build_answer_trace(
        command="rules.ask",
        question="What are blood bonds?",
        access=ResolvedBotAccess(tier="player", user_id="user", role_ids=["role"], matched_by="role"),
        route=BotCommandRoute(
            command="rules.ask",
            min_tier="player",
            index_scope="player",
            include_rules=True,
        ),
        sources=[
            {
                "source_type": "rules",
                "citation": "R1",
                "book_id": "core",
                "book_title": "Core Rulebook",
                "page_start": 1,
                "page_end": 1,
                "section_label": "Blood Bond",
                "content": source_text,
                "score": 1.0,
                "match_reasons": ["exact"],
            }
        ],
        retrieval_errors=[],
        generated={"mode": "template", "fallback_used": False, "diagnostics": {}},
        text="Blood Bond rules text. Sources: Core Rulebook p. 1",
        parts=["Blood Bond rules text. Sources: Core Rulebook p. 1"],
        response_private=True,
        denied=False,
        retrieval_attempted=True,
    )

    traced_source = trace["retrieval"]["selected_sources"][0]
    assert trace["trace_schema_version"] == 1
    assert len(traced_source["snippet"]) <= ANSWER_TRACE_SNIPPET_CHARS
    assert "@everyone" not in traced_source["snippet"]
    assert trace["stages"]["query_plan"]["status"] == "unavailable"
    assert trace["stages"]["reranking"]["status"] == "unavailable"
    assert trace["stages"]["answerability"]["status"] == "unavailable"
    assert trace["generation"]["mode"] == "template"
