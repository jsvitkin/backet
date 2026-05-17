from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from backet.errors import AppError
from backet.models import CommandResult, Issue

MIN_TESSERACT_VERSION = Version("5.0.0")
WINDOWS_TESSERACT_PACKAGE_ID = "UB-Mannheim.TesseractOCR"


@dataclass(slots=True)
class DependencyStatus:
    name: str
    installed: bool
    ok: bool
    path: str | None
    version: str | None
    minimum_version: str | None
    outdated: bool
    install_supported: bool
    install_command: list[str] | None
    upgrade_command: list[str] | None
    hint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "installed": self.installed,
            "ok": self.ok,
            "path": self.path,
            "version": self.version,
            "minimum_version": self.minimum_version,
            "outdated": self.outdated,
            "install_supported": self.install_supported,
            "install_command": self.install_command,
            "upgrade_command": self.upgrade_command,
            "hint": self.hint,
        }


def check_system_dependencies() -> CommandResult:
    tesseract = tesseract_status()
    issues = issues_for_tesseract(tesseract)
    return CommandResult(
        message="System dependency check complete",
        issues=issues,
        data={
            "dependencies": {
                "tesseract": tesseract.to_dict(),
            },
            "ok": not issues,
        },
    )


def install_system_dependencies(yes: bool = False) -> CommandResult:
    tesseract = tesseract_status()
    if tesseract.ok:
        return CommandResult(
            message="System dependencies already installed",
            data={"dependencies": {"tesseract": tesseract.to_dict()}, "installed": [], "updated": []},
        )
    if not yes:
        raise AppError(
            code="system_dependency_install_confirmation_required",
            message="Installing system dependencies requires confirmation.",
            hint="Re-run with `backet setup install --yes` after reviewing the planned install command.",
            details={"dependencies": {"tesseract": tesseract.to_dict()}},
            exit_code=2,
        )
    if not tesseract.install_supported:
        raise AppError(
            code="system_dependency_install_unsupported",
            message="Backet cannot install Tesseract automatically on this machine.",
            hint=tesseract.hint,
            details={"dependencies": {"tesseract": tesseract.to_dict()}},
            exit_code=2,
        )

    command = tesseract.upgrade_command if tesseract.outdated and tesseract.upgrade_command else tesseract.install_command
    if not command:
        raise AppError(
            code="system_dependency_install_unavailable",
            message="No install command is available for Tesseract on this machine.",
            hint=tesseract.hint,
            details={"dependencies": {"tesseract": tesseract.to_dict()}},
            exit_code=2,
        )
    _run_install_command(command)

    refreshed = tesseract_status()
    if not refreshed.ok:
        raise AppError(
            code="system_dependency_install_failed",
            message="Tesseract installation finished, but Backet still cannot use it.",
            hint="Open a new terminal so PATH changes take effect, then run `backet setup check`.",
            details={"dependencies": {"tesseract": refreshed.to_dict()}},
            exit_code=2,
        )

    return CommandResult(
        message="System dependencies installed",
        fixed=["tesseract"],
        data={
            "dependencies": {"tesseract": refreshed.to_dict()},
            "installed": ["tesseract"] if not tesseract.installed else [],
            "updated": ["tesseract"] if tesseract.outdated else [],
        },
    )


def tesseract_status() -> DependencyStatus:
    path = tesseract_executable()
    version = tesseract_version(path) if path else None
    outdated = _version_is_outdated(version, MIN_TESSERACT_VERSION) if version else False
    installed = path is not None
    ok = installed and not outdated
    install_command, upgrade_command = _tesseract_install_commands()
    install_supported = install_command is not None
    return DependencyStatus(
        name="tesseract",
        installed=installed,
        ok=ok,
        path=path,
        version=version,
        minimum_version=str(MIN_TESSERACT_VERSION),
        outdated=outdated,
        install_supported=install_supported,
        install_command=install_command,
        upgrade_command=upgrade_command,
        hint=tesseract_install_hint(),
    )


def tesseract_executable() -> str | None:
    path = shutil.which("tesseract")
    if path:
        return path
    if sys.platform == "win32":
        for candidate in (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
        ):
            if candidate.exists():
                return str(candidate)
    return None


def tesseract_command() -> str:
    return tesseract_executable() or "tesseract"


def tesseract_version(executable: str | None = None) -> str | None:
    command = executable or tesseract_executable()
    if not command:
        return None
    completed = subprocess.run([command, "--version"], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return None
    first_line = (completed.stdout or completed.stderr).splitlines()[0] if (completed.stdout or completed.stderr) else ""
    match = re.search(r"\btesseract\s+v?([0-9]+(?:\.[0-9]+){0,3})\b", first_line, flags=re.IGNORECASE)
    return match.group(1) if match else None


def has_tesseract() -> bool:
    return tesseract_executable() is not None


def tesseract_install_hint() -> str:
    if sys.platform == "darwin":
        return "Install or update Tesseract with `brew install tesseract` or `brew upgrade tesseract`, then rerun the command."
    if sys.platform == "win32":
        return (
            "Install or update Tesseract with "
            f"`winget install --id {WINDOWS_TESSERACT_PACKAGE_ID} --exact --source winget`, "
            "then open a new terminal and rerun the command."
        )
    if sys.platform.startswith("linux"):
        return "Install or update Tesseract with your package manager, for example `sudo apt-get install tesseract-ocr`."
    return "Install Tesseract on this machine and rerun the command."


def issues_for_tesseract(status: DependencyStatus) -> list[Issue]:
    if status.ok:
        return []
    if status.outdated:
        return [
            Issue(
                code="tesseract_outdated",
                severity="warning",
                message="Tesseract is installed but below Backet's supported OCR version.",
                path=status.path,
                hint=status.hint,
                safe_to_fix=status.install_supported,
            )
        ]
    return [
        Issue(
            code="tesseract_missing",
            severity="warning",
            message="Tesseract is not available, so OCR fallback for scanned/image-only PDFs will not work.",
            hint=status.hint,
            safe_to_fix=status.install_supported,
        )
    ]


def _tesseract_install_commands() -> tuple[list[str] | None, list[str] | None]:
    if sys.platform == "darwin" and shutil.which("brew"):
        return ["brew", "install", "tesseract"], ["brew", "upgrade", "tesseract"]
    if sys.platform == "win32" and shutil.which("winget"):
        agreements = ["--accept-package-agreements", "--accept-source-agreements"]
        return (
            ["winget", "install", "--id", WINDOWS_TESSERACT_PACKAGE_ID, "--exact", "--source", "winget", *agreements],
            ["winget", "upgrade", "--id", WINDOWS_TESSERACT_PACKAGE_ID, "--exact", "--source", "winget", *agreements],
        )
    if sys.platform.startswith("linux") and shutil.which("apt-get"):
        command = ["sudo", "apt-get", "install", "-y", "tesseract-ocr"] if shutil.which("sudo") else [
            "apt-get",
            "install",
            "-y",
            "tesseract-ocr",
        ]
        return command, command
    return None, None


def _version_is_outdated(version: str, minimum: Version) -> bool:
    try:
        return Version(version) < minimum
    except InvalidVersion:
        return False


def _run_install_command(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode == 0:
        return
    raise AppError(
        code="system_dependency_install_command_failed",
        message="System dependency install command failed.",
        hint="Review the command output, install Tesseract manually if needed, then rerun `backet setup check`.",
        details={
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
        },
        exit_code=2,
    )
