from __future__ import annotations

from pathlib import Path

from telegram.ext import ContextTypes


def active_word_flow_for_user(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._active_word_flow_for_user(user_id, context)


def clear_active_word_flow(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    import englishbot.bot as bot_module

    bot_module._clear_active_word_flow(user_id, context)


def start_add_words_flow(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._start_add_words_flow(context)


def apply_add_words_edit(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._apply_add_words_edit(context)


def regenerate_add_words_draft(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._regenerate_add_words_draft(context)


def approve_add_words_draft(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._approve_add_words_draft(context)


def save_approved_add_words_draft(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._save_approved_add_words_draft(context)


def generate_add_words_image_prompts(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._generate_add_words_image_prompts(context)


def mark_add_words_image_review_started(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._mark_add_words_image_review_started(context)


def start_image_review(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._start_image_review(context)


def start_published_word_image_review(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._start_published_word_image_review(context)


def get_active_image_review(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._get_active_image_review(context)


def cancel_image_review(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._cancel_image_review(context)


def search_image_review_candidates(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._search_image_review_candidates(context)


def load_next_image_review_candidates(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._load_next_image_review_candidates(context)


def load_previous_image_review_candidates(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._load_previous_image_review_candidates(context)


def select_image_review_candidate(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._select_image_review_candidate(context)


def skip_image_review_item(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._skip_image_review_item(context)


def publish_image_review(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._publish_image_review(context)


def update_image_review_prompt(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._update_image_review_prompt(context)


def attach_uploaded_image(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._attach_uploaded_image(context)


def draft_checkpoint_text(flow) -> str:
    import englishbot.bot as bot_module

    return bot_module._draft_checkpoint_text(flow)


def draft_status_text(result) -> str:
    import englishbot.bot as bot_module

    return bot_module._draft_status_text(result)


def draft_failure_message(result) -> str | None:
    import englishbot.bot as bot_module

    return bot_module._draft_failure_message(result)


def draft_prompt_count(result) -> int | None:
    import englishbot.bot as bot_module

    return bot_module._draft_prompt_count(result)


def get_preview_message_id(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    import englishbot.bot as bot_module

    return bot_module._get_preview_message_id(user_id, context)


def set_preview_message_id(user_id: int, message_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    import englishbot.bot as bot_module

    bot_module._set_preview_message_id(user_id, message_id, context)


def preview_message_ids(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._preview_message_ids(context)


def image_review_assets_dir(context: ContextTypes.DEFAULT_TYPE) -> Path:
    import englishbot.bot as bot_module

    return bot_module._image_review_assets_dir(context)


def resolve_image_review_publish_output_path(flow) -> Path | None:
    import englishbot.bot as bot_module

    return bot_module._resolve_image_review_publish_output_path(flow)


def image_review_origin(flow) -> str:
    import englishbot.bot as bot_module

    return bot_module._image_review_origin(flow)


def generate_content_pack_images(context: ContextTypes.DEFAULT_TYPE):
    import englishbot.bot as bot_module

    return bot_module._generate_content_pack_images(context)
