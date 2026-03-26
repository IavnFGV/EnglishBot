from pathlib import Path

from englishbot.bot import (
    add_words_text_handler,
    build_application,
    chat_member_logger_handler,
    group_text_observer_handler,
    raw_update_logger_handler,
    text_answer_handler,
)
from englishbot.config import Settings


def test_text_answer_handler_is_registered_after_add_words_handler() -> None:
    app = build_application(
        Settings(
            telegram_token="test-token",
            log_level="INFO",
            editor_user_ids=(),
            content_db_path=Path("test.db"),
            ollama_base_url="http://127.0.0.1:11434",
            ollama_model="qwen2.5:7b",
            ollama_temperature=None,
            ollama_top_p=None,
            ollama_num_predict=None,
            ollama_extract_line_prompt_path=Path("prompts/ollama_extract_line_prompt.txt"),
            ollama_image_prompt_path=Path("prompts/ollama_image_prompt_prompt.txt"),
        )
    )

    assert -1 in app.handlers
    assert 0 in app.handlers
    assert 1 in app.handlers
    assert 2 in app.handlers
    assert any(handler.callback is raw_update_logger_handler for handler in app.handlers[-1])
    assert any(handler.callback is add_words_text_handler for handler in app.handlers[0])
    assert any(handler.callback is chat_member_logger_handler for handler in app.handlers[0])
    assert any(handler.callback is text_answer_handler for handler in app.handlers[1])
    assert any(handler.callback is group_text_observer_handler for handler in app.handlers[2])
