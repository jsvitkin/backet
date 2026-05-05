from __future__ import annotations

import json
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from backet.cli import app
from backet.indexing import open_index_database
from backet.retrieval import assemble_context_chunks, resolve_scope_anchor
from backet.vault import initialize_vault


def test_bot_export_builds_access_scoped_indexes_and_shared_rules_db(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nThe court is public knowledge.")
    _write(vault / "NPCs" / "Sabine.md", "storyteller", ["npc"], "# Sabine\n\nHidden stat block.")
    _write(vault / "Plot.md", "storyteller", ["plotline"], "# Plot\n\nHidden plotline.")
    _write(vault / "Scratch.md", "excluded", [], "# Scratch\n\nNever export to bot indexes.")
    rules_db = vault / ".backet" / "rules" / "rules.sqlite3"
    rules_db.write_bytes(b"private rules sqlite bytes")
    (vault / ".backet" / "rules" / "source.pdf").write_bytes(b"not copied")
    (vault / ".backet" / "cache" / "scratch.txt").write_text("not copied", encoding="utf-8")
    (vault / ".backet" / "temp" / "tmp.txt").write_text("not copied", encoding="utf-8")
    (vault / ".backet" / "ocr-work" / "page.txt").parent.mkdir(parents=True, exist_ok=True)
    (vault / ".backet" / "ocr-work" / "page.txt").write_text("not copied", encoding="utf-8")
    (vault / ".backet" / "models" / "model.gguf").parent.mkdir(parents=True, exist_ok=True)
    (vault / ".backet" / "models" / "model.gguf").write_bytes(b"not copied")
    (vault / ".backet" / "deploy" / "discord-token.env").parent.mkdir(parents=True, exist_ok=True)
    (vault / ".backet" / "deploy" / "discord-token.env").write_text("DISCORD_TOKEN=nope", encoding="utf-8")

    output = tmp_path / "bundle"
    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["summary"]["player_index_notes"] == 1
    assert payload["data"]["summary"]["storyteller_index_notes"] == 3
    assert payload["data"]["rules"]["included"] is True
    assert {item["relative_path"] for item in payload["data"]["policy_decisions"]} == {
        "NPCs/Sabine.md",
        "Player Primer.md",
        "Plot.md",
        "Scratch.md",
    }
    assert payload["data"]["deploy_hints"]["target"] == "oracle-always-free-vm"
    assert (output / "manifest.json").exists()
    assert (output / "access-policy.json").exists()
    assert (output / "rules" / "rules.sqlite3").read_bytes() == b"private rules sqlite bytes"
    assert not (output / "rules" / "source.pdf").exists()
    assert not (output / "cache").exists()
    assert not (output / "temp").exists()
    exported_files = _bundle_files(output)
    assert "rules/source.pdf" not in exported_files
    assert not any(name.startswith(("cache/", "temp/", "ocr-work/", "models/", "deploy/")) for name in exported_files)
    assert not any("token" in name for name in exported_files)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    access_policy_text = (output / "access-policy.json").read_text(encoding="utf-8")
    access_policy = json.loads(access_policy_text)
    assert manifest["schema_version"] == 1
    assert manifest["backet_version"]
    assert manifest["exported_at"]
    assert manifest["source_revision"]
    assert manifest["bot"]["answer_mode"] == "template"
    assert manifest["bot"]["guild_id"] is None
    assert manifest["access_policy_hash"] == access_policy["access_policy_hash"]
    assert manifest["access_policy_hash"] == sha256(
        json.dumps(
            {"decisions": access_policy["decisions"], "summary": access_policy["summary"]},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    assert manifest["indexes"]["player"]["path"] == "indexes/player-vault-index.sqlite3"
    assert manifest["files"]["access-policy.json"] == sha256(access_policy_text.encode("utf-8")).hexdigest()
    assert manifest["files"]["indexes/player-vault-index.sqlite3"]
    assert manifest["files"]["indexes/storyteller-vault-index.sqlite3"]
    assert payload["data"]["file_fingerprints"] == manifest["files"]
    assert manifest["indexes"]["player"]["note_count"] == 1
    assert manifest["indexes"]["storyteller"]["note_count"] == 3
    assert manifest["indexes"]["player"]["chunk_count"] > 0
    assert manifest["indexes"]["player"]["embedding_backend"] == "hash"
    assert manifest["indexes"]["player"]["embedding_model"] == "hash-v1-64"
    assert manifest["model"]["answer_mode"] == "template"
    assert manifest["model"]["model_files_bundled"] is False
    assert manifest["rules"]["path"] == "rules/rules.sqlite3"

    with closing(open_index_database(output / "indexes" / "player-vault-index.sqlite3")) as connection:
        player_paths = [row["relative_path"] for row in connection.execute("SELECT relative_path FROM notes")]
        player_scope = connection.execute("SELECT value FROM index_meta WHERE key = 'access_scope'").fetchone()["value"]
        player_embedding = connection.execute("SELECT embedding_json FROM chunks LIMIT 1").fetchone()["embedding_json"]
        hidden_title = connection.execute("SELECT * FROM notes WHERE title = 'Sabine'").fetchone()
        hidden_content = connection.execute(
            "SELECT * FROM chunk_fts WHERE content MATCH ?",
            ("hidden",),
        ).fetchone()

    with closing(open_index_database(output / "indexes" / "storyteller-vault-index.sqlite3")) as connection:
        storyteller_paths = [row["relative_path"] for row in connection.execute("SELECT relative_path FROM notes")]
        storyteller_scope = connection.execute("SELECT value FROM index_meta WHERE key = 'access_scope'").fetchone()["value"]

    assert player_paths == ["Player Primer.md"]
    assert player_scope == "player"
    assert json.loads(player_embedding)
    assert hidden_title is None
    assert hidden_content is None
    assert sorted(storyteller_paths) == ["NPCs/Sabine.md", "Player Primer.md", "Plot.md"]
    assert storyteller_scope == "storyteller"


def test_bot_export_scoped_indexes_support_separate_lookup(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nCourt customs are public.")
    _write(vault / "NPCs" / "Sabine.md", "storyteller", ["npc"], "# Sabine\n\nSecret ghoul stat block.")

    output = tmp_path / "bundle"
    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])

    assert result.exit_code == 0
    with closing(open_index_database(output / "indexes" / "player-vault-index.sqlite3")) as connection:
        anchor = resolve_scope_anchor(connection, "vault", ".")
        player_sources = assemble_context_chunks(connection, anchor, query="secret ghoul stat block", limit=5)
    with closing(open_index_database(output / "indexes" / "storyteller-vault-index.sqlite3")) as connection:
        anchor = resolve_scope_anchor(connection, "vault", ".")
        storyteller_sources = assemble_context_chunks(connection, anchor, query="secret ghoul stat block", limit=5)

    assert {source["relative_path"] for source in player_sources} == {"Player Primer.md"}
    assert "NPCs/Sabine.md" in {source["relative_path"] for source in storyteller_sources}


def test_bot_export_reports_empty_player_index_warning(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "NPCs" / "Sabine.md", "storyteller", ["npc"], "# Sabine\n\nHidden stat block.")

    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(tmp_path / "bundle")])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["issues"][0]["code"] == "bot_export_no_player_notes"
    assert payload["data"]["indexes"]["player"]["note_count"] == 0


def test_bot_export_fails_closed_for_invalid_visibility_metadata(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "Bad.md").write_text("---\nbacket:\n  visibility: public\n---\n\n# Bad\n", encoding="utf-8")

    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(tmp_path / "bundle")])

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "bot_visibility_invalid"
    assert not (tmp_path / "bundle").exists()


def test_bot_export_refuses_existing_output_without_force_and_doctor_checks_bundle(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nThe court is public knowledge.")
    output = tmp_path / "bundle"

    first = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])
    second = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])
    forced = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output), "--force"])
    doctor = runner.invoke(app, ["--json", "bot", "doctor", str(output)])

    assert first.exit_code == 0
    assert second.exit_code == 2
    assert json.loads(second.stdout)["error"]["code"] == "bot_export_output_exists"
    assert forced.exit_code == 0
    assert doctor.exit_code == 0
    assert json.loads(doctor.stdout)["data"]["ok"] is True


def test_bot_doctor_reports_missing_manifest(runner, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()

    result = runner.invoke(app, ["--json", "bot", "doctor", str(bundle)])

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "bot_bundle_manifest_missing"


def test_bot_doctor_reports_missing_bundle_files_and_schema_mismatch(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nThe court is public knowledge.")
    output = tmp_path / "bundle"

    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])
    assert result.exit_code == 0
    (output / "indexes" / "player-vault-index.sqlite3").unlink()

    missing = runner.invoke(app, ["--json", "bot", "doctor", str(output)])

    assert missing.exit_code == 0
    payload = json.loads(missing.stdout)
    assert payload["data"]["ok"] is False
    assert payload["issues"][0]["code"] == "bot_bundle_index_missing"

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 999
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    bad_schema = runner.invoke(app, ["--json", "bot", "doctor", str(output)])

    assert bad_schema.exit_code == 2
    assert json.loads(bad_schema.stdout)["error"]["code"] == "bot_bundle_schema_unsupported"


def test_bot_doctor_reports_manifest_mismatches(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "Player Primer.md", "player", ["canon"], "# Player Primer\n\nThe court is public knowledge.")
    output = tmp_path / "bundle"

    result = runner.invoke(app, ["--json", "bot", "export", str(vault), "--output", str(output)])
    assert result.exit_code == 0
    (output / "access-policy.json").write_text('{"access_policy_hash": "wrong"}', encoding="utf-8")

    doctor = runner.invoke(app, ["--json", "bot", "doctor", str(output)])

    assert doctor.exit_code == 0
    payload = json.loads(doctor.stdout)
    assert payload["data"]["ok"] is False
    issue_codes = {issue["code"] for issue in payload["issues"]}
    assert "bot_bundle_access_policy_hash_mismatch" in issue_codes
    assert "bot_bundle_file_fingerprint_mismatch" in issue_codes


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    initialize_vault(vault, cli_version="0.1.0")
    return vault


def _write(path: Path, visibility: str, topics: list[str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    topic_lines = "".join(f"    - {topic}\n" for topic in topics)
    topics_block = f"  bot_topics:\n{topic_lines}" if topics else ""
    path.write_text(f"---\nbacket:\n  visibility: {visibility}\n{topics_block}---\n\n{body}\n", encoding="utf-8")


def _bundle_files(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
