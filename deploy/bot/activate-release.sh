#!/usr/bin/env bash
set -euo pipefail

ROOT="${BACKET_BOT_ROOT:-/srv/backet-bot}"
ARCHIVE="${1:?usage: activate-release.sh <bundle.tar.gz> [release-id]}"
RELEASE_ID="${2:-$(date -u +%Y%m%dT%H%M%SZ)}"
COMPOSE_FILE="${ROOT}/deploy/docker-compose.yml"
RELEASE_DIR="${ROOT}/releases/${RELEASE_ID}"

mkdir -p "${ROOT}/uploads" "${ROOT}/releases" "${ROOT}/data" "${ROOT}/models"
rm -rf "${RELEASE_DIR}"
mkdir -p "${RELEASE_DIR}"
echo "Extracting Backet bot release: ${RELEASE_ID}"
tar -xzf "${ARCHIVE}" -C "${RELEASE_DIR}"

echo "Checking Backet bot bundle"
if command -v backet >/dev/null 2>&1; then
  backet bot doctor "${RELEASE_DIR}"
else
  docker compose -f "${COMPOSE_FILE}" run --rm --no-deps \
    -v "${RELEASE_DIR}:/srv/backet-bot/check:ro" \
    backet-bot bot doctor /srv/backet-bot/check
fi

ln -sfn "${RELEASE_DIR}" "${ROOT}/data/current.next"
mv -Tf "${ROOT}/data/current.next" "${ROOT}/data/current"

echo "Preparing optional Llama model"
"${ROOT}/deploy/bootstrap-llama-model.sh"

echo "Starting Backet bot services"
docker compose -f "${COMPOSE_FILE}" --env-file "${ROOT}/deploy/.env" up -d --build
echo "Inspecting running Backet bot container"
docker compose -f "${COMPOSE_FILE}" exec -T backet-bot backet bot inspect /srv/backet-bot/data/current
