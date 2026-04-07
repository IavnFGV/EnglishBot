from __future__ import annotations

import asyncio
import json

from telegram import ForceReply, Update
from telegram.ext import ContextTypes

from englishbot import bot as bot_module
from englishbot.presentation.telegram_views import (
    build_image_review_attach_photo_view,
    build_image_review_prompt_edit_view,
    build_image_review_search_query_edit_view,
    edit_telegram_text_view,
    send_telegram_view,
)


async def published_images_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, topic_id = query.data.split(":")
    try:
        content_pack = bot_module._content_store(context).get_content_pack(topic_id)
    except ValueError:
        await query.edit_message_text(
            bot_module._tg("published_content_not_found", context=context, user=user)
        )
        return
    raw_items = content_pack.get("vocabulary_items", [])
    if not isinstance(raw_items, list) or not raw_items:
        await query.edit_message_text(
            bot_module._tg("no_vocabulary_items_found", context=context, user=user)
        )
        return
    await query.edit_message_text(
        bot_module._tg("choose_word_edit_image", context=context, user=user),
        reply_markup=bot_module._published_image_items_keyboard(
            topic_id=topic_id,
            raw_items=raw_items,
            context=context,
            user_id=int(user.id),
            language=bot_module._telegram_ui_language(context, user),
        ),
    )


async def published_image_item_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    token = query.data.removeprefix("words:edit_published_image:")
    payload = bot_module._consume_callback_token(
        context=context,
        user_id=int(user.id),
        action=bot_module._PUBLISHED_IMAGE_ITEM_CALLBACK_ACTION,
        token=token,
        fallback_key="selection",
        allow_colon_fallback=True,
    )
    if payload is None:
        await query.edit_message_text(
            bot_module._tg("selected_word_unavailable", context=context, user=user)
        )
        return
    topic_id = payload.get("topic_id")
    item_index = payload.get("item_index")
    if isinstance(topic_id, str) and isinstance(item_index, int):
        resolved_topic_id = topic_id
        resolved_item_index = item_index
    else:
        selection = payload.get("selection")
        if not isinstance(selection, str) or ":" not in selection:
            await query.edit_message_text(
                bot_module._tg("selected_word_unavailable", context=context, user=user)
            )
            return
        resolved_topic_id, raw_item_index = selection.rsplit(":", 1)
        try:
            resolved_item_index = int(raw_item_index)
        except ValueError:
            await query.edit_message_text(
                bot_module._tg("selected_word_unavailable", context=context, user=user)
            )
            return
    try:
        content_pack = bot_module._content_store(context).get_content_pack(resolved_topic_id)
    except ValueError:
        await query.edit_message_text(
            bot_module._tg("published_content_not_found", context=context, user=user)
        )
        return
    raw_items = content_pack.get("vocabulary_items", [])
    if not isinstance(raw_items, list):
        await query.edit_message_text(
            bot_module._tg("no_vocabulary_items_found", context=context, user=user)
        )
        return
    try:
        selected_item = raw_items[resolved_item_index]
    except (ValueError, IndexError):
        await query.edit_message_text(
            bot_module._tg("selected_word_unavailable", context=context, user=user)
        )
        return
    if not isinstance(selected_item, dict):
        await query.edit_message_text(
            bot_module._tg("selected_word_unavailable", context=context, user=user)
        )
        return
    item_id = str(selected_item.get("id", "")).strip()
    if not item_id:
        await query.edit_message_text(
            bot_module._tg("selected_word_unavailable", context=context, user=user)
        )
        return
    review_flow = await asyncio.to_thread(
        bot_module._start_published_word_image_review(context).execute,
        user_id=user.id,
        topic_id=resolved_topic_id,
        item_id=item_id,
    )
    await bot_module._send_current_published_image_preview(
        query.message,
        context,
        review_flow,
        user=user,
    )
    await bot_module._send_image_review_step(query.message, context, review_flow, user=user)
    await bot_module._delete_message_if_possible(context, message=query.message)


async def image_review_generate_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    if not bot_module._local_image_generation_available(context):
        await query.edit_message_text(
            bot_module._tg("image_generation_unavailable", context=context, user=user)
        )
        return
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg("start_image_generation", context=context, user=user)
        ),
    )
    await bot_module._prepare_and_send_image_review_step(
        query.message,
        context,
        user.id,
        flow,
        user=user,
    )


async def image_review_search_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    current_position = flow.current_index + 1
    total_items = len(flow.items)
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "pixabay_search_progress",
                context=context,
                user=user,
                current=current_position,
                total=total_items,
            )
        ),
    )
    try:
        updated_flow = await asyncio.to_thread(
            bot_module._search_image_review_candidates(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            query=flow.current_item.search_query,
        )
    except ValueError as error:
        await query.edit_message_text(str(error))
        return
    except Exception:  # noqa: BLE001
        bot_module.logger.exception(
            "Image review Pixabay search callback failed for user=%s",
            user.id,
        )
        await edit_telegram_text_view(
            query,
            bot_module._status_view(
                text=bot_module._tg("searching_pixabay_failed", context=context, user=user)
            ),
        )
        return
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "pixabay_candidates_ready",
                context=context,
                user=user,
                current=current_position,
                total=total_items,
            )
        ),
    )
    await bot_module._send_image_review_step(query.message, context, updated_flow, user=user)


async def image_review_next_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    current_position = flow.current_index + 1
    total_items = len(flow.items)
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "loading_next_pixabay",
                context=context,
                user=user,
                current=current_position,
                total=total_items,
            )
        ),
    )
    try:
        updated_flow = await asyncio.to_thread(
            bot_module._load_next_image_review_candidates(context).execute,
            user_id=user.id,
            flow_id=flow_id,
        )
    except ValueError as error:
        await query.edit_message_text(str(error))
        return
    except Exception:  # noqa: BLE001
        bot_module.logger.exception(
            "Image review next Pixabay page failed for user=%s",
            user.id,
        )
        await edit_telegram_text_view(
            query,
            bot_module._status_view(
                text=bot_module._tg("searching_pixabay_failed", context=context, user=user)
            ),
        )
        return
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "pixabay_candidates_ready",
                context=context,
                user=user,
                current=current_position,
                total=total_items,
            )
        ),
    )
    await bot_module._send_image_review_step(query.message, context, updated_flow, user=user)


async def image_review_previous_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    current_position = flow.current_index + 1
    total_items = len(flow.items)
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "loading_previous_pixabay",
                context=context,
                user=user,
                current=current_position,
                total=total_items,
            )
        ),
    )
    try:
        updated_flow = await asyncio.to_thread(
            bot_module._load_previous_image_review_candidates(context).execute,
            user_id=user.id,
            flow_id=flow_id,
        )
    except ValueError as error:
        await query.edit_message_text(str(error))
        return
    except Exception:  # noqa: BLE001
        bot_module.logger.exception(
            "Image review previous Pixabay page failed for user=%s",
            user.id,
        )
        await edit_telegram_text_view(
            query,
            bot_module._status_view(
                text=bot_module._tg("searching_pixabay_failed", context=context, user=user)
            ),
        )
        return
    await edit_telegram_text_view(
        query,
        bot_module._status_view(
            text=bot_module._tg(
                "pixabay_candidates_ready",
                context=context,
                user=user,
                current=current_position,
                total=total_items,
            )
        ),
    )
    await bot_module._send_image_review_step(query.message, context, updated_flow, user=user)


async def image_review_pick_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id, candidate_index = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    updated_flow = await asyncio.to_thread(
        bot_module._select_image_review_candidate(context).execute,
        user_id=user.id,
        flow_id=flow_id,
        item_id=flow.current_item.item_id,
        candidate_index=int(candidate_index),
    )
    if updated_flow.completed:
        if bot_module._image_review_origin(updated_flow) == "published_word_edit":
            registry = bot_module._telegram_flow_messages(context)
            tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
            await bot_module._delete_tracked_messages(
                context,
                tracked_messages=bot_module._tracked_messages_except_source_message(
                    tracked_messages=tracked_messages,
                    message=query.message,
                ),
            )
            await asyncio.to_thread(
                bot_module._publish_image_review(context).execute,
                user_id=user.id,
                flow_id=flow_id,
                output_path=None,
            )
            bot_module._reload_training_service(context)
            topic = updated_flow.content_pack.get("topic", {})
            topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
            raw_items = updated_flow.content_pack.get("vocabulary_items", [])
            await query.edit_message_text(
                "\n".join(
                    (
                        bot_module._tg("image_selected", context=context, user=user),
                        bot_module._tg("choose_another_word_to_edit", context=context, user=user),
                    )
                ),
                reply_markup=bot_module._published_image_items_keyboard(
                    topic_id=topic_id,
                    raw_items=raw_items if isinstance(raw_items, list) else [],
                    language=bot_module._telegram_ui_language(context, user),
                ),
            )
            if registry is not None:
                registry.clear(flow_id=flow_id)
            return
        output_path = bot_module._resolve_image_review_publish_output_path(updated_flow)
        topic = updated_flow.content_pack.get("topic", {})
        topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
        registry = bot_module._telegram_flow_messages(context)
        tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
        await bot_module._delete_tracked_messages(
            context,
            tracked_messages=bot_module._tracked_messages_except_source_message(
                tracked_messages=tracked_messages,
                message=query.message,
            ),
        )
        await asyncio.to_thread(
            bot_module._publish_image_review(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            output_path=output_path,
        )
        bot_module._reload_training_service(context)
        bot_module._clear_active_word_flow(user.id, context)
        await query.edit_message_text(
            bot_module._tg(
                "image_review_completed_published",
                context=context,
                user=user,
                destination=bot_module._publish_destination_text(
                    context,
                    output_path=output_path,
                    topic_id=topic_id,
                ),
            )
        )
        if registry is not None:
            registry.clear(flow_id=flow_id)
        return
    await query.edit_message_text(
        bot_module._tg("image_selected", context=context, user=user)
    )
    await bot_module._send_image_review_step(query.message, context, updated_flow, user=user)


async def image_review_skip_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    updated_flow = await asyncio.to_thread(
        bot_module._skip_image_review_item(context).execute,
        user_id=user.id,
        flow_id=flow_id,
        item_id=flow.current_item.item_id,
    )
    if updated_flow.completed:
        if bot_module._image_review_origin(updated_flow) == "published_word_edit":
            registry = bot_module._telegram_flow_messages(context)
            tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
            await bot_module._delete_tracked_messages(
                context,
                tracked_messages=bot_module._tracked_messages_except_source_message(
                    tracked_messages=tracked_messages,
                    message=query.message,
                ),
            )
            bot_module._cancel_image_review(context).execute(user_id=user.id)
            topic = updated_flow.content_pack.get("topic", {})
            topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
            raw_items = updated_flow.content_pack.get("vocabulary_items", [])
            await query.edit_message_text(
                bot_module._tg("no_changes_choose_another_word", context=context, user=user),
                reply_markup=bot_module._published_image_items_keyboard(
                    topic_id=topic_id,
                    raw_items=raw_items if isinstance(raw_items, list) else [],
                    language=bot_module._telegram_ui_language(context, user),
                ),
            )
            if registry is not None:
                registry.clear(flow_id=flow_id)
            return
        output_path = bot_module._resolve_image_review_publish_output_path(updated_flow)
        topic = updated_flow.content_pack.get("topic", {})
        topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
        registry = bot_module._telegram_flow_messages(context)
        tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
        await bot_module._delete_tracked_messages(
            context,
            tracked_messages=bot_module._tracked_messages_except_source_message(
                tracked_messages=tracked_messages,
                message=query.message,
            ),
        )
        await asyncio.to_thread(
            bot_module._publish_image_review(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            output_path=output_path,
        )
        bot_module._reload_training_service(context)
        bot_module._clear_active_word_flow(user.id, context)
        await query.edit_message_text(
            bot_module._tg(
                "image_review_completed_published",
                context=context,
                user=user,
                destination=bot_module._publish_destination_text(
                    context,
                    output_path=output_path,
                    topic_id=topic_id,
                ),
            )
        )
        if registry is not None:
            registry.clear(flow_id=flow_id)
        return
    await query.edit_message_text(
        bot_module._tg("image_skipped", context=context, user=user)
    )
    await bot_module._send_image_review_step(query.message, context, updated_flow, user=user)


async def image_review_edit_prompt_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import start_image_review_text_edit_interaction

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    instruction_view, current_prompt_view = build_image_review_prompt_edit_view(
        instruction_text=bot_module._tg("send_new_full_prompt", context=context, user=user),
        current_prompt_text=bot_module._tg(
            "current_prompt",
            context=context,
            user=user,
            prompt=flow.current_item.prompt,
        ),
        instruction_markup=ForceReply(selective=True),
    )
    prompt_message = await send_telegram_view(query.message, instruction_view)
    start_image_review_text_edit_interaction(
        context,
        mode=bot_module._IMAGE_REVIEW_AWAITING_PROMPT_TEXT,
        flow_id=flow_id,
        item_id=flow.current_item.item_id,
        chat_id=bot_module._message_chat_id(prompt_message),
        message_id=getattr(prompt_message, "message_id", None),
    )
    await send_telegram_view(query.message, current_prompt_view)


async def image_review_edit_search_query_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram.interaction import start_image_review_text_edit_interaction

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    current_query = flow.current_item.search_query or flow.current_item.english_word
    instruction_view, current_query_view = build_image_review_search_query_edit_view(
        instruction_text=bot_module._tg("send_new_search_query", context=context, user=user),
        current_query_text=bot_module._tg(
            "current_query",
            context=context,
            user=user,
            query=current_query,
        ),
        instruction_markup=ForceReply(selective=True),
    )
    prompt_message = await send_telegram_view(query.message, instruction_view)
    start_image_review_text_edit_interaction(
        context,
        mode=bot_module._IMAGE_REVIEW_AWAITING_SEARCH_QUERY_TEXT,
        flow_id=flow_id,
        item_id=flow.current_item.item_id,
        chat_id=bot_module._message_chat_id(prompt_message),
        message_id=getattr(prompt_message, "message_id", None),
    )
    await send_telegram_view(query.message, current_query_view)


async def image_review_show_json_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    current_item_id = flow.current_item.item_id
    raw_items = flow.content_pack.get("vocabulary_items", [])
    item_payload: dict[str, object] | None = None
    if isinstance(raw_items, list):
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            if str(raw_item.get("id", "")).strip() != current_item_id:
                continue
            item_payload = raw_item
            break
    if item_payload is None:
        item_payload = {
            "id": flow.current_item.item_id,
            "english_word": flow.current_item.english_word,
            "translation": flow.current_item.translation,
            "image_prompt": flow.current_item.prompt,
            "pixabay_search_query": flow.current_item.search_query,
        }
    payload = json.dumps(item_payload, ensure_ascii=False, indent=2)
    if len(payload) > 3500:
        payload = payload[:3400].rstrip() + "\n..."
    await query.message.reply_text(f"```json\n{payload}\n```", parse_mode="Markdown")


async def image_review_attach_photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(
            bot_module._tg("image_review_flow_inactive", context=context, user=user)
        )
        return
    context.user_data["words_flow_mode"] = bot_module._IMAGE_REVIEW_AWAITING_PHOTO
    context.user_data["image_review_flow_id"] = flow_id
    context.user_data["image_review_item_id"] = flow.current_item.item_id
    await send_telegram_view(
        query.message,
        build_image_review_attach_photo_view(
            instruction_text=bot_module._tg("attach_one_photo", context=context, user=user),
            instruction_markup=ForceReply(selective=True),
        ),
    )


async def image_review_photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if context.user_data.get("words_flow_mode") != bot_module._IMAGE_REVIEW_AWAITING_PHOTO:
        return
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None or not getattr(message, "photo", None):
        return
    flow_id = context.user_data.get("image_review_flow_id")
    item_id = context.user_data.get("image_review_item_id")
    flow = bot_module._get_active_image_review(context).execute(user_id=user.id)
    if (
        flow is None
        or flow.flow_id != flow_id
        or flow.current_item is None
        or flow.current_item.item_id != item_id
    ):
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("image_review_flow_id", None)
        context.user_data.pop("image_review_item_id", None)
        await message.reply_text(
            bot_module._tg("image_review_task_inactive", context=context, user=user)
        )
        return
    context.user_data.pop("words_flow_mode", None)
    context.user_data.pop("image_review_flow_id", None)
    context.user_data.pop("image_review_item_id", None)
    status_message = await message.reply_text(
        bot_module._tg("saving_uploaded_photo", context=context, user=user)
    )
    photo = message.photo[-1]
    telegram_file = await photo.get_file()
    topic = flow.content_pack.get("topic", {})
    topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
    output_path = (
        bot_module._image_review_assets_dir(context)
        / topic_id
        / "review"
        / f"{item_id}--user-upload.jpg"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await telegram_file.download_to_drive(custom_path=str(output_path))
    image_ref = output_path.as_posix()
    updated_flow = await asyncio.to_thread(
        bot_module._attach_uploaded_image(context).execute,
        user_id=user.id,
        flow_id=flow_id,
        item_id=item_id,
        image_ref=image_ref,
        output_path=output_path,
    )
    await status_message.edit_text(
        bot_module._status_view(
            text=bot_module._tg("uploaded_photo_attached", context=context, user=user)
        ).text
    )
    if updated_flow.completed:
        output_path = bot_module._resolve_image_review_publish_output_path(updated_flow)
        topic = updated_flow.content_pack.get("topic", {})
        topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
        registry = bot_module._telegram_flow_messages(context)
        tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
        await bot_module._delete_tracked_messages(context, tracked_messages=tracked_messages)
        await asyncio.to_thread(
            bot_module._publish_image_review(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            output_path=output_path,
        )
        bot_module._reload_training_service(context)
        bot_module._clear_active_word_flow(user.id, context)
        await message.reply_text(
            bot_module._tg(
                "image_review_completed_published",
                context=context,
                user=user,
                destination=bot_module._publish_destination_text(
                    context,
                    output_path=output_path,
                    topic_id=topic_id,
                ),
            )
        )
        return
    await bot_module._send_image_review_step(message, context, updated_flow)
