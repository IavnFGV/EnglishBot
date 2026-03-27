from types import SimpleNamespace

import pytest

from englishbot.bot import text_answer_handler


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str, reply_markup=None, parse_mode=None) -> None:  # noqa: ARG002
        self.replies.append(text)


class _ExplodingService:
    def get_active_session(self, *, user_id: int):  # noqa: ARG002
        return None

    def submit_answer(self, *, user_id: int, answer: str):  # noqa: ARG002
        raise AssertionError("submit_answer must not be called when there is no active session")


@pytest.mark.anyio
async def test_text_answer_handler_clears_stale_awaiting_state_when_session_missing() -> None:
    message = _FakeMessage("рюкзак")
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123, language_code="ru"),
    )
    context = SimpleNamespace(
        user_data={"awaiting_text_answer": True},
        application=SimpleNamespace(
            bot_data={
                "training_service": _ExplodingService(),
                "telegram_ui_language": "en",
            }
        ),
    )

    await text_answer_handler(update, context)  # type: ignore[arg-type]

    assert context.user_data["awaiting_text_answer"] is False
    assert message.replies == ["Нет активной сессии. Отправьте /start, чтобы начать."]
