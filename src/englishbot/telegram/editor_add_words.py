from __future__ import annotations

import asyncio
import json

from telegram import ForceReply, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from englishbot import bot as bot_module
from englishbot.importing.draft_io import draft_to_data
from englishbot.presentation.add_words_text import (
    format_draft_edit_text,
    parse_edited_vocabulary_line,
)
from englishbot.presentation.telegram_views import (
    build_published_word_edit_prompt_view,
    edit_telegram_text_view,
    send_telegram_view,
)


async def words_add_words_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import start_add_words_text_interaction

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not bot_module._has_menu_permission(
        context,
        user_id=user.id,
        permission=bot_module.PERMISSION_WORDS_ADD,
    ):
        await query.edit_message_text(
            bot_module._tg("only_editors_add_words", context=context, user=user)
        )
        return
    start_add_words_text_interaction(context)
    await query.edit_message_text(
        bot_module._tg("send_raw_lesson_text", context=context, user=user)
    )


async def words_edit_words_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not bot_module._has_menu_permission(
        context,
        user_id=user.id,
        permission=bot_module.PERMISSION_WORDS_EDIT,
    ):
        await query.edit_message_text(
            bot_module._tg("only_editors_edit_words", context=context, user=user)
        )
        return
    topics = bot_module._list_editable_topics(context).execute()
    topics_view = bot_module._editable_topics_view(
        text=bot_module._tg("choose_topic_edit_words", context=context, user=user),
        topics=topics,
        context=context,
        user=update.effective_user,
    )
    await query.edit_message_text(
        topics_view.text,
        reply_markup=topics_view.reply_markup,
    )


async def words_edit_images_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not bot_module._has_menu_permission(
        context,
        user_id=user.id,
        permission=bot_module.PERMISSION_WORD_IMAGES_EDIT,
    ):
        await query.edit_message_text(
            bot_module._tg("only_editors_edit_images", context=context, user=user)
        )
        return
    topics = bot_module._list_editable_topics(context).execute()
    topics_view = bot_module._editable_topics_view(
        text=bot_module._tg("choose_topic_edit_images", context=context, user=user),
        topics=topics,
        context=context,
        user=update.effective_user,
        for_images=True,
    )
    await query.edit_message_text(
        topics_view.text,
        reply_markup=topics_view.reply_markup,
    )


async def words_edit_topic_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _, _, topic_id = query.data.split(":")
    words = bot_module._list_editable_words(context).execute(topic_id=topic_id)
    words_view = bot_module._editable_words_view(
        text=bot_module._tg(
            "choose_word_to_edit",
            context=context,
            user=update.effective_user,
        ),
        topic_id=topic_id,
        words=words,
        context=context,
        user=update.effective_user,
    )
    await query.edit_message_text(
        words_view.text,
        reply_markup=words_view.reply_markup,
    )


async def words_edit_item_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import (
        start_published_word_edit_interaction,
        start_published_word_edit_prompt_interaction,
    )

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, topic_id, item_index = query.data.split(":")
    words = bot_module._list_editable_words(context).execute(topic_id=topic_id)
    try:
        selected_word = words[int(item_index)]
    except (ValueError, IndexError):
        await query.edit_message_text(
            bot_module._tg("selected_word_unavailable", context=context, user=user)
        )
        return
    instruction_view, current_value_view = build_published_word_edit_prompt_view(
        instruction_text=bot_module._tg("send_updated_word_format", context=context, user=user),
        current_value_text=bot_module._tg(
            "current_value",
            context=context,
            user=user,
            value=f"{selected_word.english_word}: {selected_word.translation}",
        ),
        instruction_markup=bot_module._published_word_edit_keyboard(
            topic_id=topic_id,
            language=bot_module._telegram_ui_language(context, update.effective_user),
        ),
        current_value_markup=ForceReply(selective=True),
    )
    await query.edit_message_text(
        instruction_view.text,
        reply_markup=instruction_view.reply_markup,
    )
    start_published_word_edit_prompt_interaction(
        context,
        topic_id=topic_id,
        item_id=selected_word.id,
        chat_id=bot_module._message_chat_id(query.message),
        message_id=getattr(query.message, "message_id", None),
    )
    helper_message = await send_telegram_view(query.message, current_value_view)
    await start_published_word_edit_interaction(
        context,
        user_id=user.id,
        source_message=query.message,
        helper_message=helper_message,
        fallback_chat_id=bot_module._message_chat_id(query.message),
    )


async def words_edit_cancel_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import (
        clear_published_word_edit_prompt_interaction,
        finish_published_word_edit_interaction,
    )

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, topic_id = query.data.split(":")
    await finish_published_word_edit_interaction(
        context,
        user_id=user.id,
        keep_source_message=True,
        source_message=query.message,
    )
    clear_published_word_edit_prompt_interaction(context)
    words = bot_module._list_editable_words(context).execute(topic_id=topic_id)
    await query.edit_message_text(
        "Edit cancelled. Choose a word to edit.",
        reply_markup=bot_module._editable_words_keyboard(topic_id=topic_id, words=words),
    )


async def add_words_start_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import start_add_words_text_interaction

    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    if not bot_module._has_menu_permission(
        context,
        user_id=user.id,
        permission=bot_module.PERMISSION_WORDS_ADD,
    ):
        await message.reply_text(
            bot_module._tg("no_permission_add_words", context=context, user=user)
        )
        return
    existing_flow = bot_module._active_word_flow_for_user(user.id, context)
    if existing_flow is not None:
        await message.reply_text(
            bot_module._tg("active_add_words_flow_exists", context=context, user=user)
        )
        start_add_words_text_interaction(context)
        return
    start_add_words_text_interaction(context)
    await message.reply_text(
        bot_module._tg("send_raw_lesson_text_with_menu", context=context, user=user),
        reply_markup=bot_module._chat_menu_keyboard(
            command_rows=bot_module._visible_command_rows(context, user_id=user.id)
        ),
    )


async def add_words_cancel_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import clear_add_words_text_interaction

    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    bot_module._clear_active_word_flow(user.id, context)
    clear_add_words_text_interaction(context)
    await message.reply_text(
        bot_module._tg("add_words_flow_cancelled", context=context, user=user),
        reply_markup=bot_module._chat_menu_keyboard(
            command_rows=bot_module._visible_command_rows(context, user_id=user.id)
        ),
    )


async def add_words_cancel_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import clear_add_words_text_interaction

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text(
            bot_module._tg("add_words_flow_inactive", context=context, user=user)
        )
        return
    bot_module._clear_active_word_flow(user.id, context)
    clear_add_words_text_interaction(context)
    await query.edit_message_text(
        bot_module._tg("add_words_flow_cancelled", context=context, user=user)
    )
    await bot_module._ensure_chat_menu_message(context, message=query.message, user=user)


async def add_words_text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import (
        clear_add_words_draft_edit_interaction,
        clear_add_words_text_interaction,
        clear_published_word_edit_prompt_interaction,
        finish_published_word_edit_interaction,
        get_add_words_draft_edit_interaction,
        get_published_word_edit_prompt_interaction,
    )

    words_flow_mode = context.user_data.get("words_flow_mode")
    if words_flow_mode not in {
        bot_module._ADD_WORDS_AWAITING_TEXT,
        bot_module._ADD_WORDS_AWAITING_EDIT_TEXT,
        bot_module._IMAGE_REVIEW_AWAITING_PROMPT_TEXT,
        bot_module._IMAGE_REVIEW_AWAITING_SEARCH_QUERY_TEXT,
        bot_module._IMAGE_REVIEW_AWAITING_PHOTO,
        bot_module._PUBLISHED_WORD_AWAITING_EDIT_TEXT,
    }:
        return
    message = update.effective_message
    user = update.effective_user
    if message is None or message.text is None or user is None:
        return
    if not bot_module._has_menu_permission(
        context,
        user_id=user.id,
        permission=bot_module.PERMISSION_WORDS_ADD,
    ):
        context.user_data.pop("words_flow_mode", None)
        bot_module._clear_expected_user_input(context)
        return
    if words_flow_mode == bot_module._PUBLISHED_WORD_AWAITING_EDIT_TEXT:
        edit_interaction = get_published_word_edit_prompt_interaction(context)
        if edit_interaction is None:
            clear_published_word_edit_prompt_interaction(context)
            await message.reply_text(
                bot_module._tg("word_edit_task_inactive", context=context, user=user)
            )
            return
        topic_id = edit_interaction.topic_id
        item_id = edit_interaction.item_id
        parsed_pair = parse_edited_vocabulary_line(message.text)
        if parsed_pair is None:
            await message.reply_text(
                bot_module._tg("send_one_line_word_format", context=context, user=user)
            )
            return
        english_word, translation = parsed_pair
        try:
            updated_word = await asyncio.to_thread(
                bot_module._update_editable_word(context).execute,
                topic_id=topic_id,
                item_id=item_id,
                english_word=english_word,
                translation=translation,
            )
        except ValueError as error:
            await message.reply_text(str(error))
            return
        bot_module._reload_training_service(context)
        clear_published_word_edit_prompt_interaction(context)
        await finish_published_word_edit_interaction(
            context,
            user_id=user.id,
        )
        await bot_module._delete_message_if_possible(context, message=message)
        words = bot_module._list_editable_words(context).execute(topic_id=topic_id)
        await message.reply_text(
            bot_module._tg(
                "word_updated",
                context=context,
                user=user,
                word=updated_word.english_word,
                translation=updated_word.translation,
            )
        )
        await message.reply_text(
            bot_module._tg("choose_another_word_to_edit", context=context, user=user),
            reply_markup=bot_module._editable_words_keyboard(
                topic_id=topic_id,
                words=words,
                context=context,
                user_id=int(user.id),
                language=bot_module._telegram_ui_language(context, user),
            ),
        )
        return
    if words_flow_mode == bot_module._IMAGE_REVIEW_AWAITING_PROMPT_TEXT:
        from englishbot.telegram.interaction import clear_image_review_text_edit_interaction

        review_flow_id = context.user_data.get("image_review_flow_id")
        review_item_id = context.user_data.get("image_review_item_id")
        review_flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
        if (
            review_flow is None
            or review_flow.flow_id != review_flow_id
            or review_flow.current_item is None
            or review_flow.current_item.item_id != review_item_id
        ):
            clear_image_review_text_edit_interaction(context)
            await message.reply_text(
                bot_module._tg("image_review_task_inactive", context=context, user=user)
            )
            return
        clear_image_review_text_edit_interaction(context)
        status_message = await message.reply_text(
            bot_module._tg("updating_image_prompt", context=context, user=user)
        )
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            bot_module._run_status_heartbeat(
                status_message,
                stage="Updating image prompt",
                stop_event=stop_event,
            )
        )
        try:
            updated_flow = await asyncio.to_thread(
                bot_module._update_image_review_prompt(context).execute,
                user_id=user.id,
                flow_id=review_flow.flow_id,
                item_id=review_item_id,
                prompt=message.text,
            )
        except Exception:  # noqa: BLE001
            stop_event.set()
            await heartbeat_task
            bot_module.logger.exception(
                "Image review prompt update failed for user=%s",
                user.id,
            )
            await status_message.edit_text(
                bot_module._status_view(
                    text=bot_module._tg(
                        "updating_image_prompt_failed",
                        context=context,
                        user=user,
                    )
                ).text
            )
            return
        stop_event.set()
        await heartbeat_task
        await bot_module._delete_message_if_possible(context, message=message)
        await status_message.edit_text(
            bot_module._status_view(
                text=bot_module._tg("prompt_updated", context=context, user=user)
            ).text
        )
        await bot_module._send_image_review_step(message, context, updated_flow)
        return
    if words_flow_mode == bot_module._IMAGE_REVIEW_AWAITING_SEARCH_QUERY_TEXT:
        from englishbot.telegram.interaction import clear_image_review_text_edit_interaction

        review_flow_id = context.user_data.get("image_review_flow_id")
        review_item_id = context.user_data.get("image_review_item_id")
        review_flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
        if (
            review_flow is None
            or review_flow.flow_id != review_flow_id
            or review_flow.current_item is None
            or review_flow.current_item.item_id != review_item_id
        ):
            clear_image_review_text_edit_interaction(context)
            await message.reply_text(
                bot_module._tg("image_review_task_inactive", context=context, user=user)
            )
            return
        clear_image_review_text_edit_interaction(context)
        status_message = await message.reply_text(
            bot_module._tg("searching_pixabay", context=context, user=user)
        )
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            bot_module._run_status_heartbeat(
                status_message,
                stage="Searching Pixabay",
                stop_event=stop_event,
            )
        )
        try:
            updated_flow = await asyncio.to_thread(
                bot_module._search_image_review_candidates(context).execute,
                user_id=user.id,
                flow_id=review_flow.flow_id,
                query=message.text,
            )
        except Exception:  # noqa: BLE001
            stop_event.set()
            await heartbeat_task
            bot_module.logger.exception(
                "Image review Pixabay search update failed for user=%s",
                user.id,
            )
            await status_message.edit_text(
                bot_module._status_view(
                    text=bot_module._tg(
                        "searching_pixabay_failed",
                        context=context,
                        user=user,
                    )
                ).text
            )
            return
        stop_event.set()
        await heartbeat_task
        await bot_module._delete_message_if_possible(context, message=message)
        await status_message.edit_text(
            bot_module._status_view(
                text=bot_module._tg(
                    "pixabay_candidates_updated",
                    context=context,
                    user=user,
                )
            ).text
        )
        await bot_module._send_image_review_step(message, context, updated_flow)
        return
    if words_flow_mode == bot_module._IMAGE_REVIEW_AWAITING_PHOTO:
        await message.reply_text(
            bot_module._tg("send_photo_not_text", context=context, user=user)
        )
        return
    if words_flow_mode == bot_module._ADD_WORDS_AWAITING_EDIT_TEXT:
        draft_edit_interaction = get_add_words_draft_edit_interaction(context)
        active_flow_id = draft_edit_interaction.flow_id if draft_edit_interaction is not None else None
        flow = bot_module._active_word_flow_for_user(user.id, context)
        if flow is None or flow.flow_id != active_flow_id:
            clear_add_words_draft_edit_interaction(context)
            await message.reply_text(
                bot_module._tg("add_words_flow_inactive", context=context, user=user)
            )
            return
        flow = bot_module._apply_add_words_edit(context).execute(
            user_id=user.id,
            flow_id=flow.flow_id,
            edited_text=message.text,
        )
        clear_add_words_draft_edit_interaction(context)
        preview_view = bot_module._draft_review_view(
            flow_id=flow.flow_id,
            result=flow.draft_result,
            is_valid=flow.draft_result.validation.is_valid,
            context=context,
            user=user,
        )
        preview_message_id = bot_module._get_preview_message_id(user.id, context)
        await message.reply_text(
            f"{bot_module._tg('draft_updated_from_text', context=context, user=user)}\n\n{preview_view.text}",
            reply_markup=preview_view.reply_markup,
        )
        if preview_message_id is not None:
            try:
                await context.bot.edit_message_text(
                    chat_id=message.chat_id,
                    message_id=preview_message_id,
                    text=preview_view.text,
                    reply_markup=preview_view.reply_markup,
                )
            except BadRequest as error:
                if "message is not modified" in str(error).lower():
                    bot_module.logger.debug(
                        "Preview message unchanged after edit flow_id=%s message_id=%s",
                        flow.flow_id,
                        preview_message_id,
                    )
                else:
                    bot_module.logger.debug(
                        "Failed to update preview message after edit",
                        exc_info=True,
                    )
            except Exception:  # noqa: BLE001
                bot_module.logger.debug(
                    "Failed to update preview message after edit",
                    exc_info=True,
                )
        return
    bot_module.logger.info(
        "User %s submitted raw text for add-words flow",
        user.id,
    )
    status_message = await message.reply_text(
        bot_module._tg("parsing_draft", context=context, user=user)
    )
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        bot_module._run_status_heartbeat(
            status_message,
            stage="Parsing draft",
            stop_event=stop_event,
        )
    )
    try:
        flow = await asyncio.to_thread(
            bot_module._start_add_words_flow(context).execute,
            user_id=user.id,
            raw_text=message.text,
        )
    except Exception:  # noqa: BLE001
        bot_module.logger.exception(
            "Add-words draft extraction failed for user=%s",
            user.id,
        )
        await status_message.edit_text(
            bot_module._status_view(
                text=bot_module._tg(
                    "parsing_draft_failed_generic",
                    context=context,
                    user=user,
                )
            ).text
        )
        clear_add_words_text_interaction(context)
        return
    finally:
        stop_event.set()
        await heartbeat_task
    clear_add_words_text_interaction(context)
    failure_message = bot_module._draft_failure_message(flow.draft_result)
    if failure_message is not None:
        await status_message.edit_text(bot_module._status_view(text=failure_message).text)
        return
    await status_message.edit_text(
        bot_module._status_view(
            text=bot_module._draft_status_text(flow.draft_result)
        ).text
    )
    preview_view = bot_module._draft_review_view(
        flow_id=flow.flow_id,
        result=flow.draft_result,
        is_valid=flow.draft_result.validation.is_valid,
        context=context,
        user=user,
    )
    preview_message = await send_telegram_view(message, preview_view)
    bot_module._set_preview_message_id(user.id, preview_message.message_id, context)


async def add_words_edit_text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import start_add_words_draft_edit_interaction

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text(
            bot_module._tg("add_words_flow_inactive", context=context, user=user)
        )
        return
    start_add_words_draft_edit_interaction(context, flow_id=flow.flow_id)
    await query.message.reply_text(
        bot_module._tg("edit_word_list_instruction", context=context, user=user),
        reply_markup=ForceReply(selective=True),
    )
    await query.message.reply_text(format_draft_edit_text(flow.draft_result.draft))


async def add_words_show_json_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text(
            bot_module._tg("add_words_flow_inactive", context=context, user=user)
        )
        return
    payload = json.dumps(
        draft_to_data(flow.draft_result.draft),
        ensure_ascii=False,
        indent=2,
    )
    if len(payload) > 3500:
        payload = payload[:3400].rstrip() + "\n..."
    await query.message.reply_text(f"```json\n{payload}\n```", parse_mode="Markdown")


async def add_words_regenerate_draft_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text(
            bot_module._tg("add_words_flow_inactive", context=context, user=user)
        )
        return
    if not bot_module._smart_parsing_available(context):
        await edit_telegram_text_view(
            query,
            bot_module._status_view(
                text=bot_module._tg(
                    "smart_parsing_unavailable",
                    context=context,
                    user=user,
                )
            ),
        )
        return
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg("re_recognizing_draft", context=context, user=user)
        ),
    )
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        bot_module._run_status_heartbeat(
            query,
            stage="Re-recognizing draft",
            stop_event=stop_event,
        )
    )
    try:
        flow = await asyncio.to_thread(
            bot_module._regenerate_add_words_draft(context).execute,
            user_id=user.id,
            flow_id=flow.flow_id,
        )
    except Exception:  # noqa: BLE001
        bot_module.logger.exception(
            "Add-words draft regeneration failed for user=%s",
            user.id,
        )
        await edit_telegram_text_view(
            query,
            bot_module._status_view(
                text=bot_module._tg(
                    "parsing_draft_failed_generic",
                    context=context,
                    user=user,
                )
            ),
        )
        return
    finally:
        stop_event.set()
        await heartbeat_task
    review_view = bot_module._draft_review_view(
        flow_id=flow.flow_id,
        result=flow.draft_result,
        is_valid=flow.draft_result.validation.is_valid,
        context=context,
        user=user,
    )
    await query.edit_message_text(
        review_view.text,
        reply_markup=review_view.reply_markup,
    )


async def add_words_publish_without_images_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text(
            bot_module._tg("add_words_flow_inactive", context=context, user=user)
        )
        return
    result = flow.draft_result
    if not result.validation.is_valid:
        review_view = bot_module._draft_review_view(
            flow_id=flow.flow_id,
            result=result,
            is_valid=False,
            context=context,
            user=user,
        )
        await query.edit_message_text(
            review_view.text,
            reply_markup=review_view.reply_markup,
        )
        return
    await query.edit_message_text(
        "Publishing content pack...\n"
        "Validated items: "
        f"{len(result.draft.vocabulary_items)}/{len(result.draft.vocabulary_items)}"
    )
    approved = bot_module._approve_add_words_draft(context).execute(
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    finalized = approved.import_result
    if not finalized.validation.is_valid or finalized.canonicalization is None:
        await query.edit_message_text(
            bot_module._tg("draft_finalization_failed", context=context, user=user)
        )
        return
    topic_id = approved.published_topic_id
    bot_module._reload_training_service(context)
    bot_module._preview_message_ids(context).pop(user.id, None)
    await query.edit_message_text(
        bot_module._tg(
            "draft_approved_published",
            context=context,
            user=user,
            destination=bot_module._publish_destination_text(
                context,
                output_path=approved.output_path,
                topic_id=topic_id,
            ),
            item_count=len(finalized.draft.vocabulary_items),
        )
    )
    await bot_module._ensure_chat_menu_message(context, message=query.message, user=user)


async def add_words_approve_draft_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text(
            bot_module._tg("add_words_flow_inactive", context=context, user=user)
        )
        return
    result = flow.draft_result
    if not result.validation.is_valid:
        review_view = bot_module._draft_review_view(
            flow_id=flow.flow_id,
            result=result,
            is_valid=False,
            context=context,
            user=user,
        )
        await query.edit_message_text(
            review_view.text,
            reply_markup=review_view.reply_markup,
        )
        return
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg("saving_approved_draft", context=context, user=user)
        ),
    )
    saved_flow = await asyncio.to_thread(
        bot_module._save_approved_add_words_draft(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "approved_draft_saved_generating_prompts",
                context=context,
                user=user,
                checkpoint=bot_module._draft_checkpoint_text(saved_flow),
            )
        ),
    )
    prompt_flow = await asyncio.to_thread(
        bot_module._generate_add_words_image_prompts(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "image_prompts_generated_starting_review",
                context=context,
                user=user,
                checkpoint=bot_module._draft_checkpoint_text(prompt_flow),
                prompt_count=bot_module._draft_prompt_count(prompt_flow.draft_result) or 0,
            )
        ),
    )
    image_review_flow = await asyncio.to_thread(
        bot_module._start_image_review(context).execute,
        user_id=user.id,
        draft=prompt_flow.draft_result.draft,
    )
    await asyncio.to_thread(
        bot_module._mark_add_words_image_review_started(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
        image_review_flow_id=image_review_flow.flow_id,
    )
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "image_prompts_generated_saved_continue_review",
                context=context,
                user=user,
                checkpoint=bot_module._draft_checkpoint_text(prompt_flow),
                prompt_count=bot_module._draft_prompt_count(prompt_flow.draft_result) or 0,
            )
        ),
    )
    await bot_module._send_image_review_step(query.message, context, image_review_flow, user=user)


async def add_words_approve_auto_images_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text(
            bot_module._tg("add_words_flow_inactive", context=context, user=user)
        )
        return
    if not bot_module._local_image_generation_available(context):
        await query.edit_message_text(
            bot_module._tg("auto_images_unavailable", context=context, user=user)
        )
        return
    result = flow.draft_result
    if not result.validation.is_valid:
        review_view = bot_module._draft_review_view(
            flow_id=flow.flow_id,
            result=result,
            is_valid=False,
            context=context,
            user=user,
        )
        await query.edit_message_text(
            review_view.text,
            reply_markup=review_view.reply_markup,
        )
        return

    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg("saving_approved_draft", context=context, user=user)
        ),
    )
    saved_flow = await asyncio.to_thread(
        bot_module._save_approved_add_words_draft(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "approved_draft_saved_generating_prompts",
                context=context,
                user=user,
                checkpoint=bot_module._draft_checkpoint_text(saved_flow),
            )
        ),
    )
    prompt_flow = await asyncio.to_thread(
        bot_module._generate_add_words_image_prompts(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "image_prompts_generated_publishing",
                context=context,
                user=user,
                checkpoint=bot_module._draft_checkpoint_text(prompt_flow),
                prompt_count=bot_module._draft_prompt_count(prompt_flow.draft_result) or 0,
            )
        ),
    )
    approved = await asyncio.to_thread(
        bot_module._approve_add_words_draft(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    total_items = len(approved.import_result.draft.vocabulary_items)
    rendered_total_items = total_items if total_items > 0 else 1
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "content_pack_published_generating_images",
                context=context,
                user=user,
                destination=bot_module._publish_destination_text(
                    context,
                    output_path=approved.output_path,
                    topic_id=approved.published_topic_id,
                ),
                item_count=len(approved.import_result.draft.vocabulary_items),
                processed=0,
                total=rendered_total_items,
            )
        ),
    )
    progress_queue: asyncio.Queue[tuple[int, int] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    async def _report_generation_progress() -> None:
        last_progress: tuple[int, int] | None = None
        while True:
            progress = await progress_queue.get()
            if progress is None:
                return
            if progress == last_progress:
                continue
            last_progress = progress
            processed_count, total_count = progress
            await edit_telegram_text_view(
                query,
                bot_module._status_view(
                    text=bot_module._tg(
                        "content_pack_published_generating_images",
                        context=context,
                        user=user,
                        destination=bot_module._publish_destination_text(
                            context,
                            output_path=approved.output_path,
                            topic_id=approved.published_topic_id,
                        ),
                        item_count=len(approved.import_result.draft.vocabulary_items),
                        processed=processed_count,
                        total=total_count,
                    )
                ),
            )

    progress_task = asyncio.create_task(_report_generation_progress())
    topic_id = approved.published_topic_id
    try:
        enrichment_result = await asyncio.to_thread(
            bot_module._generate_content_pack_images(context).execute,
            topic_id=topic_id,
            assets_dir=bot_module.Path("assets"),
            progress_callback=lambda processed_count, total_count: loop.call_soon_threadsafe(
                progress_queue.put_nowait,
                (processed_count, total_count),
            ),
        )
    finally:
        await progress_queue.put(None)
        await progress_task
    bot_module._reload_training_service(context)
    bot_module._preview_message_ids(context).pop(user.id, None)
    enriched_pack = enrichment_result.content_pack
    topic = enriched_pack.get("topic", {})
    topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else topic_id
    generated_image_count = sum(
        1
        for item in enriched_pack.get("vocabulary_items", [])
        if item.get("image_ref")
    )
    generation_notice = ""
    generation_metadata = getattr(enrichment_result, "generation_metadata", None)
    if generation_metadata is not None and generation_metadata.status_messages:
        generation_notice = "\n" + "\n".join(generation_metadata.status_messages)
    await query.edit_message_text(
        bot_module._tg(
            "draft_approved_images_generated",
            context=context,
            user=user,
            destination=bot_module._publish_destination_text(
                context,
                output_path=approved.output_path,
                topic_id=topic_id,
            ),
            generated_count=generated_image_count,
        )
        + generation_notice,
        reply_markup=(
            bot_module._published_images_menu_keyboard(
                topic_id=topic_id,
                language=bot_module._telegram_ui_language(context, user),
            )
            if topic_id
            else None
        ),
    )
