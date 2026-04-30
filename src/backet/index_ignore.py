from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from backet.paths import index_ignore_path

DEFAULT_INDEX_IGNORE_CONTENT = """# Backet index ignore
# Patterns are relative to the vault root and use gitignore-style syntax.

.backet/
.obsidian/
.git/
.trash/
Templates/
Archive/
Daily Notes/
"""

BUILT_IN_IGNORED_DIRS = {".backet", ".git"}


@dataclass(frozen=True, slots=True)
class IndexIgnorePattern:
    pattern: str
    negated: bool = False
    directory_only: bool = False
    anchored: bool = False

    def matches(self, relative_path: str) -> bool:
        path = normalize_relative_path(relative_path)
        if not path:
            return False

        pattern = self.pattern
        if self.directory_only:
            return self._matches_directory(path, pattern)
        return self._matches_path(path, pattern)

    def _matches_path(self, path: str, pattern: str) -> bool:
        if self.anchored or "/" in pattern:
            return fnmatchcase(path, pattern)
        return any(fnmatchcase(part, pattern) for part in path.split("/"))

    def _matches_directory(self, path: str, pattern: str) -> bool:
        directories = path.split("/")[:-1]
        if not directories:
            return False
        if self.anchored or "/" in pattern:
            prefixes = ["/".join(directories[: index + 1]) for index in range(len(directories))]
            return any(fnmatchcase(prefix, pattern) for prefix in prefixes)
        return any(fnmatchcase(directory, pattern) for directory in directories)


@dataclass(frozen=True, slots=True)
class IndexIgnoreMatcher:
    patterns: tuple[IndexIgnorePattern, ...]

    @classmethod
    def from_lines(cls, lines: list[str] | tuple[str, ...]) -> IndexIgnoreMatcher:
        patterns = []
        for line in lines:
            parsed = parse_ignore_pattern(line)
            if parsed is not None:
                patterns.append(parsed)
        return cls(patterns=tuple(patterns))

    def matches(self, relative_path: str) -> bool:
        ignored = False
        for pattern in self.patterns:
            if pattern.matches(relative_path):
                ignored = not pattern.negated
        return ignored


@dataclass(frozen=True, slots=True)
class IndexIgnorePolicy:
    path: Path
    exists: bool
    matcher: IndexIgnoreMatcher

    def ignores(self, relative_path: str) -> bool:
        normalized = normalize_relative_path(relative_path)
        if not normalized:
            return False
        if has_builtin_ignored_dir(normalized):
            return True
        return self.matcher.matches(normalized)


def load_index_ignore_policy(vault_root: Path) -> IndexIgnorePolicy:
    path = index_ignore_path(vault_root)
    if not path.exists():
        return IndexIgnorePolicy(path=path, exists=False, matcher=IndexIgnoreMatcher(patterns=()))
    return IndexIgnorePolicy(
        path=path,
        exists=True,
        matcher=IndexIgnoreMatcher.from_lines(path.read_text(encoding="utf-8").splitlines()),
    )


def parse_ignore_pattern(line: str) -> IndexIgnorePattern | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    negated = stripped.startswith("!")
    if negated:
        stripped = stripped[1:].strip()
    if not stripped:
        return None

    anchored = stripped.startswith("/")
    if anchored:
        stripped = stripped[1:]

    directory_only = stripped.endswith("/")
    if directory_only:
        stripped = stripped.rstrip("/")

    if not stripped:
        return None

    return IndexIgnorePattern(
        pattern=normalize_relative_path(stripped),
        negated=negated,
        directory_only=directory_only,
        anchored=anchored,
    )


def has_builtin_ignored_dir(relative_path: str) -> bool:
    parts = normalize_relative_path(relative_path).split("/")
    return any(part in BUILT_IN_IGNORED_DIRS for part in parts)


def normalize_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")
