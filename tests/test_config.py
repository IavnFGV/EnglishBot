from pathlib import Path

import pytest

from englishbot.config import Settings, create_runtime_config_service, resolve_ollama_extraction_mode, resolve_ollama_model
from englishbot.image_generation.clients import ComfyUIImageGenerationClient
from englishbot.image_generation.pixabay import PixabayImageSearchClient
from englishbot.importing.clients import OllamaLessonExtractionClient
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from tests.support.config import make_test_config_service


def test_resolve_ollama_model_prefers_primary_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_PULL_MODEL", "llama3.2:3b")

    assert resolve_ollama_model() == "qwen2.5:7b"


def test_resolve_ollama_model_falls_back_to_legacy_pull_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_PULL_MODEL", "llama3.2:3b")

    assert resolve_ollama_model() == "llama3.2:3b"


def test_resolve_ollama_extraction_mode_falls_back_for_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_EXTRACTION_MODE", "weird")

    assert resolve_ollama_extraction_mode() == "line_by_line"


def test_runtime_config_service_reads_file_and_env_with_env_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OLLAMA_MODEL=qwen2.5:7b\n"
        "OLLAMA_TIMEOUT_SEC=120\n"
        "EDITOR_USER_IDS=1,2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OLLAMA_TIMEOUT_SEC", "45")

    service = create_runtime_config_service(env_file_path=env_file)

    assert service.get_str("ollama_model") == "qwen2.5:7b"
    assert service.get_int("ollama_timeout_sec") == 45
    assert service.get("editor_user_ids") == (1, 2)


def test_runtime_config_service_can_persist_updates_to_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OLLAMA_MODEL=qwen2.5:7b\n", encoding="utf-8")
    service = create_runtime_config_service(env_file_path=env_file, environ={})

    service.set("ollama_model", "llama3.2:3b", persist=True)
    service.set("ollama_extract_text_prompt_path", Path("prompts/custom.txt"), persist=True)
    service.reload()

    assert service.get_str("ollama_model") == "llama3.2:3b"
    assert service.get_path("ollama_extract_text_prompt_path") == Path("prompts/custom.txt")
    assert "OLLAMA_MODEL=llama3.2:3b" in env_file.read_text(encoding="utf-8")


def test_settings_from_config_service_reads_centralized_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\n"
        "OLLAMA_TRACE_FILE_PATH=logs/ollama_extraction.jsonl\n"
        "TELEGRAM_UI_LANGUAGE=ru\n",
        encoding="utf-8",
    )
    service = create_runtime_config_service(env_file_path=env_file, environ={})

    settings = Settings.from_config_service(service)

    assert settings.telegram_token == "test-token"
    assert settings.ollama_trace_file_path == Path("logs/ollama_extraction.jsonl")
    assert settings.telegram_ui_language == "ru"


def test_clients_can_read_defaults_from_injected_config_service(tmp_path: Path) -> None:
    service = make_test_config_service(
        {
            "ollama_model": "llama3.2:3b",
            "ollama_base_url": "http://ollama.local:11434",
            "ollama_extract_text_prompt_path": Path("prompts/custom_extract.txt"),
            "comfyui_base_url": "http://comfy.local:8188",
            "comfyui_checkpoint_name": "custom-checkpoint.safetensors",
            "pixabay_api_key": "pixabay-key",
            "pixabay_base_url": "https://pixabay.local/api/",
        }
    )

    extraction_client = OllamaLessonExtractionClient(config_service=service)
    image_client = ComfyUIImageGenerationClient(config_service=service)
    pixabay_client = PixabayImageSearchClient(config_service=service)

    assert extraction_client.base_url == "http://ollama.local:11434"
    assert extraction_client._resolved_model() == "llama3.2:3b"
    assert extraction_client._extract_text_prompt_path == Path("prompts/custom_extract.txt")
    assert image_client.base_url == "http://comfy.local:8188"
    assert image_client._checkpoint_name == "custom-checkpoint.safetensors"
    assert pixabay_client._api_key == "pixabay-key"
    assert pixabay_client._base_url == "https://pixabay.local/api"


def test_clients_require_explicit_required_values_without_config_service() -> None:
    with pytest.raises(ValueError, match="ollama_model"):
        OllamaLessonExtractionClient()

    with pytest.raises(ValueError, match="ollama_model"):
        OllamaImagePromptEnricher()

    with pytest.raises(ValueError, match="comfyui_base_url"):
        ComfyUIImageGenerationClient()

    with pytest.raises(ValueError, match="pixabay_api_key"):
        PixabayImageSearchClient()


def test_clients_use_explicit_values_without_reading_runtime_config_service() -> None:
    extraction_client = OllamaLessonExtractionClient(
        model="explicit-model",
        base_url="http://explicit-ollama:11434",
    )
    prompt_enricher = OllamaImagePromptEnricher(
        model="explicit-model",
        base_url="http://explicit-ollama:11434",
    )
    image_client = ComfyUIImageGenerationClient(
        base_url="http://explicit-comfy:8188",
    )
    pixabay_client = PixabayImageSearchClient(api_key="explicit-key")

    assert extraction_client.base_url == "http://explicit-ollama:11434"
    assert extraction_client._resolved_model() == "explicit-model"
    assert prompt_enricher._resolved_model() == "explicit-model"
    assert image_client.base_url == "http://explicit-comfy:8188"
    assert image_client._checkpoint_name == "dreamshaper_8.safetensors"
    assert pixabay_client._api_key == "explicit-key"
    assert pixabay_client._base_url == "https://pixabay.com/api"
