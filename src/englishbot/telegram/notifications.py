from __future__ import annotations

from datetime import UTC, datetime, timedelta

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from englishbot.telegram.buttons import InlineKeyboardButton


def pending_notifications(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    import englishbot.bot as bot_module

    return bot_module._mutable_bot_data_dict(context, "pending_notifications")


def pending_notification_repository(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._optional_bot_data(context, "pending_telegram_notification_repository")


def recent_assignment_activity_by_user(context: ContextTypes.DEFAULT_TYPE) -> dict[int, datetime]:
    import englishbot.bot as bot_module

    return bot_module._mutable_bot_data_dict(
        context,
        "recent_assignment_activity_by_user",
        fallback_key="recent_quiz_activity_by_user",
    )


def notification_action_button_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification_key: str,
    user_id: int,
):
    import englishbot.bot as bot_module

    language = bot_module._telegram_ui_language_for_user_id(context, user_id=user_id)
    if notification_key.startswith("assignment-completed:"):
        return InlineKeyboardButton(
            bot_module._tg("notification_open_users_progress", language=language),
            callback_data="assign:users",
        )
    if notification_key.startswith("assignment-assigned:homework:"):
        return InlineKeyboardButton(
            bot_module._tg("notification_start_homework", language=language),
            callback_data="start:launch:homework",
        )
    return InlineKeyboardButton(
        bot_module._tg("notification_open_assignments", language=language),
        callback_data="assign:menu",
    )


def dismiss_notification_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification_key: str,
    user_id: int,
) -> InlineKeyboardMarkup:
    import englishbot.bot as bot_module

    language = bot_module._telegram_ui_language_for_user_id(context, user_id=user_id)
    return InlineKeyboardMarkup(
        [[
            notification_action_button_for_user(
                context,
                notification_key=notification_key,
                user_id=user_id,
            ),
            InlineKeyboardButton(
                bot_module._tg("notification_dismiss", language=language),
                callback_data=bot_module._NOTIFICATION_DISMISS_CALLBACK,
            ),
        ]]
    )


def notification_wait_seconds(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> float:
    import englishbot.bot as bot_module

    recent_activity_at = recent_assignment_activity_by_user(context).get(user_id)
    if recent_activity_at is None:
        return 0.0
    now = datetime.now(UTC)
    elapsed = now - recent_activity_at
    active_session = bot_module._service(context).get_active_session(user_id=user_id)
    if active_session is not None and elapsed < bot_module._NOTIFICATION_ACTIVE_SESSION_ACTIVITY_WINDOW:
        remaining = bot_module._NOTIFICATION_ACTIVE_SESSION_ACTIVITY_WINDOW - elapsed
        return max(0.0, remaining.total_seconds())
    if elapsed < bot_module._NOTIFICATION_RECENT_ANSWER_GRACE_PERIOD:
        remaining = bot_module._NOTIFICATION_DELAY_AFTER_RECENT_ANSWER - elapsed
        return max(0.0, remaining.total_seconds())
    return 0.0


def notification_should_wait(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> bool:
    return notification_wait_seconds(context, user_id=user_id) > 0.0


def record_assignment_activity(context: ContextTypes.DEFAULT_TYPE, *, user_id: int) -> None:
    recent_assignment_activity_by_user(context)[user_id] = datetime.now(UTC)


def schedule_notification(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification,
) -> None:
    import englishbot.bot as bot_module

    delay_seconds = notification_wait_seconds(context, user_id=notification.recipient_user_id)
    not_before_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
    repository = pending_notification_repository(context)
    if repository is not None:
        repository.save(
            notification_key=notification.key,
            recipient_user_id=notification.recipient_user_id,
            text=notification.text,
            not_before_at=not_before_at,
        )
    else:
        pending = pending_notifications(context)
        pending[notification.key] = bot_module._PendingNotification(
            key=notification.key,
            recipient_user_id=notification.recipient_user_id,
            text=notification.text,
            not_before_at=not_before_at,
            created_at=datetime.now(UTC),
        )
    job_queue = bot_module._job_queue_or_none(context.application)
    if job_queue is None:
        return
    job_queue.run_once(
        bot_module._deliver_pending_notification_job,
        when=delay_seconds,
        data={"notification_key": notification.key},
        name=notification.key,
    )


async def deliver_notification_now(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification_key: str,
    force: bool = False,
) -> bool:
    repository = pending_notification_repository(context)
    notification = (
        repository.get(notification_key=notification_key)
        if repository is not None
        else pending_notifications(context).get(notification_key)
    )
    if notification is None:
        return False
    if not force and notification_should_wait(context, user_id=notification.recipient_user_id):
        return False
    try:
        await context.bot.send_message(
            chat_id=notification.recipient_user_id,
            text=notification.text,
            reply_markup=dismiss_notification_keyboard(
                context,
                notification_key=notification.key,
                user_id=notification.recipient_user_id,
            ),
        )
    except BadRequest:
        import englishbot.bot as bot_module

        bot_module.logger.debug("Failed to deliver notification key=%s", notification.key, exc_info=True)
    finally:
        if repository is not None:
            repository.remove(notification_key=notification_key)
        else:
            pending_notifications(context).pop(notification_key, None)
    return True


async def deliver_pending_notification_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    import englishbot.bot as bot_module

    job = getattr(context, "job", None)
    data = getattr(job, "data", None)
    notification_key = data.get("notification_key") if isinstance(data, dict) else None
    if not isinstance(notification_key, str):
        return
    delivered = await deliver_notification_now(context, notification_key=notification_key)
    if delivered:
        return
    repository = pending_notification_repository(context)
    if repository is not None:
        if repository.get(notification_key=notification_key) is None:
            return
    elif notification_key not in pending_notifications(context):
        return
    job_queue = bot_module._job_queue_or_none(context.application)
    if job_queue is None:
        return
    job_queue.run_once(
        bot_module._deliver_pending_notification_job,
        when=notification_wait_seconds(
            context,
            user_id=(
                repository.get(notification_key=notification_key).recipient_user_id
                if repository is not None
                else pending_notifications(context)[notification_key].recipient_user_id
            ),
        ),
        data={"notification_key": notification_key},
        name=notification_key,
    )


async def homework_assignment_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    import englishbot.bot as bot_module

    rows = bot_module._content_store(context).list_users_goal_overview()
    today = datetime.now(UTC).date().isoformat()
    for row in rows:
        user_id = int(row["user_id"])
        active_goals_count = int(row["active_goals_count"])
        if active_goals_count <= 0:
            continue
        schedule_notification(
            context,
            notification=bot_module._PendingNotification(
                key=f"assignment-reminder:{today}:{user_id}",
                recipient_user_id=user_id,
                text=bot_module._tg(
                    "homework_assignment_reminder"
                    if active_goals_count != 1
                    else "homework_assignment_reminder_one",
                    language=bot_module._telegram_ui_language_for_user_id(context, user_id=user_id),
                    goal_count=active_goals_count,
                ),
            ),
        )


async def flush_pending_notifications_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> None:
    repository = pending_notification_repository(context)
    pending_keys = (
        [item.key for item in repository.list(recipient_user_id=user_id)]
        if repository is not None
        else [
            key
            for key, notification in pending_notifications(context).items()
            if notification.recipient_user_id == user_id
        ]
    )
    for notification_key in pending_keys:
        await deliver_notification_now(context, notification_key=notification_key, force=True)


def schedule_assignment_assigned_notifications(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    goals: list,
) -> None:
    import englishbot.bot as bot_module

    for goal in goals:
        language = bot_module._telegram_ui_language_for_user_id(context, user_id=int(goal.user_id))
        goal_type_key = {
            bot_module.GoalType.NEW_WORDS.value: "goal_type_new_words",
            bot_module.GoalType.WORD_LEVEL_HOMEWORK.value: "goal_type_word_level_homework",
        }.get(goal.goal_type.value)
        period_label = bot_module._tg("goal_period_homework", language=language)
        goal_type_label = bot_module._tg(goal_type_key, language=language) if goal_type_key is not None else goal.goal_type.value
        emoji = bot_module._assignment_assigned_notification_emoji(goal_id=str(goal.id))
        text = "\n".join(
            [
                bot_module._tg("assignment_assigned_title", language=language, emoji=emoji),
                bot_module._tg(
                    (
                        "assignment_assigned_word_level_homework"
                        if goal.goal_type.value == bot_module.GoalType.WORD_LEVEL_HOMEWORK.value
                        else "assignment_assigned_new_words"
                    ),
                    language=language,
                    period=period_label,
                    goal_type=goal_type_label,
                    target=int(goal.target_count),
                ),
            ]
        )
        notification = bot_module._PendingNotification(
            key=f"assignment-assigned:{goal.goal_period.value}:{goal.id}:{goal.user_id}",
            recipient_user_id=goal.user_id,
            text=text,
        )
        schedule_notification(context, notification=notification)


def schedule_goal_completed_notifications(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    learner,
    completed_goals,
) -> None:
    import englishbot.bot as bot_module

    role_repository = bot_module._optional_bot_data(context, "telegram_user_role_repository")
    if role_repository is None:
        return
    memberships = role_repository.list_memberships()
    admin_ids = memberships.get("admin", frozenset())
    learner_name = getattr(learner, "username", None) or getattr(learner, "first_name", None) or str(learner.id)
    for admin_user_id in admin_ids:
        for goal in completed_goals:
            notification = bot_module._PendingNotification(
                key=f"assignment-completed:{goal.goal.id}:{admin_user_id}",
                recipient_user_id=admin_user_id,
                text=(
                    "Assignment completed: "
                    f"{learner_name} finished "
                    f"{goal.goal.goal_period.value}/{goal.goal.goal_type.value} "
                    f"{goal.goal.progress_count}/{goal.goal.target_count}."
                ),
            )
            schedule_notification(context, notification=notification)


async def notification_dismiss_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import englishbot.bot as bot_module

    query = update.callback_query
    if query is None:
        return
    await query.answer()
    await bot_module._delete_message_if_possible(context, message=query.message)
