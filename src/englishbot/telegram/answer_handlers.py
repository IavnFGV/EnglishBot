from __future__ import annotations

import logging
from collections.abc import Callable

from telegram.ext import ContextTypes

from englishbot.application.homework_progress_use_cases import AssignmentSessionKind
from englishbot.domain.models import SessionItem, TrainingMode

logger = logging.getLogger("englishbot.bot")


async def hard_skip_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    tg: Callable,
    consume_callback_token: Callable,
    active_training_session: Callable,
    service: Callable,
    assignment_kind_from_session: Callable,
    process_answer: Callable,
    content_store: Callable,
    send_question: Callable,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, _, token = parts
    payload = consume_callback_token(
        context=context,
        user_id=int(user.id),
        token=token,
        fallback_key="session_id",
    )
    if payload is None:
        return
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return
    active_session = active_training_session(context, user_id=user.id)
    if active_session is None or active_session.id != session_id:
        return
    try:
        current_question = service(context).get_current_question(user_id=user.id)
    except Exception:
        return
    if (
        current_question.session_id != session_id
        or current_question.mode is not TrainingMode.HARD
    ):
        return
    assignment_kind = assignment_kind_from_session(active_session)
    if assignment_kind is not AssignmentSessionKind.HOMEWORK:
        await process_answer(update, context, "__skip_hard__")
        return
    if active_session.current_index >= len(active_session.items):
        return
    current_item = active_session.items[active_session.current_index]
    active_session.items[active_session.current_index] = SessionItem(
        order=current_item.order,
        vocabulary_item_id=current_item.vocabulary_item_id,
        mode=TrainingMode.MEDIUM,
    )
    active_session.combo_correct_streak = 0
    active_session.combo_hard_active = False
    active_session.bonus_item_id = None
    active_session.bonus_mode = None
    content_store(context).save_session(active_session)
    context.user_data["awaiting_text_answer"] = False
    next_question = service(context).get_current_question(user_id=user.id)
    await send_question(update, context, next_question)


async def medium_answer_callback_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    service: Callable,
    medium_task_lock: Callable,
    get_medium_task_state: Callable,
    set_medium_task_state: Callable,
    clear_medium_task_state: Callable,
    medium_task_is_complete: Callable,
    build_medium_question_view: Callable,
    edit_training_question_view: Callable,
    medium_task_answer_text: Callable,
    process_answer: Callable,
    medium_task_state_type,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    async with medium_task_lock(context):
        state = get_medium_task_state(context)
        message = getattr(query, "message", None)
        message_id = getattr(message, "message_id", None)
        if state is None:
            logger.debug("Medium callback ignored: no medium state user_id=%s data=%s", user.id, query.data)
            return
        if state.message_id is None:
            logger.debug("Medium callback ignored: state has no message_id user_id=%s data=%s", user.id, query.data)
            return
        if message_id != state.message_id:
            logger.debug(
                "Medium callback ignored: stale message user_id=%s data=%s callback_message_id=%s state_message_id=%s",
                user.id,
                query.data,
                message_id,
                state.message_id,
            )
            return
        active_session = service(context).get_active_session(user_id=user.id)
        if active_session is None:
            logger.debug("Medium callback ignored: no active session user_id=%s data=%s", user.id, query.data)
            return
        current_question = service(context).get_current_question(user_id=user.id)
        if (
            current_question.mode is not TrainingMode.MEDIUM
            or current_question.session_id != state.session_id
            or current_question.item_id != state.item_id
        ):
            logger.debug(
                "Medium callback ignored: question mismatch user_id=%s data=%s current_mode=%s current_session_id=%s state_session_id=%s current_item_id=%s state_item_id=%s",
                user.id,
                query.data,
                current_question.mode.value,
                current_question.session_id,
                state.session_id,
                current_question.item_id,
                state.item_id,
            )
            clear_medium_task_state(context)
            return
        if query.data == "medium:backspace":
            if not state.selected_letter_indexes:
                logger.debug("Medium callback ignored: backspace on empty answer user_id=%s", user.id)
                return
            state = medium_task_state_type(
                session_id=state.session_id,
                item_id=state.item_id,
                target_word=state.target_word,
                shuffled_letters=state.shuffled_letters,
                selected_letter_indexes=state.selected_letter_indexes[:-1],
                message_id=state.message_id,
            )
        elif query.data.startswith("medium:noop:"):
            logger.debug("Medium callback ignored: noop button user_id=%s data=%s", user.id, query.data)
            return
        elif query.data.startswith("medium:pick:"):
            if medium_task_is_complete(state):
                logger.debug("Medium callback ignored: answer already complete user_id=%s data=%s", user.id, query.data)
                return
            try:
                picked_index = int(query.data.rsplit(":", 1)[-1])
            except ValueError:
                logger.debug("Medium callback ignored: invalid pick payload user_id=%s data=%s", user.id, query.data)
                return
            if picked_index < 0 or picked_index >= len(state.shuffled_letters):
                logger.debug(
                    "Medium callback ignored: pick index out of range user_id=%s data=%s index=%s letter_count=%s",
                    user.id,
                    query.data,
                    picked_index,
                    len(state.shuffled_letters),
                )
                return
            if picked_index in state.selected_letter_indexes:
                logger.debug(
                    "Medium callback ignored: letter already used user_id=%s data=%s index=%s",
                    user.id,
                    query.data,
                    picked_index,
                )
                return
            state = medium_task_state_type(
                session_id=state.session_id,
                item_id=state.item_id,
                target_word=state.target_word,
                shuffled_letters=state.shuffled_letters,
                selected_letter_indexes=(*state.selected_letter_indexes, picked_index),
                message_id=state.message_id,
            )
        elif query.data == "medium:check":
            if not medium_task_is_complete(state):
                logger.debug("Medium callback ignored: check before complete user_id=%s", user.id)
                return
        else:
            logger.debug("Medium callback ignored: unsupported payload user_id=%s data=%s", user.id, query.data)
            return
        set_medium_task_state(context, state)
        if query.data == "medium:check":
            await edit_training_question_view(
                query,
                view=build_medium_question_view(current_question, state=state, context=context, user=user),
            )
            clear_medium_task_state(context)
            await process_answer(update, context, medium_task_answer_text(state))
            return
        await edit_training_question_view(
            query,
            view=build_medium_question_view(current_question, state=state, context=context, user=user),
        )


async def choice_answer_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    process_answer: Callable,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    answer = query.data.removeprefix("answer:")
    await process_answer(update, context, answer)


async def text_answer_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    service: Callable,
    clear_medium_task_state: Callable,
    tg: Callable,
    process_answer: Callable,
) -> None:
    if not context.user_data.get("awaiting_text_answer"):
        return
    message = update.effective_message
    user = update.effective_user
    if message is None or message.text is None or user is None:
        return
    if service(context).get_active_session(user_id=user.id) is None:
        context.user_data["awaiting_text_answer"] = False
        clear_medium_task_state(context)
        await message.reply_text(tg("no_active_session_begin", context=context, user=user))
        return
    await process_answer(update, context, message.text)
