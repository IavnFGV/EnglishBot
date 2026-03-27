#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/englishbot/app}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-master}"

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

echo "==> Rebuilding and restarting englishbot"
docker compose up -d --build

echo "==> Current container status"
docker compose ps
