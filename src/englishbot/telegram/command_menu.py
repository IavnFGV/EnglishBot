from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, time

from telegram import BotCommand, BotCommandScopeChat, ReplyKeyboardMarkup

from englishbot.presentation.telegram_editor_ui import chat_menu_keyboard as ui_chat_menu_keyboard
from englishbot.presentation.telegram_menu_access import (
    DEFAULT_TELEGRAM_COMMAND_SPECS,
    PERMISSION_WORDS_ADD,
    TelegramCommandSpec,
    TelegramMenuAccessPolicy,
)


def visible_command_specs(
    bot_data: Mapping[str, object],
    *,
    user_id: int | None,
    only_chat_menu: bool = False,
) -> tuple[TelegramCommandSpec, ...]:
    return TelegramMenuAccessPolicy.from_bot_data(bot_data).visible_commands(
        user_id,
        command_specs=DEFAULT_TELEGRAM_COMMAND_SPECS,
        only_chat_menu=only_chat_menu,
    )


def visible_command_rows(
    bot_data: Mapping[str, object],
    *,
    user_id: int | None,
) -> list[list[str]]:
    commands = {
        spec.command
        for spec in visible_command_specs(
            bot_data,
            user_id=user_id,
            only_chat_menu=True,
        )
    }
    rows = [
        ["/start", "/help"],
        ["/version", "/words"],
    ]
    if "assign" in commands:
        rows.append(["/assign"])
    if "add_words" in commands:
        rows.append(["/add_words", "/cancel"])
    return rows


def chat_menu_keyboard(*, command_rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ui_chat_menu_keyboard(command_rows=command_rows)


async def post_init_command_setup(
    app,
    *,
    deliver_pending_notification_job,
    homework_assignment_reminder_job,
    daily_assignment_reminder_time: time,
    job_queue_or_none: Callable[[object], object | None],
) -> None:
    policy = TelegramMenuAccessPolicy.from_bot_data(app.bot_data)
    public_commands = [
        BotCommand(spec.command, spec.description)
        for spec in policy.visible_commands(user_id=None)
    ]
    await app.bot.set_my_commands(public_commands)

    elevated_user_ids: set[int] = set()
    for role_name, user_ids in policy.role_memberships.items():
        if role_name == "user":
            continue
        role_permissions = policy.role_permissions.get(role_name, frozenset())
        if "*" in role_permissions or PERMISSION_WORDS_ADD in role_permissions:
            elevated_user_ids.update(user_ids)
    for user_id in sorted(elevated_user_ids):
        scoped_commands = [
            BotCommand(spec.command, spec.description)
            for spec in policy.visible_commands(user_id=user_id)
        ]
        await app.bot.set_my_commands(scoped_commands, scope=BotCommandScopeChat(chat_id=user_id))

    notification_repository = app.bot_data.get("pending_telegram_notification_repository")
    job_queue = job_queue_or_none(app)
    if notification_repository is None or job_queue is None:
        return

    now = datetime.now(UTC)
    for notification in notification_repository.list():
        delay_seconds = max(0.0, (notification.not_before_at - now).total_seconds())
        job_queue.run_once(
            deliver_pending_notification_job,
            when=delay_seconds,
            data={"notification_key": notification.key},
            name=notification.key,
        )
    job_queue.run_daily(
        homework_assignment_reminder_job,
        time=daily_assignment_reminder_time,
        name="homework-assignment-reminder",
    )
