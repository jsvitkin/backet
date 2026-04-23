from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

import yaml

from backet.errors import AppError
from backet.models import CommandResult, Issue
from backet.paths import (
    DURABLE_DIRS,
    OPTIONAL_SAFE_DIRS,
    SAFE_REBUILD_DIRS,
    backet_root,
    config_path,
    gitignore_path,
)

GITIGNORE_CONTENT = """cache/
temp/
ocr-work/
"""


def ensure_vault_directory(vault_root: Path) -> None:
    if not vault_root.exists() or not vault_root.is_dir():
        raise AppError(
            code="vault_not_found",
            message=f"Vault path does not exist: {vault_root}",
            hint="Check the vault path and try again.",
            details={"vault": str(vault_root)},
            exit_code=2,
        )


def ensure_bootstrapped_vault(vault_root: Path) -> Path:
    ensure_vault_directory(vault_root)
    root = backet_root(vault_root)
    if not root.exists():
        raise AppError(
            code="not_bootstrapped",
            message="Vault is not bootstrapped for backet yet.",
            hint="Run `backet init <vault>` first.",
            details={"vault": str(vault_root)},
            exit_code=2,
        )
    return root


def initialize_vault(vault_root: Path, cli_version: str) -> CommandResult:
    if not vault_root.exists() or not vault_root.is_dir():
        raise AppError(
            code="vault_not_found",
            message=f"Vault path does not exist: {vault_root}",
            hint="Create the vault directory first, then rerun `backet init`.",
            details={"vault": str(vault_root)},
            exit_code=2,
        )

    root = backet_root(vault_root)
    if root.exists():
        raise AppError(
            code="already_bootstrapped",
            message=f"Vault already contains {root.name}.",
            hint="Run `backet doctor` to inspect the existing setup instead of overwriting it.",
            details={"vault": str(vault_root), "backet_root": str(root)},
            exit_code=2,
        )

    created: list[str] = []
    root.mkdir()
    created.append(str(root.relative_to(vault_root)))

    for directory in (*DURABLE_DIRS, *SAFE_REBUILD_DIRS):
        path = root / directory
        path.mkdir(parents=True, exist_ok=True)
        created.append(str(path.relative_to(vault_root)))

    for directory in OPTIONAL_SAFE_DIRS:
        path = root / directory
        path.mkdir(parents=True, exist_ok=True)
        created.append(str(path.relative_to(vault_root)))

    config = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": {"cli_version": cli_version},
    }
    config_file = config_path(vault_root)
    config_file.write_text(yaml.safe_dump(config, sort_keys=True), encoding="utf-8")
    created.append(str(config_file.relative_to(vault_root)))

    ignore_file = gitignore_path(vault_root)
    ignore_file.write_text(GITIGNORE_CONTENT, encoding="utf-8")
    created.append(str(ignore_file.relative_to(vault_root)))

    return CommandResult(
        message=f"Initialized backet in {vault_root}",
        created=created,
        data={
            "vault": str(vault_root),
            "backet_root": str(root),
        },
    )


def diagnose_vault(vault_root: Path, fix: bool) -> CommandResult:
    root = ensure_bootstrapped_vault(vault_root)

    issues: list[Issue] = []
    fixed: list[str] = []

    for path in [config_path(vault_root), *(root / name for name in DURABLE_DIRS)]:
        if not path.exists():
            issues.append(
                Issue(
                    code="missing_durable_state",
                    severity="error",
                    message="Missing durable backet state",
                    path=str(path.relative_to(vault_root)),
                    hint="Restore the missing file from Git or rerun initialization manually if appropriate.",
                    safe_to_fix=False,
                )
            )

    ignore_file = gitignore_path(vault_root)
    if not ignore_file.exists():
        issues.append(
            Issue(
                code="missing_gitignore",
                severity="warning",
                message="Missing scoped .backet/.gitignore",
                path=str(ignore_file.relative_to(vault_root)),
                hint="Run `backet doctor --fix` to restore the default ignore rules.",
                safe_to_fix=True,
            )
        )
        if fix:
            ignore_file.write_text(GITIGNORE_CONTENT, encoding="utf-8")
            fixed.append(str(ignore_file.relative_to(vault_root)))

    safe_dirs = [*(root / name for name in SAFE_REBUILD_DIRS), *(root / name for name in OPTIONAL_SAFE_DIRS)]
    for path in safe_dirs:
        if not path.exists():
            issue = Issue(
                code="missing_rebuildable_dir",
                severity="warning",
                message="Missing rebuildable local directory",
                path=str(path.relative_to(vault_root)),
                hint="Run `backet doctor --fix` to recreate this directory.",
                safe_to_fix=True,
            )
            issues.append(issue)
            if fix:
                path.mkdir(parents=True, exist_ok=True)
                fixed.append(str(path.relative_to(vault_root)))

    message = "Vault health check complete"
    if fix and fixed:
        message = "Vault health check complete with safe repairs"

    return CommandResult(
        message=message,
        fixed=fixed,
        issues=issues,
        data={
            "vault": str(vault_root),
            "backet_root": str(root),
            "safe_fix_applied": bool(fixed),
        },
    )
