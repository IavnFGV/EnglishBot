from pathlib import Path


def test_env_example_includes_content_db_path() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "CONTENT_DB_PATH=" in env_example


def test_env_example_includes_ollama_prompt_paths() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "OLLAMA_EXTRACT_LINE_PROMPT_PATH=" in env_example
    assert "OLLAMA_IMAGE_PROMPT_PATH=" in env_example


def test_main_loads_dotenv_from_repo_root() -> None:
    main_module = Path("src/englishbot/__main__.py").read_text(encoding="utf-8")

    assert 'load_dotenv(_REPO_ROOT / ".env")' in main_module
