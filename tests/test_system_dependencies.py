from __future__ import annotations

import json
from pathlib import Path

import pytest

import backet.cli
import backet.system_dependencies as deps
from backet.cli import app
from backet.errors import AppError
from backet.models import CommandResult, Issue
from backet.system_dependencies import DependencyStatus


def test_tesseract_executable_finds_windows_exe_outside_current_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "Tesseract-OCR"
    install_root.mkdir()
    executable = install_root / "tesseract.exe"
    executable.write_text("", encoding="utf-8")

    monkeypatch.setattr(deps.sys, "platform", "win32")
    monkeypatch.setattr(deps.shutil, "which", lambda _name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))

    assert deps.tesseract_executable() == str(executable)


def test_tesseract_status_reports_outdated_supported_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps, "tesseract_executable", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(deps, "tesseract_version", lambda _path=None: "4.1.1")
    monkeypatch.setattr(deps, "_tesseract_install_commands", lambda: (["brew", "install", "tesseract"], ["brew", "upgrade", "tesseract"]))

    status = deps.tesseract_status()

    assert status.installed is True
    assert status.ok is False
    assert status.outdated is True
    assert status.minimum_version == "5.0.0"
    assert status.upgrade_command == ["brew", "upgrade", "tesseract"]


def test_tesseract_version_accepts_windows_version_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        returncode = 0
        stdout = "tesseract v5.4.0.20240606\n leptonica-1.84.1\n"
        stderr = ""

    monkeypatch.setattr(deps.subprocess, "run", lambda *_args, **_kwargs: Completed())

    assert deps.tesseract_version("tesseract.exe") == "5.4.0.20240606"


def test_windows_tesseract_hint_and_install_command_use_winget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_which(name: str) -> str | None:
        return "C:/Windows/System32/winget.exe" if name == "winget" else None

    monkeypatch.setattr(deps.sys, "platform", "win32")
    monkeypatch.setattr(deps.shutil, "which", fake_which)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "Program Files (x86)"))

    status = deps.tesseract_status()

    assert status.installed is False
    assert status.install_supported is True
    assert status.install_command is not None
    assert "UB-Mannheim.TesseractOCR" in status.install_command
    assert "winget install" in status.hint


def test_macos_tesseract_hint_and_install_command_use_homebrew(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(name: str) -> str | None:
        return "/opt/homebrew/bin/brew" if name == "brew" else None

    monkeypatch.setattr(deps.sys, "platform", "darwin")
    monkeypatch.setattr(deps.shutil, "which", fake_which)

    status = deps.tesseract_status()

    assert status.installed is False
    assert status.install_supported is True
    assert status.install_command == ["brew", "install", "tesseract"]
    assert status.upgrade_command == ["brew", "upgrade", "tesseract"]
    assert "brew install tesseract" in status.hint


def test_install_system_dependencies_requires_explicit_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        deps,
        "tesseract_status",
        lambda: DependencyStatus(
            name="tesseract",
            installed=False,
            ok=False,
            path=None,
            version=None,
            minimum_version="5.0.0",
            outdated=False,
            install_supported=True,
            install_command=["winget", "install", "--id", "UB-Mannheim.TesseractOCR", "--exact"],
            upgrade_command=None,
            hint="Install Tesseract.",
        ),
    )

    with pytest.raises(AppError) as error:
        deps.install_system_dependencies(yes=False)

    assert error.value.code == "system_dependency_install_confirmation_required"


def test_setup_check_cli_emits_dependency_payload(
    runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_payload = CommandResult(
        message="System dependency check complete",
        data={
            "dependencies": {
                "tesseract": {
                    "installed": False,
                    "ok": False,
                    "hint": "Install Tesseract.",
                }
            }
        },
    )
    monkeypatch.setattr(backet.cli, "check_system_dependencies", lambda: result_payload)

    result = runner.invoke(app, ["--json", "setup", "check"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["dependencies"]["tesseract"]["ok"] is False


def test_setup_check_cli_emits_human_summary_without_raw_dependency_dump(
    runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_payload = CommandResult(
        message="System dependency check complete",
        data={
            "dependencies": {
                "tesseract": {
                    "installed": True,
                    "ok": True,
                    "path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    "version": "5.4.0.20240606",
                    "minimum_version": "5.0.0",
                    "outdated": False,
                    "install_command": ["winget", "install", "--id", "UB-Mannheim.TesseractOCR"],
                }
            },
            "ok": True,
        },
    )
    monkeypatch.setattr(backet.cli, "check_system_dependencies", lambda: result_payload)

    result = runner.invoke(app, ["setup", "check"])

    assert result.exit_code == 0
    assert "System dependency check complete" in result.stdout
    assert "Tesseract: ready" in result.stdout
    assert "Version: 5.4.0.20240606" in result.stdout
    assert r"Path: C:\Program Files\Tesseract-OCR\tesseract.exe" in result.stdout
    assert "OCR fallback: available" in result.stdout
    assert "Ready: yes" in result.stdout
    assert "dependencies:" not in result.stdout
    assert "install_command" not in result.stdout
    assert "{" not in result.stdout


def test_setup_check_cli_human_summary_reports_install_action_for_missing_dependency(
    runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_payload = CommandResult(
        message="System dependency check complete",
        issues=[
            Issue(
                code="tesseract_missing",
                severity="warning",
                message="Tesseract is not available, so OCR fallback for scanned/image-only PDFs will not work.",
                hint="Install Tesseract.",
                safe_to_fix=True,
            )
        ],
        data={
            "dependencies": {
                "tesseract": {
                    "installed": False,
                    "ok": False,
                    "path": None,
                    "version": None,
                    "minimum_version": "5.0.0",
                    "outdated": False,
                    "install_command": ["winget", "install", "--id", "UB-Mannheim.TesseractOCR"],
                    "hint": "Install Tesseract.",
                }
            },
            "ok": False,
        },
    )
    monkeypatch.setattr(backet.cli, "check_system_dependencies", lambda: result_payload)

    result = runner.invoke(app, ["setup", "check"])

    assert result.exit_code == 0
    assert "Tesseract: missing" in result.stdout
    assert "Required: >= 5.0.0" in result.stdout
    assert "OCR fallback: unavailable" in result.stdout
    assert "Install: winget install --id UB-Mannheim.TesseractOCR" in result.stdout
    assert "Ready: no" in result.stdout
    assert "dependencies:" not in result.stdout
    assert "install_command" not in result.stdout
    assert "{" not in result.stdout
