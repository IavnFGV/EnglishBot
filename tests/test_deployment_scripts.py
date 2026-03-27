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
    assert 'mkdir -p "${APP_ROOT}/shared/content/custom"' in script
    assert 'mkdir -p "${APP_ROOT}/shared/logs"' in script
    assert 'touch "${APP_ROOT}/shared/.env"' in script


def test_production_dockerfile_installs_bot_runtime_and_demo_content() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in dockerfile
    assert "fonts-dejavu-core" in dockerfile
    assert "python -m pip install -e '.[llm]'" in dockerfile
    assert "COPY content/demo ./content/demo" in dockerfile
    assert 'CMD ["python", "-m", "englishbot"]' in dockerfile


def test_docker_compose_mounts_persistent_runtime_directories() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "/srv/englishbot/shared/.env:/app/.env:ro" in compose
    assert "/srv/englishbot/shared/data:/app/data" in compose
    assert "/srv/englishbot/shared/assets:/app/assets" in compose
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
    assert 'DEPLOY_BRANCH="${DEPLOY_BRANCH:-master}"' in script
    assert 'git fetch origin "${DEPLOY_BRANCH}"' in script
    assert 'git reset --hard "origin/${DEPLOY_BRANCH}"' in script
    assert "docker compose up -d --build" in script


def test_github_actions_workflow_runs_tests_and_deploys_over_ssh() -> None:
    workflow = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert "branches:" in workflow
    assert "- master" in workflow
    assert 'python -m pip install -e ".[dev,llm]"' in workflow
    assert "PYTHONPATH=. pytest -q" in workflow
    assert "ssh-keyscan" in workflow
    assert "DEPLOY_SSH_KEY" in workflow
    assert "cd /srv/englishbot/app" in workflow
    assert "git fetch origin ${DEPLOY_BRANCH}" in workflow
    assert "git reset --hard origin/${DEPLOY_BRANCH}" in workflow
    assert "bash scripts/deploy-docker-app.sh" in workflow
