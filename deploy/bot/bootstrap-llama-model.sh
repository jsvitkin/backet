#!/usr/bin/env bash
set -euo pipefail

ROOT="${BACKET_BOT_ROOT:-/srv/backet-bot}"
ENV_FILE="${ROOT}/deploy/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

MODEL_RELATIVE_PATH="${LLAMA_MODEL_RELATIVE_PATH:-}"
MODEL_SHA256="${LLAMA_MODEL_SHA256:-}"
MODEL_URL="${LLAMA_MODEL_URL:-}"

if [[ -z "${MODEL_RELATIVE_PATH}" ]]; then
  exit 0
fi

MODEL_PATH="${ROOT}/models/${MODEL_RELATIVE_PATH}"
mkdir -p "$(dirname "${MODEL_PATH}")"

if [[ -f "${MODEL_PATH}" && -n "${MODEL_SHA256}" ]]; then
  echo "${MODEL_SHA256}  ${MODEL_PATH}" | sha256sum --check --status && exit 0
fi

if [[ -f "${MODEL_PATH}" && -z "${MODEL_SHA256}" ]]; then
  echo "Model exists but LLAMA_MODEL_SHA256 is empty; leaving it in place." >&2
  exit 0
fi

if [[ -z "${MODEL_URL}" ]]; then
  echo "Model file is missing and LLAMA_MODEL_URL is not configured: ${MODEL_PATH}" >&2
  exit 1
fi

TMP_PATH="${MODEL_PATH}.download"
rm -f "${TMP_PATH}"

if [[ -n "${MODEL_DOWNLOAD_TOKEN:-}" ]]; then
  curl --fail --location --silent --show-error \
    --header "Authorization: Bearer ${MODEL_DOWNLOAD_TOKEN}" \
    --output "${TMP_PATH}" \
    "${MODEL_URL}"
else
  curl --fail --location --silent --show-error \
    --output "${TMP_PATH}" \
    "${MODEL_URL}"
fi

if [[ -n "${MODEL_SHA256}" ]]; then
  echo "${MODEL_SHA256}  ${TMP_PATH}" | sha256sum --check --status
fi

mv "${TMP_PATH}" "${MODEL_PATH}"
