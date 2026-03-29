from pathlib import Path


def test_switch_devcontainer_profile_supports_noai() -> None:
    script = Path("scripts/switch-devcontainer-profile.sh").read_text(encoding="utf-8")

    assert 'noai)' in script
    assert 'devcontainer.noai.json' in script
    assert 'Usage: $0 [cpu|gpu|noai]' in script


def test_noai_devcontainer_disables_local_ai_build_and_startup() -> None:
    config = Path(".devcontainer/devcontainer.noai.json").read_text(encoding="utf-8")

    assert '"OLLAMA_INSTALL": "0"' in config
    assert '"COMFYUI_INSTALL": "0"' in config
    assert '"PYTHON_EXTRAS": "dev"' in config
    assert 'bash .devcontainer/start-ollama.sh' not in config
    assert 'bash .devcontainer/start-comfyui.sh' not in config
    assert "pip install -e .[dev] --no-deps" in config
    assert "pip install -e .[dev,llm] --no-deps" not in config


def test_cpu_and_gpu_profiles_load_local_ai_switch_env_file() -> None:
    cpu = Path(".devcontainer/devcontainer.cpu.json").read_text(encoding="utf-8")
    gpu = Path(".devcontainer/devcontainer.gpu.json").read_text(encoding="utf-8")

    assert '${localWorkspaceFolder}/.devcontainer/local-ai.env' in cpu
    assert '${localWorkspaceFolder}/.devcontainer/local-ai.env' in gpu


def test_switch_local_ai_mode_script_uses_on_off_presets() -> None:
    script = Path("scripts/switch-local-ai-mode.sh").read_text(encoding="utf-8")

    assert 'mode="${1:-off}"' in script
    assert 'local-ai.on.env' in script
    assert 'local-ai.off.env' in script
    assert 'Usage: $0 [on|off]' in script


def test_local_ai_off_preset_disables_autostart_and_model_pull() -> None:
    env_content = Path(".devcontainer/local-ai.off.env").read_text(encoding="utf-8")

    assert 'OLLAMA_AUTOSTART=0' in env_content
    assert 'COMFYUI_AUTOSTART=0' in env_content
    assert 'OLLAMA_PULL_MODEL=' in env_content


def test_fix_container_perms_skips_missing_comfyui_dirs() -> None:
    script = Path(".devcontainer/fix-container-perms.sh").read_text(encoding="utf-8")

    assert 'ensure_owned_dir_if_exists()' in script
    assert 'ensure_owned_dir_if_exists "/opt/ComfyUI"' in script
    assert 'ensure_owned_dir_if_exists "/opt/ComfyUI/output"' in script


def test_dockerfile_uses_profile_controlled_python_extras() -> None:
    dockerfile = Path(".devcontainer/Dockerfile").read_text(encoding="utf-8")

    assert "ARG PYTHON_EXTRAS=dev,llm" in dockerfile
    assert 'python -m pip install ".[${PYTHON_EXTRAS}]"' in dockerfile
