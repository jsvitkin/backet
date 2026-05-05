from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from backet import __version__
from backet.bot_access import load_bot_config, scan_bot_visibility, summarize_visibility
from backet.errors import AppError
from backet.indexing import build_scoped_index, timestamp_now
from backet.models import CommandResult, Issue
from backet.paths import rules_db_path
from backet.vault import ensure_bootstrapped_vault

BOT_BUNDLE_SCHEMA_VERSION = 1


def export_bot_bundle(vault_root: Path, output_path: Path, force: bool = False) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    output_root = output_path.expanduser().resolve()
    if output_root.exists():
        if not force:
            raise AppError(
                code="bot_export_output_exists",
                message="Bot export output path already exists.",
                hint="Choose another --output path or re-run with --force.",
                details={"output_path": str(output_root)},
                exit_code=2,
            )
        if output_root.is_dir():
            shutil.rmtree(output_root)
        else:
            output_root.unlink()

    decisions = scan_bot_visibility(vault_root)
    summary = summarize_visibility(decisions)
    config = load_bot_config(vault_root)
    output_root.mkdir(parents=True, exist_ok=True)
    indexes_dir = output_root / "indexes"
    rules_dir = output_root / "rules"
    indexes_dir.mkdir()
    rules_dir.mkdir()

    player_paths = [decision.relative_path for decision in decisions if decision.included_in_player]
    storyteller_paths = [decision.relative_path for decision in decisions if decision.included_in_storyteller]
    player_index = build_scoped_index(vault_root, indexes_dir / "player-vault-index.sqlite3", player_paths, "player")
    storyteller_index = build_scoped_index(
        vault_root,
        indexes_dir / "storyteller-vault-index.sqlite3",
        storyteller_paths,
        "storyteller",
    )

    rules_meta: dict[str, Any] = {"included": False}
    source_rules_db = rules_db_path(vault_root)
    if source_rules_db.exists():
        target_rules_db = rules_dir / "rules.sqlite3"
        shutil.copy2(source_rules_db, target_rules_db)
        rules_meta = {
            "included": True,
            "path": "rules/rules.sqlite3",
            "size_bytes": target_rules_db.stat().st_size,
            "fingerprint": _fingerprint_file_bytes(target_rules_db),
        }

    decisions_payload = [decision.to_dict() for decision in decisions]
    access_policy_hash = _fingerprint_json({"decisions": decisions_payload, "summary": summary})
    access_policy_payload = {
        "schema_version": 1,
        "summary": summary,
        "decisions": decisions_payload,
        "access_policy_hash": access_policy_hash,
    }
    (output_root / "access-policy.json").write_text(
        json.dumps(access_policy_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    file_fingerprints = {
        "access-policy.json": _fingerprint_file_bytes(output_root / "access-policy.json"),
        "indexes/player-vault-index.sqlite3": _fingerprint_file_bytes(indexes_dir / "player-vault-index.sqlite3"),
        "indexes/storyteller-vault-index.sqlite3": _fingerprint_file_bytes(indexes_dir / "storyteller-vault-index.sqlite3"),
    }
    if rules_meta["included"]:
        file_fingerprints["rules/rules.sqlite3"] = str(rules_meta["fingerprint"])

    manifest = {
        "schema_version": BOT_BUNDLE_SCHEMA_VERSION,
        "backet_version": __version__,
        "exported_at": timestamp_now(),
        "vault": str(vault_root),
        "bot": _portable_bot_config(config.to_dict()),
        "source_revision": _fingerprint_json(
            {
                "decisions": decisions_payload,
                "rules": rules_meta,
                "indexes": {
                    "player": player_index["content_fingerprint"],
                    "storyteller": storyteller_index["content_fingerprint"],
                },
            }
        ),
        "access_policy_hash": access_policy_hash,
        "visibility_summary": summary,
        "files": file_fingerprints,
        "indexes": {
            "player": _portable_index_meta(player_index, "indexes/player-vault-index.sqlite3"),
            "storyteller": _portable_index_meta(storyteller_index, "indexes/storyteller-vault-index.sqlite3"),
        },
        "rules": rules_meta,
        "model": _portable_model_meta(config.to_dict()),
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    issues = []
    if summary["player_index_notes"] == 0:
        issues.append(
            Issue(
                code="bot_export_no_player_notes",
                severity="warning",
                message="No notes are explicitly player-visible for bot export.",
                hint="Open the guided visibility editor and mark player-facing notes.",
                safe_to_fix=False,
            )
        )

    return CommandResult(
        message="Exported private bot bundle",
        created=[
            str((output_root / "manifest.json").relative_to(output_root)),
            str((output_root / "access-policy.json").relative_to(output_root)),
            "indexes/player-vault-index.sqlite3",
            "indexes/storyteller-vault-index.sqlite3",
            *(['rules/rules.sqlite3'] if rules_meta["included"] else []),
        ],
        issues=issues,
        data={
            "vault": str(vault_root),
            "output_path": str(output_root),
            "manifest_path": str(output_root / "manifest.json"),
            "summary": summary,
            "indexes": manifest["indexes"],
            "rules": rules_meta,
            "access_policy_hash": access_policy_hash,
            "policy_decisions": decisions_payload,
            "file_fingerprints": file_fingerprints,
            "deploy_hints": {
                "private_bundle": True,
                "target": "oracle-always-free-vm",
                "activation": "github-actions-upload-activate-smoke",
                "model_files_bundled": False,
            },
        },
    )


def doctor_bot_bundle(bundle_root: Path) -> CommandResult:
    root = bundle_root.expanduser().resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise AppError(
            code="bot_bundle_manifest_missing",
            message="Bot bundle manifest is missing.",
            hint="Export a bot bundle before checking it.",
            details={"bundle_root": str(root)},
            exit_code=2,
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema_version = int(manifest.get("schema_version", 0))
    if schema_version != BOT_BUNDLE_SCHEMA_VERSION:
        raise AppError(
            code="bot_bundle_schema_unsupported",
            message="Bot bundle schema version is unsupported.",
            hint=f"Expected schema version {BOT_BUNDLE_SCHEMA_VERSION}.",
            details={"schema_version": schema_version, "bundle_root": str(root)},
            exit_code=2,
        )

    issues: list[Issue] = []
    for scope, meta in manifest.get("indexes", {}).items():
        path = root / str(meta.get("path", ""))
        if not path.exists():
            issues.append(
                Issue(
                    code="bot_bundle_index_missing",
                    severity="error",
                    message=f"Missing bot index for {scope}",
                    path=str(path),
                    hint="Re-export the bundle.",
                    safe_to_fix=False,
                )
            )
            continue
        _append_fingerprint_issue(issues, root, manifest, str(meta.get("path", "")))
    rules = manifest.get("rules", {})
    if rules.get("included"):
        rules_path = root / str(rules.get("path", ""))
        if not rules_path.exists():
            issues.append(
                Issue(
                    code="bot_bundle_rules_missing",
                    severity="error",
                    message="Bundled shared rules database is missing",
                    path=str(rules_path),
                    hint="Re-export the bundle.",
                    safe_to_fix=False,
                )
            )
        else:
            _append_fingerprint_issue(issues, root, manifest, str(rules.get("path", "")))

    policy_path = root / "access-policy.json"
    if not policy_path.exists():
        issues.append(
            Issue(
                code="bot_bundle_access_policy_missing",
                severity="error",
                message="Bundled access policy is missing",
                path=str(policy_path),
                hint="Re-export the bundle.",
                safe_to_fix=False,
            )
        )
    else:
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(
                Issue(
                    code="bot_bundle_access_policy_invalid",
                    severity="error",
                    message="Bundled access policy is not valid JSON",
                    path=str(policy_path),
                    hint=str(exc),
                    safe_to_fix=False,
                )
            )
        else:
            if policy.get("access_policy_hash") != manifest.get("access_policy_hash"):
                issues.append(
                    Issue(
                        code="bot_bundle_access_policy_hash_mismatch",
                        severity="error",
                        message="Access policy hash does not match the bundle manifest",
                        path=str(policy_path),
                        hint="Re-export the bundle.",
                        safe_to_fix=False,
                    )
                )
        _append_fingerprint_issue(issues, root, manifest, "access-policy.json")

    return CommandResult(
        message="Bot bundle health check complete",
        issues=issues,
        data={
            "bundle_root": str(root),
            "manifest_path": str(manifest_path),
            "schema_version": schema_version,
            "ok": not any(issue.severity == "error" for issue in issues),
            "manifest": manifest,
        },
    )


def _portable_index_meta(meta: dict[str, object], path: str) -> dict[str, object]:
    return {
        "scope": meta["scope"],
        "path": path,
        "note_count": meta["note_count"],
        "chunk_count": meta["chunk_count"],
        "content_fingerprint": meta["content_fingerprint"],
        "embedding_backend": meta["embedding_backend"],
        "embedding_model": meta["embedding_model"],
        "relative_paths": meta["relative_paths"],
    }


def _portable_bot_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "guild_id": config.get("guild_id"),
        "roles": config.get("roles", {}),
        "users": config.get("users", {}),
        "commands": config.get("commands", {}),
        "response_defaults": config.get("response_defaults", {}),
        "answer_mode": config.get("answer_mode", "template"),
        "model": config.get("model", {}),
        "config_exists": bool(config.get("exists")),
    }


def _portable_model_meta(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer_mode": config.get("answer_mode", "template"),
        "model_files_bundled": False,
        "configured": config.get("model", {}),
        "recommended": {
            "default": "Llama-3.2-3B-Instruct GGUF Q4",
            "stronger_optional": "Llama-3.1-8B-Instruct GGUF Q4",
        },
    }


def _append_fingerprint_issue(
    issues: list[Issue],
    root: Path,
    manifest: dict[str, Any],
    relative_path: str,
) -> None:
    expected = manifest.get("files", {}).get(relative_path)
    if not expected:
        return
    path = root / relative_path
    actual = _fingerprint_file_bytes(path)
    if actual == expected:
        return
    issues.append(
        Issue(
            code="bot_bundle_file_fingerprint_mismatch",
            severity="error",
            message=f"Bundle file fingerprint mismatch for {relative_path}",
            path=str(path),
            hint="Re-export the bundle.",
            safe_to_fix=False,
        )
    )


def _fingerprint_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _fingerprint_file_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
