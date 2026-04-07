from types import SimpleNamespace

import pytest

from englishbot.telegram.game_mode import finish_game_session, game_repeat_handler
from englishbot.presentation.telegram_game_ui import game_result_keyboard


class _FakeMessage:
    def __init__(self) -> None:
        self.text_replies: list[tuple[str, object | None]] = []
        self.from_user = SimpleNamespace(id=123)
        self.chat_id = 1
        self.message_id = 10

    async def reply_text(self, text: str, reply_markup=None, parse_mode=None):  # noqa: ARG002
        self.text_replies.append((text, reply_markup))
        return SimpleNamespace(message_id=11, chat_id=self.chat_id)


class _FakeQuery:
    def __init__(self, message: _FakeMessage) -> None:
        self.message = message
        self.answers = 0
        self.edits: list[str] = []

    async def answer(self, text=None, show_alert=None):  # noqa: ARG002
        self.answers += 1

    async def edit_message_text(self, text: str, reply_markup=None, parse_mode=None):  # noqa: ARG002
        self.edits.append(text)


def test_game_result_keyboard_uses_expected_callbacks() -> None:
    markup = game_result_keyboard(tg=lambda key, **kwargs: key, language="en")

    rows = markup.inline_keyboard
    assert rows[0][0].callback_data == "game:next_round"
    assert rows[1][0].callback_data == "game:repeat"
    assert rows[2][0].callback_data == "session:restart"


@pytest.mark.anyio
async def test_game_repeat_handler_builds_start_menu_without_bot_start_menu_view(monkeypatch) -> None:
    message = _FakeMessage()
    query = _FakeQuery(message)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(user_data={"game_mode_state": {"active": True}})

    sent_views: list[object] = []

    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._learner_assignment_launch_summary_use_case",
        lambda context: SimpleNamespace(execute=lambda user_id: [SimpleNamespace(kind="homework")]),  # noqa: ARG005
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._render_start_menu_text",
        lambda **kwargs: "Start menu body",
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.start_menu_keyboard",
        lambda **kwargs: "markup",
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._assignment_guide_web_app_url",
        lambda context, user: None,  # noqa: ARG005
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._admin_web_app_url",
        lambda context, user: None,  # noqa: ARG005
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._telegram_ui_language",
        lambda context, user: "en",  # noqa: ARG005
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._pop_user_data",
        lambda context, key, default=None: context.user_data.pop(key, default),  # noqa: ARG005
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._clear_medium_task_state",
        lambda context: None,
    )
    async def _fake_send_telegram_view(message, view):  # noqa: ANN001
        sent_views.append(view)

    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module.send_telegram_view",
        _fake_send_telegram_view,
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._tg",
        lambda key, **kwargs: key,
    )

    await game_repeat_handler(update, context)  # type: ignore[arg-type]

    assert query.answers == 1
    assert query.edits == ["start_menu_title"]
    assert sent_views and sent_views[0].text == "Start menu body"
    assert sent_views[0].reply_markup == "markup"


@pytest.mark.anyio
async def test_finish_game_session_uses_presentation_game_result_keyboard(monkeypatch) -> None:
    message = _FakeMessage()
    context = SimpleNamespace(user_data={"game_mode_state": {"active": True, "topic_id": "weather", "mode_value": "easy"}})

    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._game_state",
        lambda context: context.user_data["game_mode_state"],
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._content_store",
        lambda context: SimpleNamespace(  # noqa: ARG005
            add_game_stars=lambda user_id, stars: 17,  # noqa: ARG005
            update_game_streak=lambda user_id, played_at: 3,  # noqa: ARG005
        ),
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._GAME_CHEST_REWARDS",
        (2,),
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._telegram_ui_language",
        lambda context, user: "en",  # noqa: ARG005
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._tg",
        lambda key, **kwargs: key,
    )
    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._set_user_data",
        lambda context, key, value: context.user_data.__setitem__(key, value),
    )

    flushed: list[int] = []

    async def _fake_flush_pending_notifications_for_user(context, user_id):  # noqa: ANN001
        flushed.append(user_id)

    monkeypatch.setattr(
        "englishbot.telegram.game_mode.bot_module._flush_pending_notifications_for_user",
        _fake_flush_pending_notifications_for_user,
    )

    outcome = SimpleNamespace(summary=SimpleNamespace(total_questions=5))
    await finish_game_session(message, outcome, context)  # type: ignore[arg-type]

    assert message.text_replies
    _, reply_markup = message.text_replies[-1]
    assert reply_markup.inline_keyboard[0][0].callback_data == "game:next_round"
    assert reply_markup.inline_keyboard[1][0].callback_data == "game:repeat"
    assert flushed == [123]
