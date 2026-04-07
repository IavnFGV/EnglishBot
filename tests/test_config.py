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


def test_settings_from_config_service_reads_disabled_ai_flags(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\n"
        "OLLAMA_ENABLED=false\n"
        "COMFYUI_ENABLED=false\n",
        encoding="utf-8",
    )
    service = create_runtime_config_service(env_file_path=env_file, environ={})

    settings = Settings.from_config_service(service)

    assert settings.ollama_enabled is False
    assert settings.comfyui_enabled is False


def test_settings_from_config_service_reads_tts_settings(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\n"
        "TTS_SERVICE_ENABLED=true\n"
        "TTS_SERVICE_BASE_URL=http://englishbot-tts:8090\n"
        "TTS_SERVICE_TIMEOUT_SEC=22\n"
        "TTS_HOST=0.0.0.0\n"
        "TTS_PORT=8091\n"
        "TTS_CACHE_DIR=data/tts-cache\n"
        "TTS_VOICE_DIR=data/tts-voices\n"
        "TTS_VOICE_NAME=en_GB-alan-medium\n"
        "TTS_VOICE_VARIANTS=en_US-libritts-high, en_GB-cori-high\n"
        "TTS_VOICE_MODEL_PATH=data/tts-voices/custom.onnx\n"
        "TTS_VOICE_CONFIG_PATH=data/tts-voices/custom.onnx.json\n",
        encoding="utf-8",
    )
    service = create_runtime_config_service(env_file_path=env_file, environ={})

    settings = Settings.from_config_service(service)

    assert settings.tts_service_enabled is True
    assert settings.tts_service_base_url == "http://englishbot-tts:8090"
    assert settings.tts_service_timeout_sec == 22
    assert settings.tts_host == "0.0.0.0"
    assert settings.tts_port == 8091
    assert settings.tts_cache_dir == Path("data/tts-cache")
    assert settings.tts_voice_dir == Path("data/tts-voices")
    assert settings.tts_voice_name == "en_GB-alan-medium"
    assert settings.tts_voice_variants == ("en_US-libritts-high", "en_GB-cori-high")
    assert settings.tts_voice_model_path == Path("data/tts-voices/custom.onnx")
    assert settings.tts_voice_config_path == Path("data/tts-voices/custom.onnx.json")


def test_settings_exposes_grouped_capability_views(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\n"
        "PIXABAY_API_KEY=pixabay-key\n"
        "PIXABAY_BASE_URL=https://pixabay.local/api/\n"
        "OLLAMA_ENABLED=true\n"
        "OLLAMA_BASE_URL=http://ollama.local:11434\n"
        "OLLAMA_MODEL=llama3.2:3b\n"
        "TTS_SERVICE_ENABLED=true\n"
        "TTS_SERVICE_BASE_URL=http://tts.local:8090\n"
        "TTS_VOICE_NAME=en_GB-alan-medium\n",
        encoding="utf-8",
    )
    service = create_runtime_config_service(env_file_path=env_file, environ={})

    settings = Settings.from_config_service(service)

    assert settings.ai_text.enabled is True
    assert settings.ai_text.base_url == "http://ollama.local:11434"
    assert settings.ai_text.model == "llama3.2:3b"
    assert settings.ai_images.enabled is True
    assert settings.ai_images.pixabay_api_key == "pixabay-key"
    assert settings.ai_images.pixabay_base_url == "https://pixabay.local/api/"
    assert settings.tts.enabled is True
    assert settings.tts.service_base_url == "http://tts.local:8090"
    assert settings.tts.voice_name == "en_GB-alan-medium"


def test_settings_from_config_service_reads_admin_bootstrap_secret(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\n"
        "ADMIN_BOOTSTRAP_SECRET=recover-me\n",
        encoding="utf-8",
    )
    service = create_runtime_config_service(env_file_path=env_file, environ={})

    settings = Settings.from_config_service(service)

    assert settings.admin_bootstrap_secret == "recover-me"


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
