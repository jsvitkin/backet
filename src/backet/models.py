from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Issue:
    code: str
    severity: str
    message: str
    path: str | None = None
    hint: str | None = None
    safe_to_fix: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CommandResult:
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    created: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "data": self.data,
            "created": self.created,
            "fixed": self.fixed,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(slots=True)
class MachinePaths:
    config_dir: Path
    skill_manifest_path: Path
    update_state_path: Path
    codex_skills_dir: Path
