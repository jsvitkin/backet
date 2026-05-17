from __future__ import annotations

import shlex
from typing import Any

from backet.models import CommandResult, Issue
from backet.output import console


def emit_system_dependencies_report(result: CommandResult) -> None:
    data = result.data if isinstance(result.data, dict) else {}
    dependencies = dict(data.get("dependencies", {}) or {})
    tesseract = dict(dependencies.get("tesseract", {}) or {})
    ok = bool(data.get("ok", not result.issues))

    console.print(f"[bold green]{result.message}[/bold green]")
    if tesseract:
        _print_tesseract_status(tesseract)
    _print_changes("Installed", data.get("installed"))
    _print_changes("Updated", data.get("updated"))
    _print_issues(result.issues)
    console.print(f"Ready: {_yes_no(ok)}")


def _print_tesseract_status(tesseract: dict[str, Any]) -> None:
    installed = bool(tesseract.get("installed"))
    ok = bool(tesseract.get("ok"))
    outdated = bool(tesseract.get("outdated"))
    status = "ready" if ok else "update recommended" if outdated else "missing"

    console.print(f"Tesseract: {status}")
    if tesseract.get("version"):
        console.print(f"  Version: {tesseract['version']}", markup=False)
    if tesseract.get("minimum_version") and not ok:
        console.print(f"  Required: >= {tesseract['minimum_version']}", markup=False)
    if tesseract.get("path"):
        console.print(f"  Path: {tesseract['path']}", markup=False)
    console.print(f"  OCR fallback: {'available' if ok else 'unavailable'}")

    command = tesseract.get("upgrade_command") if outdated else tesseract.get("install_command")
    command_label = "Update" if installed and outdated else "Install"
    formatted = _format_command(command)
    if formatted and not ok:
        console.print(f"  {command_label}: {formatted}", markup=False)
    elif tesseract.get("hint") and not ok:
        console.print(f"  Next: {tesseract['hint']}", markup=False)


def _print_changes(label: str, values: Any) -> None:
    items = [str(item) for item in values or []]
    if items:
        console.print(f"{label}: {', '.join(items)}", markup=False)


def _print_issues(issues: list[Issue]) -> None:
    if not issues:
        return
    console.print("Issues:")
    for issue in issues:
        console.print(f"  - [{issue.severity}] {issue.message}", markup=False)
        if issue.path:
            console.print(f"    Path: {issue.path}", markup=False)
        if issue.hint:
            console.print(f"    Next: {issue.hint}", markup=False)


def _format_command(command: Any) -> str | None:
    if not command:
        return None
    if isinstance(command, str):
        return command
    if isinstance(command, list):
        return shlex.join(str(part) for part in command)
    return None


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
