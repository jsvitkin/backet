from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import typer

import backet.cli
import backet.cli_update as cli_update
from backet.cli import app
from backet.cli_update import (
    UPDATE_REQUIRED_EXIT_CODE,
    UpdateStatus,
    check_cli_update,
    discover_latest_release,
    is_update_snoozed,
    read_update_state,
    snooze_update,
    status_for_version,
)
from backet.distribution import load_distribution_metadata
from backet.errors import AppError
from backet.paths import resolve_machine_paths


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def fake_latest_response(version: str, *, prerelease: bool = False) -> dict[str, Any]:
    return {
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/jsvitkin/backet/releases/tag/v{version}",
        "prerelease": prerelease,
    }


def available_status(installed: str = "0.1.4", latest: str = "0.1.6") -> UpdateStatus:
    return UpdateStatus(
        installed_version=installed,
        latest_version=latest,
        update_available=True,
        repository="jsvitkin/backet",
        release_url=f"https://github.com/jsvitkin/backet/releases/tag/v{latest}",
        wheel_url=f"https://github.com/jsvitkin/backet/releases/download/v{latest}/backet-{latest}-py3-none-any.whl",
        checked_at=datetime.now(timezone.utc).isoformat(),
        source="network",
    )


def write_legacy_update_cache(latest: str = "0.1.3", *, update_available: bool = True) -> Path:
    legacy_cache_path = resolve_machine_paths().config_dir / "update-check.json"
    legacy_cache_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_cache_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "latest_version": latest,
                "update_available": update_available,
                "repository": "jsvitkin/backet",
                "release_url": f"https://github.com/jsvitkin/backet/releases/tag/v{latest}",
                "wheel_url": f"https://github.com/jsvitkin/backet/releases/download/v{latest}/backet-{latest}-py3-none-any.whl",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return legacy_cache_path


def test_discover_latest_release_resolves_stable_wheel_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        assert "releases/latest" in request.full_url  # type: ignore[attr-defined]
        assert timeout == cli_update.GITHUB_TIMEOUT_SECONDS
        return FakeResponse(fake_latest_response("0.1.3"))

    monkeypatch.setattr(cli_update, "urlopen", fake_urlopen)

    status = discover_latest_release("0.1.2", metadata=load_distribution_metadata())

    assert status.update_available is True
    assert status.latest_version == "0.1.3"
    assert status.release_url == "https://github.com/jsvitkin/backet/releases/tag/v0.1.3"
    assert status.wheel_url == "https://github.com/jsvitkin/backet/releases/download/v0.1.3/backet-0.1.3-py3-none-any.whl"


def test_discover_latest_release_ignores_prerelease(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_update, "urlopen", lambda *_args, **_kwargs: FakeResponse(fake_latest_response("0.2.0", prerelease=True)))

    status = discover_latest_release("0.1.2", metadata=load_distribution_metadata())

    assert status.latest_version == "0.2.0"
    assert status.update_available is False


def test_check_cli_update_ignores_legacy_cached_prerelease(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    write_legacy_update_cache(latest="0.2.0", update_available=False)
    monkeypatch.setattr(cli_update, "urlopen", lambda *_args, **_kwargs: FakeResponse(fake_latest_response("0.1.6")))

    status = check_cli_update("0.1.2", now=now)

    assert status.source == "network"
    assert status.latest_version == "0.1.6"
    assert status.update_available is True


def test_status_for_version_compares_versions_and_builds_artifact_url() -> None:
    newer = status_for_version("0.1.2", "v0.1.4")
    same = status_for_version("0.1.2", "0.1.2")

    assert newer.update_available is True
    assert newer.wheel_url == "https://github.com/jsvitkin/backet/releases/download/v0.1.4/backet-0.1.4-py3-none-any.whl"
    assert same.update_available is False


def test_update_check_always_uses_network_when_legacy_cache_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    write_legacy_update_cache(latest="0.1.3")
    calls: list[str] = []

    def fake_urlopen(*_args: object, **_kwargs: object) -> FakeResponse:
        calls.append("network")
        return FakeResponse(fake_latest_response("0.1.6"))

    monkeypatch.setattr(cli_update, "urlopen", fake_urlopen)
    status = check_cli_update("0.1.2", now=now)

    assert calls == ["network"]
    assert status.source == "network"
    assert status.latest_version == "0.1.6"


def test_update_check_ignores_cached_update_on_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    write_legacy_update_cache(latest="0.1.3")
    monkeypatch.setattr(cli_update, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))

    status = check_cli_update("0.1.2")

    assert status.update_available is False
    assert status.source == "unknown"
    assert status.latest_version is None
    assert "offline" in (status.error or "")


def test_update_check_returns_unknown_when_offline_without_cached_update(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_update, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))

    status = check_cli_update("0.1.2")

    assert status.update_available is False
    assert status.source == "unknown"
    assert status.latest_version is None


def test_declined_update_snooze_only_applies_to_that_version() -> None:
    status = available_status(latest="0.1.3")
    future = available_status(latest="0.1.4")

    snooze_update(status)

    assert is_update_snoozed(status) is True
    assert is_update_snoozed(future) is False


def test_declined_update_snooze_writes_snooze_only_state() -> None:
    legacy_cache_path = write_legacy_update_cache(latest="0.1.3")

    snooze_update(available_status(latest="0.1.6"))

    assert legacy_cache_path.exists()
    state = read_update_state()
    assert state is not None
    assert state["snoozed_version"] == "0.1.6"
    assert "latest_version" not in state
    assert "wheel_url" not in state


def test_update_check_command_supports_json_and_human_output(runner, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_urlopen(*_args: object, **_kwargs: object) -> FakeResponse:
        calls.append("network")
        return FakeResponse(fake_latest_response("0.1.21"))

    monkeypatch.setattr(cli_update, "urlopen", fake_urlopen)

    json_result = runner.invoke(app, ["--json", "update", "check"])
    human_result = runner.invoke(app, ["update", "check"])

    assert calls == ["network", "network"]
    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["data"]["update_available"] is True
    assert payload["data"]["latest_version"] == "0.1.21"
    assert human_result.exit_code == 0
    assert "A Backet update is available" in human_result.output


def test_update_apply_yes_runs_pipx_install_with_resolved_wheel(
    runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(cli_update, "urlopen", lambda *_args, **_kwargs: FakeResponse(fake_latest_response("0.1.21")))
    monkeypatch.setenv("BACKET_PIPX", "/tmp/pipx")

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(cli_update.subprocess, "run", fake_run)

    result = runner.invoke(app, ["--json", "update", "apply", "--yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["updated"] is True
    assert commands == [
        [
            "/tmp/pipx",
            "install",
            "--force",
            "https://github.com/jsvitkin/backet/releases/download/v0.1.21/backet-0.1.21-py3-none-any.whl",
        ]
    ]


def test_update_apply_reports_already_current_without_reinstalling(
    runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_update, "urlopen", lambda *_args, **_kwargs: FakeResponse(fake_latest_response("0.1.6")))
    monkeypatch.setattr(cli_update.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("pipx should not run"))

    result = runner.invoke(app, ["--json", "update", "apply", "--yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["message"] == "Backet is already current."
    assert payload["data"]["updated"] is False


def test_update_apply_reports_unsupported_updater(runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_update, "urlopen", lambda *_args, **_kwargs: FakeResponse(fake_latest_response("0.1.21")))
    monkeypatch.delenv("BACKET_PIPX", raising=False)
    monkeypatch.setattr(cli_update.shutil, "which", lambda _name: None)

    result = runner.invoke(app, ["--json", "update", "apply", "--yes"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "cli_update_unsupported"


def test_normal_commands_run_preflight_before_command_work(runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.delenv("BACKET_SKIP_UPDATE_CHECK", raising=False)

    def fake_check(*_args: object, **_kwargs: object) -> UpdateStatus:
        calls.append("checked")
        return UpdateStatus(
            installed_version="0.1.4",
            latest_version="0.1.4",
            update_available=False,
            repository="jsvitkin/backet",
        )

    monkeypatch.setattr(backet.cli, "check_cli_update", fake_check)

    result = runner.invoke(app, ["--json", "init", str(tmp_path / "missing")])

    assert calls == ["checked"]
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "vault_not_found"


def test_update_commands_and_version_skip_preflight(runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BACKET_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(backet.cli, "_run_update_preflight", lambda _state: pytest.fail("preflight should be skipped"))
    monkeypatch.setattr(
        backet.cli,
        "check_cli_update",
        lambda *_args, **_kwargs: UpdateStatus(
            installed_version="0.1.4",
            latest_version="0.1.4",
            update_available=False,
            repository="jsvitkin/backet",
        ),
    )

    assert runner.invoke(app, ["--json", "--version"]).exit_code == 0
    assert runner.invoke(app, ["--json", "update", "check"]).exit_code == 0


def test_interactive_preflight_accepts_update_and_reexecs(
    runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied: list[UpdateStatus] = []
    reexeced: list[list[str]] = []
    monkeypatch.delenv("BACKET_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(backet.cli, "check_cli_update", lambda *_args, **_kwargs: available_status())
    monkeypatch.setattr(backet.cli, "is_interactive_caller", lambda *, json_output: True)
    monkeypatch.setattr(backet.cli, "apply_cli_update", lambda status, **_kwargs: applied.append(status))

    def fake_reexec(argv: list[str]) -> None:
        reexeced.append(list(argv))
        raise typer.Exit(0)

    monkeypatch.setattr(backet.cli, "reexec_backet", fake_reexec)

    result = runner.invoke(app, ["init", str(tmp_path)], input="y\n")

    assert result.exit_code == 0
    assert applied and applied[0].latest_version == "0.1.6"
    assert reexeced


def test_interactive_preflight_failed_accepted_update_aborts_original_command(
    runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BACKET_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(backet.cli, "check_cli_update", lambda *_args, **_kwargs: available_status())
    monkeypatch.setattr(backet.cli, "is_interactive_caller", lambda *, json_output: True)

    def fail_update(_status: UpdateStatus, **_kwargs: object) -> None:
        raise AppError(code="cli_update_failed", message="update failed", exit_code=1)

    monkeypatch.setattr(backet.cli, "apply_cli_update", fail_update)

    result = runner.invoke(app, ["init", str(tmp_path)], input="y\n")

    assert result.exit_code == 1
    assert "update failed" in result.output
    assert not (tmp_path / ".backet").exists()


def test_interactive_preflight_decline_snoozes_and_continues(
    runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snoozed: list[UpdateStatus] = []
    monkeypatch.delenv("BACKET_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(backet.cli, "check_cli_update", lambda *_args, **_kwargs: available_status())
    monkeypatch.setattr(backet.cli, "is_interactive_caller", lambda *, json_output: True)
    monkeypatch.setattr(backet.cli, "snooze_update", lambda status: snoozed.append(status))

    result = runner.invoke(app, ["init", str(tmp_path)], input="n\n")

    assert result.exit_code == 0
    assert snoozed and snoozed[0].latest_version == "0.1.6"
    assert (tmp_path / ".backet").exists()


def test_agent_preflight_emits_update_required_before_command_work(
    runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BACKET_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(backet.cli, "check_cli_update", lambda *_args, **_kwargs: available_status())

    result = runner.invoke(app, ["--json", "init", str(tmp_path / "missing")])

    assert result.exit_code == UPDATE_REQUIRED_EXIT_CODE
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "update_required"
    assert payload["error"]["details"]["update_command"] == "backet update apply --yes"
    assert payload["error"]["details"]["retry_after_update"] is True
    assert payload["error"]["details"]["latest_version"] == "0.1.6"


def test_offline_preflight_without_cached_update_continues_normal_command(
    runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BACKET_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(cli_update, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))

    result = runner.invoke(app, ["--json", "init", str(tmp_path)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "ok"


def test_cli_update_does_not_write_vault_state_or_skill_metadata(
    runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(cli_update, "urlopen", lambda *_args, **_kwargs: FakeResponse(fake_latest_response("0.1.6")))
    monkeypatch.setenv("BACKET_PIPX", "/tmp/pipx")
    monkeypatch.setattr(
        cli_update.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, stdout="", stderr=""),
    )

    result = runner.invoke(app, ["--json", "update", "apply", "--yes"])

    assert result.exit_code == 0
    assert not (vault / ".backet").exists()
    assert not resolve_machine_paths().skill_manifest_path.exists()
    assert read_update_state() is None
