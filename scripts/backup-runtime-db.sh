#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/englishbot/app}"
SHARED_DIR="${SHARED_DIR:-/srv/englishbot/shared}"
ENV_FILE="${ENV_FILE:-${SHARED_DIR}/.env}"
BACKUP_DIR="${BACKUP_DIR:-${SHARED_DIR}/backups/db}"
CONTAINER_NAME="${CONTAINER_NAME:-englishbot}"
KEEP_BACKUPS="${KEEP_BACKUPS:-5}"
DEPLOY_LABEL="${1:-manual}"

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

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SAFE_LABEL="$(printf '%s' "${DEPLOY_LABEL}" | tr '/: ' '---')"
BACKUP_FILE_NAME="englishbot-db-${SAFE_LABEL}-${TIMESTAMP}.sqlite3"
BACKUP_PATH_HOST="${BACKUP_DIR}/${BACKUP_FILE_NAME}"
BACKUP_PATH_CONTAINER="/app/backups/db/${BACKUP_FILE_NAME}"

mkdir -p "${BACKUP_DIR}"

if docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "==> Backing up live SQLite database from container ${CONTAINER_NAME}" >&2
  docker exec \
    -e ENGLISHBOT_DB_PATH="${CONTENT_DB_PATH}" \
    -e ENGLISHBOT_DB_BACKUP_PATH="${BACKUP_PATH_CONTAINER}" \
    "${CONTAINER_NAME}" \
    python - <<'PY'
import os
import sqlite3
from pathlib import Path

source_path = Path(os.environ["ENGLISHBOT_DB_PATH"])
if not source_path.is_absolute():
    source_path = Path("/app") / source_path
backup_path = Path(os.environ["ENGLISHBOT_DB_BACKUP_PATH"])
backup_path.parent.mkdir(parents=True, exist_ok=True)

source = sqlite3.connect(source_path)
target = sqlite3.connect(backup_path)
try:
    source.backup(target)
finally:
    target.close()
    source.close()
PY
else
  DB_PATH_HOST="${SHARED_DIR}/${CONTENT_DB_PATH}"
  if [[ ! -f "${DB_PATH_HOST}" ]]; then
    echo "Database file not found: ${DB_PATH_HOST}" >&2
    exit 1
  fi
  echo "==> Backing up SQLite database from host file ${DB_PATH_HOST}" >&2
  cp "${DB_PATH_HOST}" "${BACKUP_PATH_HOST}"
fi

mapfile -t EXISTING_BACKUPS < <(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'englishbot-db-*.sqlite3' -printf '%T@ %p\n' | sort -rn | awk '{print $2}')
if [[ ${#EXISTING_BACKUPS[@]} -gt "${KEEP_BACKUPS}" ]]; then
  for backup_path in "${EXISTING_BACKUPS[@]:KEEP_BACKUPS}"; do
    rm -f "${backup_path}"
  done
fi

printf '%s\n' "${BACKUP_PATH_HOST}"
