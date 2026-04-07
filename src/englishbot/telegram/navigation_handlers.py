from __future__ import annotations

import logging
from collections.abc import Callable

from telegram.error import BadRequest
from telegram.ext import ContextTypes

from englishbot.application.homework_progress_use_cases import AssignmentSessionKind

logger = logging.getLogger(__name__)


async def assign_menu_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    send_view: Callable,
    telegram_user_login_repository: Callable,
    tg: Callable,
    assign_menu_view: Callable,
    ensure_chat_menu_message: Callable,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    telegram_user_login_repository(context).record(
        user_id=user.id,
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
        language_code=getattr(user, "language_code", None),
    )
    await send_view(
        message,
        assign_menu_view(
            text=tg("assign_menu_prompt", context=context, user=user),
            context=context,
            user=user,
        ),
    )
    await ensure_chat_menu_message(context, message=message, user=user)


async def words_menu_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    send_view: Callable,
    tg: Callable,
    words_menu_view: Callable,
    ensure_chat_menu_message: Callable,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    await send_view(
        message,
        words_menu_view(
            text=tg("words_menu_prompt", context=context, user=user),
            context=context,
            user=user,
        ),
    )
    if user is not None:
        await ensure_chat_menu_message(context, message=message, user=user)


async def assign_menu_callback_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    edit_text_view: Callable,
    tg: Callable,
    assign_menu_view: Callable,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    try:
        await edit_text_view(
            query,
            assign_menu_view(
                text=tg("assign_menu_title", context=context, user=update.effective_user),
                context=context,
                user=update.effective_user,
            ),
        )
    except BadRequest as error:
        if "message is not modified" in str(error).lower():
            logger.debug("Assign menu message unchanged")
            return
        raise


async def words_menu_callback_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    edit_text_view: Callable,
    tg: Callable,
    words_menu_view: Callable,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    try:
        await edit_text_view(
            query,
            words_menu_view(
                text=tg("words_menu_title", context=context, user=update.effective_user),
                context=context,
                user=update.effective_user,
            ),
        )
    except BadRequest as error:
        if "message is not modified" in str(error).lower():
            logger.debug("Words menu message unchanged")
            return
        raise


async def words_topics_callback_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    service: Callable,
    topic_selection_view: Callable,
    edit_text_view: Callable,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    topics = service(context).list_topics()
    topic_view = topic_selection_view(
        text="Choose a topic to start training.",
        topics=topics,
        context=context,
        user=update.effective_user,
    )
    await edit_text_view(query, topic_view)


async def start_menu_callback_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    edit_text_view: Callable,
    start_menu_view: Callable,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await edit_text_view(query, start_menu_view(context=context, user=user))


async def start_assignment_round_callback_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    start_assignment_round_use_case: Callable,
    execute_assignment_start_use_case: Callable,
    telegram_ui_language: Callable,
    tg: Callable,
    start_submenu_keyboard: Callable,
    expects_text_answer_for_question: Callable,
    send_or_update_assignment_progress_message: Callable,
    send_question: Callable,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    kind = AssignmentSessionKind.HOMEWORK
    try:
        use_case = start_assignment_round_use_case(context)
        question = execute_assignment_start_use_case(
            use_case,
            user_id=user.id,
            kind=kind,
            ui_language=telegram_ui_language(context, user),
        )
    except ValueError:
        await query.edit_message_text(
            tg("start_assignment_empty", context=context, user=user),
            reply_markup=start_submenu_keyboard(language=telegram_ui_language(context, user)),
        )
        return
    context.user_data["awaiting_text_answer"] = expects_text_answer_for_question(question)
    callback_message = getattr(query, "message", None)
    if callback_message is not None:
        await send_or_update_assignment_progress_message(
            context,
            message=callback_message,
            user=user,
            kind=kind,
        )
    await send_question(update, context, question)


async def start_assignment_unavailable_callback_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    tg: Callable,
    telegram_ui_language: Callable,
    start_submenu_keyboard: Callable,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await query.edit_message_text(
        tg("start_assignment_empty", context=context, user=user),
        reply_markup=start_submenu_keyboard(language=telegram_ui_language(context, user)),
    )
