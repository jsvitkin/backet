from __future__ import annotations

import json
import shutil
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from backet.distribution import PreparedSkillSource, prepare_remote_skill_source
from backet.errors import AppError
from backet.models import CommandResult
from backet.paths import resolve_machine_paths
from backet.repository import default_skills_source


@dataclass(slots=True)
class SkillPackManifest:
    schema_version: int
    pack_version: str
    cli_requirement: str
    skills: list[dict[str, str]]

    @classmethod
    def from_path(cls, path: Path) -> "SkillPackManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=payload["schema_version"],
            pack_version=payload["pack_version"],
            cli_requirement=payload["cli_requirement"],
            skills=payload.get("skills", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pack_version": self.pack_version,
            "cli_requirement": self.cli_requirement,
            "skills": self.skills,
        }


def _compatible(cli_version: str, requirement: str) -> bool:
    return Version(cli_version) in SpecifierSet(requirement)


def _manifest_path_from_source(source_dir: Path) -> Path:
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.exists():
        raise AppError(
            code="skill_manifest_missing",
            message=f"Skill manifest not found in {source_dir}.",
            hint="Provide a skill pack directory containing `manifest.json`.",
            details={"source": str(source_dir)},
            exit_code=2,
        )
    return manifest_path


def skills_status(cli_version: str) -> CommandResult:
    machine = resolve_machine_paths()
    installed = machine.skill_manifest_path.exists()
    data: dict[str, Any] = {
        "config_dir": str(machine.config_dir),
        "codex_skills_dir": str(machine.codex_skills_dir),
        "installed": installed,
        "cli_version": cli_version,
    }

    if installed:
        payload = json.loads(machine.skill_manifest_path.read_text(encoding="utf-8"))
        data["installed_manifest"] = payload
        data["compatible"] = _compatible(cli_version, payload["cli_requirement"])

    return CommandResult(message="Skill pack status", data=data)


def install_skills(
    cli_version: str,
    source_dir: Path | None = None,
    repository: str | None = None,
    ref: str | None = None,
) -> CommandResult:
    source_context = _resolve_skill_source(source_dir=source_dir, repository=repository, ref=ref)
    with source_context as prepared_source:
        manifest_path = _manifest_path_from_source(prepared_source.source_dir)
        manifest = SkillPackManifest.from_path(manifest_path)

        if not _compatible(cli_version, manifest.cli_requirement):
            raise AppError(
                code="skill_pack_incompatible",
                message="Skill pack is not compatible with the installed backet CLI.",
                hint="Install a compatible skill pack or upgrade the CLI first.",
                details={"cli_version": cli_version, "cli_requirement": manifest.cli_requirement},
                exit_code=2,
            )

        machine = resolve_machine_paths()
        machine.config_dir.mkdir(parents=True, exist_ok=True)
        machine.codex_skills_dir.mkdir(parents=True, exist_ok=True)

        previous_manifest = _read_installed_manifest()
        copied: list[str] = []
        removed: list[str] = []
        desired_paths = {skill["path"] for skill in manifest.skills}

        for stale_path in _stale_skill_paths(previous_manifest, desired_paths):
            target_dir = machine.codex_skills_dir / stale_path
            if target_dir.exists():
                shutil.rmtree(target_dir)
                removed.append(str(target_dir))

        for skill in manifest.skills:
            source_skill_dir = prepared_source.source_dir / skill["path"]
            if not source_skill_dir.exists():
                raise AppError(
                    code="skill_directory_missing",
                    message=f"Skill directory listed in manifest is missing: {skill['path']}",
                    hint="Fix the skill pack manifest or restore the missing directory.",
                    details={"source": str(prepared_source.source_dir), "skill_path": skill["path"]},
                    exit_code=2,
                )
            target_skill_dir = machine.codex_skills_dir / skill["path"]
            if target_skill_dir.exists():
                shutil.rmtree(target_skill_dir)
            shutil.copytree(source_skill_dir, target_skill_dir)
            copied.append(str(target_skill_dir))

        installed_manifest = {
            **manifest.to_dict(),
            "installed_from": prepared_source.source_label,
            "source_kind": prepared_source.source_kind,
            "installed_cli_version": cli_version,
            "codex_skills_dir": str(machine.codex_skills_dir),
        }
        if prepared_source.repository:
            installed_manifest["repository"] = prepared_source.repository
        if prepared_source.ref:
            installed_manifest["ref"] = prepared_source.ref
        machine.skill_manifest_path.write_text(json.dumps(installed_manifest, indent=2, sort_keys=True), encoding="utf-8")

        return CommandResult(
            message="Installed backet skill pack",
            created=copied,
            fixed=removed,
            data={
                "manifest_path": str(machine.skill_manifest_path),
                "skills_installed": len(copied),
                "source": prepared_source.source_label,
                "source_kind": prepared_source.source_kind,
            },
        )


def update_skills(cli_version: str, repository: str | None = None, ref: str | None = None) -> CommandResult:
    machine = resolve_machine_paths()
    if not machine.skill_manifest_path.exists():
        raise AppError(
            code="skills_not_installed",
            message="No installed skill pack metadata was found.",
            hint="Run `backet skills install` first.",
            details={"manifest_path": str(machine.skill_manifest_path)},
            exit_code=2,
        )

    payload = json.loads(machine.skill_manifest_path.read_text(encoding="utf-8"))
    source_kind = payload.get("source_kind", "directory")

    if source_kind == "directory":
        source_dir = Path(payload["installed_from"])
        return install_skills(cli_version=cli_version, source_dir=source_dir)

    if source_kind == "repository_archive":
        return install_skills(
            cli_version=cli_version,
            repository=repository or payload.get("repository"),
            ref=ref or payload.get("ref"),
        )

    raise AppError(
        code="skills_update_unsupported",
        message="The installed skill source cannot be refreshed automatically.",
        hint="Re-run `backet skills install` with `--source` or `--repo`.",
        details={"source_kind": source_kind},
        exit_code=2,
    )


def _resolve_skill_source(source_dir: Path | None, repository: str | None, ref: str | None):
    if source_dir is not None:
        return nullcontext(
            PreparedSkillSource(
                source_dir=source_dir,
                source_label=str(source_dir),
                source_kind="directory",
            )
        )

    if repository is not None or ref is not None:
        return prepare_remote_skill_source(repository=repository, ref=ref)

    default_source = default_skills_source()
    if default_source is not None:
        return nullcontext(
            PreparedSkillSource(
                source_dir=default_source,
                source_label=str(default_source),
                source_kind="directory",
            )
        )

    return prepare_remote_skill_source(repository=repository, ref=ref)


def _read_installed_manifest() -> dict[str, Any] | None:
    machine = resolve_machine_paths()
    if not machine.skill_manifest_path.exists():
        return None
    return json.loads(machine.skill_manifest_path.read_text(encoding="utf-8"))


def _stale_skill_paths(installed_manifest: dict[str, Any] | None, desired_paths: set[str]) -> list[str]:
    if not installed_manifest:
        return []
    return [
        skill["path"]
        for skill in installed_manifest.get("skills", [])
        if skill["path"] not in desired_paths
    ]
