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
ADD_WORDS_AWAITING_TEXT_MODE = "awaiting_raw_text"
ADD_WORDS_AWAITING_EDIT_TEXT_MODE = "awaiting_edit_text"
PUBLISHED_WORD_AWAITING_EDIT_TEXT_MODE = "awaiting_published_word_edit_text"


@dataclass(frozen=True, slots=True)
class TelegramExpectedInputPrompt:
    chat_id: int
    message_id: int


@dataclass(frozen=True, slots=True)
class ImageReviewPhotoAttachInteraction:
    flow_id: str
    item_id: str


@dataclass(frozen=True, slots=True)
class ImageReviewTextEditInteraction:
    mode: str
    flow_id: str
    item_id: str


@dataclass(frozen=True, slots=True)
class AddWordsDraftEditInteraction:
    flow_id: str


@dataclass(frozen=True, slots=True)
class PublishedWordEditPromptInteraction:
    topic_id: str
    item_id: str


@dataclass(frozen=True, slots=True)
class AdminGoalCreationState:
    goal_period: str | None = None
    goal_type: str | None = None
    target_count: int | None = None
    source: str | None = None
    deadline_date: str | None = None
    manual_word_ids: frozenset[str] = frozenset()
    recipient_user_ids: frozenset[int] = frozenset()
    recipients_page: int = 0


ADMIN_GOAL_STATE_KEYS = (
    "admin_goal_period",
    "admin_goal_type",
    "admin_goal_target_count",
    "admin_goal_source",
    "admin_goal_deadline_date",
    "admin_goal_manual_word_ids",
    "admin_goal_recipient_user_ids",
    "admin_goal_recipients_page",
)


def lesson_interaction_id(*, session_id: str) -> str:
    return session_id


def chat_menu_interaction_id(*, user_id: int) -> str:
    return f"chat-menu:{user_id}"


def published_word_edit_interaction_id(*, user_id: int) -> str:
    return f"published-word-edit:{user_id}"


def tts_voice_interaction_id(*, user_id: int) -> str:
    return f"tts-voice:{user_id}"


def assignment_progress_interaction_id(
    *,
    user_id: int,
    kind_value: str,
    goal_id: str | None = None,
) -> str:
    suffix = f":{goal_id}" if goal_id else ""
    return f"assignment-progress:{user_id}:{kind_value}{suffix}"


async def replace_chat_menu_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
    user,
) -> None:
    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        return
    import englishbot.bot as bot_module

    sent_message = await bot_module.send_telegram_view(
        message,
        bot_module._quick_actions_view(context=context, user=user),
    )
    if sent_message is None:
        return
    await replace_flow_message(
        context,
        flow_id=chat_menu_interaction_id(user_id=user_id),
        tag=CHAT_MENU_TAG,
        message=sent_message,
        fallback_chat_id=bot_module._message_chat_id(message),
    )


async def replace_tts_voice_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    message,
    voice,
):
    import englishbot.bot as bot_module

    sent_message = await message.reply_voice(voice=voice)
    await replace_flow_message(
        context,
        flow_id=tts_voice_interaction_id(user_id=user_id),
        tag=TTS_VOICE_TAG,
        message=sent_message,
        fallback_chat_id=bot_module._message_chat_id(message),
    )
    return sent_message


async def replace_image_review_context_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    message,
    fallback_chat_id: int | None = None,
) -> None:
    await replace_flow_message(
        context,
        flow_id=flow_id,
        tag=IMAGE_REVIEW_CONTEXT_TAG,
        message=message,
        fallback_chat_id=fallback_chat_id,
    )


async def replace_flow_messages(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    tag: str,
    messages: list,
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
    for message in messages:
        track_flow_message(
            context,
            flow_id=flow_id,
            tag=tag,
            message=message,
            fallback_chat_id=fallback_chat_id,
        )


async def replace_image_review_step_messages(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    messages: list,
    fallback_chat_id: int | None = None,
) -> None:
    await replace_flow_messages(
        context,
        flow_id=flow_id,
        tag=IMAGE_REVIEW_STEP_TAG,
        messages=messages,
        fallback_chat_id=fallback_chat_id,
    )


async def finish_image_review_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
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
        return
    tracked_messages = registry.list(flow_id=flow_id)
    if keep_source_message and source_message is not None:
        tracked_messages = tracked_messages_except_source_message(
            tracked_messages=tracked_messages,
            message=source_message,
        )
    await delete_tracked_messages(
        context,
        tracked_messages=tracked_messages,
    )
    registry.clear(flow_id=flow_id)


def start_image_review_photo_attach_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    item_id: str,
) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data["words_flow_mode"] = "awaiting_image_review_photo"
        user_data["image_review_flow_id"] = flow_id
        user_data["image_review_item_id"] = item_id


def get_image_review_photo_attach_interaction(
    context: ContextTypes.DEFAULT_TYPE,
) -> ImageReviewPhotoAttachInteraction | None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return None
    if user_data.get("words_flow_mode") != "awaiting_image_review_photo":
        return None
    flow_id = user_data.get("image_review_flow_id")
    item_id = user_data.get("image_review_item_id")
    if not isinstance(flow_id, str) or not flow_id:
        return None
    if not isinstance(item_id, str) or not item_id:
        return None
    return ImageReviewPhotoAttachInteraction(flow_id=flow_id, item_id=item_id)


def clear_image_review_photo_attach_interaction(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data.pop("words_flow_mode", None)
        user_data.pop("image_review_flow_id", None)
        user_data.pop("image_review_item_id", None)


def has_active_interaction_mode(context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_data = getattr(context, "user_data", None)
    return isinstance(user_data, dict) and user_data.get("words_flow_mode") is not None


def start_add_words_text_interaction(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data["words_flow_mode"] = ADD_WORDS_AWAITING_TEXT_MODE


def is_add_words_text_interaction(context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_data = getattr(context, "user_data", None)
    return isinstance(user_data, dict) and user_data.get("words_flow_mode") == ADD_WORDS_AWAITING_TEXT_MODE


def clear_add_words_text_interaction(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict) and user_data.get("words_flow_mode") == ADD_WORDS_AWAITING_TEXT_MODE:
        user_data.pop("words_flow_mode", None)


def start_add_words_draft_edit_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data["words_flow_mode"] = ADD_WORDS_AWAITING_EDIT_TEXT_MODE
        user_data["edit_flow_id"] = flow_id


def get_add_words_draft_edit_interaction(
    context: ContextTypes.DEFAULT_TYPE,
) -> AddWordsDraftEditInteraction | None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return None
    if user_data.get("words_flow_mode") != ADD_WORDS_AWAITING_EDIT_TEXT_MODE:
        return None
    flow_id = user_data.get("edit_flow_id")
    if not isinstance(flow_id, str) or not flow_id:
        return None
    return AddWordsDraftEditInteraction(flow_id=flow_id)


def clear_add_words_draft_edit_interaction(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        if user_data.get("words_flow_mode") == ADD_WORDS_AWAITING_EDIT_TEXT_MODE:
            user_data.pop("words_flow_mode", None)
        user_data.pop("edit_flow_id", None)


def start_published_word_edit_prompt_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    topic_id: str,
    item_id: str,
    chat_id: int | None,
    message_id: int | None,
) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data["words_flow_mode"] = PUBLISHED_WORD_AWAITING_EDIT_TEXT_MODE
        user_data["published_edit_topic_id"] = topic_id
        user_data["published_edit_item_id"] = item_id
    remember_expected_user_input(
        context,
        chat_id=chat_id,
        message_id=message_id,
    )


def get_published_word_edit_prompt_interaction(
    context: ContextTypes.DEFAULT_TYPE,
) -> PublishedWordEditPromptInteraction | None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return None
    if user_data.get("words_flow_mode") != PUBLISHED_WORD_AWAITING_EDIT_TEXT_MODE:
        return None
    topic_id = user_data.get("published_edit_topic_id")
    item_id = user_data.get("published_edit_item_id")
    if not isinstance(topic_id, str) or not topic_id:
        return None
    if not isinstance(item_id, str) or not item_id:
        return None
    return PublishedWordEditPromptInteraction(topic_id=topic_id, item_id=item_id)


def clear_published_word_edit_prompt_interaction(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        if user_data.get("words_flow_mode") == PUBLISHED_WORD_AWAITING_EDIT_TEXT_MODE:
            user_data.pop("words_flow_mode", None)
        user_data.pop("published_edit_topic_id", None)
        user_data.pop("published_edit_item_id", None)
    clear_expected_user_input(context)


def get_admin_goal_creation_state(context: ContextTypes.DEFAULT_TYPE) -> AdminGoalCreationState:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return AdminGoalCreationState()
    raw_manual_word_ids = user_data.get("admin_goal_manual_word_ids", set())
    raw_recipient_user_ids = user_data.get("admin_goal_recipient_user_ids", set())
    raw_recipients_page = user_data.get("admin_goal_recipients_page", 0)
    manual_word_ids = frozenset(
        str(value) for value in raw_manual_word_ids if isinstance(value, str) and value
    )
    recipient_user_ids = frozenset(
        int(value)
        for value in raw_recipient_user_ids
        if isinstance(value, int)
    )
    recipients_page = raw_recipients_page if isinstance(raw_recipients_page, int) else 0
    target_count = user_data.get("admin_goal_target_count")
    return AdminGoalCreationState(
        goal_period=(
            user_data.get("admin_goal_period")
            if isinstance(user_data.get("admin_goal_period"), str)
            else None
        ),
        goal_type=(
            user_data.get("admin_goal_type")
            if isinstance(user_data.get("admin_goal_type"), str)
            else None
        ),
        target_count=(target_count if isinstance(target_count, int) else None),
        source=(
            user_data.get("admin_goal_source")
            if isinstance(user_data.get("admin_goal_source"), str)
            else None
        ),
        deadline_date=(
            user_data.get("admin_goal_deadline_date")
            if isinstance(user_data.get("admin_goal_deadline_date"), str)
            else None
        ),
        manual_word_ids=manual_word_ids,
        recipient_user_ids=recipient_user_ids,
        recipients_page=recipients_page,
    )


def update_admin_goal_creation_state(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    goal_period: str | None = None,
    goal_type: str | None = None,
    target_count: int | None = None,
    source: str | None = None,
    deadline_date: str | None = None,
    manual_word_ids: set[str] | frozenset[str] | None = None,
    recipient_user_ids: set[int] | frozenset[int] | None = None,
    recipients_page: int | None = None,
) -> None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return
    if goal_period is not None:
        user_data["admin_goal_period"] = goal_period
    if goal_type is not None:
        user_data["admin_goal_type"] = goal_type
    if target_count is not None:
        user_data["admin_goal_target_count"] = target_count
    if source is not None:
        user_data["admin_goal_source"] = source
    if deadline_date is not None:
        user_data["admin_goal_deadline_date"] = deadline_date
    if manual_word_ids is not None:
        user_data["admin_goal_manual_word_ids"] = set(manual_word_ids)
    if recipient_user_ids is not None:
        user_data["admin_goal_recipient_user_ids"] = set(recipient_user_ids)
    if recipients_page is not None:
        user_data["admin_goal_recipients_page"] = recipients_page


def start_admin_goal_creation_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_admin_goal_creation_state(context)
    update_admin_goal_creation_state(context, recipient_user_ids=set())


def clear_admin_goal_creation_state(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    clear_prompt: bool = False,
) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        for key in ADMIN_GOAL_STATE_KEYS:
            user_data.pop(key, None)
    if clear_prompt:
        clear_admin_goal_prompt_interaction(context)


def start_image_review_text_edit_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
    flow_id: str,
    item_id: str,
    chat_id: int | None,
    message_id: int | None,
) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data["words_flow_mode"] = mode
        user_data["image_review_flow_id"] = flow_id
        user_data["image_review_item_id"] = item_id
    remember_expected_user_input(
        context,
        chat_id=chat_id,
        message_id=message_id,
    )


def get_image_review_text_edit_interaction(
    context: ContextTypes.DEFAULT_TYPE,
) -> ImageReviewTextEditInteraction | None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return None
    mode = user_data.get("words_flow_mode")
    if mode not in {
        "awaiting_image_review_prompt_text",
        "awaiting_image_review_search_query_text",
    }:
        return None
    flow_id = user_data.get("image_review_flow_id")
    item_id = user_data.get("image_review_item_id")
    if not isinstance(flow_id, str) or not flow_id:
        return None
    if not isinstance(item_id, str) or not item_id:
        return None
    return ImageReviewTextEditInteraction(mode=mode, flow_id=flow_id, item_id=item_id)


def clear_image_review_text_edit_interaction(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data.pop("words_flow_mode", None)
        user_data.pop("image_review_flow_id", None)
        user_data.pop("image_review_item_id", None)
    clear_expected_user_input(context)


def start_admin_goal_prompt_interaction(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
    chat_id: int | None,
    message_id: int | None,
) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data["words_flow_mode"] = mode
    remember_expected_user_input(
        context,
        chat_id=chat_id,
        message_id=message_id,
    )


def clear_admin_goal_prompt_interaction(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data.pop("words_flow_mode", None)
    clear_expected_user_input(context)


def get_admin_goal_prompt_mode(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return None
    mode = user_data.get("words_flow_mode")
    if mode in {"awaiting_admin_goal_target_text", "awaiting_admin_goal_deadline_text"}:
        return mode
    return None


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
