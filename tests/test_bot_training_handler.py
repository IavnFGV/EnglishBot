from types import SimpleNamespace

import pytest

from englishbot.application.homework_progress_use_cases import AssignmentLaunchView, AssignmentSessionKind
from englishbot import bot
from englishbot.bot import (
    _process_answer,
    _send_question,
    makeadmin_handler,
    start_handler,
    text_answer_handler,
)
from englishbot.domain.models import CheckResult, SessionSummary, TrainingMode, TrainingQuestion


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []
        self.chat_id = 1
        self.message_id = 10

    async def reply_text(self, text: str, reply_markup=None, parse_mode=None) -> None:  # noqa: ARG002
        self.replies.append(text)
        self.message_id += 1
        return SimpleNamespace(message_id=self.message_id, chat_id=self.chat_id)


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


class _RecordingTelegramUserLoginRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str | None, str | None, str | None]] = []

    def record(
        self,
        *,
        user_id: int,
        username: str | None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> None:
        self.calls.append((user_id, username, first_name, last_name))


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
                    execute=lambda user_id: [
                        AssignmentLaunchView(AssignmentSessionKind.DAILY, False, 0, 0),
                        AssignmentLaunchView(AssignmentSessionKind.WEEKLY, False, 0, 0),
                        AssignmentLaunchView(AssignmentSessionKind.HOMEWORK, False, 0, 0),
                        AssignmentLaunchView(AssignmentSessionKind.ALL, False, 0, 0),
                    ]
                ),
            }
        ),
    )

    await start_handler(update, context)  # type: ignore[arg-type]

    assert user_login_repository.calls == [(321, "local_test_user", "Local", "Tester")]
    assert len(sent_views) == 2
    assert sent_views[0].text.startswith("Что хотите сделать сейчас?")
    assert sent_views[0].reply_markup.inline_keyboard[0][0].callback_data == "start:game"


@pytest.mark.anyio
async def test_start_handler_shows_admin_web_app_button_when_configured(
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
                    execute=lambda user_id: [
                        AssignmentLaunchView(AssignmentSessionKind.DAILY, False, 0, 0),
                        AssignmentLaunchView(AssignmentSessionKind.WEEKLY, False, 0, 0),
                        AssignmentLaunchView(AssignmentSessionKind.HOMEWORK, False, 0, 0),
                        AssignmentLaunchView(AssignmentSessionKind.ALL, False, 0, 0),
                    ]
                ),
            }
        ),
    )

    await start_handler(update, context)  # type: ignore[arg-type]

    assert sent_views[0].reply_markup.inline_keyboard[-1][0].web_app.url == "https://admin.example.com/webapp"


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
    assert registry.list(flow_id="session-1", tag="training_question") == []
