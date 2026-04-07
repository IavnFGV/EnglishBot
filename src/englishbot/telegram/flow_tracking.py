from __future__ import annotations

import logging

from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def delete_tracked_messages(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    tracked_messages,
) -> None:
    import englishbot.bot as bot_module

    registry = bot_module._telegram_flow_messages(context)
    bot = getattr(context, "bot", None)
    if registry is None:
        return
    for tracked in tracked_messages:
        if bot is not None:
            try:
                await bot.delete_message(chat_id=tracked.chat_id, message_id=tracked.message_id)
            except BadRequest:
                logger.debug(
                    "Tracked Telegram message already missing flow_id=%s chat_id=%s message_id=%s",
                    tracked.flow_id,
                    tracked.chat_id,
                    tracked.message_id,
                )
        registry.remove(
            flow_id=tracked.flow_id,
            chat_id=tracked.chat_id,
            message_id=tracked.message_id,
        )


async def delete_tracked_flow_messages(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    tag: str,
) -> None:
    import englishbot.bot as bot_module

    registry = bot_module._telegram_flow_messages(context)
    if registry is None:
        return
    await delete_tracked_messages(
        context,
        tracked_messages=registry.list(flow_id=flow_id, tag=tag),
    )


async def ensure_chat_menu_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
    user,
) -> None:
    import englishbot.bot as bot_module

    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        return
    flow_id = bot_module._chat_menu_flow_id(user_id=user_id)
    await delete_tracked_flow_messages(
        context,
        flow_id=flow_id,
        tag=bot_module._CHAT_MENU_TAG,
    )
    sent_message = await bot_module.send_telegram_view(
        message,
        bot_module._quick_actions_view(context=context, user=user),
    )
    if sent_message is None:
        return
    track_flow_message(
        context,
        flow_id=flow_id,
        tag=bot_module._CHAT_MENU_TAG,
        message=sent_message,
        fallback_chat_id=bot_module._message_chat_id(message),
    )


async def delete_message_if_possible(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
) -> None:
    import englishbot.bot as bot_module

    bot = getattr(context, "bot", None)
    chat_id = bot_module._message_chat_id(message)
    message_id = getattr(message, "message_id", None)
    if bot is None or not isinstance(chat_id, int) or not isinstance(message_id, int):
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest:
        logger.debug(
            "Telegram message already missing chat_id=%s message_id=%s",
            chat_id,
            message_id,
        )


def tracked_messages_except_source_message(*, tracked_messages, message) -> list:
    import englishbot.bot as bot_module

    source_chat_id = bot_module._message_chat_id(message)
    source_message_id = getattr(message, "message_id", None)
    if not isinstance(source_chat_id, int) or not isinstance(source_message_id, int):
        return list(tracked_messages)
    return [
        tracked
        for tracked in tracked_messages
        if not (
            tracked.chat_id == source_chat_id
            and tracked.message_id == source_message_id
        )
    ]


def track_flow_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    tag: str,
    message,
    fallback_chat_id: int | None = None,
) -> None:
    import englishbot.bot as bot_module

    registry = bot_module._telegram_flow_messages(context)
    if registry is None:
        return
    message_id = getattr(message, "message_id", None)
    if not isinstance(message_id, int):
        return
    chat_id = bot_module._message_chat_id(message)
    if chat_id is None:
        chat_id = fallback_chat_id
    if not isinstance(chat_id, int):
        return
    registry.track(flow_id=flow_id, chat_id=chat_id, message_id=message_id, tag=tag)


def published_word_edit_flow_id(*, user_id: int) -> str:
    from englishbot.telegram.interaction import published_word_edit_interaction_id

    return published_word_edit_interaction_id(user_id=user_id)


def tts_voice_flow_id(*, user_id: int) -> str:
    from englishbot.telegram.interaction import tts_voice_interaction_id

    return tts_voice_interaction_id(user_id=user_id)


async def reply_voice_replacing_previous_tts(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    message,
    voice,
):
    import englishbot.bot as bot_module

    flow_id = tts_voice_flow_id(user_id=user_id)
    await delete_tracked_flow_messages(
        context,
        flow_id=flow_id,
        tag=bot_module._TTS_VOICE_TAG,
    )
    sent_message = await message.reply_voice(voice=voice)
    track_flow_message(
        context,
        flow_id=flow_id,
        tag=bot_module._TTS_VOICE_TAG,
        message=sent_message,
        fallback_chat_id=bot_module._message_chat_id(message),
    )
    return sent_message
