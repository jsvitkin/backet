#!/usr/bin/env bash
set -euo pipefail

REPO=""
VERSION=""
PYTHON_BIN="${PYTHON:-python3}"

usage() {
  cat <<'EOF'
Usage: install.sh --repo OWNER/REPO [--version X.Y.Z] [--python /path/to/python]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$REPO" ]]; then
  echo "--repo OWNER/REPO is required." >&2
  exit 2
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 2
fi

resolve_version() {
  "$PYTHON_BIN" - "$REPO" "$VERSION" <<'PY'
import json
import sys
from urllib.request import urlopen

repo, requested = sys.argv[1], sys.argv[2]
if requested:
    print(requested.lstrip("v"))
    raise SystemExit(0)

with urlopen(f"https://api.github.com/repos/{repo}/releases/latest") as response:
    payload = json.load(response)

tag = payload.get("tag_name")
if not tag:
    raise SystemExit("Could not resolve the latest release tag.")
print(tag.lstrip("v"))
PY
}

ensure_pipx() {
  if command -v pipx >/dev/null 2>&1; then
    echo "pipx found on PATH."
    PIPX_CMD=(pipx)
    return
  fi

  echo "pipx not found. Bootstrapping it with $PYTHON_BIN -m pip install --user pipx"
  "$PYTHON_BIN" -m pip install --user pipx
  "$PYTHON_BIN" -m pipx ensurepath >/dev/null 2>&1 || true
  PIPX_CMD=("$PYTHON_BIN" -m pipx)
}

ensure_pipx
RESOLVED_VERSION="$(resolve_version)"
WHEEL_URL="https://github.com/${REPO}/releases/download/v${RESOLVED_VERSION}/backet-${RESOLVED_VERSION}-py3-none-any.whl"

echo "Installing backet ${RESOLVED_VERSION} from ${WHEEL_URL}"
"${PIPX_CMD[@]}" install --force "$WHEEL_URL"
"${PIPX_CMD[@]}" ensurepath >/dev/null 2>&1 || true

cat <<EOF
Installed backet ${RESOLVED_VERSION}.
If \`backet\` is not available in your current shell yet, open a new shell or run:
  ${PIPX_CMD[*]} ensurepath
EOF
