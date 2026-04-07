from __future__ import annotations

import logging
from dataclasses import dataclass

from telegram.error import BadRequest
from telegram.ext import ContextTypes


logger = logging.getLogger(__name__)

EXPECTED_USER_INPUT_STATE_KEY = "expected_user_input_state"
IMAGE_REVIEW_STEP_TAG = "image_review_step"
IMAGE_REVIEW_CONTEXT_TAG = "image_review_context"
PUBLISHED_WORD_EDIT_TAG = "published_word_edit"
TRAINING_QUESTION_TAG = "training_question"
TRAINING_FEEDBACK_TAG = "training_feedback"
TTS_VOICE_TAG = "tts_voice"
ASSIGNMENT_PROGRESS_TAG = "assignment_progress"
CHAT_MENU_TAG = "chat_menu"


@dataclass(frozen=True, slots=True)
class TelegramExpectedInputPrompt:
    chat_id: int
    message_id: int


def lesson_interaction_id(*, session_id: str) -> str:
    return session_id


def chat_menu_interaction_id(*, user_id: int) -> str:
    return f"chat-menu:{user_id}"


def published_word_edit_interaction_id(*, user_id: int) -> str:
    return f"published-word-edit:{user_id}"


def tts_voice_interaction_id(*, user_id: int) -> str:
    return f"tts-voice:{user_id}"


async def replace_lesson_question_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    session_id: str,
    message,
    fallback_chat_id: int | None = None,
) -> None:
    await replace_flow_message(
        context,
        flow_id=lesson_interaction_id(session_id=session_id),
        tag=TRAINING_QUESTION_TAG,
        message=message,
        fallback_chat_id=fallback_chat_id,
    )


async def replace_lesson_feedback_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    session_id: str,
    message,
    fallback_chat_id: int | None = None,
) -> None:
    await replace_flow_message(
        context,
        flow_id=lesson_interaction_id(session_id=session_id),
        tag=TRAINING_FEEDBACK_TAG,
        message=message,
        fallback_chat_id=fallback_chat_id,
    )


async def finish_lesson_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    session_id: str,
    clear_expected_input_prompt: bool = False,
) -> None:
    await finish_interaction(
        context,
        flow_id=lesson_interaction_id(session_id=session_id),
        tags=(TRAINING_QUESTION_TAG, TRAINING_FEEDBACK_TAG),
        clear_expected_input_prompt=clear_expected_input_prompt,
    )


async def start_published_word_edit_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    source_message,
    helper_message=None,
    fallback_chat_id: int | None = None,
) -> None:
    await finish_published_word_edit_interaction(
        context,
        user_id=user_id,
        keep_source_message=True,
        source_message=source_message,
    )
    from englishbot.telegram.flow_tracking import track_flow_message

    flow_id = published_word_edit_interaction_id(user_id=user_id)
    track_flow_message(
        context,
        flow_id=flow_id,
        tag=PUBLISHED_WORD_EDIT_TAG,
        message=source_message,
        fallback_chat_id=fallback_chat_id,
    )
    if helper_message is not None:
        track_flow_message(
            context,
            flow_id=flow_id,
            tag=PUBLISHED_WORD_EDIT_TAG,
            message=helper_message,
            fallback_chat_id=fallback_chat_id,
        )


async def finish_published_word_edit_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    keep_source_message: bool = False,
    source_message=None,
) -> None:
    from englishbot.telegram.flow_tracking import (
        delete_tracked_messages,
        tracked_messages_except_source_message,
    )
    import englishbot.bot as bot_module

    registry = bot_module._telegram_flow_messages(context)
    if registry is None:
        clear_expected_user_input(context)
        return
    flow_id = published_word_edit_interaction_id(user_id=user_id)
    tracked_messages = registry.list(
        flow_id=flow_id,
        tag=PUBLISHED_WORD_EDIT_TAG,
    )
    if keep_source_message and source_message is not None:
        tracked_messages = tracked_messages_except_source_message(
            tracked_messages=tracked_messages,
            message=source_message,
        )
    await delete_tracked_messages(
        context,
        tracked_messages=tracked_messages,
    )
    registry.clear(flow_id=flow_id, tag=PUBLISHED_WORD_EDIT_TAG)
    clear_expected_user_input(context)


def remember_expected_user_input(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int | None,
    message_id: int | None,
) -> None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return
    if chat_id is None or message_id is None:
        return
    user_data[EXPECTED_USER_INPUT_STATE_KEY] = {
        "chat_id": chat_id,
        "message_id": message_id,
    }


def clear_expected_user_input(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return
    user_data.pop(EXPECTED_USER_INPUT_STATE_KEY, None)


def get_expected_user_input_prompt(
    context: ContextTypes.DEFAULT_TYPE,
) -> TelegramExpectedInputPrompt | None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return None
    stored = user_data.get(EXPECTED_USER_INPUT_STATE_KEY)
    if not isinstance(stored, dict):
        return None
    chat_id = stored.get("chat_id")
    message_id = stored.get("message_id")
    if not isinstance(chat_id, int) or not isinstance(message_id, int):
        return None
    return TelegramExpectedInputPrompt(chat_id=chat_id, message_id=message_id)


async def edit_expected_user_input_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    text: str,
    reply_markup,
) -> bool:
    prompt = get_expected_user_input_prompt(context)
    if prompt is None:
        return False
    bot = getattr(context, "bot", None)
    if bot is None:
        return False
    try:
        await bot.edit_message_text(
            chat_id=prompt.chat_id,
            message_id=prompt.message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except BadRequest as error:
        if "message is not modified" in str(error).lower():
            return True
        logger.debug(
            "Failed to edit expected-input prompt chat_id=%s message_id=%s",
            prompt.chat_id,
            prompt.message_id,
            exc_info=True,
        )
        return False
    return True


async def replace_flow_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    tag: str,
    message,
    fallback_chat_id: int | None = None,
) -> None:
    from englishbot.telegram.flow_tracking import (
        delete_tracked_flow_messages,
        track_flow_message,
    )

    await delete_tracked_flow_messages(
        context,
        flow_id=flow_id,
        tag=tag,
    )
    track_flow_message(
        context,
        flow_id=flow_id,
        tag=tag,
        message=message,
        fallback_chat_id=fallback_chat_id,
    )


async def finish_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    tags: tuple[str, ...] = (),
    clear_expected_input_prompt: bool = False,
) -> None:
    from englishbot.telegram.flow_tracking import delete_tracked_flow_messages

    for tag in tags:
        await delete_tracked_flow_messages(
            context,
            flow_id=flow_id,
            tag=tag,
        )
    if clear_expected_input_prompt:
        clear_expected_user_input(context)
