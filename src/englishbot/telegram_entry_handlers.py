from __future__ import annotations

import logging
from collections.abc import Callable

from telegram.ext import ContextTypes

from englishbot.domain.models import TrainingMode
from englishbot.presentation.telegram_views import (
    build_active_session_exists_view,
    build_status_view,
)

logger = logging.getLogger(__name__)


async def start_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    send_view: Callable,
    telegram_user_login_repository: Callable,
    service: Callable,
    tg: Callable,
    active_session_topic_label: Callable,
    active_session_lesson_label: Callable,
    active_session_keyboard: Callable,
    telegram_ui_language: Callable,
    start_menu_view: Callable,
    ensure_chat_menu_message: Callable,
) -> None:
    message = update.effective_message
    if message is None:
        return
    user = update.effective_user
    if user is not None:
        telegram_user_login_repository(context).record(
            user_id=user.id,
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
            language_code=getattr(user, "language_code", None),
        )
        logger.info("User %s opened /start", user.id)
        active_session = service(context).get_active_session(user_id=user.id)
        if active_session is not None:
            context.user_data["awaiting_text_answer"] = active_session.mode is TrainingMode.HARD
            await send_view(
                message,
                build_active_session_exists_view(
                    text=tg(
                        "active_session_exists",
                        context=context,
                        user=user,
                        topic_id=active_session_topic_label(
                            context=context,
                            user=user,
                            topic_id=active_session.topic_id,
                            source_tag=active_session.source_tag,
                            lesson_id=active_session.lesson_id,
                        ),
                        lesson_id=active_session_lesson_label(
                            context=context,
                            user=user,
                            topic_id=active_session.topic_id,
                            lesson_id=active_session.lesson_id,
                            source_tag=active_session.source_tag,
                        ),
                        mode=active_session.mode.value,
                        current_position=active_session.current_position,
                        total_items=active_session.total_items,
                    ),
                    reply_markup=active_session_keyboard(
                        language=telegram_ui_language(context, user),
                    ),
                ),
            )
            return
    await send_view(
        message,
        start_menu_view(context=context, user=user),
    )
    if user is not None:
        await ensure_chat_menu_message(context, message=message, user=user)


async def help_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    send_view: Callable,
    visible_command_specs: Callable,
    help_command_text: dict[str, str],
    tg: Callable,
    help_view: Callable,
    ensure_chat_menu_message: Callable,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    visible_commands = visible_command_specs(
        context,
        user_id=(user.id if user is not None else None),
    )
    commands = [
        f"/{spec.command} - {help_command_text.get(spec.command, spec.description.lower())}"
        for spec in visible_commands
    ]
    await send_view(
        message,
        help_view(
            text=tg("help_title", context=context, user=user, commands="\n".join(commands)),
            context=context,
            user=user,
        ),
    )
    if user is not None:
        await ensure_chat_menu_message(context, message=message, user=user)


async def version_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    send_view: Callable,
    runtime_version_info: Callable,
    tg: Callable,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    version_info = runtime_version_info(context)
    lines = [
        tg("version_title", context=context, user=user),
        tg(
            "version_line",
            context=context,
            user=user,
            version=version_info.package_version,
        ),
    ]
    if version_info.build_number:
        lines.append(
            tg(
                "build_line",
                context=context,
                user=user,
                build_number=version_info.build_number,
            )
        )
    if version_info.git_sha:
        lines.append(
            tg(
                "git_sha_line",
                context=context,
                user=user,
                git_sha=version_info.git_sha,
            )
        )
    if version_info.git_branch:
        lines.append(
            tg(
                "git_branch_line",
                context=context,
                user=user,
                branch=version_info.git_branch,
            )
        )
    await send_view(
        message,
        build_status_view(text="\n".join(lines)),
    )
