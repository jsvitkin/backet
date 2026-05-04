from __future__ import annotations

import shlex
from typing import Any

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

import backet.output as output
from backet.models import CommandResult
from backet.rules import RulesIngestProgressEvent

PHASE_LABELS = {
    "inspect": "Inspecting PDF",
    "extract": "Extracting pages",
    "ocr": "OCR fallback",
    "fingerprint": "Fingerprinting PDF",
    "store": "Storing chunks",
    "scope": "Generating scopes",
    "index": "Building search index",
    "semantic-index": "Building semantic index",
    "audit": "Summarizing quality",
}


class RulesIngestProgressReporter:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(stderr=True)
        self.interactive = self.console.is_terminal
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._last_phase: str | None = None
        self._plain_buckets: dict[str, int] = {}

    def __enter__(self) -> RulesIngestProgressReporter:
        if self.interactive:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TextColumn("{task.fields[extra]}"),
                console=self.console,
                transient=False,
            )
            self._progress.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._progress is not None:
            self._progress.stop()

    def __call__(self, event: RulesIngestProgressEvent) -> None:
        if event.phase == "start":
            self._print_start(event)
            return
        if self.interactive:
            self._render_interactive(event)
            return
        self._render_plain(event)

    def _print_start(self, event: RulesIngestProgressEvent) -> None:
        details = event.details
        title = _detail(details, "book_title", "rulebook")
        book_id = _detail(details, "book_id", "unknown")
        tier = _detail(details, "tier", "unknown")
        selected_pages = _detail(details, "selected_pages", "unknown")
        page_count = details.get("page_count")
        pages_label = f"{selected_pages} selected"
        if page_count:
            pages_label += f" of {page_count}"
        pages_spec = details.get("pages_spec")
        if pages_spec:
            pages_label += f" ({pages_spec})"

        lines = [
            f"Ingesting {title}",
            f"Book:   {book_id} ({tier})",
            f"Source: {_detail(details, 'pdf_path', 'unknown')}",
            f"Pages:  {pages_label}",
            f"Target: {_detail(details, 'rules_db', 'unknown')}",
        ]
        for line in lines:
            self.console.print(line, markup=False, highlight=False)

    def _render_interactive(self, event: RulesIngestProgressEvent) -> None:
        if self._progress is None:
            return
        description = _event_label(event)
        total = _progress_total(event)
        current = _progress_current(event, total)
        extra = _format_counters(event.counters)
        if self._task_id is None:
            self._task_id = self._progress.add_task(description, total=total, completed=current, extra=extra)
            return
        self._progress.update(self._task_id, description=description, total=total, completed=current, extra=extra)

    def _render_plain(self, event: RulesIngestProgressEvent) -> None:
        if not self._should_print_plain(event):
            return
        self.console.print(_plain_event_line(event), markup=False, highlight=False)

    def _should_print_plain(self, event: RulesIngestProgressEvent) -> bool:
        if event.phase == "ocr":
            self._last_phase = event.phase
            return True

        phase_changed = event.phase != self._last_phase
        if phase_changed:
            self._last_phase = event.phase
            self._plain_buckets[event.phase] = -1
            return True

        if event.current is None or event.total is None or event.total <= 0:
            return False

        if event.current >= event.total:
            return True

        bucket = int((event.current / event.total) * 10)
        last_bucket = self._plain_buckets.get(event.phase, -1)
        if bucket > last_bucket:
            self._plain_buckets[event.phase] = bucket
            return True
        return False


def emit_rules_ingest_report(result: CommandResult) -> None:
    data = result.data
    title = str(data.get("book_title") or data.get("book_id") or "rulebook")
    book_id = str(data.get("book_id") or "unknown")
    tier = str(data.get("tier") or "unknown")
    pages_processed = int(data.get("pages_processed") or 0)
    chunk_count = int(data.get("chunk_count") or 0)
    scope_tags = _list_values(data.get("scope_tags"))
    scope_assertions = data.get("scope_assertions")
    ocr_pages = _int_values(data.get("ocr_used_on_pages"))
    suspect_pages = _int_values(data.get("suspect_pages"))

    output.console.print(f"[bold green]Ingested {title}[/bold green]")
    output.console.print("")
    output.console.print(f"Book:    {book_id} ({tier})")
    if scope_tags:
        output.console.print(f"Scope:   {', '.join(scope_tags)}")
    if isinstance(scope_assertions, dict):
        source_scope = _list_values(scope_assertions.get("source_scope"))
        if source_scope:
            output.console.print(f"Source scope: {', '.join(source_scope)}")
    output.console.print(f"Pages:   {pages_processed:,} processed")
    output.console.print(f"Chunks:  {chunk_count:,} stored")
    if isinstance(scope_assertions, dict):
        applied = int(scope_assertions.get("applied") or 0)
        suggested = int(scope_assertions.get("suggested") or 0)
        review_needed = int(scope_assertions.get("review_needed") or 0)
        output.console.print(f"Scopes:  {applied:,} applied")
        if suggested:
            output.console.print(f"Suggest: {suggested:,} scope assertions need review")
        if review_needed:
            output.console.print(f"Review:  {review_needed:,} scope assertions need review")
    semantic_index = data.get("semantic_index")
    if isinstance(semantic_index, dict):
        mode = semantic_index.get("retrieval_mode") or "exact_only"
        backend = semantic_index.get("embedding_backend")
        model = semantic_index.get("embedding_model")
        semantic_label = str(mode)
        if backend and model:
            semantic_label += f" ({backend}: {model})"
        output.console.print(f"Search:  {semantic_label}")
    if ocr_pages:
        output.console.print(f"OCR:     {_page_count_label(len(ocr_pages))} required OCR")
    if suspect_pages:
        output.console.print(f"Review:  {_page_count_label(len(suspect_pages))} {_review_verb(len(suspect_pages))} review")
    output.console.print("")
    output.console.print(f"Stored:  {data.get('rules_db')}")
    output.console.print(f"Source:  {data.get('pdf_path')}")
    if result.created:
        output.console.print("Created:")
        for item in result.created:
            output.console.print(f"  - {item}")
    if isinstance(scope_assertions, dict):
        notable = scope_assertions.get("notable")
        if isinstance(notable, list) and notable:
            output.console.print("")
            output.console.print("Scope preview:")
            for item in notable[:5]:
                if not isinstance(item, dict):
                    continue
                output.console.print(
                    f"  - {item.get('pages')}: {item.get('tag')} ({item.get('role')}, {item.get('status')})"
                )
        if int(scope_assertions.get("review_needed") or 0):
            output.console.print(f"Run: {scope_audit_command(data)}")

    if ocr_pages:
        output.console.print("")
        output.console.print(f"Pages requiring OCR: {_page_preview(ocr_pages)}")
    if suspect_pages:
        output.console.print("")
        output.console.print("[bold yellow]Review recommended[/bold yellow]")
        output.console.print(f"Pages needing review: {_page_preview(suspect_pages)}")
        output.console.print(f"Run: {audit_command(data)}")
    if isinstance(semantic_index, dict) and not semantic_index.get("available", False):
        output.console.print("")
        output.console.print("[bold yellow]Semantic rules retrieval unavailable[/bold yellow]")
        output.console.print("Rules queries will use exact search until the semantic index is refreshed.")
        output.console.print(f"Run: {rules_index_command(data)}")


def emit_rules_audit_report(result: CommandResult, *, show_cards: bool = False) -> None:
    data = result.data
    books = data.get("books") if isinstance(data.get("books"), list) else []
    output.console.print("[bold green]Rules audit[/bold green]")
    output.console.print("")
    if not books:
        output.console.print("No ingested rulebooks matched this audit scope.")
        return

    maintenance = data.get("maintenance") if isinstance(data.get("maintenance"), list) else []
    if maintenance:
        output.console.print("[bold yellow]Maintenance[/bold yellow]")
        for item in maintenance:
            if not isinstance(item, dict):
                continue
            missing = int(item.get("missing") or 0)
            stale = int(item.get("stale") or 0)
            output.console.print(f"  - Search index needs refresh ({missing:,} missing, {stale:,} stale)")
            if item.get("repair_hint"):
                output.console.print(f"    {item.get('repair_hint')}")
        output.console.print("")

    for book in books:
        if not isinstance(book, dict):
            continue
        _emit_audit_book_summary(book)
        if show_cards:
            output.console.print("")
            _emit_audit_review_cards(book)
        notices = book.get("notices") if isinstance(book.get("notices"), list) else []
        if show_cards and notices:
            output.console.print("Notices:")
            for notice in notices[:5]:
                if not isinstance(notice, dict):
                    continue
                output.console.print(f"  - Page {notice.get('page_start')}: {notice.get('reason')}")
            remaining = len(notices) - 5
            if remaining > 0:
                output.console.print(f"  - +{remaining} more notices")
            output.console.print("")
        elif not show_cards:
            output.console.print("")


def emit_rules_audit_review_card(book: dict[str, Any], card: dict[str, Any], *, index: int, total: int) -> None:
    title = str(book.get("book_title") or book.get("book_id") or "rulebook")
    page = card.get("page_start")
    category = card.get("category") or "review"
    output.console.print("")
    output.console.print(f"[bold yellow]Review {index:,}/{total:,}: {title}, page {page}[/bold yellow]")
    output.console.print(f"Kind:   {category}")
    reasons = card.get("reasons") if isinstance(card.get("reasons"), list) else []
    if reasons:
        output.console.print(f"Reason: {reasons[0]}")
    source = card.get("source_status") if isinstance(card.get("source_status"), dict) else {}
    if source:
        output.console.print(f"Source: {source.get('status')} - {source.get('message')}")
    flags = _list_values(card.get("quality_flags"))
    if flags:
        output.console.print(f"Flags:  {', '.join(flags)}")
    excerpt = str(card.get("excerpt") or "")
    if excerpt:
        output.console.print("")
        output.console.print(excerpt, markup=False, highlight=False)
    output.console.print("")


def emit_rules_scope_audit_report(result: CommandResult) -> None:
    data = result.data
    books = data.get("books") if isinstance(data.get("books"), list) else []
    output.console.print("[bold green]Rules scope audit[/bold green]")
    output.console.print("")
    if not books:
        output.console.print("No ingested rulebooks matched this scope audit.")
        return
    for book in books:
        if not isinstance(book, dict):
            continue
        title = str(book.get("book_title") or book.get("book_id") or "rulebook")
        book_id = str(book.get("book_id") or "unknown")
        output.console.print(f"{title} ({book_id})")
        output.console.print(f"  Applied:   {int(book.get('applied') or 0):,}")
        output.console.print(f"  Suggested: {int(book.get('suggested') or 0):,}")
        output.console.print(f"  Rejected:  {int(book.get('rejected') or 0):,}")
        source_scope = _list_values(book.get("source_scope"))
        if source_scope:
            output.console.print(f"  Source:    {', '.join(source_scope)}")
        notable = book.get("notable") if isinstance(book.get("notable"), list) else []
        if notable:
            output.console.print("  Preview:")
            for item in notable[:5]:
                if not isinstance(item, dict):
                    continue
                output.console.print(
                    f"    - {item.get('pages')}: {item.get('tag')} ({item.get('role')}, {item.get('status')})"
                )
        output.console.print("")


def audit_command(data: dict[str, Any]) -> str:
    vault = shlex.quote(str(data.get("vault") or "."))
    return f"backet rules audit {vault}"


def rules_index_command(data: dict[str, Any]) -> str:
    vault = shlex.quote(str(data.get("vault") or "."))
    book_id = shlex.quote(str(data.get("book_id") or ""))
    return f"backet rules index {vault} --book-id {book_id}"


def scope_audit_command(data: dict[str, Any]) -> str:
    vault = shlex.quote(str(data.get("vault") or "."))
    book_id = shlex.quote(str(data.get("book_id") or ""))
    return f"backet rules scope audit {vault} --book-id {book_id}"


def _event_label(event: RulesIngestProgressEvent) -> str:
    if event.phase == "ocr":
        return event.message
    return PHASE_LABELS.get(event.phase, event.message or event.phase.title())


def _plain_event_line(event: RulesIngestProgressEvent) -> str:
    parts = [f"[rules ingest] {_event_label(event)}"]
    if event.current is not None and event.total is not None:
        parts.append(f"{event.current}/{event.total}")
    counters = _format_counters(event.counters)
    if counters:
        parts.append(f"({counters})")
    return " ".join(parts)


def _format_counters(counters: dict[str, int]) -> str:
    labels = {
        "ocr_pages": "OCR",
        "review_pages": "review",
        "chunks": "chunks",
        "assertions": "assertions",
        "embeddings": "embeddings",
    }
    parts = [f"{labels.get(key, key)}: {value:,}" for key, value in counters.items() if value]
    return ", ".join(parts)


def _progress_total(event: RulesIngestProgressEvent) -> int:
    if event.total is None or event.total <= 0:
        return 1
    return event.total


def _progress_current(event: RulesIngestProgressEvent, total: int) -> int:
    if event.current is None:
        return 0
    return min(max(event.current, 0), total)


def _detail(details: dict[str, Any], key: str, default: str) -> str:
    value = details.get(key)
    return str(value) if value not in (None, "") else default


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _int_values(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _page_preview(page_numbers: list[int], limit: int = 10) -> str:
    preview = ", ".join(str(page) for page in page_numbers[:limit])
    remaining = len(page_numbers) - limit
    if remaining > 0:
        return f"{preview}, +{remaining} more"
    return preview


def _page_count_label(count: int) -> str:
    noun = "page" if count == 1 else "pages"
    return f"{count:,} {noun}"


def _review_verb(count: int) -> str:
    return "needs" if count == 1 else "need"


def _emit_audit_book_summary(book: dict[str, Any]) -> None:
    title = str(book.get("book_title") or book.get("book_id") or "rulebook")
    book_id = str(book.get("book_id") or "unknown")
    tier = str(book.get("tier") or "unknown")
    source_status = book.get("source_status") if isinstance(book.get("source_status"), dict) else {}
    summary = book.get("review_summary") if isinstance(book.get("review_summary"), dict) else {}
    output.console.print(f"[bold]{title}[/bold] ({book_id}, {tier})")
    output.console.print(
        f"  Corpus: {int(book.get('page_count') or 0):,} pages, {int(book.get('chunk_count') or 0):,} chunks"
    )
    ocr_pages = _int_values(book.get("ocr_fallback_pages"))
    output.console.print(f"  OCR:    {_page_count_label(len(ocr_pages)) if ocr_pages else 'none flagged'}")
    status = str(source_status.get("status") or "unknown")
    output.console.print(f"  Source: {status} - {source_status.get('message') or 'No source status available.'}")
    pending = int(summary.get("pending_pages") or 0)
    notices = int(summary.get("notices") or 0)
    blocked = int(summary.get("blocked") or 0)
    excluded = int(summary.get("excluded_chunks") or 0)
    output.console.print(
        f"  Review: {pending:,} pending pages, {blocked:,} blocked findings, {notices:,} notices, {excluded:,} excluded chunks"
    )


def _emit_audit_review_cards(book: dict[str, Any]) -> None:
    cards = book.get("review_cards") if isinstance(book.get("review_cards"), list) else []
    if not cards:
        output.console.print("Review queue: clear")
        return
    output.console.print("[bold yellow]Review queue[/bold yellow]")
    for card in cards[:5]:
        if not isinstance(card, dict):
            continue
        page = card.get("page_start")
        category = card.get("category") or "review"
        output.console.print(f"  Page {page} ({category})")
        reasons = card.get("reasons") if isinstance(card.get("reasons"), list) else []
        if reasons:
            output.console.print(f"    Reason: {reasons[0]}")
        excerpt = str(card.get("excerpt") or "")
        if excerpt:
            output.console.print(f"    Text:   {excerpt}")
        output.console.print("    Decide: accepted | ignored | excluded | skipped")
    remaining = len(cards) - 5
    if remaining > 0:
        output.console.print(f"  +{remaining} more review cards")
