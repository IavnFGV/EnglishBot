#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/englishbot/app}"
SHARED_DIR="${SHARED_DIR:-/srv/englishbot/shared}"
CURRENT_RELEASE_FILE="${CURRENT_RELEASE_FILE:-${SHARED_DIR}/deploy/current-release.env}"
DEPLOY_TAG_PREFIX="${DEPLOY_TAG_PREFIX:-deploy-v}"
TARGET_TAG="${1:-}"
CORE_COMPOSE_FILE="${CORE_COMPOSE_FILE:-docker-compose.yml}"
OPTIONAL_COMPOSE_FILE="${OPTIONAL_COMPOSE_FILE:-docker-compose.optional.yml}"
DEPLOY_OPTIONAL_SERVICES="${DEPLOY_OPTIONAL_SERVICES:-auto}"

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

echo "==> Fetching tags"
git fetch --tags origin

CURRENT_DEPLOY_TAG=""
if [[ -f "${CURRENT_RELEASE_FILE}" ]]; then
  CURRENT_DEPLOY_TAG="$(grep '^ENGLISHBOT_DEPLOY_TAG=' "${CURRENT_RELEASE_FILE}" | cut -d= -f2- || true)"
  if [[ -z "${DEPLOY_OPTIONAL_SERVICES}" ]]; then
    DEPLOY_OPTIONAL_SERVICES="$(grep '^ENGLISHBOT_DEPLOY_OPTIONAL_SERVICES=' "${CURRENT_RELEASE_FILE}" | cut -d= -f2- || true)"
  fi
fi

DEPLOY_OPTIONAL_SERVICES="$(
  PYTHONPATH=src python -m englishbot.deploy.optional_services \
    --mode "${DEPLOY_OPTIONAL_SERVICES}" \
    --current-release-file "${CURRENT_RELEASE_FILE}" \
    --shared-env-file "${SHARED_DIR}/.env"
)"

compose_args=(-f "${CORE_COMPOSE_FILE}")
if [[ "${DEPLOY_OPTIONAL_SERVICES}" == "true" ]]; then
  if [[ ! -f "${OPTIONAL_COMPOSE_FILE}" ]]; then
    echo "${OPTIONAL_COMPOSE_FILE} not found in ${APP_DIR}" >&2
    exit 1
  fi
  compose_args+=(-f "${OPTIONAL_COMPOSE_FILE}")
fi

if [[ -z "${TARGET_TAG}" ]]; then
  mapfile -t DEPLOY_TAGS < <(git for-each-ref --sort=-creatordate --format='%(refname:short)' "refs/tags/${DEPLOY_TAG_PREFIX}*")
  if [[ ${#DEPLOY_TAGS[@]} -eq 0 ]]; then
    echo "No deploy tags found." >&2
    exit 1
  fi
  if [[ -n "${CURRENT_DEPLOY_TAG}" ]]; then
    for index in "${!DEPLOY_TAGS[@]}"; do
      if [[ "${DEPLOY_TAGS[$index]}" == "${CURRENT_DEPLOY_TAG}" ]]; then
        next_index=$((index + 1))
        if [[ ${next_index} -ge ${#DEPLOY_TAGS[@]} ]]; then
          echo "No previous deploy tag exists before ${CURRENT_DEPLOY_TAG}." >&2
          exit 1
        fi
        TARGET_TAG="${DEPLOY_TAGS[$next_index]}"
        break
      fi
    done
  fi
  if [[ -z "${TARGET_TAG}" ]]; then
    TARGET_TAG="${DEPLOY_TAGS[0]}"
  fi
fi

if ! git rev-parse -q --verify "refs/tags/${TARGET_TAG}" >/dev/null; then
  echo "Deploy tag not found: ${TARGET_TAG}" >&2
  exit 1
fi

if [[ ! "${TARGET_TAG}" =~ ^deploy-v(.+)-b([0-9]+)$ ]]; then
  echo "Unsupported deploy tag format: ${TARGET_TAG}" >&2
  exit 1
fi

ENGLISHBOT_BUILD_VERSION="${BASH_REMATCH[1]}"
ENGLISHBOT_BUILD_NUMBER="${BASH_REMATCH[2]}"
ENGLISHBOT_GIT_SHA="$(git rev-list -n 1 "${TARGET_TAG}" | cut -c1-7)"
ENGLISHBOT_GIT_BRANCH="rollback:${TARGET_TAG}"
ENGLISHBOT_DEPLOY_TAG="${TARGET_TAG}"

echo "==> Checking out ${TARGET_TAG}"
git checkout --detach "${TARGET_TAG}"

mkdir -p "$(dirname "${CURRENT_RELEASE_FILE}")"
cat > "${CURRENT_RELEASE_FILE}" <<EOF
ENGLISHBOT_BUILD_VERSION=${ENGLISHBOT_BUILD_VERSION}
ENGLISHBOT_BUILD_NUMBER=${ENGLISHBOT_BUILD_NUMBER}
ENGLISHBOT_GIT_SHA=${ENGLISHBOT_GIT_SHA}
ENGLISHBOT_GIT_BRANCH=${ENGLISHBOT_GIT_BRANCH}
ENGLISHBOT_DEPLOY_TAG=${ENGLISHBOT_DEPLOY_TAG}
ENGLISHBOT_DEPLOY_OPTIONAL_SERVICES=${DEPLOY_OPTIONAL_SERVICES}
EOF

export ENGLISHBOT_BUILD_VERSION
export ENGLISHBOT_BUILD_NUMBER
export ENGLISHBOT_GIT_SHA
export ENGLISHBOT_GIT_BRANCH
export ENGLISHBOT_DEPLOY_TAG
export DEPLOY_OPTIONAL_SERVICES

echo "==> Rolling back to tag=${ENGLISHBOT_DEPLOY_TAG} version=${ENGLISHBOT_BUILD_VERSION} build=${ENGLISHBOT_BUILD_NUMBER}"
docker compose "${compose_args[@]}" up -d --build

echo "==> Current container status"
docker compose "${compose_args[@]}" ps
