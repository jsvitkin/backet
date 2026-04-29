from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from backet.errors import AppError
from backet.models import CommandResult
from backet.paths import blueprint_state_path
from backet.vault import ensure_bootstrapped_vault

BLUEPRINT_STATE_SCHEMA_VERSION = 1
BACKET_FRONTMATTER_DELIMITER = "---"
NEXT_MISSING_TARGET_LIMIT = 3


@dataclass(slots=True)
class BlueprintSlot:
    slot_id: str
    title: str
    default_path: str
    template: str
    priority: int


@dataclass(slots=True)
class BlueprintManifest:
    schema_version: int
    blueprint_id: str
    version: str
    title: str
    workflow: str
    slots: list[BlueprintSlot]

    @classmethod
    def from_path(cls, path: Path) -> "BlueprintManifest":
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.from_payload(payload, source=str(path))

    @classmethod
    def from_payload(cls, payload: dict[str, Any], source: str) -> "BlueprintManifest":
        slots = [
            BlueprintSlot(
                slot_id=item["slot_id"],
                title=item["title"],
                default_path=item["default_path"],
                template=item["template"],
                priority=int(item["priority"]),
            )
            for item in payload.get("slots", [])
        ]
        if not slots:
            raise AppError(
                code="blueprint_manifest_invalid",
                message=f"Blueprint manifest does not define any slots: {source}",
                hint="Add at least one slot definition to the blueprint manifest.",
                details={"manifest_path": source},
                exit_code=2,
            )
        return cls(
            schema_version=int(payload["schema_version"]),
            blueprint_id=payload["blueprint_id"],
            version=str(payload["version"]),
            title=payload["title"],
            workflow=payload["workflow"],
            slots=slots,
        )

    def slot_map(self) -> dict[str, BlueprintSlot]:
        return {slot.slot_id: slot for slot in self.slots}


@dataclass(slots=True)
class BlueprintSlotMapping:
    slot_id: str
    title: str
    default_path: str
    resolved_path: str
    mapping_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "title": self.title,
            "default_path": self.default_path,
            "resolved_path": self.resolved_path,
            "mapping_source": self.mapping_source,
        }


@dataclass(slots=True)
class BlueprintState:
    schema_version: int
    blueprint_id: str
    blueprint_version: str
    workflow: str
    applied_at: str
    updated_at: str
    slots: list[BlueprintSlotMapping]

    @classmethod
    def from_path(cls, path: Path) -> "BlueprintState":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=int(payload["schema_version"]),
            blueprint_id=payload["blueprint_id"],
            blueprint_version=str(payload["blueprint_version"]),
            workflow=payload["workflow"],
            applied_at=payload["applied_at"],
            updated_at=payload["updated_at"],
            slots=[
                BlueprintSlotMapping(
                    slot_id=item["slot_id"],
                    title=item["title"],
                    default_path=item["default_path"],
                    resolved_path=item["resolved_path"],
                    mapping_source=item["mapping_source"],
                )
                for item in payload.get("slots", [])
            ],
        )

    def slot_map(self) -> dict[str, BlueprintSlotMapping]:
        return {slot.slot_id: slot for slot in self.slots}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "blueprint_id": self.blueprint_id,
            "blueprint_version": self.blueprint_version,
            "workflow": self.workflow,
            "applied_at": self.applied_at,
            "updated_at": self.updated_at,
            "slots": [slot.to_dict() for slot in self.slots],
        }


def apply_blueprint(vault_root: Path, blueprint_id: str, slot_paths: list[str] | None = None) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    manifest = load_blueprint_manifest(blueprint_id)
    overrides = parse_slot_path_overrides(manifest, slot_paths or [])
    state_path = blueprint_state_path(vault_root, blueprint_id)
    previous_state = _load_blueprint_state(state_path)
    previous_slot_map = previous_state.slot_map() if previous_state is not None else {}

    slot_mappings: list[BlueprintSlotMapping] = []
    created: list[str] = []

    for slot in manifest.slots:
        previous_mapping = previous_slot_map.get(slot.slot_id)
        if slot.slot_id in overrides:
            resolved_path = overrides[slot.slot_id]
            mapping_source = "custom"
        elif previous_mapping is not None:
            resolved_path = previous_mapping.resolved_path
            mapping_source = previous_mapping.mapping_source
        else:
            resolved_path = normalize_note_path(slot.default_path)
            mapping_source = "default"

        slot_mapping = BlueprintSlotMapping(
            slot_id=slot.slot_id,
            title=slot.title,
            default_path=normalize_note_path(slot.default_path),
            resolved_path=resolved_path,
            mapping_source=mapping_source,
        )
        slot_mappings.append(slot_mapping)

        target_path = vault_root / PurePosixPath(resolved_path)
        if target_path.exists():
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(render_workflow_note(manifest, slot, load_slot_template(manifest, slot)), encoding="utf-8")
        created.append(str(PurePosixPath(resolved_path)))

    new_state = build_blueprint_state(manifest, slot_mappings, previous_state=previous_state)
    state_changed = write_blueprint_state(state_path, new_state)
    if previous_state is None or state_changed:
        created.append(str(state_path.relative_to(vault_root)))

    slot_data = []
    for mapping in slot_mappings:
        slot_data.append(
            {
                "slot_id": mapping.slot_id,
                "title": mapping.title,
                "resolved_path": mapping.resolved_path,
                "default_path": mapping.default_path,
                "mapping_source": mapping.mapping_source,
                "exists": (vault_root / PurePosixPath(mapping.resolved_path)).exists(),
            }
        )

    return CommandResult(
        message="Applied workflow blueprint",
        created=created,
        data={
            "vault": str(vault_root),
            "blueprint_id": manifest.blueprint_id,
            "blueprint_version": manifest.version,
            "workflow": manifest.workflow,
            "state_path": str(state_path),
            "slots": slot_data,
            "custom_slot_ids": sorted(slot_id for slot_id, path in overrides.items() if path),
        },
    )


def blueprint_status(vault_root: Path, blueprint_id: str) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    manifest = load_blueprint_manifest(blueprint_id)
    state_path = blueprint_state_path(vault_root, blueprint_id)
    state = _load_blueprint_state(state_path)
    slot_state_map = state.slot_map() if state is not None else {}

    slot_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []

    for slot in sorted(manifest.slots, key=lambda item: (item.priority, item.slot_id)):
        mapping = slot_state_map.get(slot.slot_id)
        if mapping is None:
            resolved_path = normalize_note_path(slot.default_path)
            mapping_source = "default"
        else:
            resolved_path = mapping.resolved_path
            mapping_source = mapping.mapping_source

        note_path = vault_root / PurePosixPath(resolved_path)
        exists = note_path.exists()
        frontmatter = read_note_frontmatter(note_path) if exists else None
        workflow_owned = bool(
            isinstance(frontmatter, dict)
            and isinstance(frontmatter.get("backet"), dict)
            and frontmatter["backet"].get("blueprint") == manifest.blueprint_id
            and frontmatter["backet"].get("slot") == slot.slot_id
        )
        row = {
            "slot_id": slot.slot_id,
            "title": slot.title,
            "default_path": normalize_note_path(slot.default_path),
            "resolved_path": resolved_path,
            "mapping_source": mapping_source,
            "priority": slot.priority,
            "status": "present" if exists else "missing",
            "exists": exists,
            "workflow_owned": workflow_owned,
        }
        slot_rows.append(row)
        if not exists:
            missing_rows.append(row)

    next_missing = missing_rows[:NEXT_MISSING_TARGET_LIMIT]
    return CommandResult(
        message="Workflow blueprint status",
        data={
            "vault": str(vault_root),
            "blueprint_id": manifest.blueprint_id,
            "blueprint_version": manifest.version,
            "workflow": manifest.workflow,
            "title": manifest.title,
            "applied": state is not None,
            "state_path": str(state_path),
            "slots": slot_rows,
            "missing_slots": missing_rows,
            "next_priority_missing": next_missing,
        },
    )


def load_blueprint_manifest(blueprint_id: str) -> BlueprintManifest:
    manifest_resource = files("backet.resources").joinpath("blueprints").joinpath(blueprint_id).joinpath("manifest.yaml")
    if not manifest_resource.is_file():
        raise AppError(
            code="blueprint_unknown",
            message=f"Unknown workflow blueprint: {blueprint_id}",
            hint="Use a supported blueprint identifier such as `city-by-night-v1`.",
            details={"blueprint_id": blueprint_id},
            exit_code=2,
        )
    payload = yaml.safe_load(manifest_resource.read_text(encoding="utf-8"))
    return BlueprintManifest.from_payload(payload, source=f"resource:{blueprint_id}/manifest.yaml")


def load_slot_template(manifest: BlueprintManifest, slot: BlueprintSlot) -> str:
    template_resource = (
        files("backet.resources")
        .joinpath("blueprints")
        .joinpath(manifest.blueprint_id)
        .joinpath("templates")
        .joinpath(slot.template)
    )
    if not template_resource.is_file():
        raise AppError(
            code="blueprint_template_missing",
            message=f"Blueprint template is missing for slot `{slot.slot_id}`.",
            hint="Restore the packaged template or fix the blueprint manifest.",
            details={"blueprint_id": manifest.blueprint_id, "slot_id": slot.slot_id, "template": slot.template},
            exit_code=2,
        )
    return template_resource.read_text(encoding="utf-8")


def parse_slot_path_overrides(manifest: BlueprintManifest, slot_paths: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    known_slots = manifest.slot_map()
    for raw_item in slot_paths:
        if "=" not in raw_item:
            raise AppError(
                code="blueprint_slot_path_invalid",
                message=f"Invalid slot override: {raw_item}",
                hint="Use `--slot-path slot-id=relative/path.md`.",
                details={"value": raw_item},
                exit_code=2,
            )
        slot_id, raw_path = raw_item.split("=", 1)
        slot_key = slot_id.strip()
        if slot_key not in known_slots:
            raise AppError(
                code="blueprint_slot_unknown",
                message=f"Unknown blueprint slot: {slot_key}",
                hint="Use one of the slot identifiers defined by the chosen blueprint.",
                details={"slot_id": slot_key, "blueprint_id": manifest.blueprint_id},
                exit_code=2,
            )
        overrides[slot_key] = normalize_note_path(raw_path)
    return overrides


def normalize_note_path(raw_path: str) -> str:
    candidate = raw_path.strip().replace("\\", "/")
    if not candidate:
        raise AppError(
            code="blueprint_note_path_invalid",
            message="Blueprint note paths cannot be empty.",
            hint="Provide a vault-relative Markdown path.",
            exit_code=2,
        )
    if candidate.startswith("/"):
        raise AppError(
            code="blueprint_note_path_absolute",
            message="Blueprint note paths must stay inside the vault.",
            hint="Use a vault-relative path such as `Setting/City Tone.md`.",
            details={"path": candidate},
            exit_code=2,
        )
    path = PurePosixPath(candidate)
    if path.parts and path.parts[0] == ".backet":
        raise AppError(
            code="blueprint_note_path_reserved",
            message="Blueprint note paths cannot point inside `.backet/`.",
            hint="Choose a canonical note path outside `.backet/`.",
            details={"path": candidate},
            exit_code=2,
        )
    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")
    return path.as_posix()


def read_note_frontmatter(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != BACKET_FRONTMATTER_DELIMITER:
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == BACKET_FRONTMATTER_DELIMITER:
            frontmatter_text = "\n".join(lines[1:index])
            payload = yaml.safe_load(frontmatter_text)
            return payload if isinstance(payload, dict) else None
    return None


def render_workflow_note(manifest: BlueprintManifest, slot: BlueprintSlot, template_text: str) -> str:
    frontmatter = {
        "backet": {
            "blueprint": manifest.blueprint_id,
            "workflow": manifest.workflow,
            "slot": slot.slot_id,
        }
    }
    frontmatter_text = yaml.safe_dump(frontmatter, sort_keys=False).strip()
    body = template_text.format(
        blueprint_id=manifest.blueprint_id,
        workflow=manifest.workflow,
        slot_id=slot.slot_id,
        title=slot.title,
    ).strip()
    return f"{BACKET_FRONTMATTER_DELIMITER}\n{frontmatter_text}\n{BACKET_FRONTMATTER_DELIMITER}\n\n{body}\n"


def build_blueprint_state(
    manifest: BlueprintManifest,
    slot_mappings: list[BlueprintSlotMapping],
    previous_state: BlueprintState | None = None,
) -> BlueprintState:
    timestamp = timestamp_now()
    applied_at = previous_state.applied_at if previous_state is not None else timestamp
    updated_at = timestamp if previous_state is None else previous_state.updated_at
    return BlueprintState(
        schema_version=BLUEPRINT_STATE_SCHEMA_VERSION,
        blueprint_id=manifest.blueprint_id,
        blueprint_version=manifest.version,
        workflow=manifest.workflow,
        applied_at=applied_at,
        updated_at=updated_at,
        slots=slot_mappings,
    )


def write_blueprint_state(path: Path, state: BlueprintState) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = state.to_dict()
    existing_payload: dict[str, Any] | None = None
    if path.exists():
        existing_payload = json.loads(path.read_text(encoding="utf-8"))
        existing_without_updated = dict(existing_payload)
        existing_without_updated.pop("updated_at", None)
        payload_without_updated = dict(payload)
        payload_without_updated.pop("updated_at", None)
        if existing_without_updated == payload_without_updated:
            return False
    payload["updated_at"] = timestamp_now()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return existing_payload != payload


def timestamp_now() -> str:
    return datetime.now(UTC).isoformat()


def _load_blueprint_state(path: Path) -> BlueprintState | None:
    if not path.exists():
        return None
    state = BlueprintState.from_path(path)
    if state.schema_version != BLUEPRINT_STATE_SCHEMA_VERSION:
        raise AppError(
            code="blueprint_state_schema_unknown",
            message="Stored workflow blueprint state uses an unsupported schema version.",
            hint="Re-apply the blueprint after upgrading `backet`, or migrate the stored state.",
            details={"state_path": str(path), "schema_version": state.schema_version},
            exit_code=2,
        )
    return state
