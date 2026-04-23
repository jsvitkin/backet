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
export PIPX_HOME PIPX_BIN_DIR
export BACKET_CONFIG_HOME="${TMP_ROOT}/machine-config"
export CODEX_HOME="${TMP_ROOT}/codex-home"

"$PYTHON_BIN" -m pip install --upgrade pip pipx >/dev/null
"$PYTHON_BIN" -m pipx install "$WHEEL_PATH" >/dev/null
PATH="${PIPX_BIN_DIR}:${PATH}"
export PATH

BACKET_BIN="${PIPX_BIN_DIR}/backet"
VAULT_DIR="${TMP_ROOT}/vault"
ARCHIVE_PATH="${TMP_ROOT}/skills-repo.zip"

mkdir -p "$VAULT_DIR"

"$BACKET_BIN" --json --version | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["data"]["version"]'
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
