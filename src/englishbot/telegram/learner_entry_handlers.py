from __future__ import annotations

import logging
from collections.abc import Callable

from telegram.ext import ContextTypes

from englishbot.application.services import ApplicationError, InvalidSessionStateError
from englishbot.domain.models import TrainingMode

logger = logging.getLogger(__name__)


async def continue_session_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    service: Callable,
    clear_medium_task_state: Callable,
    tg: Callable,
    expects_text_answer_for_question: Callable,
    record_assignment_activity: Callable,
    assignment_kind_from_session: Callable,
    send_or_update_assignment_progress_message: Callable,
    send_question: Callable,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    logger.info("User %s chose to continue the active session", user.id)
    try:
        question = service(context).get_current_question(user_id=user.id)
    except InvalidSessionStateError:
        context.user_data["awaiting_text_answer"] = False
        clear_medium_task_state(context)
        await query.edit_message_text(tg("no_active_session_send_start", context=context, user=user))
        return
    record_assignment_activity(context, user_id=user.id)
    context.user_data["awaiting_text_answer"] = expects_text_answer_for_question(question)
    await query.edit_message_text(tg("continue_current_session", context=context, user=user))
    active_session = service(context).get_active_session(user_id=user.id)
    assignment_kind = assignment_kind_from_session(active_session)
    callback_message = getattr(query, "message", None)
    if assignment_kind is not None and callback_message is not None:
        await send_or_update_assignment_progress_message(
            context,
            message=callback_message,
            user=user,
            kind=assignment_kind,
            active_session=active_session,
        )
    await send_question(update, context, question)


async def restart_session_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    service: Callable,
    clear_medium_task_state: Callable,
    tg: Callable,
    send_view: Callable,
    start_menu_view: Callable,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    logger.info("User %s chose to discard the active session", user.id)
    service(context).discard_active_session(user_id=user.id)
    context.user_data["awaiting_text_answer"] = False
    clear_medium_task_state(context)
    await query.edit_message_text(tg("previous_session_discarded", context=context, user=user))
    await send_view(
        query.message,
        start_menu_view(context=context, user=user),
    )


async def topic_selected_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    service: Callable,
    lesson_selection_view: Callable,
    mode_selection_view: Callable,
    tg: Callable,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    topic_id = query.data.removeprefix("topic:")
    lesson_selection = service(context).list_lessons_by_topic(topic_id=topic_id)
    if lesson_selection.has_lessons:
        lesson_view = lesson_selection_view(
            text=tg("choose_lesson", context=context, user=update.effective_user),
            topic_id=topic_id,
            lessons=lesson_selection.lessons,
            context=context,
            user=update.effective_user,
        )
        await query.edit_message_text(
            lesson_view.text,
            reply_markup=lesson_view.reply_markup,
        )
        return
    mode_view = mode_selection_view(
        text=tg("choose_mode", context=context, user=update.effective_user),
        topic_id=topic_id,
        lesson_id=None,
        context=context,
        user=update.effective_user,
    )
    await query.edit_message_text(
        mode_view.text,
        reply_markup=mode_view.reply_markup,
    )


async def lesson_selected_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode_selection_view: Callable,
    tg: Callable,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _, topic_id, lesson_id = query.data.split(":")
    selected_lesson_id = None if lesson_id == "all" else lesson_id
    mode_view = mode_selection_view(
        text=tg("choose_mode", context=context, user=update.effective_user),
        topic_id=topic_id,
        lesson_id=selected_lesson_id,
        context=context,
        user=update.effective_user,
    )
    await query.edit_message_text(
        mode_view.text,
        reply_markup=mode_view.reply_markup,
    )


async def mode_selected_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    service: Callable,
    start_training_session_with_ui_language: Callable,
    telegram_ui_language: Callable,
    tg: Callable,
    expects_text_answer_for_question: Callable,
    send_question: Callable,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _, topic_id, lesson_id, mode_value = query.data.split(":")
    resolved_service = service(context)
    user = update.effective_user
    if user is None:
        return
    selected_lesson_id = None if lesson_id == "all" else lesson_id
    try:
        question = start_training_session_with_ui_language(
            resolved_service,
            user_id=user.id,
            topic_id=topic_id,
            lesson_id=selected_lesson_id,
            mode=TrainingMode(mode_value),
            ui_language=telegram_ui_language(context, user),
        )
    except ApplicationError as error:
        await query.edit_message_text(str(error))
        return
    context.user_data["awaiting_text_answer"] = expects_text_answer_for_question(question)
    await query.edit_message_text(tg("session_started", context=context, user=user))
    await send_question(update, context, question)


async def game_mode_placeholder_callback_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    tg: Callable,
    start_submenu_keyboard: Callable,
    telegram_ui_language: Callable,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await query.edit_message_text(
        tg("game_mode_coming_soon", context=context, user=user),
        reply_markup=start_submenu_keyboard(language=telegram_ui_language(context, user)),
    )
