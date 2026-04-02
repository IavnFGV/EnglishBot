import asyncio
from types import SimpleNamespace

import pytest

from englishbot.application.homework_progress_use_cases import (
    AssignmentLaunchView,
    AssignmentSessionKind,
    GoalProgressView,
)
from englishbot import bot
from englishbot.bot import (
    choice_answer_handler,
    _process_answer,
    _send_question,
    clear_user_handler,
    makeadmin_handler,
    start_handler,
    text_answer_handler,
)
from englishbot.domain.models import (
    CheckResult,
    Goal,
    GoalPeriod,
    GoalStatus,
    GoalType,
    SessionItem,
    SessionSummary,
    TrainingMode,
    TrainingQuestion,
    TrainingSession,
)


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []
        self.reply_markup_calls: list[object | None] = []
        self.reply_audio_calls: list[object] = []
        self.chat_id = 1
        self.message_id = 10

    async def reply_text(self, text: str, reply_markup=None, parse_mode=None) -> None:  # noqa: ARG002
        self.replies.append(text)
        self.reply_markup_calls.append(reply_markup)
        self.message_id += 1
        return SimpleNamespace(message_id=self.message_id, chat_id=self.chat_id)

    async def reply_audio(self, audio, **kwargs):  # noqa: ANN001, ARG002
        self.reply_audio_calls.append(audio)
        self.message_id += 1
        return SimpleNamespace(message_id=self.message_id, chat_id=self.chat_id)


class _FakePhotoCapableMessage(_FakeMessage):
    async def reply_photo(self, photo, caption=None, reply_markup=None, parse_mode=None):  # noqa: ARG002
        return SimpleNamespace(message_id=self.message_id + 1, chat_id=self.chat_id)


class _FakeEditableMessage(_FakeMessage):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.edits: list[str] = []
        self.edit_reply_markup_calls: list[object | None] = []

    async def edit_caption(self, caption: str, reply_markup=None, parse_mode=None) -> None:  # noqa: ARG002
        self.edits.append(caption)
        self.edit_reply_markup_calls.append(reply_markup)


class _FakeQuery:
    def __init__(self, data: str, message: _FakeEditableMessage, *, user_id: int = 123) -> None:
        self.data = data
        self.message = message
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = 0
        self.answer_payloads: list[tuple[object | None, object | None]] = []
        self.edit_calls: list[tuple[str, object | None, str | None]] = []

    async def answer(self, text=None, show_alert=None) -> None:  # noqa: ARG002
        self.answers += 1
        self.answer_payloads.append((text, show_alert))

    async def edit_message_text(self, text: str, reply_markup=None, parse_mode=None) -> None:
        self.edit_calls.append((text, reply_markup, parse_mode))
        self.message.edits.append(text)
        self.message.edit_reply_markup_calls.append(reply_markup)


class _FakeCallbackMessage(_FakeMessage):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.from_user = SimpleNamespace(id=999, is_bot=True, language_code="en")


class _FakeTelegramFlowMessageRepository:
    def __init__(self) -> None:
        self.messages: list[SimpleNamespace] = []

    def track(self, *, flow_id: str, chat_id: int, message_id: int, tag: str) -> None:
        self.messages = [
            item
            for item in self.messages
            if not (item.flow_id == flow_id and item.chat_id == chat_id and item.message_id == message_id)
        ]
        self.messages.append(
            SimpleNamespace(flow_id=flow_id, chat_id=chat_id, message_id=message_id, tag=tag)
        )

    def list(self, *, flow_id: str, tag: str | None = None):
        return [
            item
            for item in self.messages
            if item.flow_id == flow_id and (tag is None or item.tag == tag)
        ]

    def remove(self, *, flow_id: str, chat_id: int, message_id: int) -> None:
        self.messages = [
            item
            for item in self.messages
            if not (item.flow_id == flow_id and item.chat_id == chat_id and item.message_id == message_id)
        ]


class _FakeBot:
    def __init__(self) -> None:
        self.deleted_messages: list[tuple[int, int]] = []

    async def delete_message(self, *, chat_id: int, message_id: int) -> None:
        self.deleted_messages.append((chat_id, message_id))


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


class _MediumQuestionService:
    def __init__(self, question: TrainingQuestion) -> None:
        self.question = question

    def get_active_session(self, *, user_id: int):  # noqa: ARG002
        return SimpleNamespace(
            session_id=self.question.session_id,
            topic_id="weather",
            lesson_id=None,
            source_tag=None,
            mode=TrainingMode.MEDIUM,
            current_position=1,
            total_items=1,
        )

    def get_current_question(self, *, user_id: int):  # noqa: ARG002
        return self.question


class _CompletingService:
    def get_active_session(self, *, user_id: int):  # noqa: ARG002
        return SimpleNamespace(
            session_id="session-1",
            topic_id="weather",
            lesson_id=None,
            source_tag=None,
            mode=TrainingMode.EASY,
            current_position=1,
            total_items=1,
        )

    def submit_answer(self, *, user_id: int, answer: str):  # noqa: ARG002
        return bot.AnswerOutcome(
            result=CheckResult(is_correct=True, expected_answer="cloud", normalized_answer="cloud"),
            summary=SessionSummary(total_questions=1, correct_answers=1),
            next_question=None,
        )


class _CompletingHomeworkAssignmentService:
    def get_active_session(self, *, user_id: int):  # noqa: ARG002
        return SimpleNamespace(
            session_id="session-hw-1",
            user_id=123,
            topic_id="weather",
            lesson_id=None,
            source_tag="assignment:homework",
            mode=TrainingMode.MEDIUM,
            current_position=1,
            total_items=1,
        )

    def submit_answer(self, *, user_id: int, answer: str):  # noqa: ARG002
        return bot.AnswerOutcome(
            result=CheckResult(is_correct=True, expected_answer="cloud", normalized_answer="cloud"),
            summary=SessionSummary(total_questions=1, correct_answers=1),
            next_question=None,
        )


class _InProgressHomeworkAssignmentService:
    def get_active_session(self, *, user_id: int):  # noqa: ARG002
        return SimpleNamespace(
            session_id="session-hw-2",
            user_id=123,
            topic_id="weather",
            lesson_id=None,
            source_tag="assignment:homework",
            mode=TrainingMode.MEDIUM,
            current_position=1,
            total_items=2,
        )

    def submit_answer(self, *, user_id: int, answer: str):  # noqa: ARG002
        return bot.AnswerOutcome(
            result=CheckResult(is_correct=True, expected_answer="cloud", normalized_answer="cloud"),
            summary=None,
            next_question=TrainingQuestion(
                session_id="session-hw-2",
                item_id="sun",
                mode=TrainingMode.MEDIUM,
                prompt="Translation: солнце",
                image_ref=None,
                correct_answer="sun",
                letter_hint="nus",
            ),
        )


class _CompletingHomeworkAssignmentServiceWithGoal:
    def get_active_session(self, *, user_id: int):  # noqa: ARG002
        return SimpleNamespace(
            session_id="session-hw-goal-1",
            user_id=123,
            topic_id="weather",
            lesson_id=None,
            source_tag="assignment:homework:goal-1",
            mode=TrainingMode.MEDIUM,
            current_position=1,
            total_items=1,
        )

    def submit_answer(self, *, user_id: int, answer: str):  # noqa: ARG002
        return bot.AnswerOutcome(
            result=CheckResult(is_correct=True, expected_answer="cloud", normalized_answer="cloud"),
            summary=SessionSummary(total_questions=1, correct_answers=1),
            next_question=None,
        )


class _SummarySequenceUseCase:
    def __init__(self, summaries: list[object]) -> None:
        self._summaries = list(summaries)
        self.calls = 0

    def get_summary(self, user_id: int):  # noqa: ARG002
        index = min(self.calls, len(self._summaries) - 1)
        self.calls += 1
        return self._summaries[index]


class _RecordingTelegramUserLoginRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str | None, str | None, str | None, str | None]] = []

    def record(
        self,
        *,
        user_id: int,
        username: str | None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> None:
        self.calls.append((user_id, username, first_name, last_name, language_code))


class _RecordingTelegramUserRoleRepository:
    def __init__(
        self,
        memberships: dict[str, frozenset[int]] | None = None,
        *,
        persist_grants: bool = True,
        raise_on_grant: bool = False,
    ) -> None:
        self._memberships = {"user": frozenset()} if memberships is None else dict(memberships)
        self.grants: list[tuple[int, str]] = []
        self._persist_grants = persist_grants
        self._raise_on_grant = raise_on_grant

    def list_memberships(self) -> dict[str, frozenset[int]]:
        return self._memberships

    def grant(self, *, user_id: int, role: str) -> None:
        if self._raise_on_grant:
            raise RuntimeError("grant failed")
        self.grants.append((user_id, role))
        if self._persist_grants:
            current = set(self._memberships.get(role, frozenset()))
            current.add(user_id)
            self._memberships[role] = frozenset(current)


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
        effective_user=SimpleNamespace(
            id=321,
            username="local_test_user",
            first_name="Local",
            last_name="Tester",
            language_code="ru",
        ),
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
                "learner_assignment_launch_summary_use_case": SimpleNamespace(
                    execute=lambda user_id: [AssignmentLaunchView(AssignmentSessionKind.HOMEWORK, False, 0, 0)]
                ),
            }
        ),
    )

    await start_handler(update, context)  # type: ignore[arg-type]

    assert user_login_repository.calls == [(321, "local_test_user", "Local", "Tester", "ru")]
    assert len(sent_views) == 2
    assert sent_views[0].text.startswith("Что хотите сделать сейчас?")
    assert sent_views[0].reply_markup.inline_keyboard[0][0].callback_data == "start:game"
    assert sent_views[1].text == "Быстрые действия:"


@pytest.mark.anyio
async def test_start_handler_shows_admin_panel_link_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_views: list[object] = []

    async def _fake_send_telegram_view(message, view):  # noqa: ARG001
        sent_views.append(view)

    monkeypatch.setattr(bot, "send_telegram_view", _fake_send_telegram_view)

    update = SimpleNamespace(
        effective_message=SimpleNamespace(),
        effective_user=SimpleNamespace(
            id=321,
            username="boss",
            first_name="Boss",
            last_name="User",
            language_code="en",
        ),
    )
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "training_service": _IdleService(),
                "telegram_user_login_repository": _RecordingTelegramUserLoginRepository(),
                "telegram_ui_language": "en",
                "editor_user_ids": set(),
                "admin_user_ids": {321},
                "web_app_base_url": "https://admin.example.com",
                "learner_assignment_launch_summary_use_case": SimpleNamespace(
                    execute=lambda user_id: [AssignmentLaunchView(AssignmentSessionKind.HOMEWORK, False, 0, 0)]
                ),
            }
        ),
    )

    await start_handler(update, context)  # type: ignore[arg-type]

    assert sent_views[0].reply_markup.inline_keyboard[-1][0].url == "https://admin.example.com/webapp?user_id=321&lang=en"


@pytest.mark.anyio
async def test_makeadmin_handler_grants_admin_with_bootstrap_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_views: list[object] = []

    async def _fake_send_telegram_view(message, view):  # noqa: ARG001
        sent_views.append(view)

    monkeypatch.setattr(bot, "send_telegram_view", _fake_send_telegram_view)

    role_repository = _RecordingTelegramUserRoleRepository({"user": frozenset(), "admin": frozenset()})
    update = SimpleNamespace(
        effective_message=SimpleNamespace(),
        effective_user=SimpleNamespace(id=321, username="recover", first_name="Rec", last_name="Over"),
    )
    context = SimpleNamespace(
        args=["777", "topsecret"],
        application=SimpleNamespace(
            bot_data={
                "telegram_user_login_repository": _RecordingTelegramUserLoginRepository(),
                "telegram_user_role_repository": role_repository,
                "admin_bootstrap_secret": "topsecret",
            }
        ),
    )

    await makeadmin_handler(update, context)  # type: ignore[arg-type]

    assert role_repository.grants == [(777, "admin")]
    assert sent_views[0].text == "Admin role granted to Telegram user 777."


@pytest.mark.anyio
async def test_makeadmin_handler_rejects_non_admin_without_valid_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_views: list[object] = []

    async def _fake_send_telegram_view(message, view):  # noqa: ARG001
        sent_views.append(view)

    monkeypatch.setattr(bot, "send_telegram_view", _fake_send_telegram_view)

    role_repository = _RecordingTelegramUserRoleRepository({"user": frozenset(), "admin": frozenset()})
    update = SimpleNamespace(
        effective_message=SimpleNamespace(),
        effective_user=SimpleNamespace(id=321, username="recover", first_name="Rec", last_name="Over"),
    )
    context = SimpleNamespace(
        args=["777"],
        application=SimpleNamespace(
            bot_data={
                "telegram_user_login_repository": _RecordingTelegramUserLoginRepository(),
                "telegram_user_role_repository": role_repository,
                "admin_bootstrap_secret": "topsecret",
            }
        ),
    )

    await makeadmin_handler(update, context)  # type: ignore[arg-type]

    assert role_repository.grants == []
    assert "Access denied." in sent_views[0].text


@pytest.mark.anyio
async def test_makeadmin_handler_does_not_show_success_when_admin_role_was_not_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_views: list[object] = []

    async def _fake_send_telegram_view(message, view):  # noqa: ARG001
        sent_views.append(view)

    monkeypatch.setattr(bot, "send_telegram_view", _fake_send_telegram_view)

    role_repository = _RecordingTelegramUserRoleRepository(
        {"user": frozenset(), "admin": frozenset()},
        persist_grants=False,
    )
    update = SimpleNamespace(
        effective_message=SimpleNamespace(),
        effective_user=SimpleNamespace(id=321, username="recover", first_name="Rec", last_name="Over"),
    )
    context = SimpleNamespace(
        args=["777", "topsecret"],
        application=SimpleNamespace(
            bot_data={
                "telegram_user_login_repository": _RecordingTelegramUserLoginRepository(),
                "telegram_user_role_repository": role_repository,
                "admin_bootstrap_secret": "topsecret",
            }
        ),
    )

    await makeadmin_handler(update, context)  # type: ignore[arg-type]

    assert role_repository.grants == [(777, "admin")]
    assert sent_views[0].text == "Failed to grant the admin role."


@pytest.mark.anyio
async def test_clear_user_handler_clears_learning_data_for_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_views: list[object] = []

    async def _fake_send_telegram_view(message, view):  # noqa: ARG001
        sent_views.append(view)

    monkeypatch.setattr(bot, "send_telegram_view", _fake_send_telegram_view)

    discarded_user_ids: list[int] = []
    cleared_user_ids: list[int] = []
    cancelled_add_words_user_ids: list[int] = []

    update = SimpleNamespace(
        effective_message=SimpleNamespace(),
        effective_user=SimpleNamespace(id=321),
    )
    context = SimpleNamespace(
        args=["777", "topsecret"],
        application=SimpleNamespace(
            bot_data={
                "admin_user_ids": {321},
                "admin_bootstrap_secret": "topsecret",
                "training_service": SimpleNamespace(
                    discard_active_session=lambda user_id: discarded_user_ids.append(user_id)
                ),
                "content_store": SimpleNamespace(
                    clear_user_learning_data=lambda user_id: (
                        cleared_user_ids.append(user_id)
                        or {"goals": 2, "sessions": 1, "word_stats": 3}
                    )
                ),
                "recent_assignment_activity_by_user": {777: "recent"},
                "word_import_preview_message_ids": {777: 55},
                "add_words_cancel_use_case": SimpleNamespace(
                    execute=lambda user_id: cancelled_add_words_user_ids.append(user_id)
                ),
            }
        ),
    )

    await clear_user_handler(update, context)  # type: ignore[arg-type]

    assert discarded_user_ids == [777]
    assert cleared_user_ids == [777]
    assert cancelled_add_words_user_ids == [777]
    assert context.application.bot_data["recent_assignment_activity_by_user"] == {}
    assert context.application.bot_data["word_import_preview_message_ids"] == {}
    assert sent_views[0].text == "Learning data cleared for Telegram user 777. Goals: 2, sessions: 1, stats: 3."


@pytest.mark.anyio
async def test_clear_user_handler_rejects_invalid_confirmation_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_views: list[object] = []

    async def _fake_send_telegram_view(message, view):  # noqa: ARG001
        sent_views.append(view)

    monkeypatch.setattr(bot, "send_telegram_view", _fake_send_telegram_view)

    update = SimpleNamespace(
        effective_message=SimpleNamespace(),
        effective_user=SimpleNamespace(id=321),
    )
    context = SimpleNamespace(
        args=["777", "WRONG"],
        application=SimpleNamespace(
            bot_data={
                "admin_user_ids": set(),
                "admin_bootstrap_secret": "topsecret",
                "training_service": SimpleNamespace(
                    discard_active_session=lambda user_id: (_ for _ in ()).throw(AssertionError("must not discard"))
                ),
                "content_store": SimpleNamespace(
                    clear_user_learning_data=lambda user_id: (_ for _ in ()).throw(AssertionError("must not clear"))
                ),
            }
        ),
    )

    await clear_user_handler(update, context)  # type: ignore[arg-type]

    assert sent_views[0].text == (
        "Access denied. Current admins can use /clearuser directly. "
        "Otherwise provide a valid bootstrap secret."
    )


@pytest.mark.anyio
async def test_send_question_replaces_previous_tracked_training_question() -> None:
    message = _FakeMessage("start")
    registry = _FakeTelegramFlowMessageRepository()
    fake_bot = _FakeBot()
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=fake_bot,
    )
    update = SimpleNamespace(effective_message=message)
    question = TrainingQuestion(
        session_id="session-1",
        item_id="cloud",
        mode=TrainingMode.EASY,
        prompt="cloud",
        image_ref=None,
        correct_answer="cloud",
        options=["cloud", "bag", "book"],
    )

    await _send_question(update, context, question)  # type: ignore[arg-type]
    await _send_question(update, context, question)  # type: ignore[arg-type]

    assert fake_bot.deleted_messages == [(1, 11)]
    tracked = registry.list(flow_id="session-1", tag="training_question")
    assert len(tracked) == 1
    assert tracked[0].message_id == 12


@pytest.mark.anyio
async def test_send_question_builds_medium_inline_keyboard_and_state() -> None:
    message = _FakeMessage("start")
    registry = _FakeTelegramFlowMessageRepository()
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=_FakeBot(),
    )
    update = SimpleNamespace(effective_message=message)
    question = TrainingQuestion(
        session_id="session-medium-1",
        item_id="apple",
        mode=TrainingMode.MEDIUM,
        prompt="Translation: яблоко\nVisual clue: Image is shown above.\nShuffled letters hint: APLEP\nType the English word.",
        image_ref=None,
        correct_answer="APPLE",
        letter_hint="APLEP",
    )

    await _send_question(update, context, question)  # type: ignore[arg-type]

    assert "🧩" in message.replies[0]
    assert "_ _ _ _ _" in message.replies[0]
    keyboard = message.reply_markup_calls[0]
    assert [button.text for row in keyboard.inline_keyboard[:-1] for button in row] == [
        "A",
        "P",
        "L",
        "E",
        "P",
    ]
    assert keyboard.inline_keyboard[-1][0].text == "⌫"
    assert keyboard.inline_keyboard[-1][1].text == "✅ Check"
    assert keyboard.inline_keyboard[-1][1].callback_data == "medium:noop:check"
    state = context.user_data["medium_task_state"]
    assert state.target_word == "APPLE"
    assert state.shuffled_letters == ("A", "P", "L", "E", "P")
    assert state.selected_letter_indexes == ()
    assert state.message_id == 11


@pytest.mark.anyio
async def test_send_question_adds_tts_button_when_enabled() -> None:
    message = _FakeMessage("start")
    registry = _FakeTelegramFlowMessageRepository()
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "telegram_flow_message_repository": registry,
                "settings": SimpleNamespace(tts_service_enabled=True),
            }
        ),
        bot=_FakeBot(),
    )
    update = SimpleNamespace(effective_message=message)
    question = TrainingQuestion(
        session_id="session-easy-tts",
        item_id="cloud",
        mode=TrainingMode.EASY,
        prompt="Translation: облако",
        image_ref=None,
        correct_answer="cloud",
        options=["cloud", "bag", "book"],
    )

    await _send_question(update, context, question)  # type: ignore[arg-type]

    keyboard = message.reply_markup_calls[0]
    assert keyboard.inline_keyboard[-1][0].text == "🔊 Play"
    assert keyboard.inline_keyboard[-1][0].callback_data == "tts:current"


@pytest.mark.anyio
async def test_medium_answer_callback_handler_uses_backspace_and_repeated_letters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = TrainingQuestion(
        session_id="session-medium-2",
        item_id="apple",
        mode=TrainingMode.MEDIUM,
        prompt="Translation: яблоко\nVisual clue: Image is shown above.\nShuffled letters hint: APLEP\nType the English word.",
        image_ref=None,
        correct_answer="APPLE",
        letter_hint="APLEP",
    )
    processed_answers: list[str] = []

    async def _fake_process_answer(update, context, answer: str) -> None:  # noqa: ARG001
        processed_answers.append(answer)

    monkeypatch.setattr(bot, "_process_answer", _fake_process_answer)

    message = _FakeEditableMessage("medium")
    message.message_id = 77
    query = _FakeQuery("medium:pick:0", message)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, language_code="en"),
        effective_message=message,
    )
    context = SimpleNamespace(
        user_data={
            "medium_task_state": bot._MediumTaskState(
                session_id=question.session_id,
                item_id=question.item_id,
                target_word=question.correct_answer,
                shuffled_letters=("A", "P", "L", "E", "P"),
                selected_letter_indexes=(),
                message_id=77,
            )
        },
        application=SimpleNamespace(
            bot_data={
                "training_service": _MediumQuestionService(question),
                "telegram_ui_language": "en",
            }
        ),
    )

    for callback_data in (
        "medium:pick:0",
        "medium:pick:1",
        "medium:backspace",
        "medium:pick:1",
        "medium:pick:4",
        "medium:pick:2",
        "medium:pick:3",
    ):
        query.data = callback_data
        await bot.medium_answer_callback_handler(update, context)  # type: ignore[arg-type]

    assert processed_answers == []
    assert context.user_data["medium_task_state"].selected_letter_indexes == (0, 1, 4, 2, 3)
    assert any("A P _ _ _" in text for text, _reply_markup, _parse_mode in query.edit_calls)
    assert any("A P P _ _" in text for text, _reply_markup, _parse_mode in query.edit_calls)
    assert any("A P P L E" in text for text, _reply_markup, _parse_mode in query.edit_calls)
    assert any(
        reply_markup is not None
        and reply_markup.inline_keyboard[-1][1].callback_data == "medium:check"
        for _text, reply_markup, _parse_mode in query.edit_calls
    )
    assert any(
        any(button.text == "·" for row in reply_markup.inline_keyboard[:-1] for button in row)
        for _text, reply_markup, _parse_mode in query.edit_calls
        if reply_markup is not None
    )

    query.data = "medium:check"
    await bot.medium_answer_callback_handler(update, context)  # type: ignore[arg-type]

    assert processed_answers == ["APPLE"]
    assert "medium_task_state" not in context.user_data


@pytest.mark.anyio
async def test_medium_answer_callback_handler_ignores_check_before_word_is_complete(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    question = TrainingQuestion(
        session_id="session-medium-2b",
        item_id="apple",
        mode=TrainingMode.MEDIUM,
        prompt="Translation: яблоко\nVisual clue: Image is shown above.\nShuffled letters hint: APLEP\nType the English word.",
        image_ref=None,
        correct_answer="APPLE",
        letter_hint="APLEP",
    )
    processed_answers: list[str] = []

    async def _fake_process_answer(update, context, answer: str) -> None:  # noqa: ARG001
        processed_answers.append(answer)

    monkeypatch.setattr(bot, "_process_answer", _fake_process_answer)

    message = _FakeEditableMessage("medium")
    message.message_id = 77
    query = _FakeQuery("medium:check", message)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, language_code="en"),
        effective_message=message,
    )
    context = SimpleNamespace(
        user_data={
            "medium_task_state": bot._MediumTaskState(
                session_id=question.session_id,
                item_id=question.item_id,
                target_word=question.correct_answer,
                shuffled_letters=("A", "P", "L", "E", "P"),
                selected_letter_indexes=(0, 1),
                message_id=77,
            )
        },
        application=SimpleNamespace(
            bot_data={
                "training_service": _MediumQuestionService(question),
                "telegram_ui_language": "en",
            }
        ),
    )

    with caplog.at_level("DEBUG", logger="englishbot.bot"):
        await bot.medium_answer_callback_handler(update, context)  # type: ignore[arg-type]

    assert processed_answers == []
    assert query.edit_calls == []
    assert context.user_data["medium_task_state"].selected_letter_indexes == (0, 1)
    assert "Medium callback ignored: check before complete" in caplog.text


@pytest.mark.anyio
async def test_medium_answer_callback_handler_ignores_stale_message_callbacks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    question = TrainingQuestion(
        session_id="session-medium-3",
        item_id="apple",
        mode=TrainingMode.MEDIUM,
        prompt="Translation: яблоко\nVisual clue: Image is shown above.\nShuffled letters hint: APLEP\nType the English word.",
        image_ref=None,
        correct_answer="APPLE",
        letter_hint="APLEP",
    )
    message = _FakeEditableMessage("medium")
    message.message_id = 88
    query = _FakeQuery("medium:pick:0", message)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, language_code="en"),
        effective_message=message,
    )
    context = SimpleNamespace(
        user_data={
            "medium_task_state": bot._MediumTaskState(
                session_id=question.session_id,
                item_id=question.item_id,
                target_word=question.correct_answer,
                shuffled_letters=("A", "P", "L", "E", "P"),
                selected_letter_indexes=(),
                message_id=99,
            )
        },
        application=SimpleNamespace(
            bot_data={
                "training_service": _MediumQuestionService(question),
                "telegram_ui_language": "en",
            }
        ),
    )

    with caplog.at_level("DEBUG", logger="englishbot.bot"):
        await bot.medium_answer_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answers == 1
    assert query.edit_calls == []
    assert context.user_data["medium_task_state"].selected_letter_indexes == ()
    assert "Medium callback ignored: stale message" in caplog.text


@pytest.mark.anyio
async def test_medium_answer_callback_handler_logs_reused_letter_press(
    caplog: pytest.LogCaptureFixture,
) -> None:
    question = TrainingQuestion(
        session_id="session-medium-4",
        item_id="apple",
        mode=TrainingMode.MEDIUM,
        prompt="Translation: яблоко\nVisual clue: Image is shown above.\nShuffled letters hint: APLEP\nType the English word.",
        image_ref=None,
        correct_answer="APPLE",
        letter_hint="APLEP",
    )
    message = _FakeEditableMessage("medium")
    message.message_id = 77
    query = _FakeQuery("medium:pick:0", message)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, language_code="en"),
        effective_message=message,
    )
    context = SimpleNamespace(
        user_data={
            "medium_task_state": bot._MediumTaskState(
                session_id=question.session_id,
                item_id=question.item_id,
                target_word=question.correct_answer,
                shuffled_letters=("A", "P", "L", "E", "P"),
                selected_letter_indexes=(0,),
                message_id=77,
            )
        },
        application=SimpleNamespace(
            bot_data={
                "training_service": _MediumQuestionService(question),
                "telegram_ui_language": "en",
            }
        ),
    )

    with caplog.at_level("DEBUG", logger="englishbot.bot"):
        await bot.medium_answer_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.edit_calls == []
    assert "Medium callback ignored: letter already used" in caplog.text


@pytest.mark.anyio
async def test_medium_answer_callback_handler_serializes_fast_parallel_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = TrainingQuestion(
        session_id="session-medium-5",
        item_id="apple",
        mode=TrainingMode.MEDIUM,
        prompt="Translation: яблоко\nVisual clue: Image is shown above.\nShuffled letters hint: APLEP\nType the English word.",
        image_ref=None,
        correct_answer="APPLE",
        letter_hint="APLEP",
    )
    message = _FakeEditableMessage("medium")
    message.message_id = 77
    query_a = _FakeQuery("medium:pick:0", message)
    query_b = _FakeQuery("medium:pick:1", message)
    update_a = SimpleNamespace(
        callback_query=query_a,
        effective_user=SimpleNamespace(id=123, language_code="en"),
        effective_message=message,
    )
    update_b = SimpleNamespace(
        callback_query=query_b,
        effective_user=SimpleNamespace(id=123, language_code="en"),
        effective_message=message,
    )
    context = SimpleNamespace(
        user_data={
            "medium_task_state": bot._MediumTaskState(
                session_id=question.session_id,
                item_id=question.item_id,
                target_word=question.correct_answer,
                shuffled_letters=("A", "P", "L", "E", "P"),
                selected_letter_indexes=(),
                message_id=77,
            )
        },
        application=SimpleNamespace(
            bot_data={
                "training_service": _MediumQuestionService(question),
                "telegram_ui_language": "en",
            }
        ),
    )
    first_edit_started = asyncio.Event()
    release_first_edit = asyncio.Event()
    edit_call_count = 0

    original_edit = bot._edit_training_question_view

    async def _wrapped_edit_training_question_view(query, *, view) -> None:  # noqa: ANN001
        nonlocal edit_call_count
        edit_call_count += 1
        if edit_call_count == 1:
            first_edit_started.set()
            await release_first_edit.wait()
        await original_edit(query, view=view)

    monkeypatch.setattr(bot, "_edit_training_question_view", _wrapped_edit_training_question_view)

    task_a = asyncio.create_task(bot.medium_answer_callback_handler(update_a, context))  # type: ignore[arg-type]
    await first_edit_started.wait()
    task_b = asyncio.create_task(bot.medium_answer_callback_handler(update_b, context))  # type: ignore[arg-type]
    await asyncio.sleep(0)
    assert context.user_data["medium_task_state"].selected_letter_indexes == (0,)

    release_first_edit.set()
    await asyncio.gather(task_a, task_b)

    assert context.user_data["medium_task_state"].selected_letter_indexes == (0, 1)


@pytest.mark.anyio
async def test_process_answer_cleans_tracked_training_question_after_completion() -> None:
    message = _FakeMessage("cloud")
    registry = _FakeTelegramFlowMessageRepository()
    registry.track(flow_id="session-1", chat_id=1, message_id=99, tag="training_question")
    fake_bot = _FakeBot()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123, language_code="en"),
    )
    context = SimpleNamespace(
        user_data={},
        bot=fake_bot,
        application=SimpleNamespace(
            bot_data={
                "training_service": _CompletingService(),
                "telegram_ui_language": "en",
                "telegram_flow_message_repository": registry,
            }
        ),
    )

    await _process_answer(update, context, "cloud")  # type: ignore[arg-type]

    assert fake_bot.deleted_messages == [(1, 99)]


@pytest.mark.anyio
async def test_process_answer_reports_weekly_points_and_completed_goal() -> None:
    message = _FakeMessage("cloud")
    active_goal = GoalProgressView(
        goal=Goal(
            id="goal-1",
            user_id=123,
            goal_period=GoalPeriod.HOMEWORK,
            goal_type=GoalType.NEW_WORDS,
            target_count=1,
            progress_count=0,
            status=GoalStatus.ACTIVE,
        ),
        progress_percent=0,
    )
    completed_goal = GoalProgressView(
        goal=Goal(
            id="goal-1",
            user_id=123,
            goal_period=GoalPeriod.HOMEWORK,
            goal_type=GoalType.NEW_WORDS,
            target_count=1,
            progress_count=1,
            status=GoalStatus.COMPLETED,
        ),
        progress_percent=100,
    )
    summary_use_case = _SummarySequenceUseCase(
        [
            SimpleNamespace(
                correct_answers=0,
                incorrect_answers=0,
                game_streak_days=0,
                weekly_points=0,
                active_goals=[active_goal],
            ),
            SimpleNamespace(
                correct_answers=1,
                incorrect_answers=0,
                game_streak_days=0,
                weekly_points=11,
                active_goals=[],
            ),
        ]
    )
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123, language_code="en"),
    )
    context = SimpleNamespace(
        user_data={},
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "training_service": _CompletingService(),
                "telegram_ui_language": "en",
                "telegram_flow_message_repository": _FakeTelegramFlowMessageRepository(),
                "homework_progress_use_case": summary_use_case,
                "list_user_goals_use_case": SimpleNamespace(
                    execute=lambda user_id, include_history=True: [completed_goal]
                ),
                "learner_assignment_launch_summary_use_case": SimpleNamespace(execute=lambda user_id: []),
            }
        ),
    )

    await _process_answer(update, context, "cloud")  # type: ignore[arg-type]

    assert any("Weekly points +11" in reply for reply in message.replies)
    assert any("Completed goals:" in reply for reply in message.replies)
    assert not any("Daily/Words: 1/1 (100%)" in reply for reply in message.replies)


@pytest.mark.anyio
async def test_process_answer_shows_homework_progress_track_and_continue_button() -> None:
    message = _FakeMessage("cloud")
    message.from_user = SimpleNamespace(id=123, language_code="en")
    update = SimpleNamespace(
        effective_message=message,
        effective_user=message.from_user,
    )
    context = SimpleNamespace(
        user_data={},
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "training_service": _CompletingHomeworkAssignmentService(),
                "telegram_ui_language": "en",
                "telegram_flow_message_repository": _FakeTelegramFlowMessageRepository(),
                "learner_assignment_launch_summary_use_case": SimpleNamespace(
                    execute=lambda user_id: [
                        AssignmentLaunchView(
                            AssignmentSessionKind.HOMEWORK,
                            True,
                            3,
                            1,
                            completed_word_count=2,
                            total_word_count=5,
                            progress_variant_key="homework-alpha",
                        )
                    ]
                ),
            }
        ),
    )

    await _process_answer(update, context, "cloud")  # type: ignore[arg-type]

    assert any("📘 Homework progress:" in reply for reply in message.replies)
    assert any("✅ Done: 2/5 words" in reply for reply in message.replies)
    assert any("🎯 Homework left: 3" in reply for reply in message.replies)
    assert any("🐣" in reply and "🏁" in reply for reply in message.replies)
    keyboard = message.reply_markup_calls[-1]
    assert [row[0].callback_data for row in keyboard.inline_keyboard] == ["assign:menu", "start:menu"]


@pytest.mark.anyio
async def test_process_answer_shows_homework_progress_during_active_round_too() -> None:
    message = _FakeMessage("cloud")
    message.from_user = SimpleNamespace(id=123, language_code="en")
    update = SimpleNamespace(
        effective_message=message,
        effective_user=message.from_user,
    )
    context = SimpleNamespace(
        user_data={},
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "training_service": _InProgressHomeworkAssignmentService(),
                "telegram_ui_language": "en",
                "telegram_flow_message_repository": _FakeTelegramFlowMessageRepository(),
                "learner_assignment_launch_summary_use_case": SimpleNamespace(
                    execute=lambda user_id: [
                        AssignmentLaunchView(
                            AssignmentSessionKind.HOMEWORK,
                            True,
                            3,
                            1,
                            completed_word_count=2,
                            total_word_count=5,
                            progress_variant_key="homework-alpha",
                        )
                    ]
                ),
            }
        ),
    )

    await _process_answer(update, context, "cloud")  # type: ignore[arg-type]

    assert any("📘 Homework progress:" in reply for reply in message.replies)
    assert any("✅ Done: 2/5 words" in reply for reply in message.replies)
    assert any("🎯 Homework left: 3" in reply for reply in message.replies)
    assert any(
        "📘 Homework progress:" in reply and reply_markup is None
        for reply, reply_markup in zip(message.replies, message.reply_markup_calls, strict=False)
    )


@pytest.mark.anyio
async def test_send_feedback_keeps_compact_first_line_and_restores_assignment_progress_track() -> None:
    message = _FakePhotoCapableMessage("cloud")
    user = SimpleNamespace(id=123, language_code="en")
    message.from_user = user
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "telegram_ui_language": "en",
                "learner_assignment_launch_summary_use_case": SimpleNamespace(
                    execute=lambda user_id: [
                        AssignmentLaunchView(
                            AssignmentSessionKind.HOMEWORK,
                            True,
                            3,
                            1,
                            completed_word_count=2,
                            total_word_count=5,
                            progress_variant_key="homework-alpha",
                        )
                    ]
                ),
            }
        )
    )

    await bot._send_feedback(
        message,
        bot.AnswerOutcome(
            result=CheckResult(is_correct=True, expected_answer="cloud", normalized_answer="cloud"),
            summary=None,
            next_question=None,
        ),
        context=context,  # type: ignore[arg-type]
        active_session=SimpleNamespace(source_tag="assignment:homework", session_id="session-hw-3"),
        user=user,
        feedback_update=bot._GoalFeedbackUpdate(
            weekly_points_delta=6,
            progressed_goals=(),
            completed_goals=(),
        ),
    )

    assert len(message.replies) == 1
    first_line, *_rest = message.replies[0].splitlines()
    assert "Weekly points +6" in first_line
    assert "📘 Homework progress:" not in message.replies[0]
    assert "🏁" not in message.replies[0]


@pytest.mark.anyio
async def test_hard_skip_handler_downgrades_homework_hard_to_same_word_on_medium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _FakeEditableMessage("bonus")
    query = _FakeQuery("hard:skip:skip-token", message)
    sent_questions: list[TrainingQuestion] = []
    saved_sessions: list[TrainingSession] = []

    async def _fake_send_question(update, context, question):  # noqa: ANN001
        sent_questions.append(question)

    monkeypatch.setattr(bot, "_send_question", _fake_send_question)
    session = TrainingSession(
        id="session-hard",
        user_id=123,
        topic_id="animals",
        mode=TrainingMode.HARD,
        source_tag="assignment:homework:goal-1",
        combo_correct_streak=4,
        combo_hard_active=True,
        items=[SessionItem(order=0, vocabulary_item_id="cat", mode=TrainingMode.HARD)],
    )
    context = SimpleNamespace(
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "training_service": SimpleNamespace(
                    get_current_question=lambda user_id: TrainingQuestion(  # noqa: ARG005
                        session_id="session-hard",
                        item_id="cat",
                        mode=TrainingMode.HARD,
                        prompt="hard",
                        image_ref=None,
                        correct_answer="cat",
                    )
                    if not saved_sessions
                    else TrainingQuestion(
                        session_id="session-hard",
                        item_id="cat",
                        mode=TrainingMode.MEDIUM,
                        prompt="medium",
                        image_ref=None,
                        correct_answer="cat",
                        letter_hint="act",
                    )
                ),
                "content_store": SimpleNamespace(
                    get_active_session_by_user=lambda user_id: session,  # noqa: ARG005
                    save_session=lambda updated: saved_sessions.append(updated),
                    consume_telegram_callback_token=lambda **kwargs: {"session_id": "session-hard"},
                ),
                "telegram_ui_language": "en",
            }
        ),
        user_data={},
    )

    await bot.hard_skip_handler(
        SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123, language_code="en")),
        context,  # type: ignore[arg-type]
    )

    assert len(saved_sessions) == 1
    assert saved_sessions[0].items[0].mode is TrainingMode.MEDIUM
    assert saved_sessions[0].combo_correct_streak == 0
    assert saved_sessions[0].combo_hard_active is False
    assert [question.mode for question in sent_questions] == [TrainingMode.MEDIUM]


@pytest.mark.anyio
async def test_hard_skip_handler_uses_existing_answer_flow_outside_homework(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _FakeEditableMessage("hard")
    query = _FakeQuery("hard:skip:skip-token", message)
    handled: list[str] = []

    async def _fake_process_answer(update, context, answer):  # noqa: ANN001
        handled.append(answer)

    monkeypatch.setattr(bot, "_process_answer", _fake_process_answer)
    context = SimpleNamespace(
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "training_service": SimpleNamespace(
                    get_current_question=lambda user_id: TrainingQuestion(  # noqa: ARG005
                        session_id="session-hard",
                        item_id="cat",
                        mode=TrainingMode.HARD,
                        prompt="hard",
                        image_ref=None,
                        correct_answer="cat",
                    )
                ),
                "content_store": SimpleNamespace(
                    get_active_session_by_user=lambda user_id: TrainingSession(  # noqa: ARG005
                        id="session-hard",
                        user_id=123,
                        topic_id="animals",
                        mode=TrainingMode.HARD,
                        source_tag=None,
                        items=[SessionItem(order=0, vocabulary_item_id="cat", mode=TrainingMode.HARD)],
                    ),
                    consume_telegram_callback_token=lambda **kwargs: {"session_id": "session-hard"},
                ),
                "telegram_ui_language": "en",
            }
        ),
        user_data={},
    )

    await bot.hard_skip_handler(
        SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123, language_code="en")),
        context,  # type: ignore[arg-type]
    )

    assert handled == ["__skip_hard__"]


def test_hard_skip_keyboard_uses_short_callback_token() -> None:
    created: list[dict[str, object]] = []
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "content_store": SimpleNamespace(
                    create_telegram_callback_token=lambda **kwargs: created.append(kwargs) or "cbtok123456"
                ),
                "telegram_ui_language": "en",
            }
        )
    )
    user = SimpleNamespace(id=321, language_code="en")

    markup = bot._hard_skip_keyboard(
        context=context,  # type: ignore[arg-type]
        user=user,
        session_id="session-hard-very-long-id",
    )

    button = markup.inline_keyboard[0][0]
    assert button.callback_data == "hard:skip:cbtok123456"
    assert len(button.callback_data) < 64
    assert created == [
        {
            "user_id": 321,
            "action": "hard_skip",
            "payload": {"session_id": "session-hard-very-long-id"},
            "ttl_seconds": 172800,
        }
    ]


@pytest.mark.anyio
async def test_tts_current_handler_sends_audio_for_current_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _FakeEditableMessage("question")
    query = _FakeQuery("tts:current", message)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, language_code="en"),
    )
    synthesized: list[str] = []

    class _FakeTtsClient:
        def synthesize(self, *, text: str) -> bytes:
            synthesized.append(text)
            return b"RIFFfakewav"

    monkeypatch.setattr(bot, "_tts_client_or_none", lambda context: _FakeTtsClient())
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "training_service": SimpleNamespace(
                    get_active_session=lambda user_id: SimpleNamespace(id="session-1"),  # noqa: ARG005
                    get_current_question=lambda user_id: TrainingQuestion(  # noqa: ARG005
                        session_id="session-1",
                        item_id="cloud",
                        mode=TrainingMode.EASY,
                        prompt="Translation: облако",
                        image_ref=None,
                        correct_answer="cloud",
                        options=["cloud", "bag", "book"],
                    ),
                ),
                "telegram_ui_language": "en",
            }
        )
    )

    await bot.tts_current_handler(update, context)  # type: ignore[arg-type]

    assert synthesized == ["cloud"]
    assert query.answers == 1
    assert query.answer_payloads == [(None, None)]
    assert len(message.reply_audio_calls) == 1


@pytest.mark.anyio
async def test_tts_current_handler_answers_gracefully_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _FakeEditableMessage("question")
    query = _FakeQuery("tts:current", message)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, language_code="en"),
    )

    monkeypatch.setattr(bot, "_tts_client_or_none", lambda context: None)
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"telegram_ui_language": "en"})
    )

    await bot.tts_current_handler(update, context)  # type: ignore[arg-type]

    assert query.answers == 1
    assert query.answer_payloads == [("Audio is unavailable right now.", None)]
    assert message.reply_audio_calls == []


@pytest.mark.anyio
async def test_process_answer_shows_assignment_progress_for_homework_assignment() -> None:
    message = _FakeMessage("cloud")
    message.from_user = SimpleNamespace(id=123, language_code="en")
    update = SimpleNamespace(
        effective_message=message,
        effective_user=message.from_user,
    )
    context = SimpleNamespace(
        user_data={},
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "training_service": SimpleNamespace(
                    get_active_session=lambda user_id: SimpleNamespace(  # noqa: ARG005
                        session_id="session-homework-1",
                        user_id=123,
                        topic_id="weather",
                        lesson_id=None,
                        source_tag="assignment:homework",
                        mode=TrainingMode.MEDIUM,
                        current_position=1,
                        total_items=1,
                    ),
                    submit_answer=lambda user_id, answer: bot.AnswerOutcome(  # noqa: ARG005
                        result=CheckResult(
                            is_correct=True,
                            expected_answer="cloud",
                            normalized_answer="cloud",
                        ),
                        summary=SessionSummary(total_questions=1, correct_answers=1),
                        next_question=None,
                    ),
                ),
                "telegram_ui_language": "en",
                "telegram_flow_message_repository": _FakeTelegramFlowMessageRepository(),
                "learner_assignment_launch_summary_use_case": SimpleNamespace(
                    execute=lambda user_id: [  # noqa: ARG005
                        AssignmentLaunchView(
                            AssignmentSessionKind.HOMEWORK,
                            True,
                            4,
                            1,
                            completed_word_count=5,
                            total_word_count=9,
                            progress_variant_key="homework-alpha",
                        )
                    ]
                ),
            }
        ),
    )

    await _process_answer(update, context, "cloud")  # type: ignore[arg-type]

    assert any("📘 Homework progress:" in reply for reply in message.replies)
    assert any("🎯 Homework left: 4" in reply for reply in message.replies)


@pytest.mark.anyio
async def test_process_answer_autocontinues_homework_after_session_complete_when_words_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _FakeMessage("cloud")
    user = SimpleNamespace(id=123, language_code="en")
    message.from_user = user
    update = SimpleNamespace(
        effective_message=message,
        effective_user=user,
    )
    start_calls: list[tuple[int, str | None, int, bool]] = []
    sent_questions: list[str] = []
    feedback_summaries: list[SessionSummary | None] = []

    async def _fake_send_question(update, context, question):  # noqa: ANN001
        sent_questions.append(question.prompt)

    async def _fake_send_assignment_progress(context, *, message, user, kind, active_session=None):  # noqa: ANN001
        return None

    async def _fake_send_feedback(message, outcome, *, context, active_session=None, user=None, feedback_update=None):  # noqa: ANN001
        feedback_summaries.append(outcome.summary)
        return None

    monkeypatch.setattr(bot, "_send_question", _fake_send_question)
    monkeypatch.setattr(bot, "_send_or_update_assignment_progress_message", _fake_send_assignment_progress)
    monkeypatch.setattr(bot, "_send_feedback", _fake_send_feedback)

    context = SimpleNamespace(
        user_data={},
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "training_service": _CompletingHomeworkAssignmentServiceWithGoal(),
                "telegram_ui_language": "en",
                "telegram_flow_message_repository": _FakeTelegramFlowMessageRepository(),
                "content_store": SimpleNamespace(
                    get_session_by_id=lambda session_id: TrainingSession(
                        id="session-hw-goal-1",
                        user_id=123,
                        topic_id="weather",
                        mode=TrainingMode.MEDIUM,
                        source_tag="assignment:homework:goal-1",
                        current_index=1,
                        combo_correct_streak=4,
                        combo_hard_active=True,
                        completed=True,
                        items=[SessionItem(order=0, vocabulary_item_id="cloud", mode=TrainingMode.MEDIUM)],
                    )
                ),
                "start_assignment_round_use_case": SimpleNamespace(
                    execute=lambda user_id, kind, goal_id=None, combo_correct_streak=0, combo_hard_active=False: (
                        start_calls.append((user_id, goal_id, combo_correct_streak, combo_hard_active))
                        or TrainingQuestion(
                            session_id="session-hw-goal-2",
                            item_id="rain",
                            mode=TrainingMode.HARD,
                            prompt="Translation: дождь",
                            image_ref=None,
                            correct_answer="rain",
                            input_hint="Type it",
                        )
                    )
                ),
            }
        ),
    )

    await _process_answer(update, context, "cloud")  # type: ignore[arg-type]

    assert start_calls == [(123, "goal-1", 4, True)]
    assert sent_questions == ["Translation: дождь"]
    assert feedback_summaries == [None]
    assert context.user_data["awaiting_text_answer"] is True


@pytest.mark.anyio
async def test_choice_answer_handler_uses_active_session_user_for_homework_progress() -> None:
    message = _FakeCallbackMessage("question")
    query = _FakeQuery("answer:cloud", _FakeEditableMessage("question"))
    query.message = message
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, language_code="en"),
        effective_message=message,
    )
    context = SimpleNamespace(
        user_data={},
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "training_service": SimpleNamespace(
                    get_active_session=lambda user_id: SimpleNamespace(  # noqa: ARG005
                        session_id="session-homework-2",
                        user_id=123,
                        topic_id="weather",
                        lesson_id=None,
                        source_tag="assignment:homework",
                        mode=TrainingMode.EASY,
                        current_position=1,
                        total_items=1,
                    ),
                    submit_answer=lambda user_id, answer: bot.AnswerOutcome(  # noqa: ARG005
                        result=CheckResult(
                            is_correct=True,
                            expected_answer="cloud",
                            normalized_answer="cloud",
                        ),
                        summary=None,
                        next_question=TrainingQuestion(
                            session_id="session-homework-2",
                            item_id="sun",
                            mode=TrainingMode.EASY,
                            prompt="sun",
                            image_ref=None,
                            correct_answer="sun",
                            options=["sun", "moon", "book"],
                        ),
                    ),
                ),
                "telegram_ui_language": "en",
                "telegram_flow_message_repository": _FakeTelegramFlowMessageRepository(),
                "learner_assignment_launch_summary_use_case": SimpleNamespace(
                    execute=lambda user_id: [  # noqa: ARG005
                        AssignmentLaunchView(
                            AssignmentSessionKind.HOMEWORK,
                            True,
                            4,
                            1,
                            completed_word_count=5,
                            total_word_count=9,
                            progress_variant_key="homework-alpha",
                        )
                    ]
                ),
            }
        ),
    )

    await choice_answer_handler(update, context)  # type: ignore[arg-type]

    assert any("📘 Homework progress:" in reply for reply in message.replies)
    assert any("🎯 Homework left: 4" in reply for reply in message.replies)


def test_assignment_progress_track_uses_stable_variant_key() -> None:
    first = bot._render_assignment_progress_track(
        completed=2,
        total=5,
        variant_key="goal-a",
    )
    second = bot._render_assignment_progress_track(
        completed=2,
        total=5,
        variant_key="goal-a",
    )
    third = bot._render_assignment_progress_track(
        completed=2,
        total=5,
        variant_key="goal-b",
    )

    assert first == second
    assert first != third


def test_assignment_progress_track_marks_completed_cells_separately() -> None:
    track = bot._render_assignment_progress_track(
        completed=3,
        total=10,
        variant_key="goal-mouse",
    )

    assert len(track) >= 18
    assert "🏠" in track or "🏁" in track or "🌼" in track
    assert "🐭" in track or "🐣" in track or "🚗" in track or "🐛" in track
    assert "▫️" in track or "🟨" in track or "🟩" in track or "🍂" in track


@pytest.mark.anyio
async def test_process_answer_replaces_previous_feedback_message() -> None:
    message = _FakeMessage("cloud")
    registry = _FakeTelegramFlowMessageRepository()
    registry.track(flow_id="session-1", chat_id=1, message_id=55, tag="training_feedback")
    fake_bot = _FakeBot()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123, language_code="en"),
    )
    context = SimpleNamespace(
        user_data={},
        bot=fake_bot,
        application=SimpleNamespace(
            bot_data={
                "training_service": _CompletingService(),
                "telegram_ui_language": "en",
                "telegram_flow_message_repository": registry,
            }
        ),
    )

    await _process_answer(update, context, "cloud")  # type: ignore[arg-type]

    assert fake_bot.deleted_messages == [(1, 55)]
    tracked = registry.list(flow_id="session-1", tag="training_feedback")
    assert len(tracked) == 1
    assert tracked[0].message_id == 11
