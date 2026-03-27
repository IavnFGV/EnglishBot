from pathlib import Path


def test_env_example_includes_content_db_path() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "CONTENT_DB_PATH=" in env_example
    assert "TELEGRAM_UI_LANGUAGE=" in env_example
    assert "LOG_LEVEL=" in env_example
    assert "LOG_FILE_PATH=" in env_example
    assert "LOG_MAX_BYTES=" in env_example
    assert "LOG_BACKUP_COUNT=" in env_example
    assert "PIXABAY_API_KEY=" in env_example
    assert "PIXABAY_BASE_URL=" in env_example


def test_env_example_includes_ollama_prompt_paths() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "OLLAMA_MODEL=" in env_example
    assert "OLLAMA_MODEL_FILE_PATH=" in env_example
    assert "OLLAMA_TIMEOUT_SEC=" in env_example
    assert "OLLAMA_TRACE_FILE_PATH=" in env_example
    assert "OLLAMA_EXTRACTION_MODE=" in env_example
    assert "OLLAMA_EXTRACT_LINE_PROMPT_PATH=" in env_example
    assert "OLLAMA_EXTRACT_TEXT_PROMPT_PATH=" in env_example
    assert "OLLAMA_IMAGE_PROMPT_PATH=" in env_example


def test_main_loads_dotenv_from_repo_root() -> None:
    main_module = Path("src/englishbot/__main__.py").read_text(encoding="utf-8")

    assert 'env_file_path = _REPO_ROOT / ".env"' in main_module
    assert "load_dotenv(env_file_path, override=True)" in main_module
    assert "create_runtime_config_service(env_file_path=env_file_path)" in main_module
    assert "log_max_bytes=settings.log_max_bytes" in main_module
    assert "log_backup_count=settings.log_backup_count" in main_module
    assert "settings.ollama_extraction_mode" in main_module
