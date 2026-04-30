from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from backet.distribution import DistributionMetadata, load_distribution_metadata
from backet.errors import AppError
from backet.models import CommandResult
from backet.paths import resolve_machine_paths

UPDATE_CACHE_SCHEMA_VERSION = 1
UPDATE_CACHE_TTL = timedelta(hours=24)
UPDATE_SNOOZE_TTL = timedelta(hours=24)
UPDATE_REQUIRED_EXIT_CODE = 75
SKIP_UPDATE_CHECK_ENV = "BACKET_SKIP_UPDATE_CHECK"
PIPX_ENV = "BACKET_PIPX"
UPDATE_COMMAND = "backet update apply --yes"
GITHUB_TIMEOUT_SECONDS = 2.0


@dataclass(slots=True)
class UpdateStatus:
    installed_version: str
    latest_version: str | None
    update_available: bool
    repository: str
    release_url: str | None = None
    wheel_url: str | None = None
    checked_at: str | None = None
    source: str = "unknown"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "installed_version": self.installed_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "repository": self.repository,
            "release_url": self.release_url,
            "wheel_url": self.wheel_url,
            "checked_at": self.checked_at,
            "source": self.source,
            "error": self.error,
            "update_command": UPDATE_COMMAND,
            "retry_after_update": self.update_available,
        }


def check_cli_update(
    installed_version: str,
    *,
    force_refresh: bool = False,
    fail_on_error: bool = False,
    now: datetime | None = None,
) -> UpdateStatus:
    metadata = load_distribution_metadata()
    repository = metadata.resolved_repository()
    cache_path = resolve_machine_paths().update_cache_path
    current_time = now or _utc_now()
    cache = read_update_cache(cache_path)

    if not force_refresh and _cache_is_fresh(cache, current_time):
        return _status_from_cache(cache, installed_version, metadata, source="cache")

    try:
        status = discover_latest_release(installed_version, metadata=metadata, now=current_time)
        write_update_cache(status, cache_path=cache_path, existing_cache=cache)
        return status
    except AppError as exc:
        if fail_on_error:
            raise
        return _fallback_status_from_error(
            exc,
            cache=cache,
            installed_version=installed_version,
            metadata=metadata,
            repository=repository,
        )
    except Exception as exc:  # pragma: no cover - defensive around urllib/runtime edges
        if fail_on_error:
            raise AppError(
                code="cli_update_check_failed",
                message="Could not check for a newer Backet CLI release.",
                hint="Check your network connection and try `backet update check --fresh` again.",
                details={"error": str(exc)},
                exit_code=1,
            ) from exc
        return _fallback_status_from_error(
            exc,
            cache=cache,
            installed_version=installed_version,
            metadata=metadata,
            repository=repository,
        )


def discover_latest_release(
    installed_version: str,
    *,
    metadata: DistributionMetadata | None = None,
    now: datetime | None = None,
    timeout: float = GITHUB_TIMEOUT_SECONDS,
) -> UpdateStatus:
    metadata = metadata or load_distribution_metadata()
    repository = metadata.resolved_repository()
    if repository == "OWNER/REPO":
        raise AppError(
            code="cli_update_repo_unknown",
            message="No GitHub repository is configured for Backet CLI updates.",
            hint="Set BACKET_REPOSITORY or install a release built with repository metadata.",
            exit_code=2,
        )

    request = Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "backet-cli"},
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except Exception as exc:
        raise AppError(
            code="cli_update_check_failed",
            message="Could not check for a newer Backet CLI release.",
            hint="Check your network connection and try `backet update check --fresh` again.",
            details={"repository": repository, "error": str(exc)},
            exit_code=1,
        ) from exc

    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise AppError(
            code="cli_update_release_invalid",
            message="The latest Backet release metadata did not include a tag name.",
            hint="Retry later or check the repository release page.",
            details={"repository": repository},
            exit_code=1,
        )

    latest_version = normalize_release_tag(tag)
    release_url = str(payload.get("html_url") or _release_page_url(repository, latest_version))
    prerelease = bool(payload.get("prerelease"))
    update_available = (not prerelease) and is_newer_version(latest_version, installed_version)
    wheel_url = metadata.release_artifact_url(latest_version, repository=repository)

    return UpdateStatus(
        installed_version=installed_version,
        latest_version=latest_version,
        update_available=update_available,
        repository=repository,
        release_url=release_url,
        wheel_url=wheel_url,
        checked_at=(now or _utc_now()).isoformat(),
        source="network",
    )


def status_for_version(installed_version: str, target_version: str) -> UpdateStatus:
    metadata = load_distribution_metadata()
    repository = metadata.resolved_repository()
    normalized = normalize_release_tag(target_version)
    return UpdateStatus(
        installed_version=installed_version,
        latest_version=normalized,
        update_available=is_newer_version(normalized, installed_version),
        repository=repository,
        release_url=_release_page_url(repository, normalized),
        wheel_url=metadata.release_artifact_url(normalized, repository=repository),
        checked_at=_utc_now().isoformat(),
        source="requested",
    )


def apply_cli_update(
    status: UpdateStatus,
    *,
    capture_output: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> CommandResult:
    if not status.update_available:
        return already_current_result(status)
    if not status.latest_version or not status.wheel_url:
        raise AppError(
            code="cli_update_target_missing",
            message="No installable Backet CLI update target was resolved.",
            hint="Run `backet update check --fresh` and retry the update.",
            details=status.to_dict(),
            exit_code=1,
        )

    pipx_command = resolve_pipx_command()
    command = [*pipx_command, "install", "--force", status.wheel_url]
    run = runner or subprocess.run
    try:
        completed = run(command, text=True, capture_output=capture_output)
    except OSError as exc:
        raise AppError(
            code="cli_update_failed",
            message="Could not run the Backet CLI updater.",
            hint="Ensure `pipx` is installed or set BACKET_PIPX to the updater command.",
            details={"command": command, "error": str(exc)},
            exit_code=1,
        ) from exc

    if completed.returncode != 0:
        details: dict[str, Any] = {"command": command, "returncode": completed.returncode}
        if capture_output:
            details["stdout"] = completed.stdout
            details["stderr"] = completed.stderr
        raise AppError(
            code="cli_update_failed",
            message=f"Could not update Backet to {status.latest_version}.",
            hint="Check the updater output and retry `backet update apply`.",
            details=details,
            exit_code=1,
        )

    return CommandResult(
        message=f"Updated Backet to {status.latest_version}.",
        data={
            **status.to_dict(),
            "updated": True,
            "pipx_command": " ".join(command),
        },
    )


def resolve_pipx_command() -> list[str]:
    override = os.environ.get(PIPX_ENV)
    if override:
        command = shlex.split(override)
        if command:
            return command

    pipx_path = shutil.which("pipx")
    if pipx_path:
        return [pipx_path]

    raise AppError(
        code="cli_update_unsupported",
        message="This Backet installation cannot update itself because `pipx` is not available.",
        hint="Install pipx or set BACKET_PIPX to the command Backet should use for `pipx`.",
        details={"env_override": PIPX_ENV},
        exit_code=1,
    )


def update_check_result(status: UpdateStatus) -> CommandResult:
    if status.update_available:
        message = f"A Backet update is available: {status.installed_version} -> {status.latest_version}."
    elif status.latest_version is None:
        message = "Could not determine the latest Backet release."
    else:
        message = "Backet is already current."
    return CommandResult(message=message, data=status.to_dict())


def already_current_result(status: UpdateStatus) -> CommandResult:
    return CommandResult(
        message="Backet is already current.",
        data={
            **status.to_dict(),
            "updated": False,
        },
    )


def update_skipped_result(status: UpdateStatus) -> CommandResult:
    return CommandResult(
        message="Backet update skipped.",
        data={
            **status.to_dict(),
            "updated": False,
            "skipped": True,
        },
    )


def update_required_error(status: UpdateStatus) -> AppError:
    return AppError(
        code="update_required",
        message=f"A newer Backet CLI is available: {status.installed_version} -> {status.latest_version}.",
        hint="Run `backet update apply --yes`, then retry the original command.",
        details=status.to_dict(),
        exit_code=UPDATE_REQUIRED_EXIT_CODE,
    )


def read_update_cache(cache_path: Path | None = None) -> dict[str, Any] | None:
    path = cache_path or resolve_machine_paths().update_cache_path
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("schema_version") != UPDATE_CACHE_SCHEMA_VERSION:
        return None
    return payload


def write_update_cache(
    status: UpdateStatus,
    *,
    cache_path: Path | None = None,
    existing_cache: dict[str, Any] | None = None,
) -> None:
    if status.latest_version is None:
        return
    path = cache_path or resolve_machine_paths().update_cache_path
    payload = {
        "schema_version": UPDATE_CACHE_SCHEMA_VERSION,
        "checked_at": status.checked_at or _utc_now().isoformat(),
        "latest_version": status.latest_version,
        "update_available": status.update_available,
        "repository": status.repository,
        "release_url": status.release_url,
        "wheel_url": status.wheel_url,
    }
    existing = existing_cache or read_update_cache(path) or {}
    if existing.get("snoozed_version"):
        payload["snoozed_version"] = existing["snoozed_version"]
    if existing.get("snoozed_at"):
        payload["snoozed_at"] = existing["snoozed_at"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def snooze_update(status: UpdateStatus, *, cache_path: Path | None = None, now: datetime | None = None) -> None:
    if not status.latest_version:
        return
    path = cache_path or resolve_machine_paths().update_cache_path
    existing = read_update_cache(path) or {}
    if existing.get("latest_version") != status.latest_version:
        write_update_cache(status, cache_path=path, existing_cache=existing)
        existing = read_update_cache(path) or {}
    existing["schema_version"] = UPDATE_CACHE_SCHEMA_VERSION
    existing["snoozed_version"] = status.latest_version
    existing["snoozed_at"] = (now or _utc_now()).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")


def is_update_snoozed(status: UpdateStatus, *, cache_path: Path | None = None, now: datetime | None = None) -> bool:
    if not status.latest_version:
        return False
    cache = read_update_cache(cache_path)
    if not cache or cache.get("snoozed_version") != status.latest_version:
        return False
    snoozed_at = _parse_timestamp(cache.get("snoozed_at"))
    if snoozed_at is None:
        return False
    return (now or _utc_now()) - snoozed_at < UPDATE_SNOOZE_TTL


def is_interactive_caller(*, json_output: bool) -> bool:
    if json_output:
        return False
    if os.environ.get("CI") or os.environ.get("BACKET_AGENT") or os.environ.get("CODEX_AGENT"):
        return False
    return _stream_is_tty("stdin") and _stream_is_tty("stderr")


def reexec_backet(argv: Sequence[str]) -> None:
    executable = argv[0] if argv else shutil.which("backet") or "backet"
    args = list(argv) if argv else ["backet"]
    env = os.environ.copy()
    env[SKIP_UPDATE_CHECK_ENV] = "rerun"
    os.execvpe(executable, args, env)


def normalize_release_tag(tag: str) -> str:
    normalized = tag.strip()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    return normalized


def is_newer_version(candidate: str | None, installed: str) -> bool:
    if candidate is None:
        return False
    try:
        return Version(candidate) > Version(installed)
    except InvalidVersion:
        return False


def _status_from_cache(
    cache: dict[str, Any] | None,
    installed_version: str,
    metadata: DistributionMetadata,
    *,
    source: str,
) -> UpdateStatus:
    repository = str(cache.get("repository") or metadata.resolved_repository()) if cache else metadata.resolved_repository()
    latest_version = str(cache.get("latest_version")) if cache and cache.get("latest_version") else None
    wheel_url = str(cache.get("wheel_url")) if cache and cache.get("wheel_url") else None
    release_url = str(cache.get("release_url")) if cache and cache.get("release_url") else None
    if latest_version and wheel_url is None:
        wheel_url = metadata.release_artifact_url(latest_version, repository=repository)
    if latest_version and release_url is None:
        release_url = _release_page_url(repository, latest_version)
    version_is_newer = is_newer_version(latest_version, installed_version)
    cached_update_available = bool(cache.get("update_available", version_is_newer)) if cache else version_is_newer
    return UpdateStatus(
        installed_version=installed_version,
        latest_version=latest_version,
        update_available=cached_update_available and version_is_newer,
        repository=repository,
        release_url=release_url,
        wheel_url=wheel_url,
        checked_at=str(cache.get("checked_at")) if cache and cache.get("checked_at") else None,
        source=source,
    )


def _fallback_status_from_error(
    exc: Exception,
    *,
    cache: dict[str, Any] | None,
    installed_version: str,
    metadata: DistributionMetadata,
    repository: str,
) -> UpdateStatus:
    if cache:
        cached = _status_from_cache(cache, installed_version, metadata, source="cache-stale")
        if cached.update_available:
            cached.error = _error_text(exc)
            return cached
    return UpdateStatus(
        installed_version=installed_version,
        latest_version=None,
        update_available=False,
        repository=repository,
        source="unknown",
        error=_error_text(exc),
    )


def _error_text(exc: Exception) -> str:
    if isinstance(exc, AppError):
        detail_error = exc.details.get("error")
        if detail_error:
            return f"{exc.message}: {detail_error}"
        return exc.message
    return str(exc)


def _cache_is_fresh(cache: dict[str, Any] | None, now: datetime) -> bool:
    if not cache:
        return False
    checked_at = _parse_timestamp(cache.get("checked_at"))
    if checked_at is None:
        return False
    return now - checked_at < UPDATE_CACHE_TTL


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _release_page_url(repository: str, version: str) -> str:
    return f"https://github.com/{repository}/releases/tag/v{version}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stream_is_tty(name: str) -> bool:
    stream = getattr(sys, name)
    return bool(getattr(stream, "isatty", lambda: False)())
