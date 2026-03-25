from englishbot.bot import add_words_text_handler, build_application, text_answer_handler
from englishbot.config import Settings


def test_text_answer_handler_is_registered_after_add_words_handler() -> None:
    app = build_application(
        Settings(
            telegram_token="test-token",
            log_level="INFO",
            editor_user_ids=(),
            ollama_base_url="http://127.0.0.1:11434",
            ollama_model="llama3.2:3b",
        )
    )

    assert 0 in app.handlers
    assert 1 in app.handlers
    assert any(handler.callback is add_words_text_handler for handler in app.handlers[0])
    assert any(handler.callback is text_answer_handler for handler in app.handlers[1])
