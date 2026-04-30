#!/usr/bin/env bash
set -euo pipefail

WHEEL_PATH="${1:-}"
REPO_ROOT="${2:-$(pwd)}"
PYTHON_BIN="${PYTHON:-python3}"

if [[ -z "$WHEEL_PATH" ]]; then
  echo "Usage: smoke-install.sh <wheel-path> [repo-root]" >&2
  exit 2
fi

TMP_ROOT="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

PIPX_HOME="${TMP_ROOT}/pipx-home"
PIPX_BIN_DIR="${TMP_ROOT}/pipx-bin"
BOOTSTRAP_VENV="${TMP_ROOT}/bootstrap-venv"
export PIPX_HOME PIPX_BIN_DIR
export BACKET_CONFIG_HOME="${TMP_ROOT}/machine-config"
export CODEX_HOME="${TMP_ROOT}/codex-home"
export BACKET_SKIP_UPDATE_CHECK=1

"$PYTHON_BIN" -m venv "$BOOTSTRAP_VENV"
BOOTSTRAP_PYTHON="${BOOTSTRAP_VENV}/bin/python"

"$BOOTSTRAP_PYTHON" -m pip install --upgrade pip pipx >/dev/null
"$BOOTSTRAP_PYTHON" -m pipx install "$WHEEL_PATH" >/dev/null
PATH="${PIPX_BIN_DIR}:${PATH}"
export PATH

BACKET_BIN="${PIPX_BIN_DIR}/backet"
BACKET_PYTHON="${PIPX_HOME}/venvs/backet/bin/python"
VAULT_DIR="${TMP_ROOT}/vault"
ARCHIVE_PATH="${TMP_ROOT}/skills-repo.zip"
RULES_PDF_PATH="${TMP_ROOT}/core-rulebook.pdf"

mkdir -p "$VAULT_DIR"

"$BACKET_BIN" --json update check | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok" and "update_available" in payload["data"]'
test ! -f "${BACKET_CONFIG_HOME}/update-check.json"
test ! -f "${BACKET_CONFIG_HOME}/update-state.json"
"$BACKET_BIN" --json init "$VAULT_DIR" | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok"'

rm -rf "${VAULT_DIR}/.backet/cache" "${VAULT_DIR}/.backet/temp" "${VAULT_DIR}/.backet/ocr-work"
rm -f "${VAULT_DIR}/.backet/.gitignore"
"$BACKET_BIN" --json doctor --fix "$VAULT_DIR" | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["data"]["safe_fix_applied"] is True'

"$PYTHON_BIN" - "$REPO_ROOT" "$ARCHIVE_PATH" <<'PY'
import json
import sys
from pathlib import Path
from zipfile import ZipFile

repo_root = Path(sys.argv[1]).resolve()
archive_path = Path(sys.argv[2]).resolve()
skills_root = repo_root / "skills"
manifest_path = skills_root / "manifest.json"

with ZipFile(archive_path, "w") as zip_file:
    zip_file.write(manifest_path, "backet-main/skills/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for skill in manifest.get("skills", []):
        skill_dir = skills_root / skill["path"]
        for file_path in skill_dir.rglob("*"):
            if file_path.is_file():
                zip_file.write(file_path, Path("backet-main") / "skills" / skill["path"] / file_path.relative_to(skill_dir))
PY

BACKET_SKILLS_ARCHIVE_URL="file://${ARCHIVE_PATH}" \
  "$BACKET_BIN" --json skills install --repo example/backet \
  | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok"'

"$BACKET_BIN" --json skills status | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok" and payload["data"]["installed"] is True'
test -f "${CODEX_HOME}/skills/workflow-authoring/SKILL.md"
test -f "${CODEX_HOME}/skills/city-foundation/SKILL.md"

"$BACKET_BIN" --json blueprint apply "$VAULT_DIR" city-by-night-v1 \
  | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok" and len(payload["data"]["slots"]) == 5'
"$BACKET_BIN" --json blueprint status "$VAULT_DIR" city-by-night-v1 \
  | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok" and not payload["data"]["missing_slots"]'
"$BACKET_BIN" --json index "$VAULT_DIR" \
  | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok"'
"$BACKET_BIN" --json context "$VAULT_DIR" note "1. City Identity & Thematic Structure/1.1 Aesthetic & Mood.md" \
  | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok" and payload["data"]["sources"]'

"$BACKET_PYTHON" - "$RULES_PDF_PATH" <<'PY'
import sys

import fitz

pdf_path = sys.argv[1]
document = fitz.open()
try:
    page = document.new_page()
    box = fitz.Rect(36, 36, page.rect.width - 36, page.rect.height - 36)
    page.insert_textbox(
        box,
        (
            "Feeding Rights\n"
            "Blood dolls suffer addiction and emotional dependence after repeated feeding. "
            "Repeated access to vitae can create uneven consent, social fallout, and political scrutiny "
            "inside a Camarilla domain."
        ),
        fontsize=12,
    )
    document.save(pdf_path)
finally:
    document.close()
PY

"$BACKET_BIN" --json rules ingest "$VAULT_DIR" "$RULES_PDF_PATH" --book-id core-v5 --title "Core Rulebook" --tier core \
  | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok" and payload["data"]["book_id"] == "core-v5"'
"$BACKET_BIN" --json rules query "$VAULT_DIR" "blood dolls vitae consent" --book-id core-v5 \
  | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok" and payload["data"]["primary_results"]'
"$BACKET_BIN" --json rules audit "$VAULT_DIR" --book-id core-v5 \
  | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok" and payload["data"]["books"]'
"$BACKET_BIN" --json rules scope audit "$VAULT_DIR" --book-id core-v5 \
  | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok" and payload["data"]["books"][0]["confidence_thresholds"]'
