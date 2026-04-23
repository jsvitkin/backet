from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from urllib.request import urlopen
from zipfile import ZipFile

from backet.errors import AppError
from backet.repository import find_repo_root


@dataclass(slots=True)
class DistributionMetadata:
    schema_version: int
    cli_version: str
    repository: str
    default_ref: str
    release_artifact_pattern: str
    skills_manifest_path: str
    skills_archive_url_template: str

    @classmethod
    def from_path(cls, path: Path) -> "DistributionMetadata":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=payload["schema_version"],
            cli_version=payload["cli_version"],
            repository=payload["repository"],
            default_ref=payload["default_ref"],
            release_artifact_pattern=payload["release_artifact_pattern"],
            skills_manifest_path=payload["skills_manifest_path"],
            skills_archive_url_template=payload["skills_archive_url_template"],
        )

    def resolved_repository(self, override: str | None = None) -> str:
        return override or os.environ.get("BACKET_REPOSITORY") or self.repository

    def resolved_ref(self, override: str | None = None) -> str:
        return override or os.environ.get("BACKET_SKILLS_REF") or self.default_ref

    def release_artifact_name(self, version: str) -> str:
        return self.release_artifact_pattern.format(version=version)

    def release_artifact_url(self, version: str, repository: str | None = None) -> str:
        repo = self.resolved_repository(repository)
        tag = f"v{version}"
        return f"https://github.com/{repo}/releases/download/{tag}/{self.release_artifact_name(version)}"

    def skills_archive_url(self, repository: str | None = None, ref: str | None = None) -> str:
        override = os.environ.get("BACKET_SKILLS_ARCHIVE_URL")
        if override:
            return override
        repo = self.resolved_repository(repository)
        resolved_ref = self.resolved_ref(ref)
        return self.skills_archive_url_template.format(repository=repo, ref=resolved_ref)


@dataclass(slots=True)
class PreparedSkillSource:
    source_dir: Path
    source_label: str
    source_kind: str
    repository: str | None = None
    ref: str | None = None


def load_distribution_metadata() -> DistributionMetadata:
    repo_root = find_repo_root()
    if repo_root is not None:
        candidate = repo_root / "metadata" / "compatibility.json"
        if candidate.exists():
            return DistributionMetadata.from_path(candidate)

    resource = files("backet.resources").joinpath("compatibility.json")
    with as_file(resource) as resource_path:
        return DistributionMetadata.from_path(resource_path)


@contextmanager
def prepare_remote_skill_source(repository: str | None = None, ref: str | None = None) -> Iterator[PreparedSkillSource]:
    metadata = load_distribution_metadata()
    resolved_repository = metadata.resolved_repository(repository)
    resolved_ref = metadata.resolved_ref(ref)

    if resolved_repository == "OWNER/REPO":
        raise AppError(
            code="skills_repo_unknown",
            message="No GitHub repository is configured for downloading the backet skill pack.",
            hint="Set BACKET_REPOSITORY or rerun with `backet skills install --repo OWNER/REPO`.",
            exit_code=2,
        )

    archive_url = metadata.skills_archive_url(repository=resolved_repository, ref=resolved_ref)
    manifest_relative_path = Path(metadata.skills_manifest_path)

    try:
        with urlopen(archive_url) as response:
            archive_bytes = response.read()
    except Exception as exc:  # pragma: no cover - exercised via tests with monkeypatching
        raise AppError(
            code="skills_download_failed",
            message="Could not download the backet skill pack archive.",
            hint="Check your network connection or provide `--source /path/to/skills`.",
            details={"url": archive_url, "repository": resolved_repository, "ref": resolved_ref},
            exit_code=2,
        ) from exc

    with TemporaryDirectory(prefix="backet-skills-") as temp_dir:
        temp_path = Path(temp_dir)
        archive_path = temp_path / "skills.zip"
        archive_path.write_bytes(archive_bytes)
        try:
            with ZipFile(archive_path) as zip_file:
                zip_file.extractall(temp_path)
                top_level = _archive_root(zip_file.namelist())
        except Exception as exc:
            raise AppError(
                code="skills_archive_invalid",
                message="Downloaded skill archive is not a valid ZIP payload.",
                hint="Retry the command or provide a local `--source` directory.",
                details={"url": archive_url},
                exit_code=2,
            ) from exc

        source_dir = temp_path / top_level / manifest_relative_path.parent
        manifest_path = source_dir / manifest_relative_path.name
        if not manifest_path.exists():
            raise AppError(
                code="skills_manifest_missing",
                message="The downloaded skill archive does not contain the expected manifest.",
                hint="Check the repository layout or provide `--source /path/to/skills`.",
                details={"url": archive_url, "manifest_path": str(manifest_relative_path)},
                exit_code=2,
            )

        yield PreparedSkillSource(
            source_dir=source_dir,
            source_label=archive_url,
            source_kind="repository_archive",
            repository=resolved_repository,
            ref=resolved_ref,
        )


def _archive_root(names: list[str]) -> str:
    roots = {name.split("/", 1)[0] for name in names if name}
    if len(roots) != 1:
        raise ValueError("Archive must contain exactly one top-level directory.")
    return next(iter(roots))
