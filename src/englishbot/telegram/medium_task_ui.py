from __future__ import annotations

import asyncio

from telegram.ext import ContextTypes

from englishbot import bot as bot_module
from englishbot.telegram.buttons import InlineKeyboardButton
from englishbot.telegram.question_delivery import (
    build_medium_question_view as delivery_build_medium_question_view,
    medium_task_answer_text as delivery_medium_task_answer_text,
    medium_task_is_complete as delivery_medium_task_is_complete,
    medium_task_keyboard as delivery_medium_task_keyboard,
)
from englishbot.telegram.training_markup import tts_buttons as training_tts_buttons


def clear_medium_task_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_module._pop_user_data(context, bot_module._MEDIUM_TASK_STATE_KEY, default=None)


def build_medium_task_state(
    question,
    *,
    message_id: int | None = None,
):
    letter_source = question.letter_hint or question.correct_answer
    shuffled_letters = tuple(character for character in letter_source if not character.isspace())
    return bot_module._MediumTaskState(
        session_id=question.session_id,
        item_id=question.item_id,
        target_word=question.correct_answer,
        shuffled_letters=shuffled_letters,
        selected_letter_indexes=(),
        message_id=message_id,
    )


def get_medium_task_state(context: ContextTypes.DEFAULT_TYPE):
    state = bot_module._optional_user_data(context, bot_module._MEDIUM_TASK_STATE_KEY)
    if isinstance(state, bot_module._MediumTaskState):
        return state
    return None


def set_medium_task_state(context: ContextTypes.DEFAULT_TYPE, state) -> None:
    bot_module._set_user_data(context, bot_module._MEDIUM_TASK_STATE_KEY, state)


def medium_task_lock(context: ContextTypes.DEFAULT_TYPE) -> asyncio.Lock:
    user_data = bot_module._user_data_or_none(context)
    if user_data is None:
        return asyncio.Lock()
    lock = user_data.get(bot_module._MEDIUM_TASK_LOCK_KEY)
    if isinstance(lock, asyncio.Lock):
        return lock
    created_lock = asyncio.Lock()
    user_data[bot_module._MEDIUM_TASK_LOCK_KEY] = created_lock
    return created_lock


def medium_task_is_complete(state) -> bool:
    return delivery_medium_task_is_complete(state)


def medium_task_answer_text(state) -> str:
    return delivery_medium_task_answer_text(state)


def medium_task_keyboard(
    state,
    *,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    user=None,
):
    return delivery_medium_task_keyboard(
        state,
        context=context,
        user=user,
        tts_service_enabled=bot_module._tts_service_enabled,
        tts_buttons=lambda *, context, user: training_tts_buttons(
            context=context,
            user=user,
            tg=bot_module._tg,
            tts_has_multiple_voices=bot_module._tts_has_multiple_voices,
        ),
        tg=bot_module._tg,
        inline_keyboard_button_type=InlineKeyboardButton,
    )


def build_medium_question_view(
    question,
    *,
    state,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    user=None,
):
    return delivery_build_medium_question_view(
        question,
        state=state,
        context=context,
        user=user,
        resolve_existing_image_path=bot_module.resolve_existing_image_path,
        tts_service_enabled=bot_module._tts_service_enabled,
        tts_buttons=lambda *, context, user: training_tts_buttons(
            context=context,
            user=user,
            tg=bot_module._tg,
            tts_has_multiple_voices=bot_module._tts_has_multiple_voices,
        ),
        tg=bot_module._tg,
        inline_keyboard_button_type=InlineKeyboardButton,
    )
