#!/usr/bin/env bash
set -euo pipefail

ROOT="${BACKET_BOT_ROOT:-/srv/backet-bot}"
BUNDLE="${1:-${ROOT}/data/current}"
MODELS_ROOT="${2:-${ROOT}/models}"

backet bot doctor "${BUNDLE}"
backet bot inspect "${BUNDLE}"
backet bot model-check "${BUNDLE}" --models-root "${MODELS_ROOT}"
