#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/englishbot/app}"
SHARED_DIR="${SHARED_DIR:-/srv/englishbot/shared}"
ENV_FILE="${ENV_FILE:-${SHARED_DIR}/.env}"
CONTAINER_NAME="${CONTAINER_NAME:-englishbot}"
BACKUP_PATH="${1:-}"

if [[ -z "${BACKUP_PATH}" ]]; then
  echo "Usage: bash scripts/restore-runtime-db.sh /srv/englishbot/shared/backups/db/<file>.sqlite3" >&2
  exit 1
fi

if [[ ! -f "${BACKUP_PATH}" ]]; then
  echo "Backup file not found: ${BACKUP_PATH}" >&2
  exit 1
fi

if [[ ! -d "${APP_DIR}" ]]; then
  echo "App directory does not exist: ${APP_DIR}" >&2
  exit 1
fi

CONTENT_DB_PATH="data/englishbot.db"
if [[ -f "${ENV_FILE}" ]]; then
  OVERRIDE_DB_PATH="$(grep '^CONTENT_DB_PATH=' "${ENV_FILE}" | cut -d= -f2- || true)"
  if [[ -n "${OVERRIDE_DB_PATH}" ]]; then
    CONTENT_DB_PATH="${OVERRIDE_DB_PATH}"
  fi
fi

DB_PATH_HOST="${SHARED_DIR}/${CONTENT_DB_PATH}"
mkdir -p "$(dirname "${DB_PATH_HOST}")"

cd "${APP_DIR}"

if docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "==> Stopping running container ${CONTAINER_NAME}" >&2
  docker compose stop "${CONTAINER_NAME}"
fi

echo "==> Restoring SQLite database from ${BACKUP_PATH}" >&2
cp "${BACKUP_PATH}" "${DB_PATH_HOST}"

echo "==> Starting englishbot again" >&2
docker compose up -d
