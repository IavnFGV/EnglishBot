from __future__ import annotations

DEFAULT_TELEGRAM_UI_LANGUAGE = "en"

_EN: dict[str, str] = {
    "draft_checkpoint_saved_db": "Draft checkpoint saved in database.",
    "only_editors_add_words": "Only editors can add words.",
    "only_editors_edit_words": "Only editors can edit published words.",
    "only_editors_edit_images": "Only editors can edit published word images.",
    "no_permission_add_words": "You do not have permission to add words.",
    "selected_word_unavailable": "Selected word is no longer available.",
    "add_words_flow_inactive": "This draft is no longer active.",
    "add_words_flow_cancelled": "Add-words flow cancelled.",
    "word_edit_task_inactive": "This word edit task is no longer active.",
    "image_review_task_inactive": "This image review task is no longer active.",
    "image_review_flow_inactive": "This image review flow is no longer active.",
    "image_review_completed": "Image review completed.",
    "image_selected": "Image selected.",
    "image_skipped": "Image skipped.",
    "start_image_generation": "Starting image generation...",
    "send_photo_not_text": "Send a photo, not text, for this image review step.",
    "updating_image_prompt": "Updating image prompt... 0/1",
    "searching_pixabay": "Searching Pixabay... 0/1",
    "saving_uploaded_photo": "Saving uploaded photo... 0/1",
    "parsing_draft": "Parsing draft... 0/1",
    "re_recognizing_draft": "Re-recognizing draft... 0/1",
    "saving_approved_draft": "Saving approved draft... 0/1",
    "publishing_content_pack": "Publishing content pack... 0/1",
    "draft_finalization_failed": "Draft finalization failed.",
    "published_content_not_found": "Published content pack not found.",
    "no_vocabulary_items_found": "No vocabulary items found in this content pack.",
    "session_started": "Session started.",
    "continue_current_session": "Continuing your current session.",
    "previous_session_discarded": "Previous session discarded.",
    "no_active_session_send_start": "There is no active session anymore. Send /start.",
    "no_active_session_begin": "No active session. Send /start to begin.",
    "training_topics": "Training Topics",
    "add_words": "Add Words",
    "edit_words": "Edit Words",
    "edit_word_image": "Edit Word Image",
    "approve_auto_images": "Approve + Auto Images",
    "manual_image_review": "Manual Image Review",
    "publish_without_images": "Publish Without Images",
    "show_json": "Show JSON",
    "re_recognize_draft": "Re-recognize Draft",
    "edit_text": "Edit Text",
    "cancel": "Cancel",
    "approve_disabled": "Approve Disabled",
    "review_disabled": "Review Disabled",
    "publish_disabled": "Publish Disabled",
    "continue": "Continue",
    "start_over": "Start Over",
    "all_topic_words": "All Topic Words",
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
    "no_topics": "No topics",
    "no_items": "No items",
    "no_words": "No words",
    "words_menu_title": "Words menu.",
    "quick_actions_title": "Quick actions:",
    "published_choose_word_image": "Choose a word to edit its image.",
    "search_images": "Search Images",
    "generate_image": "Generate Image",
    "edit_search_query": "Edit Search Query",
    "edit_prompt": "Edit Prompt",
    "attach_photo": "Attach Photo",
    "skip_for_now": "Skip for now",
    "next_6": "Next 6",
    "previous_6": "Previous 6",
    "use_n": "Use {index}",
    "choose_another_word_to_edit": "Choose another word to edit.",
    "edit_cancelled_choose_word": "Edit cancelled. Choose a word to edit.",
    "send_updated_word_format": "Send the updated word as one line.\nFormat: English: Translation",
    "current_value": "Current value:\n{value}",
    "word_updated": "Word updated.\n{word} — {translation}\nChanges are now available in training.",
    "current_image_intro": "Current image.\nYou can keep it, search Pixabay, generate a local image, edit the prompt, or attach your own photo.",
    "pixabay_search_progress": "Searching Pixabay {current}/{total}...",
    "pixabay_candidates_ready": "Pixabay candidates ready {current}/{total}.",
}

_RU: dict[str, str] = dict(_EN)

_STRINGS = {
    "en": _EN,
    "ru": _RU,
}


def _validate_catalogs() -> None:
    expected = set(_STRINGS[DEFAULT_TELEGRAM_UI_LANGUAGE])
    for language, bundle in _STRINGS.items():
        keys = set(bundle)
        if keys != expected:
            missing = sorted(expected - keys)
            extra = sorted(keys - expected)
            raise RuntimeError(
                f"Telegram UI catalog mismatch for {language}: missing={missing} extra={extra}"
            )


_validate_catalogs()


def telegram_ui_text(key: str, *, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE, **kwargs: object) -> str:
    bundle = _STRINGS.get(language, _STRINGS[DEFAULT_TELEGRAM_UI_LANGUAGE])
    template = bundle.get(key)
    if template is None:
        template = _STRINGS[DEFAULT_TELEGRAM_UI_LANGUAGE][key]
    return template.format(**kwargs)


def supported_telegram_ui_languages() -> tuple[str, ...]:
    return tuple(sorted(_STRINGS))
