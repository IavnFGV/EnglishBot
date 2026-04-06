from __future__ import annotations

import asyncio
from pathlib import Path

from telegram.ext import ContextTypes

from englishbot.image_generation.paths import resolve_existing_image_path
from englishbot.image_generation.previews import ensure_numbered_candidate_strip
from englishbot.presentation.telegram_views import (
    build_current_image_preview_view,
    build_image_review_step_view,
    send_telegram_view,
)


async def prepare_and_send_image_review_step(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    flow,
    *,
    user=None,
) -> None:
    import englishbot.bot as bot_module

    resolved_user = user or getattr(message, "from_user", None)
    current_item = flow.current_item
    if current_item is None:
        await message.reply_text(
            bot_module._tg(
                "image_review_completed",
                context=context,
                user=resolved_user,
            )
        )
        return
    total_items = len(flow.items)
    current_position = flow.current_index + 1
    status_message = await message.reply_text(
        bot_module._tg(
            "local_candidates_generating",
            context=context,
            user=resolved_user,
            current=current_position,
            total=total_items,
        )
    )
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        bot_module._run_status_heartbeat(
            status_message,
            stage=f"Generating local image candidates {current_position}/{total_items}",
            stop_event=stop_event,
        )
    )
    try:
        prepared_flow = await asyncio.to_thread(
            bot_module._generate_image_review_candidates(context).execute,
            user_id=user_id,
            flow_id=flow.flow_id,
        )
    finally:
        stop_event.set()
        await heartbeat_task
    await status_message.edit_text(
        bot_module._status_view(
            text=bot_module._tg(
                "local_candidates_ready",
                context=context,
                user=resolved_user,
                current=current_position,
                total=total_items,
            )
        ).text
    )
    await send_image_review_step(
        message,
        context,
        prepared_flow,
        user=resolved_user,
    )


async def send_current_published_image_preview(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    flow,
    *,
    user=None,
) -> None:
    import englishbot.bot as bot_module

    current_item = flow.current_item
    if current_item is None:
        return
    registry = bot_module._telegram_flow_messages(context)
    if registry is not None:
        await bot_module._delete_tracked_messages(
            context,
            tracked_messages=registry.list(
                flow_id=flow.flow_id,
                tag=bot_module._IMAGE_REVIEW_CONTEXT_TAG,
            ),
        )
    fallback_chat_id = bot_module._message_chat_id(message)
    raw_items = flow.content_pack.get("vocabulary_items", [])
    if not isinstance(raw_items, list):
        return
    image_ref: str | None = None
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        if str(raw_item.get("id", "")).strip() != current_item.item_id:
            continue
        raw_image_ref = raw_item.get("image_ref")
        if isinstance(raw_image_ref, str) and raw_image_ref.strip():
            image_ref = raw_image_ref
        break
    resolved_user = user or getattr(message, "from_user", None)
    image_path = resolve_existing_image_path(image_ref)
    preview_view = build_current_image_preview_view(
        image_path=image_path,
        current_image_intro=bot_module._tg(
            "current_image_intro",
            context=context,
            user=resolved_user,
        ),
        no_current_image_intro=bot_module._tg(
            "no_current_image_intro",
            context=context,
            user=resolved_user,
        ),
    )
    preview_message = await send_telegram_view(message, preview_view)
    bot_module._track_flow_message(
        context,
        flow_id=flow.flow_id,
        tag=bot_module._IMAGE_REVIEW_CONTEXT_TAG,
        message=preview_message,
        fallback_chat_id=fallback_chat_id,
    )


async def send_image_review_step(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    flow,
    *,
    user=None,
) -> None:
    import englishbot.bot as bot_module

    resolved_user = user or getattr(message, "from_user", None)
    current_item = flow.current_item
    if current_item is None:
        await message.reply_text(
            bot_module._tg(
                "image_review_completed",
                context=context,
                user=resolved_user,
            )
        )
        return
    registry = bot_module._telegram_flow_messages(context)
    tracked_before = (
        registry.list(flow_id=flow.flow_id, tag=bot_module._IMAGE_REVIEW_STEP_TAG)
        if registry is not None
        else []
    )
    fallback_chat_id = bot_module._message_chat_id(message)
    total_items = len(flow.items)
    current_position = flow.current_index + 1
    generation_lines: list[str] = []
    generation_metadata = getattr(current_item, "candidate_generation_metadata", None)
    if generation_metadata is not None and generation_metadata.status_messages:
        generation_lines.extend(generation_metadata.status_messages)
    summary_view = build_image_review_step_view(
        current_position=current_position,
        total_items=total_items,
        english_word=current_item.english_word,
        translation=current_item.translation,
        prompt=current_item.prompt,
        candidate_source_type=current_item.candidate_source_type,
        search_query=current_item.search_query,
        search_page=current_item.search_page,
        generation_status_messages=generation_lines,
        reply_markup=bot_module._image_review_markup(
            flow_id=flow.flow_id,
            current_item=current_item,
            context=context,
            user=resolved_user,
        ),
        translate=bot_module._tg,
        user=resolved_user,
    )
    summary_message = await send_telegram_view(message, summary_view)
    bot_module._track_flow_message(
        context,
        flow_id=flow.flow_id,
        tag=bot_module._IMAGE_REVIEW_STEP_TAG,
        message=summary_message,
        fallback_chat_id=fallback_chat_id,
    )
    if current_item.candidates:
        strip_path = build_image_review_candidate_strip(
            flow=flow,
            item_id=current_item.item_id,
            candidate_paths=[candidate.output_path for candidate in current_item.candidates],
        )
        with strip_path.open("rb") as photo_file:
            sent_photo = await message.reply_photo(photo=photo_file)
        bot_module._track_flow_message(
            context,
            flow_id=flow.flow_id,
            tag=bot_module._IMAGE_REVIEW_STEP_TAG,
            message=sent_photo,
            fallback_chat_id=fallback_chat_id,
        )
    await bot_module._delete_tracked_messages(context, tracked_messages=tracked_before)


def build_image_review_candidate_strip(*, flow, item_id: str, candidate_paths: list[Path]) -> Path:
    review_dir = candidate_paths[0].parent
    output_path = review_dir / f"{flow.flow_id}-{item_id}--review-strip-256.jpg"
    return ensure_numbered_candidate_strip(
        source_paths=candidate_paths,
        output_path=output_path,
        tile_size=256,
    )
