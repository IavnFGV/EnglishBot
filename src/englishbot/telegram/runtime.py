from __future__ import annotations

from telegram.ext import ContextTypes


def tg(key: str, *args, **kwargs):
    import englishbot.bot as bot_module

    return bot_module._tg(key, *args, **kwargs)


def telegram_ui_language(context: ContextTypes.DEFAULT_TYPE, user) -> str:
    import englishbot.bot as bot_module

    return bot_module._telegram_ui_language(context, user)


def telegram_ui_language_for_user_id(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> str:
    import englishbot.bot as bot_module

    return bot_module._telegram_ui_language_for_user_id(context, user_id=user_id)


def message_chat_id(message) -> int | None:
    import englishbot.bot as bot_module

    return bot_module._message_chat_id(message)


def service(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._service(context)


def content_store(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._content_store(context)


def optional_bot_data(context: ContextTypes.DEFAULT_TYPE, key: str):
    import englishbot.bot as bot_module

    return bot_module._optional_bot_data(context, key)


def mutable_bot_data_dict(
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
    *,
    fallback_key: str | None = None,
):
    import englishbot.bot as bot_module

    return bot_module._mutable_bot_data_dict(context, key, fallback_key=fallback_key)


def optional_user_data(context: ContextTypes.DEFAULT_TYPE, key: str):
    import englishbot.bot as bot_module

    return bot_module._optional_user_data(context, key)


def set_user_data(context: ContextTypes.DEFAULT_TYPE, key: str, value) -> None:
    import englishbot.bot as bot_module

    bot_module._set_user_data(context, key, value)


def pop_user_data(context: ContextTypes.DEFAULT_TYPE, key: str):
    import englishbot.bot as bot_module

    return bot_module._pop_user_data(context, key)


def active_word_flow_for_user(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._active_word_flow_for_user(user_id, context)


def clear_active_word_flow(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    import englishbot.bot as bot_module

    bot_module._clear_active_word_flow(user_id, context)


def get_active_image_review(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._get_active_image_review(context)


def reload_training_service(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._reload_training_service(context)


def publish_image_review(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._publish_image_review(context)


def resolve_image_review_publish_output_path(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._resolve_image_review_publish_output_path(context)


def known_assignment_users(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    viewer_user_id: int | None,
    viewer_username: str | None,
):
    import englishbot.bot as bot_module

    return bot_module._known_assignment_users(
        context,
        viewer_user_id=viewer_user_id,
        viewer_username=viewer_username,
    )


def publish_destination_text(result, *, context: ContextTypes.DEFAULT_TYPE) -> str:
    import englishbot.bot as bot_module

    return bot_module._publish_destination_text(result, context=context)


def has_menu_permission(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int | None,
    permission: str,
) -> bool:
    import englishbot.bot as bot_module

    return bot_module._has_menu_permission(context, user_id=user_id, permission=permission)


def is_admin(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    import englishbot.bot as bot_module

    return bot_module._is_admin(user_id, context)


def draft_checkpoint_text(result, *, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    import englishbot.bot as bot_module

    return bot_module._draft_checkpoint_text(result, context=context)


def draft_prompt_count(result) -> int | None:
    import englishbot.bot as bot_module

    return bot_module._draft_prompt_count(result)


async def run_status_heartbeat(
    status_message,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    lines: list[str],
):
    import englishbot.bot as bot_module

    return await bot_module._run_status_heartbeat(status_message, context, lines=lines)


def visible_command_rows(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int | None,
) -> list[list[str]]:
    import englishbot.bot as bot_module

    return bot_module._visible_command_rows(context, user_id=user_id)


def start_training_session_with_ui_language(
    service_instance,
    *,
    user_id: int,
    topic_id: str,
    mode,
    ui_language: str,
    lesson_id: str | None = None,
    adaptive_per_word: bool = False,
):
    import englishbot.bot as bot_module

    return bot_module._start_training_session_with_ui_language(
        service_instance,
        user_id=user_id,
        topic_id=topic_id,
        lesson_id=lesson_id,
        mode=mode,
        adaptive_per_word=adaptive_per_word,
        ui_language=ui_language,
    )


def active_training_session(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._active_training_session(context, user_id=user_id)


def assignment_kind_label(kind, *, context: ContextTypes.DEFAULT_TYPE, user) -> str:
    import englishbot.bot as bot_module

    return bot_module._assignment_kind_label(kind, context=context, user=user)


def tts_service_enabled(context: ContextTypes.DEFAULT_TYPE) -> bool:
    import englishbot.bot as bot_module

    return bot_module._tts_service_enabled(context)


def tts_has_multiple_voices(context: ContextTypes.DEFAULT_TYPE) -> bool:
    import englishbot.bot as bot_module

    return bot_module._tts_has_multiple_voices(context)


def tts_voice_variants(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._tts_voice_variants(context)


def tts_selected_voice_name(context: ContextTypes.DEFAULT_TYPE, *, item_id: str):
    import englishbot.bot as bot_module

    return bot_module._tts_selected_voice_name(context, item_id=item_id)


def tts_voice_label(context: ContextTypes.DEFAULT_TYPE, *, user, voice_name: str) -> str:
    import englishbot.bot as bot_module

    return bot_module._tts_voice_label(context, user=user, voice_name=voice_name)


def tts_recent_request(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._tts_recent_request(context)


def set_tts_recent_request(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    item_id: str,
    voice_name: str,
    sent_at: float,
) -> None:
    import englishbot.bot as bot_module

    bot_module._set_tts_recent_request(
        context,
        item_id=item_id,
        voice_name=voice_name,
        sent_at=sent_at,
    )


def game_state(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._game_state(context)


def job_queue_or_none(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._job_queue_or_none(context)


def normalize_telegram_ui_language(value: str | None) -> str:
    import englishbot.bot as bot_module

    return bot_module._normalize_telegram_ui_language(value)


def image_review_markup(
    *,
    flow_id: str,
    current_item,
    context: ContextTypes.DEFAULT_TYPE,
    user,
):
    import englishbot.bot as bot_module

    return bot_module._image_review_markup(
        flow_id=flow_id,
        current_item=current_item,
        context=context,
        user=user,
    )


def generate_image_review_candidates(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._generate_image_review_candidates(context)


def list_editable_topics(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._list_editable_topics(context)


def list_editable_words(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._list_editable_words(context)


def topic_item_counts(context: ContextTypes.DEFAULT_TYPE, topic_ids: list[str]):
    import englishbot.bot as bot_module

    return bot_module._topic_item_counts(context, topic_ids)


def local_image_generation_available(context: ContextTypes.DEFAULT_TYPE) -> bool:
    import englishbot.bot as bot_module

    return bot_module._local_image_generation_available(context)
