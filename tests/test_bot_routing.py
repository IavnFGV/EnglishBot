from pathlib import Path

from englishbot.bot import (
    add_words_text_handler,
    build_application,
    chat_member_logger_handler,
    game_mode_placeholder_callback_handler,
    goal_text_handler,
    group_text_observer_handler,
    image_review_edit_search_query_handler,
    image_review_next_handler,
    image_review_previous_handler,
    image_review_search_handler,
    raw_update_logger_handler,
    text_answer_handler,
    version_handler,
)
from englishbot.config import Settings
from englishbot.image_generation.smart_generation import DisabledImageGenerationGateway
from englishbot.importing.smart_parsing import DisabledSmartLessonParsingGateway
from tests.support.config import make_test_config_service


def test_build_application_delegates_to_telegram_bootstrap(monkeypatch) -> None:
    import englishbot.bot as bot_module
    from englishbot.telegram import bootstrap as bootstrap_module

    settings = Settings(
        telegram_token="delegated-token",
        log_level="INFO",
        content_db_path=Path("delegated.db"),
    )
    config_service = make_test_config_service(
        {
            "telegram_token": settings.telegram_token,
            "log_level": settings.log_level,
            "content_db_path": settings.content_db_path,
        }
    )
    expected_application = object()
    captured: dict[str, object] = {}

    def fake_build_application(passed_settings, *, config_service):
        captured["settings"] = passed_settings
        captured["config_service"] = config_service
        return expected_application

    monkeypatch.setattr(bootstrap_module, "build_application", fake_build_application)

    result = bot_module.build_application(settings, config_service=config_service)

    assert result is expected_application
    assert captured == {
        "settings": settings,
        "config_service": config_service,
    }


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
    assert any(handler.callback is version_handler for handler in app.handlers[0])
    assert any(handler.callback is chat_member_logger_handler for handler in app.handlers[0])
    assert any(handler.callback is game_mode_placeholder_callback_handler for handler in app.handlers[0])
    assert any(handler.callback is image_review_search_handler for handler in app.handlers[0])
    assert any(handler.callback is image_review_next_handler for handler in app.handlers[0])
    assert any(handler.callback is image_review_previous_handler for handler in app.handlers[0])
    assert any(handler.callback is image_review_edit_search_query_handler for handler in app.handlers[0])
    assert any(handler.callback is text_answer_handler for handler in app.handlers[1])
    assert any(handler.callback is group_text_observer_handler for handler in app.handlers[2])
    add_words_index = next(
        index for index, handler in enumerate(app.handlers[0]) if handler.callback is add_words_text_handler
    )
    goal_text_index = next(
        index for index, handler in enumerate(app.handlers[0]) if handler.callback is goal_text_handler
    )
    assert add_words_index < goal_text_index


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


def test_build_application_bootstraps_user_roles_into_repository() -> None:
    settings = Settings(
        telegram_token="test-token",
        log_level="INFO",
        admin_user_ids=(100,),
        editor_user_ids=(42,),
        content_db_path=Path("test-roles.db"),
        pixabay_api_key="",
        pixabay_base_url="https://pixabay.com/api/",
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
        }
    )

    app = build_application(settings, config_service=config_service)

    memberships = app.bot_data["telegram_user_role_repository"].list_memberships()

    assert memberships["admin"] == frozenset({100})
    assert memberships["editor"] == frozenset({42})


def test_build_application_uses_disabled_gateways_when_ai_is_turned_off() -> None:
    settings = Settings(
        telegram_token="test-token",
        log_level="INFO",
        editor_user_ids=(),
        content_db_path=Path("test-disabled-ai.db"),
        pixabay_api_key="",
        pixabay_base_url="https://pixabay.com/api/",
        ollama_enabled=False,
        ollama_base_url="http://ollama.example:11434",
        ollama_model="llama3.2:3b",
        ollama_temperature=None,
        ollama_top_p=None,
        ollama_num_predict=None,
        ollama_extract_line_prompt_path=Path("prompts/ollama_extract_line_prompt.txt"),
        ollama_image_prompt_path=Path("prompts/ollama_image_prompt_prompt.txt"),
        comfyui_enabled=False,
    )
    config_service = make_test_config_service(
        {
            "telegram_token": settings.telegram_token,
            "log_level": settings.log_level,
            "content_db_path": settings.content_db_path,
            "ollama_enabled": False,
            "comfyui_enabled": False,
        }
    )

    app = build_application(settings, config_service=config_service)

    assert isinstance(app.bot_data["smart_parsing_gateway"], DisabledSmartLessonParsingGateway)
    assert isinstance(app.bot_data["image_generation_gateway"], DisabledImageGenerationGateway)
    assert app.bot_data["smart_parsing_gateway"].check_availability().is_available is False
    assert app.bot_data["image_generation_gateway"].check_availability().is_available is False
