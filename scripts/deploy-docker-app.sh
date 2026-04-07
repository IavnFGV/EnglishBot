#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/englishbot/app}"
SHARED_DIR="${SHARED_DIR:-/srv/englishbot/shared}"
BUILD_COUNTER_FILE="${BUILD_COUNTER_FILE:-${SHARED_DIR}/deploy/build-counter.env}"
CURRENT_RELEASE_FILE="${CURRENT_RELEASE_FILE:-${SHARED_DIR}/deploy/current-release.env}"
DB_BACKUP_FILE="${DB_BACKUP_FILE:-${SHARED_DIR}/deploy/last-db-backup.env}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
CORE_COMPOSE_FILE="${CORE_COMPOSE_FILE:-docker-compose.yml}"
OPTIONAL_COMPOSE_FILE="${OPTIONAL_COMPOSE_FILE:-docker-compose.optional.yml}"
DEPLOY_OPTIONAL_SERVICES="${DEPLOY_OPTIONAL_SERVICES:-false}"

if [[ ! -d "${APP_DIR}" ]]; then
  echo "App directory does not exist: ${APP_DIR}" >&2
  exit 1
fi

cd "${APP_DIR}"

if [[ ! -d .git ]]; then
  echo "App directory is not a git checkout: ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f "${CORE_COMPOSE_FILE}" ]]; then
  echo "${CORE_COMPOSE_FILE} not found in ${APP_DIR}" >&2
  exit 1
fi

compose_args=(-f "${CORE_COMPOSE_FILE}")
if [[ "${DEPLOY_OPTIONAL_SERVICES}" == "true" ]]; then
  if [[ ! -f "${OPTIONAL_COMPOSE_FILE}" ]]; then
    echo "${OPTIONAL_COMPOSE_FILE} not found in ${APP_DIR}" >&2
    exit 1
  fi
  compose_args+=(-f "${OPTIONAL_COMPOSE_FILE}")
fi

echo "==> Fetching latest code"
git fetch origin "${DEPLOY_BRANCH}"
git checkout "${DEPLOY_BRANCH}"
git reset --hard "origin/${DEPLOY_BRANCH}"

APP_VERSION="$(
  awk -F'"' '
    /^\[project\]/ { in_project=1; next }
    /^\[/ && !/^\[project\]/ { in_project=0 }
    in_project && $1 ~ /^[[:space:]]*version[[:space:]]*=[[:space:]]*$/ { print $2; exit }
  ' pyproject.toml
)"

if [[ -z "${APP_VERSION}" ]]; then
  echo "Could not read project.version from pyproject.toml" >&2
  exit 1
fi

PREVIOUS_BUILD_VERSION=""
PREVIOUS_BUILD_NUMBER="0"
if [[ -f "${BUILD_COUNTER_FILE}" ]]; then
  PREVIOUS_BUILD_VERSION="$(grep '^ENGLISHBOT_BUILD_VERSION=' "${BUILD_COUNTER_FILE}" | cut -d= -f2- || true)"
  PREVIOUS_BUILD_NUMBER="$(grep '^ENGLISHBOT_BUILD_NUMBER=' "${BUILD_COUNTER_FILE}" | cut -d= -f2- || true)"
fi

if [[ "${PREVIOUS_BUILD_VERSION}" == "${APP_VERSION}" ]] && [[ "${PREVIOUS_BUILD_NUMBER}" =~ ^[0-9]+$ ]]; then
  ENGLISHBOT_BUILD_NUMBER="$((PREVIOUS_BUILD_NUMBER + 1))"
else
  ENGLISHBOT_BUILD_NUMBER="1"
fi

ENGLISHBOT_GIT_SHA="$(git rev-parse --short HEAD)"
ENGLISHBOT_GIT_BRANCH="${DEPLOY_BRANCH}"
ENGLISHBOT_DEPLOY_TAG="deploy-v${APP_VERSION}-b${ENGLISHBOT_BUILD_NUMBER}"

DB_BACKUP_PATH="$(bash scripts/backup-runtime-db.sh "${ENGLISHBOT_DEPLOY_TAG}")"

mkdir -p "$(dirname "${BUILD_COUNTER_FILE}")"
cat > "${BUILD_COUNTER_FILE}" <<EOF
ENGLISHBOT_BUILD_VERSION=${APP_VERSION}
ENGLISHBOT_BUILD_NUMBER=${ENGLISHBOT_BUILD_NUMBER}
EOF

cat > "${DB_BACKUP_FILE}" <<EOF
ENGLISHBOT_DB_BACKUP_PATH=${DB_BACKUP_PATH}
EOF

cat > "${CURRENT_RELEASE_FILE}" <<EOF
ENGLISHBOT_BUILD_VERSION=${APP_VERSION}
ENGLISHBOT_BUILD_NUMBER=${ENGLISHBOT_BUILD_NUMBER}
ENGLISHBOT_GIT_SHA=${ENGLISHBOT_GIT_SHA}
ENGLISHBOT_GIT_BRANCH=${ENGLISHBOT_GIT_BRANCH}
ENGLISHBOT_DEPLOY_TAG=${ENGLISHBOT_DEPLOY_TAG}
ENGLISHBOT_DB_BACKUP_PATH=${DB_BACKUP_PATH}
ENGLISHBOT_DEPLOY_OPTIONAL_SERVICES=${DEPLOY_OPTIONAL_SERVICES}
EOF

export ENGLISHBOT_BUILD_VERSION="${APP_VERSION}"
export ENGLISHBOT_BUILD_NUMBER
export ENGLISHBOT_GIT_SHA
export ENGLISHBOT_GIT_BRANCH
export ENGLISHBOT_DEPLOY_TAG
export DEPLOY_OPTIONAL_SERVICES

echo "==> Building runtime version metadata version=${ENGLISHBOT_BUILD_VERSION} build=${ENGLISHBOT_BUILD_NUMBER} git_sha=${ENGLISHBOT_GIT_SHA} branch=${ENGLISHBOT_GIT_BRANCH} tag=${ENGLISHBOT_DEPLOY_TAG}"
echo "==> Database backup saved to ${DB_BACKUP_PATH}"
if [[ "${DEPLOY_OPTIONAL_SERVICES}" == "true" ]]; then
  echo "==> Rebuilding and recreating core + optional runtime containers"
else
  echo "==> Rebuilding and recreating core runtime container"
fi
docker compose "${compose_args[@]}" up -d --build --force-recreate

echo "==> Current container status"
docker compose "${compose_args[@]}" ps
