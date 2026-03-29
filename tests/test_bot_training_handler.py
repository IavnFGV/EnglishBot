from types import SimpleNamespace

import pytest

from englishbot import bot
from englishbot.bot import start_handler, text_answer_handler


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


class _IdleService:
    def get_active_session(self, *, user_id: int):  # noqa: ARG002
        return None

    def list_topics(self):
        return [SimpleNamespace(id="weather", title="Weather")]


class _RecordingTelegramUserLoginRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str | None]] = []

    def record(self, *, user_id: int, username: str | None) -> None:
        self.calls.append((user_id, username))


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


@pytest.mark.anyio
async def test_start_handler_records_telegram_username(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_views: list[object] = []

    async def _fake_send_telegram_view(message, view):  # noqa: ARG001
        sent_views.append(view)

    monkeypatch.setattr(bot, "send_telegram_view", _fake_send_telegram_view)

    message = SimpleNamespace()
    user_login_repository = _RecordingTelegramUserLoginRepository()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=321, username="local_test_user", language_code="ru"),
    )
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "training_service": _IdleService(),
                "telegram_user_login_repository": user_login_repository,
                "telegram_ui_language": "en",
                "editor_user_ids": set(),
                "admin_user_ids": set(),
            }
        ),
    )

    await start_handler(update, context)  # type: ignore[arg-type]

    assert user_login_repository.calls == [(321, "local_test_user")]
    assert len(sent_views) == 2
