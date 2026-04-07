from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from englishbot.capabilities.ai_images import (
    log_ai_image_capability_settings,
    register_ai_image_capability,
)
from englishbot.capabilities.ai_text import (
    log_ai_text_capability_settings,
    register_ai_text_capability,
)
from englishbot.capabilities.tts import (
    log_tts_capability_settings,
    register_tts_capability,
)
from englishbot.config import Settings, create_runtime_config_service


def test_log_ai_text_capability_settings_logs_own_config(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        telegram_token="token",
        log_level="INFO",
        ollama_enabled=True,
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:7b",
        ollama_model_file_path=Path("models/model.gguf"),
        ollama_timeout_sec=120,
        ollama_trace_file_path=Path("logs/ollama-trace.log"),
        ollama_extraction_mode="line_by_line",
        ollama_temperature=0.2,
        ollama_top_p=0.8,
        ollama_num_predict=512,
        ollama_extract_line_prompt_path=Path("prompts/line.txt"),
        ollama_extract_text_prompt_path=Path("prompts/text.txt"),
        ollama_image_prompt_path=Path("prompts/image.txt"),
    )

    caplog.set_level(logging.INFO, logger="englishbot.capabilities.ai_text")

    log_ai_text_capability_settings(settings=settings)

    assert "AI text capability settings" in caplog.text
    assert "enabled=True" in caplog.text
    assert "model=qwen2.5:7b" in caplog.text
    assert "base_url=http://127.0.0.1:11434" in caplog.text
    assert "image_prompt_path=prompts/image.txt" in caplog.text


def test_log_ai_image_capability_settings_logs_own_config(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        telegram_token="token",
        log_level="INFO",
        comfyui_enabled=True,
        pixabay_api_key="secret",
        pixabay_base_url="https://pixabay.example/api/",
    )

    caplog.set_level(logging.INFO, logger="englishbot.capabilities.ai_images")

    log_ai_image_capability_settings(settings=settings)

    assert "AI image capability settings" in caplog.text
    assert "enabled=True" in caplog.text
    assert "pixabay_base_url=https://pixabay.example/api/" in caplog.text
    assert "pixabay_configured=True" in caplog.text


def test_log_tts_capability_settings_logs_own_config(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        telegram_token="token",
        log_level="INFO",
        tts_service_enabled=True,
        tts_service_base_url="http://englishbot-tts:8090",
        tts_service_timeout_sec=22,
        tts_voice_name="en_US-lessac-medium",
        tts_voice_variants=("en_GB-alan-medium",),
    )

    caplog.set_level(logging.INFO, logger="englishbot.capabilities.tts")

    log_tts_capability_settings(settings=settings)

    assert "TTS capability settings" in caplog.text
    assert "enabled=True" in caplog.text
    assert "service_base_url=http://englishbot-tts:8090" in caplog.text
    assert "voice_name=en_US-lessac-medium" in caplog.text


def test_register_capabilities_emit_startup_logs(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        telegram_token="token",
        log_level="INFO",
        content_db_path=tmp_path / "content.db",
        ollama_enabled=False,
        comfyui_enabled=False,
        tts_service_enabled=False,
    )
    config_service = create_runtime_config_service(
        environ={"TELEGRAM_BOT_TOKEN": "token", "LOG_LEVEL": "INFO"},
    )
    app = SimpleNamespace(bot_data={})
    content_store = SimpleNamespace()

    caplog.set_level(logging.INFO)

    register_ai_text_capability(app=app, settings=settings, config_service=config_service)
    register_ai_image_capability(
        app=app,
        settings=settings,
        config_service=config_service,
        content_store=content_store,
    )
    register_tts_capability(app=app, settings=settings)

    assert "AI text capability settings enabled=False" in caplog.text
    assert "AI image capability settings enabled=False" in caplog.text
    assert "TTS capability settings enabled=False" in caplog.text
