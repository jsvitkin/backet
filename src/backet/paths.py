from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_path

from backet.models import MachinePaths

BACKET_DIRNAME = ".backet"
BACKET_CONFIG_FILENAME = "config.yaml"
BACKET_GITIGNORE_FILENAME = ".gitignore"
INDEX_DB_FILENAME = "vault-index.sqlite3"
RULES_DB_FILENAME = "rules.sqlite3"
SAFE_REBUILD_DIRS = ("cache", "temp")
DURABLE_DIRS = ("state", "memory", "rules")
OPTIONAL_SAFE_DIRS = ("ocr-work",)


def resolve_machine_paths() -> MachinePaths:
    config_root_env = os.environ.get("BACKET_CONFIG_HOME")
    if config_root_env:
        config_dir = Path(config_root_env).expanduser().resolve()
    else:
        config_dir = user_config_path("backet", appauthor=False)

    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        codex_skills_dir = Path(codex_home).expanduser().resolve() / "skills"
    else:
        codex_skills_dir = Path.home() / ".codex" / "skills"

    return MachinePaths(
        config_dir=config_dir,
        skill_manifest_path=config_dir / "skills-installed.json",
        codex_skills_dir=codex_skills_dir,
    )


def resolve_vault_root(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def backet_root(vault_root: Path) -> Path:
    return vault_root / BACKET_DIRNAME


def config_path(vault_root: Path) -> Path:
    return backet_root(vault_root) / BACKET_CONFIG_FILENAME


def gitignore_path(vault_root: Path) -> Path:
    return backet_root(vault_root) / BACKET_GITIGNORE_FILENAME


def state_dir(vault_root: Path) -> Path:
    return backet_root(vault_root) / "state"


def memory_dir(vault_root: Path) -> Path:
    return backet_root(vault_root) / "memory"


def rules_dir(vault_root: Path) -> Path:
    return backet_root(vault_root) / "rules"


def index_db_path(vault_root: Path) -> Path:
    return state_dir(vault_root) / INDEX_DB_FILENAME


def rules_db_path(vault_root: Path) -> Path:
    return rules_dir(vault_root) / RULES_DB_FILENAME
