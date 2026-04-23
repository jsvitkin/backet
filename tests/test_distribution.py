from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from backet.distribution import DistributionMetadata, load_distribution_metadata, prepare_remote_skill_source
from backet.errors import AppError


def test_distribution_metadata_loads_from_repo() -> None:
    metadata = load_distribution_metadata()

    assert metadata.repository == "jsvitkin/backet"
    assert metadata.default_ref == "main"
    assert metadata.release_artifact_name("0.1.0") == "backet-0.1.0-py3-none-any.whl"


def test_distribution_metadata_builds_release_url() -> None:
    metadata = load_distribution_metadata()

    url = metadata.release_artifact_url("0.1.0", repository="example/backet")

    assert url == "https://github.com/example/backet/releases/download/v0.1.0/backet-0.1.0-py3-none-any.whl"


def test_skills_archive_url_honors_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = load_distribution_metadata()
    monkeypatch.setenv("BACKET_SKILLS_ARCHIVE_URL", "file:///tmp/custom.zip")

    assert metadata.skills_archive_url(repository="example/backet", ref="main") == "file:///tmp/custom.zip"


def test_prepare_remote_skill_source_errors_when_repository_metadata_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BACKET_REPOSITORY", raising=False)
    monkeypatch.delenv("BACKET_SKILLS_ARCHIVE_URL", raising=False)
    monkeypatch.setattr(
        "backet.distribution.load_distribution_metadata",
        lambda: DistributionMetadata(
            schema_version=1,
            cli_version="0.1.0",
            repository="OWNER/REPO",
            default_ref="main",
            release_artifact_pattern="backet-{version}-py3-none-any.whl",
            skills_manifest_path="skills/manifest.json",
            skills_archive_url_template="https://codeload.github.com/{repository}/zip/refs/heads/{ref}",
        ),
    )

    with pytest.raises(AppError, match="No GitHub repository is configured"):
        with prepare_remote_skill_source():
            pass


def test_prepare_remote_skill_source_rejects_invalid_zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = tmp_path / "invalid.zip"
    archive_path.write_text("not a zip archive", encoding="utf-8")
    monkeypatch.setenv("BACKET_SKILLS_ARCHIVE_URL", archive_path.as_uri())

    with pytest.raises(AppError, match="not a valid ZIP payload"):
        with prepare_remote_skill_source(repository="example/backet", ref="main"):
            pass


def test_prepare_remote_skill_source_requires_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = tmp_path / "missing-manifest.zip"
    with ZipFile(archive_path, "w") as zip_file:
        zip_file.writestr("backet-main/skills/example/SKILL.md", "# Example\n")
    monkeypatch.setenv("BACKET_SKILLS_ARCHIVE_URL", archive_path.as_uri())

    with pytest.raises(AppError, match="expected manifest"):
        with prepare_remote_skill_source(repository="example/backet", ref="main"):
            pass
