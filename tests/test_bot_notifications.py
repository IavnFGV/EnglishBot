from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from englishbot.bot import (
    _create_admin_goal_from_context,
    _daily_assignment_reminder_job,
    _deliver_pending_notification_job,
    _flush_pending_notifications_for_user,
    _post_init,
    _schedule_assignment_assigned_notifications,
    _schedule_goal_completed_notifications,
    notification_dismiss_callback_handler,
)


class _FakeJobQueue:
    def __init__(self) -> None:
        self.calls: list[SimpleNamespace] = []
        self.daily_calls: list[SimpleNamespace] = []

    def run_once(self, callback, when, data=None, name=None):  # noqa: ANN001
        self.calls.append(
            SimpleNamespace(
                callback=callback,
                when=when,
                data=data,
                name=name,
            )
        )

    def run_daily(self, callback, time, data=None, name=None):  # noqa: ANN001
        self.daily_calls.append(
            SimpleNamespace(
                callback=callback,
                time=time,
                data=data,
                name=name,
            )
        )


class _FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[SimpleNamespace] = []
        self.deleted_messages: list[tuple[int, int]] = []

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None) -> None:  # noqa: ANN001
        self.sent_messages.append(
            SimpleNamespace(chat_id=chat_id, text=text, reply_markup=reply_markup)
        )

    async def delete_message(self, *, chat_id: int, message_id: int) -> None:
        self.deleted_messages.append((chat_id, message_id))


def _build_context(*, active_session=None):
    job_queue = _FakeJobQueue()
    bot = _FakeBot()
    application = SimpleNamespace(
        bot_data={
            "pending_notifications": {},
            "recent_assignment_activity_by_user": {},
            "content_store": SimpleNamespace(list_users_goal_overview=lambda: []),
            "telegram_user_login_repository": SimpleNamespace(list=lambda: []),
            "telegram_ui_language": "en",
            "training_service": SimpleNamespace(get_active_session=lambda user_id: active_session),  # noqa: ARG005
            "telegram_user_role_repository": SimpleNamespace(
                list_memberships=lambda: {"admin": frozenset({101, 202})}
            ),
        },
        job_queue=job_queue,
    )
    context = SimpleNamespace(application=application, bot=bot)
    return context, job_queue, bot


class _FakeNotificationRepository:
    def __init__(self) -> None:
        self.items: dict[str, _PendingNotification] = {}

    def save(self, *, notification_key: str, recipient_user_id: int, text: str, not_before_at):  # noqa: ANN001
        created_at = self.items.get(
            notification_key,
            SimpleNamespace(created_at=not_before_at),
        ).created_at
        self.items[notification_key] = SimpleNamespace(
            key=notification_key,
            recipient_user_id=recipient_user_id,
            text=text,
            not_before_at=not_before_at,
            created_at=created_at,
        )

    def get(self, *, notification_key: str):
        return self.items.get(notification_key)

    def list(self, *, recipient_user_id: int | None = None):
        values = list(self.items.values())
        if recipient_user_id is None:
            return values
        return [item for item in values if item.recipient_user_id == recipient_user_id]

    def remove(self, *, notification_key: str) -> None:
        self.items.pop(notification_key, None)


def test_schedule_assignment_assigned_notifications_enqueues_user_messages() -> None:
    context, job_queue, _ = _build_context()
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository

    _schedule_assignment_assigned_notifications(
        context,
        goals=[
            SimpleNamespace(
                id="goal-1",
                user_id=77,
                goal_period=SimpleNamespace(value="daily"),
                goal_type=SimpleNamespace(value="new_words"),
                target_count=10,
            )
        ],
    )

    assert "assignment-assigned:daily:goal-1:77" in repository.items
    assert job_queue.calls[0].when == 0
    assert "New assignment is ready!" in repository.items["assignment-assigned:daily:goal-1:77"].text
    assert "Daily" in repository.items["assignment-assigned:daily:goal-1:77"].text


@pytest.mark.anyio
async def test_create_admin_goal_from_context_sends_assignment_notification_immediately() -> None:
    context, _, bot = _build_context()
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository
    context.application.bot_data["assign_goal_to_users_use_case"] = SimpleNamespace(
        execute=lambda **kwargs: [  # noqa: ARG005
            SimpleNamespace(
                id="goal-1",
                user_id=77,
                goal_period=SimpleNamespace(value="homework"),
                goal_type=SimpleNamespace(value="word_level_homework"),
                target_count=10,
            )
        ]
    )
    context.user_data = {
        "admin_goal_recipient_user_ids": [77],
    }
    query = SimpleNamespace(
        edits=[],
    )

    async def _edit_message_text(text: str) -> None:
        query.edits.append(text)

    query.edit_message_text = _edit_message_text

    await _create_admin_goal_from_context(
        query=query,
        context=context,  # type: ignore[arg-type]
        user=SimpleNamespace(id=101, language_code="en"),
    )

    assert len(bot.sent_messages) == 1
    assert bot.sent_messages[0].chat_id == 77
    assert "New assignment is ready!" in bot.sent_messages[0].text
    assert bot.sent_messages[0].reply_markup.inline_keyboard[0][0].callback_data == "start:launch:homework"
    assert repository.items == {}


@pytest.mark.anyio
async def test_deliver_pending_notification_job_requeues_when_user_was_recently_active() -> None:
    context, job_queue, bot = _build_context()
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository
    repository.items["n1"] = SimpleNamespace(
        key="n1",
        recipient_user_id=77,
        text="Hello",
        not_before_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    context.application.bot_data["recent_assignment_activity_by_user"][77] = datetime.now(UTC)
    job_context = SimpleNamespace(
        application=context.application,
        bot=bot,
        job=SimpleNamespace(data={"notification_key": "n1"}),
    )

    await _deliver_pending_notification_job(job_context)  # type: ignore[arg-type]

    assert bot.sent_messages == []
    assert job_queue.calls[-1].name == "n1"
    assert 119.0 <= job_queue.calls[-1].when <= 120.0


@pytest.mark.anyio
async def test_deliver_pending_notification_job_requeues_longer_for_active_session() -> None:
    context, job_queue, bot = _build_context(active_session=SimpleNamespace(session_id="active"))
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository
    repository.items["n1"] = SimpleNamespace(
        key="n1",
        recipient_user_id=77,
        text="Hello",
        not_before_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    context.application.bot_data["recent_assignment_activity_by_user"][77] = datetime.now(UTC)
    job_context = SimpleNamespace(
        application=context.application,
        bot=bot,
        job=SimpleNamespace(data={"notification_key": "n1"}),
    )

    await _deliver_pending_notification_job(job_context)  # type: ignore[arg-type]

    assert bot.sent_messages == []
    assert job_queue.calls[-1].name == "n1"
    assert 299.0 <= job_queue.calls[-1].when <= 300.0


@pytest.mark.anyio
async def test_deliver_pending_notification_job_ignores_stale_active_session_without_recent_activity() -> None:
    context, _, bot = _build_context(active_session=SimpleNamespace(session_id="stale"))
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository
    repository.items["n1"] = SimpleNamespace(
        key="n1",
        recipient_user_id=77,
        text="Hello now",
        not_before_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    context.application.bot_data["recent_assignment_activity_by_user"][77] = (
        datetime.now(UTC) - timedelta(minutes=6)
    )
    job_context = SimpleNamespace(
        application=context.application,
        bot=bot,
        job=SimpleNamespace(data={"notification_key": "n1"}),
    )

    await _deliver_pending_notification_job(job_context)  # type: ignore[arg-type]

    assert len(bot.sent_messages) == 1
    assert bot.sent_messages[0].chat_id == 77


@pytest.mark.anyio
async def test_flush_pending_notifications_for_user_sends_immediately_after_quiz_end() -> None:
    context, _, bot = _build_context()
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository
    repository.items["n1"] = SimpleNamespace(
        key="n1",
        recipient_user_id=77,
        text="Hello after quiz",
        not_before_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    context.application.bot_data["recent_assignment_activity_by_user"][77] = datetime.now(UTC)

    await _flush_pending_notifications_for_user(context, user_id=77)  # type: ignore[arg-type]

    assert len(bot.sent_messages) == 1
    assert bot.sent_messages[0].chat_id == 77
    assert bot.sent_messages[0].text == "Hello after quiz"
    assert bot.sent_messages[0].reply_markup.inline_keyboard[0][0].callback_data == "assign:menu"
    assert bot.sent_messages[0].reply_markup.inline_keyboard[0][1].callback_data == "notification:dismiss"
    assert "n1" not in repository.items


@pytest.mark.anyio
async def test_flush_pending_assignment_completed_notification_uses_admin_progress_button() -> None:
    context, _, bot = _build_context()
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository
    repository.items["assignment-completed:goal-1:101"] = SimpleNamespace(
        key="assignment-completed:goal-1:101",
        recipient_user_id=101,
        text="Assignment completed",
        not_before_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )

    await _flush_pending_notifications_for_user(context, user_id=101)  # type: ignore[arg-type]

    assert len(bot.sent_messages) == 1
    assert bot.sent_messages[0].reply_markup.inline_keyboard[0][0].callback_data == "assign:users"
    assert bot.sent_messages[0].reply_markup.inline_keyboard[0][1].callback_data == "notification:dismiss"


@pytest.mark.anyio
async def test_flush_pending_homework_assignment_notification_uses_direct_start_button() -> None:
    context, _, bot = _build_context()
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository
    repository.items["assignment-assigned:homework:goal-1:77"] = SimpleNamespace(
        key="assignment-assigned:homework:goal-1:77",
        recipient_user_id=77,
        text="Homework is ready",
        not_before_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )

    await _flush_pending_notifications_for_user(context, user_id=77)  # type: ignore[arg-type]

    assert len(bot.sent_messages) == 1
    assert bot.sent_messages[0].reply_markup.inline_keyboard[0][0].callback_data == "start:launch:homework"


def test_schedule_goal_completed_notifications_enqueues_admin_messages() -> None:
    context, job_queue, _ = _build_context()
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository

    _schedule_goal_completed_notifications(
        context,
        learner=SimpleNamespace(id=77, username="learner", first_name="Learner"),
        completed_goals=(
            SimpleNamespace(
                goal=SimpleNamespace(
                    id="goal-1",
                    goal_period=SimpleNamespace(value="daily"),
                    goal_type=SimpleNamespace(value="new_words"),
                    progress_count=5,
                    target_count=5,
                )
            ),
        ),
    )

    pending = repository.items
    assert "assignment-completed:goal-1:101" in pending
    assert "assignment-completed:goal-1:202" in pending
    assert len(job_queue.calls) == 2
    assert "learner finished daily/new_words 5/5" in pending["assignment-completed:goal-1:101"].text


@pytest.mark.anyio
async def test_daily_assignment_reminder_job_enqueues_notifications_for_users_with_active_goals() -> None:
    context, job_queue, _ = _build_context()
    repository = _FakeNotificationRepository()
    context.application.bot_data["pending_telegram_notification_repository"] = repository
    context.application.bot_data["content_store"] = SimpleNamespace(
        list_users_goal_overview=lambda: [
            {"user_id": 77, "active_goals_count": 2},
            {"user_id": 88, "active_goals_count": 0},
            {"user_id": 99, "active_goals_count": 1},
        ]
    )
    context.application.bot_data["telegram_user_login_repository"] = SimpleNamespace(
        list=lambda: [
            SimpleNamespace(user_id=77, language_code="ru"),
            SimpleNamespace(user_id=99, language_code="en"),
        ]
    )

    await _daily_assignment_reminder_job(context)  # type: ignore[arg-type]

    keys = set(repository.items)
    assert any(key.endswith(":77") and key.startswith("assignment-reminder:") for key in keys)
    assert any(key.endswith(":99") and key.startswith("assignment-reminder:") for key in keys)
    assert not any(key.endswith(":88") and key.startswith("assignment-reminder:") for key in keys)
    assert len(job_queue.calls) == 2
    reminder_for_77 = next(item for key, item in repository.items.items() if key.endswith(":77"))
    assert "2 активных целей" in reminder_for_77.text
    reminder_for_99 = next(item for key, item in repository.items.items() if key.endswith(":99"))
    assert "1 active goal" in reminder_for_99.text


@pytest.mark.anyio
async def test_post_init_reschedules_pending_notifications_from_repository() -> None:
    job_queue = _FakeJobQueue()
    repository = _FakeNotificationRepository()
    now = datetime.now(UTC)
    repository.items["n1"] = SimpleNamespace(
        key="n1",
        recipient_user_id=77,
        text="Hello later",
        not_before_at=now,
        created_at=now,
    )
    bot = SimpleNamespace(set_my_commands=lambda *args, **kwargs: None)

    async def _set_my_commands(*args, **kwargs) -> None:  # noqa: ANN002, ARG001
        return None

    app = SimpleNamespace(
        bot=SimpleNamespace(set_my_commands=_set_my_commands),
        bot_data={
            "pending_telegram_notification_repository": repository,
        },
        job_queue=job_queue,
    )

    await _post_init(app)  # type: ignore[arg-type]

    assert len(job_queue.calls) == 1
    assert job_queue.calls[0].data == {"notification_key": "n1"}
    assert len(job_queue.daily_calls) == 1
    assert job_queue.daily_calls[0].name == "daily-assignment-reminder"
    assert job_queue.daily_calls[0].time.hour == 13


@pytest.mark.anyio
async def test_notification_dismiss_callback_handler_deletes_message() -> None:
    bot = _FakeBot()
    query = SimpleNamespace(
        message=SimpleNamespace(chat_id=7, message_id=99),
        answer_calls=0,
    )

    async def _answer() -> None:
        query.answer_calls += 1

    query.answer = _answer
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=bot)

    await notification_dismiss_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answer_calls == 1
    assert bot.deleted_messages == [(7, 99)]
