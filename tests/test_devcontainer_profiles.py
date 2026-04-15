from pathlib import Path
import tomllib


def test_switch_devcontainer_profile_supports_default_profile() -> None:
    script = Path("scripts/switch-devcontainer-profile.sh").read_text(encoding="utf-8")

    assert 'default)' in script
    assert 'devcontainer.default.json' in script
    assert 'status)' in script
    assert 'show_profile()' in script
    assert 'Usage: $0 [default|cpu|gpu|status]' in script


def test_devcontainer_readme_documents_active_and_named_profiles() -> None:
    readme = Path(".devcontainer/README.md").read_text(encoding="utf-8")

    assert "devcontainer.json" in readme
    assert "devcontainer.default.json" in readme
    assert "devcontainer.cpu.json" in readme
    assert "devcontainer.gpu.json" in readme
    assert "switch-devcontainer-profile.sh status" in readme


def test_default_devcontainer_disables_local_ai_build_and_startup() -> None:
    config = Path(".devcontainer/devcontainer.default.json").read_text(encoding="utf-8")

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

    assert '${localWorkspaceFolder}/.devcontainer/local-ai.on.env' in cpu
    assert '${localWorkspaceFolder}/.devcontainer/local-ai.on.env' in gpu


def test_all_devcontainer_profiles_mount_host_ssh_directory_read_only() -> None:
    expected_mount = 'source=${localEnv:HOME}/.ssh,target=/home/vscode/.ssh,type=bind,readonly'

    for path in (
        ".devcontainer/devcontainer.json",
        ".devcontainer/devcontainer.cpu.json",
        ".devcontainer/devcontainer.gpu.json",
        ".devcontainer/devcontainer.default.json",
    ):
        config = Path(path).read_text(encoding="utf-8")
        assert expected_mount in config


def test_devcontainer_keeps_explicit_local_ai_on_preset_for_cpu_and_gpu_profiles() -> None:
    env_content = Path(".devcontainer/local-ai.on.env").read_text(encoding="utf-8")

    assert 'OLLAMA_AUTOSTART=1' in env_content
    assert 'COMFYUI_AUTOSTART=1' in env_content
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


def test_pixabay_runtime_dependency_is_installed_without_llm_extra() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert "requests>=2.32.0,<3.0.0" in pyproject["project"]["dependencies"]
