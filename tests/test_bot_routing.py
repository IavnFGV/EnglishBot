from pathlib import Path

from englishbot.bot import (
    add_words_text_handler,
    build_application,
    chat_member_logger_handler,
    group_text_observer_handler,
    image_review_edit_search_query_handler,
    image_review_next_handler,
    image_review_previous_handler,
    image_review_search_handler,
    raw_update_logger_handler,
    text_answer_handler,
)
from englishbot.config import Settings
from tests.support.config import make_test_config_service


def test_text_answer_handler_is_registered_after_add_words_handler() -> None:
    settings = Settings(
        telegram_token="test-token",
        log_level="INFO",
        editor_user_ids=(),
        content_db_path=Path("test.db"),
        pixabay_api_key="",
        pixabay_base_url="https://pixabay.com/api/",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:7b",
        ollama_temperature=None,
        ollama_top_p=None,
        ollama_num_predict=None,
        ollama_extract_line_prompt_path=Path("prompts/ollama_extract_line_prompt.txt"),
        ollama_image_prompt_path=Path("prompts/ollama_image_prompt_prompt.txt"),
    )
    config_service = make_test_config_service(
        {
            "telegram_token": settings.telegram_token,
            "log_level": settings.log_level,
            "editor_user_ids": settings.editor_user_ids,
            "content_db_path": settings.content_db_path,
            "pixabay_api_key": settings.pixabay_api_key,
            "pixabay_base_url": settings.pixabay_base_url,
            "ollama_base_url": settings.ollama_base_url,
            "ollama_model": settings.ollama_model,
            "ollama_extract_line_prompt_path": settings.ollama_extract_line_prompt_path,
            "ollama_image_prompt_path": settings.ollama_image_prompt_path,
        }
    )
    app = build_application(settings, config_service=config_service)

    assert -1 in app.handlers
    assert 0 in app.handlers
    assert 1 in app.handlers
    assert 2 in app.handlers
    assert any(handler.callback is raw_update_logger_handler for handler in app.handlers[-1])
    assert any(handler.callback is add_words_text_handler for handler in app.handlers[0])
    assert any(handler.callback is chat_member_logger_handler for handler in app.handlers[0])
    assert any(handler.callback is image_review_search_handler for handler in app.handlers[0])
    assert any(handler.callback is image_review_next_handler for handler in app.handlers[0])
    assert any(handler.callback is image_review_previous_handler for handler in app.handlers[0])
    assert any(handler.callback is image_review_edit_search_query_handler for handler in app.handlers[0])
    assert any(handler.callback is text_answer_handler for handler in app.handlers[1])
    assert any(handler.callback is group_text_observer_handler for handler in app.handlers[2])


def test_build_application_uses_injected_config_service() -> None:
    settings = Settings(
        telegram_token="test-token",
        log_level="INFO",
        editor_user_ids=(),
        content_db_path=Path("test-config.db"),
        pixabay_api_key="pixabay-key",
        pixabay_base_url="https://pixabay.example/api/",
        ollama_base_url="http://ollama.example:11434",
        ollama_model="llama3.2:3b",
        ollama_temperature=None,
        ollama_top_p=None,
        ollama_num_predict=None,
        ollama_extract_line_prompt_path=Path("prompts/ollama_extract_line_prompt.txt"),
        ollama_image_prompt_path=Path("prompts/ollama_image_prompt_prompt.txt"),
    )
    config_service = make_test_config_service(
        {
            "telegram_token": settings.telegram_token,
            "log_level": settings.log_level,
            "content_db_path": settings.content_db_path,
            "pixabay_api_key": settings.pixabay_api_key,
            "pixabay_base_url": settings.pixabay_base_url,
            "ollama_base_url": settings.ollama_base_url,
            "ollama_model": settings.ollama_model,
            "comfyui_base_url": "http://comfy.example:8188",
        }
    )

    app = build_application(settings, config_service=config_service)

    assert app.bot_data["config_service"] is config_service
    assert app.bot_data["smart_parsing_gateway"]._extraction_client.base_url == "http://ollama.example:11434"
    assert app.bot_data["image_generation_gateway"]._client.base_url == "http://comfy.example:8188"
