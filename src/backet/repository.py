from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "openspec").exists():
            return candidate
    return None


def default_skills_source() -> Path | None:
    repo_root = find_repo_root()
    if repo_root is None:
        return None
    manifest = repo_root / "skills" / "manifest.json"
    return manifest.parent if manifest.exists() else None

