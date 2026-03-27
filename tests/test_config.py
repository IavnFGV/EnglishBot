from pathlib import Path

from englishbot.config import Settings, resolve_ollama_extraction_mode, resolve_ollama_model


def test_resolve_ollama_model_prefers_ollama_model(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_PULL_MODEL", "llama3.2:3b")

    assert resolve_ollama_model() == "qwen2.5:7b"


def test_resolve_ollama_model_falls_back_to_legacy_pull_model(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_PULL_MODEL", "llama3.2:3b")

    assert resolve_ollama_model() == "llama3.2:3b"


def test_resolve_ollama_model_uses_default_when_env_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_PULL_MODEL", raising=False)

    assert resolve_ollama_model() == "qwen2.5:7b"


def test_resolve_ollama_extraction_mode_reads_supported_value(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_EXTRACTION_MODE", "full_text")

    assert resolve_ollama_extraction_mode() == "full_text"


def test_resolve_ollama_extraction_mode_falls_back_for_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_EXTRACTION_MODE", "weird")

    assert resolve_ollama_extraction_mode() == "line_by_line"


def test_settings_from_env_reads_ollama_trace_file_path(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("OLLAMA_TRACE_FILE_PATH", "logs/ollama_extraction.jsonl")
    monkeypatch.setenv("TELEGRAM_UI_LANGUAGE", "ru")

    settings = Settings.from_env()

    assert settings.ollama_trace_file_path == Path("logs/ollama_extraction.jsonl")
    assert settings.telegram_ui_language == "ru"
