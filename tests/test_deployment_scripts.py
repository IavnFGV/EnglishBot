from pathlib import Path


def test_hetzner_bootstrap_script_exists_and_installs_docker_stack() -> None:
    script = Path("scripts/bootstrap-hetzner-docker-host.sh").read_text(encoding="utf-8")

    assert 'apt install -y docker.io docker-compose-v2 ufw fail2ban' in script
    assert 'systemctl enable docker' in script
    assert 'systemctl start docker' in script


def test_hetzner_bootstrap_script_copies_root_ssh_keys_to_deploy_user() -> None:
    script = Path("scripts/bootstrap-hetzner-docker-host.sh").read_text(encoding="utf-8")

    assert 'ROOT_AUTH_KEYS="/root/.ssh/authorized_keys"' in script
    assert 'cp "${ROOT_AUTH_KEYS}" "${DEPLOY_HOME}/.ssh/authorized_keys"' in script
    assert 'usermod -aG docker "${DEPLOY_USER}"' in script


def test_hetzner_bootstrap_script_prepares_runtime_directories() -> None:
    script = Path("scripts/bootstrap-hetzner-docker-host.sh").read_text(encoding="utf-8")

    assert 'mkdir -p "${APP_ROOT}/app"' in script
    assert 'mkdir -p "${APP_ROOT}/shared/data"' in script
    assert 'mkdir -p "${APP_ROOT}/shared/assets"' in script
    assert 'mkdir -p "${APP_ROOT}/shared/backups/db"' in script
    assert 'mkdir -p "${APP_ROOT}/shared/backups/db-versioned"' in script
    assert 'mkdir -p "${APP_ROOT}/shared/content/custom"' in script
    assert 'mkdir -p "${APP_ROOT}/shared/deploy"' in script
    assert 'mkdir -p "${APP_ROOT}/shared/logs"' in script
    assert 'touch "${APP_ROOT}/shared/.env"' in script


def test_production_dockerfile_installs_bot_runtime_and_demo_content() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in dockerfile
    assert "fonts-dejavu-core" in dockerfile
    assert "ARG ENGLISHBOT_GIT_SHA=unknown" in dockerfile
    assert "ARG ENGLISHBOT_GIT_BRANCH=unknown" in dockerfile
    assert "ARG ENGLISHBOT_BUILD_VERSION=unknown" in dockerfile
    assert "ARG ENGLISHBOT_BUILD_NUMBER=0" in dockerfile
    assert "ENGLISHBOT_BUILD_VERSION=${ENGLISHBOT_BUILD_VERSION}" in dockerfile
    assert "ENGLISHBOT_BUILD_NUMBER=${ENGLISHBOT_BUILD_NUMBER}" in dockerfile
    assert "ENGLISHBOT_GIT_SHA=${ENGLISHBOT_GIT_SHA}" in dockerfile
    assert "ENGLISHBOT_GIT_BRANCH=${ENGLISHBOT_GIT_BRANCH}" in dockerfile
    assert "python -m pip install --upgrade pip" not in dockerfile
    assert 'python - <<\'PY\' > /tmp/requirements.txt' in dockerfile
    assert "python -m pip install -r /tmp/requirements.txt" in dockerfile
    assert "python -m pip install --no-deps ." in dockerfile
    assert "COPY content/demo ./content/demo" in dockerfile
    assert 'CMD ["python", "-m", "englishbot"]' in dockerfile


def test_docker_compose_mounts_persistent_runtime_directories() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "ENGLISHBOT_BUILD_VERSION: ${ENGLISHBOT_BUILD_VERSION:-unknown}" in compose
    assert "ENGLISHBOT_BUILD_NUMBER: ${ENGLISHBOT_BUILD_NUMBER:-0}" in compose
    assert "ENGLISHBOT_GIT_SHA: ${ENGLISHBOT_GIT_SHA:-unknown}" in compose
    assert "ENGLISHBOT_GIT_BRANCH: ${ENGLISHBOT_GIT_BRANCH:-main}" in compose
    assert "/srv/englishbot/shared/.env:/app/.env:ro" in compose
    assert "/srv/englishbot/shared/data:/app/data" in compose
    assert "/srv/englishbot/shared/assets:/app/assets" in compose
    assert "/srv/englishbot/shared/backups/db:/app/backups/db" in compose
    assert "/srv/englishbot/shared/backups/db-versioned:/app/backups/db-versioned" in compose
    assert "/srv/englishbot/shared/logs:/app/logs" in compose
    assert "/srv/englishbot/shared/content/custom:/app/content/custom" in compose


def test_server_bot_only_env_template_disables_local_ai_services() -> None:
    env_template = Path(".env.server.bot-only.example").read_text(encoding="utf-8")

    assert "OLLAMA_ENABLED=false" in env_template
    assert "COMFYUI_ENABLED=false" in env_template
    assert "PIXABAY_API_KEY=" in env_template


def test_server_deploy_script_fetches_branch_and_restarts_compose() -> None:
    script = Path("scripts/deploy-docker-app.sh").read_text(encoding="utf-8")

    assert 'APP_DIR="${APP_DIR:-/srv/englishbot/app}"' in script
    assert 'DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"' in script
    assert 'git fetch origin "${DEPLOY_BRANCH}"' in script
    assert 'git reset --hard "origin/${DEPLOY_BRANCH}"' in script
    assert 'BUILD_COUNTER_FILE="${BUILD_COUNTER_FILE:-${SHARED_DIR}/deploy/build-counter.env}"' in script
    assert 'CURRENT_RELEASE_FILE="${CURRENT_RELEASE_FILE:-${SHARED_DIR}/deploy/current-release.env}"' in script
    assert 'DB_BACKUP_FILE="${DB_BACKUP_FILE:-${SHARED_DIR}/deploy/last-db-backup.env}"' in script
    assert 'VERSION_CHANGE_DB_BACKUP_FILE="${VERSION_CHANGE_DB_BACKUP_FILE:-${SHARED_DIR}/deploy/last-version-change-db-backup.env}"' in script
    assert "awk -F'\"' " in script
    assert 'Could not read project.version from pyproject.toml' in script
    assert 'ENGLISHBOT_BUILD_NUMBER="$((PREVIOUS_BUILD_NUMBER + 1))"' in script
    assert 'ENGLISHBOT_BUILD_NUMBER="1"' in script
    assert 'ENGLISHBOT_DEPLOY_TAG="deploy-v${APP_VERSION}-b${ENGLISHBOT_BUILD_NUMBER}"' in script
    assert 'DB_BACKUP_PATH="$(bash scripts/backup-runtime-db.sh "${ENGLISHBOT_DEPLOY_TAG}")"' in script
    assert 'PERMANENT_BACKUP_LABEL="version-change-${PREVIOUS_BUILD_VERSION}-to-${APP_VERSION}"' in script
    assert 'PERMANENT_BACKUP_LABEL="${PERMANENT_BACKUP_LABEL}" \\' in script
    assert 'ENGLISHBOT_DB_BACKUP_PATH=${DB_BACKUP_PATH}' in script
    assert 'ENGLISHBOT_BUILD_VERSION=${APP_VERSION}' in script
    assert 'ENGLISHBOT_BUILD_NUMBER=${ENGLISHBOT_BUILD_NUMBER}' in script
    assert 'ENGLISHBOT_DEPLOY_TAG=${ENGLISHBOT_DEPLOY_TAG}' in script
    assert 'ENGLISHBOT_GIT_SHA="$(git rev-parse --short HEAD)"' in script
    assert 'ENGLISHBOT_GIT_BRANCH="${DEPLOY_BRANCH}"' in script
    assert "export ENGLISHBOT_GIT_BRANCH" in script
    assert "docker compose up -d --build" in script


def test_server_backup_script_keeps_only_latest_five_versions() -> None:
    script = Path("scripts/backup-runtime-db.sh").read_text(encoding="utf-8")

    assert 'BACKUP_DIR="${BACKUP_DIR:-${SHARED_DIR}/backups/db}"' in script
    assert 'PERMANENT_BACKUP_DIR="${PERMANENT_BACKUP_DIR:-${SHARED_DIR}/backups/db-versioned}"' in script
    assert 'KEEP_BACKUPS="${KEEP_BACKUPS:-5}"' in script
    assert 'PERMANENT_BACKUP_LABEL="${PERMANENT_BACKUP_LABEL:-}"' in script
    assert 'docker exec' in script
    assert 'source.backup(target)' in script
    assert 'BACKUP_PATH_CONTAINER="/tmp/${BACKUP_FILE_NAME}"' in script
    assert 'docker cp "${CONTAINER_NAME}:${BACKUP_PATH_CONTAINER}" "${BACKUP_PATH_HOST}"' in script
    assert 'docker exec "${CONTAINER_NAME}" rm -f "${BACKUP_PATH_CONTAINER}"' in script
    assert 'englishbot-db-${SAFE_LABEL}-${TIMESTAMP}.sqlite3' in script
    assert "find \"${BACKUP_DIR}\" -maxdepth 1 -type f -name 'englishbot-db-*.sqlite3'" in script
    assert 'if [[ ${#EXISTING_BACKUPS[@]} -gt "${KEEP_BACKUPS}" ]]' in script
    assert 'englishbot-db-permanent-${SAFE_PERMANENT_LABEL}-${TIMESTAMP}.sqlite3' in script


def test_server_restore_script_restores_backup_and_restarts_bot() -> None:
    script = Path("scripts/restore-runtime-db.sh").read_text(encoding="utf-8")

    assert "Usage: bash scripts/restore-runtime-db.sh" in script
    assert 'docker compose stop "${CONTAINER_NAME}"' in script
    assert 'cp "${BACKUP_PATH}" "${DB_PATH_HOST}"' in script
    assert "docker compose up -d" in script


def test_server_rollback_script_supports_previous_or_explicit_deploy_tag() -> None:
    script = Path("scripts/rollback-docker-app.sh").read_text(encoding="utf-8")

    assert 'CURRENT_RELEASE_FILE="${CURRENT_RELEASE_FILE:-${SHARED_DIR}/deploy/current-release.env}"' in script
    assert 'DEPLOY_TAG_PREFIX="${DEPLOY_TAG_PREFIX:-deploy-v}"' in script
    assert 'git fetch --tags origin' in script
    assert 'TARGET_TAG="${1:-}"' in script
    assert 'git for-each-ref --sort=-creatordate --format=' in script
    assert 'git checkout --detach "${TARGET_TAG}"' in script
    assert 'ENGLISHBOT_GIT_BRANCH="rollback:${TARGET_TAG}"' in script
    assert "docker compose up -d --build" in script


def test_github_actions_workflow_runs_tests_and_deploys_over_ssh() -> None:
    workflow = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert "contents: write" in workflow
    assert "branches:" in workflow
    assert "- main" in workflow
    assert 'python -m pip install -e ".[dev,llm]"' in workflow
    assert "PYTHONPATH=. pytest -q" in workflow
    assert "ssh-keyscan" in workflow
    assert "DEPLOY_SSH_KEY" in workflow
    assert "cd /srv/englishbot/app" in workflow
    assert "git fetch origin ${DEPLOY_BRANCH}" in workflow
    assert "git reset --hard origin/${DEPLOY_BRANCH}" in workflow
    assert "bash scripts/deploy-docker-app.sh" in workflow
    assert "current-release.env" in workflow
    assert "git tag -a" in workflow
    assert "git push origin" in workflow
