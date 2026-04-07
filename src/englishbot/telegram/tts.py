from __future__ import annotations

import asyncio
from io import BytesIO

from telegram import InputFile, Update
from telegram.ext import ContextTypes

from englishbot import bot as bot_module
from englishbot.telegram import runtime as tg_runtime
from englishbot.telegram.flow_tracking import reply_voice_replacing_previous_tts
from englishbot.telegram.training_markup import (
    question_reply_markup as training_question_reply_markup,
    tts_voice_menu_markup as training_tts_voice_menu_markup,
)


async def tts_voice_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    if not tg_runtime.tts_has_multiple_voices(context):
        await query.answer()
        return
    try:
        active_session = tg_runtime.service(context).get_active_session(user_id=user.id)
        current_question = tg_runtime.service(context).get_current_question(user_id=user.id)
    except bot_module.InvalidSessionStateError:
        await query.answer(tg_runtime.tg("no_active_session_begin", context=context, user=user))
        return
    except Exception:
        await query.answer(tg_runtime.tg("no_active_session_begin", context=context, user=user))
        return
    await query.answer()
    await query.edit_message_reply_markup(
        reply_markup=training_tts_voice_menu_markup(
            context=context,
            user=user,
            item_id=current_question.item_id,
            tg=tg_runtime.tg,
            tts_voice_variants=tg_runtime.tts_voice_variants,
            tts_selected_voice_name=tg_runtime.tts_selected_voice_name,
            tts_voice_label=tg_runtime.tts_voice_label,
        )
    )


async def tts_voice_select_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    try:
        active_session = tg_runtime.service(context).get_active_session(user_id=user.id)
        current_question = tg_runtime.service(context).get_current_question(user_id=user.id)
    except bot_module.InvalidSessionStateError:
        await query.answer(tg_runtime.tg("no_active_session_begin", context=context, user=user))
        return
    except Exception:
        await query.answer(tg_runtime.tg("no_active_session_begin", context=context, user=user))
        return
    suffix = query.data.removeprefix("tts:voice:")
    if suffix != "back":
        variants = tg_runtime.tts_voice_variants(context)
        if not suffix.isdigit():
            await query.answer()
            return
        index = int(suffix)
        if index < 0 or index >= len(variants):
            await query.answer()
            return
        bot_module._tts_selected_voice_store(context)[current_question.item_id] = variants[index]
        await query.answer(tg_runtime.tts_voice_label(context, user=user, voice_name=variants[index]))
    else:
        await query.answer()
    await query.edit_message_reply_markup(
        reply_markup=training_question_reply_markup(
            current_question,
            active_session=active_session,
            context=context,
            user=user,
            get_medium_task_state=bot_module._get_medium_task_state,
            build_medium_task_state=bot_module._build_medium_task_state,
            medium_task_keyboard=bot_module._medium_task_keyboard,
            tts_service_enabled=tg_runtime.tts_service_enabled,
            tts_buttons_builder=bot_module._tts_buttons,
            hard_skip_keyboard_builder=bot_module._hard_skip_keyboard,
        )
    )


async def send_tts_for_current_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    advance_voice: bool,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    client = bot_module._tts_client_or_none(context)
    if client is None:
        await query.answer(tg_runtime.tg("tts_unavailable", context=context, user=user))
        return
    try:
        active_session = tg_runtime.service(context).get_active_session(user_id=user.id)
    except Exception:
        active_session = None
    if active_session is None:
        await query.answer(tg_runtime.tg("no_active_session_begin", context=context, user=user))
        return
    try:
        current_question = tg_runtime.service(context).get_current_question(user_id=user.id)
    except bot_module.InvalidSessionStateError:
        await query.answer(tg_runtime.tg("no_active_session_begin", context=context, user=user))
        return
    if advance_voice:
        selected_voice_name = bot_module._advance_tts_selected_voice_name(
            context,
            item_id=current_question.item_id,
        )
    else:
        selected_voice_name = tg_runtime.tts_selected_voice_name(
            context,
            item_id=current_question.item_id,
        )
    if selected_voice_name is None:
        await query.answer(tg_runtime.tg("tts_unavailable", context=context, user=user))
        return
    lock = bot_module._tts_task_lock(context)
    if lock.locked():
        await query.answer(tg_runtime.tg("tts_already_sending", context=context, user=user))
        return
    recent_request = tg_runtime.tts_recent_request(context)
    loop = asyncio.get_running_loop()
    now = loop.time()
    if recent_request is not None:
        recent_item_id, recent_voice_name, recent_sent_at = recent_request
        if (
            recent_item_id == current_question.item_id
            and recent_voice_name == selected_voice_name
            and now - recent_sent_at < bot_module._TTS_REPEAT_COOLDOWN_SEC
        ):
            await query.answer(tg_runtime.tg("tts_recently_sent", context=context, user=user))
            return
    async with lock:
        recent_request = tg_runtime.tts_recent_request(context)
        now = loop.time()
        if recent_request is not None:
            recent_item_id, recent_voice_name, recent_sent_at = recent_request
            if (
                recent_item_id == current_question.item_id
                and recent_voice_name == selected_voice_name
                and now - recent_sent_at < bot_module._TTS_REPEAT_COOLDOWN_SEC
            ):
                await query.answer(tg_runtime.tg("tts_recently_sent", context=context, user=user))
                return
        item = None
        try:
            item = tg_runtime.content_store(context).get_vocabulary_item(current_question.item_id)
        except Exception:
            item = None
        primary_voice_name = bot_module._tts_primary_voice_name(context)
        variant = None
        if item is not None:
            try:
                variant = tg_runtime.content_store(context).get_word_audio_variant(
                    item_id=item.id,
                    voice_name=selected_voice_name,
                )
            except Exception:
                variant = None
        cached_voice_file_id = None
        cached_audio_ref = None
        if variant is not None:
            cached_voice_file_id = variant.telegram_voice_file_id
            cached_audio_ref = variant.audio_ref
        elif item is not None and selected_voice_name == primary_voice_name:
            cached_voice_file_id = item.telegram_voice_file_id
            cached_audio_ref = item.audio_ref
        if item is not None and cached_voice_file_id:
            try:
                await query.answer()
                await reply_voice_replacing_previous_tts(
                    context=context,
                    user_id=int(user.id),
                    message=query.message,
                    voice=cached_voice_file_id,
                )
                tg_runtime.content_store(context).update_word_audio_variant(
                    item_id=item.id,
                    voice_name=selected_voice_name,
                    audio_ref=cached_audio_ref,
                    telegram_voice_file_id=cached_voice_file_id,
                )
                tg_runtime.set_tts_recent_request(
                    context,
                    item_id=current_question.item_id,
                    voice_name=selected_voice_name,
                    sent_at=loop.time(),
                )
                return
            except Exception as error:
                bot_module.logger.warning(
                    "Cached Telegram voice_id failed user_id=%s item_id=%s voice_name=%s error=%s",
                    user.id,
                    current_question.item_id,
                    selected_voice_name,
                    error,
                )
        if item is not None and cached_audio_ref:
            audio_path = bot_module.resolve_existing_audio_path(cached_audio_ref)
            if audio_path is not None:
                try:
                    await query.answer()
                    with audio_path.open("rb") as audio_file:
                        sent_message = await reply_voice_replacing_previous_tts(
                            context=context,
                            user_id=int(user.id),
                            message=query.message,
                            voice=InputFile(audio_file, filename=audio_path.name),
                        )
                    voice_file_id = bot_module._extract_sent_voice_file_id(sent_message)
                    if voice_file_id is not None:
                        tg_runtime.content_store(context).update_word_audio_variant(
                            item_id=item.id,
                            voice_name=selected_voice_name,
                            audio_ref=cached_audio_ref,
                            telegram_voice_file_id=voice_file_id,
                        )
                    if voice_file_id is not None and selected_voice_name == primary_voice_name:
                        tg_runtime.content_store(context).update_word_audio(
                            item_id=item.id,
                            telegram_voice_file_id=voice_file_id,
                        )
                    tg_runtime.set_tts_recent_request(
                        context,
                        item_id=current_question.item_id,
                        voice_name=selected_voice_name,
                        sent_at=loop.time(),
                    )
                    return
                except Exception as error:
                    bot_module.logger.warning(
                        "Cached local TTS audio failed user_id=%s item_id=%s voice_name=%s error=%s",
                        user.id,
                        current_question.item_id,
                        selected_voice_name,
                        error,
                    )
        try:
            audio_bytes = client.synthesize(
                text=current_question.correct_answer,
                voice_name=selected_voice_name,
            )
        except Exception as error:
            bot_module.logger.warning(
                "TTS unavailable for user_id=%s item_id=%s voice_name=%s error=%s",
                user.id,
                current_question.item_id,
                selected_voice_name,
                error,
            )
            await query.answer(tg_runtime.tg("tts_unavailable", context=context, user=user))
            return
        audio_ref: str | None = None
        if item is not None and item.topic_id:
            is_primary_voice = selected_voice_name == primary_voice_name
            audio_path = bot_module.build_item_audio_path(
                assets_dir=bot_module.Path("assets"),
                topic_id=item.topic_id,
                item_id=item.id,
                voice_name=None if is_primary_voice else selected_voice_name,
            )
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(audio_bytes)
            audio_ref = bot_module.build_item_audio_ref(
                assets_dir=bot_module.Path("assets"),
                topic_id=item.topic_id,
                item_id=item.id,
                voice_name=None if is_primary_voice else selected_voice_name,
            )
        await query.answer()
        voice_file = InputFile(BytesIO(audio_bytes), filename="pronunciation.ogg")
        sent_message = await reply_voice_replacing_previous_tts(
            context=context,
            user_id=int(user.id),
            message=query.message,
            voice=voice_file,
        )
        voice_file_id = bot_module._extract_sent_voice_file_id(sent_message)
        if item is not None and (audio_ref is not None or voice_file_id is not None):
            tg_runtime.content_store(context).update_word_audio_variant(
                item_id=item.id,
                voice_name=selected_voice_name,
                audio_ref=audio_ref,
                telegram_voice_file_id=voice_file_id,
            )
            if selected_voice_name == primary_voice_name:
                tg_runtime.content_store(context).update_word_audio(
                    item_id=item.id,
                    audio_ref=audio_ref,
                    telegram_voice_file_id=voice_file_id,
                )
        tg_runtime.set_tts_recent_request(
            context,
            item_id=current_question.item_id,
            voice_name=selected_voice_name,
            sent_at=loop.time(),
        )


async def tts_current_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await send_tts_for_current_question(update, context, advance_voice=False)


async def tts_next_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await send_tts_for_current_question(update, context, advance_voice=True)
