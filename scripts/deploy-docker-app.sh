#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/englishbot/app}"
SHARED_DIR="${SHARED_DIR:-/srv/englishbot/shared}"
BUILD_STATE_FILE="${BUILD_STATE_FILE:-${SHARED_DIR}/deploy/build.env}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

if [[ ! -d "${APP_DIR}" ]]; then
  echo "App directory does not exist: ${APP_DIR}" >&2
  exit 1
fi

cd "${APP_DIR}"

if [[ ! -d .git ]]; then
  echo "App directory is not a git checkout: ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f docker-compose.yml ]]; then
  echo "docker-compose.yml not found in ${APP_DIR}" >&2
  exit 1
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
if [[ -f "${BUILD_STATE_FILE}" ]]; then
  PREVIOUS_BUILD_VERSION="$(grep '^ENGLISHBOT_BUILD_VERSION=' "${BUILD_STATE_FILE}" | cut -d= -f2- || true)"
  PREVIOUS_BUILD_NUMBER="$(grep '^ENGLISHBOT_BUILD_NUMBER=' "${BUILD_STATE_FILE}" | cut -d= -f2- || true)"
fi

if [[ "${PREVIOUS_BUILD_VERSION}" == "${APP_VERSION}" ]] && [[ "${PREVIOUS_BUILD_NUMBER}" =~ ^[0-9]+$ ]]; then
  ENGLISHBOT_BUILD_NUMBER="$((PREVIOUS_BUILD_NUMBER + 1))"
else
  ENGLISHBOT_BUILD_NUMBER="1"
fi

mkdir -p "$(dirname "${BUILD_STATE_FILE}")"
cat > "${BUILD_STATE_FILE}" <<EOF
ENGLISHBOT_BUILD_VERSION=${APP_VERSION}
ENGLISHBOT_BUILD_NUMBER=${ENGLISHBOT_BUILD_NUMBER}
EOF

export ENGLISHBOT_BUILD_VERSION="${APP_VERSION}"
export ENGLISHBOT_BUILD_NUMBER
export ENGLISHBOT_GIT_SHA
ENGLISHBOT_GIT_SHA="$(git rev-parse --short HEAD)"
export ENGLISHBOT_GIT_BRANCH="${DEPLOY_BRANCH}"

echo "==> Building runtime version metadata version=${ENGLISHBOT_BUILD_VERSION} build=${ENGLISHBOT_BUILD_NUMBER} git_sha=${ENGLISHBOT_GIT_SHA} branch=${ENGLISHBOT_GIT_BRANCH}"
echo "==> Rebuilding and restarting englishbot"
docker compose up -d --build

echo "==> Current container status"
docker compose ps
