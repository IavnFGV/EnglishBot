from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from telegram import (
    BotCommand,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from englishbot.application.add_words_flow import (
    AddWordsFlowHarness,
    build_publish_output_path,
)
from englishbot.application.add_words_use_cases import (
    ApplyAddWordsEditUseCase,
    ApproveAddWordsDraftUseCase,
    CancelAddWordsFlowUseCase,
    GenerateAddWordsImagePromptsUseCase,
    GetActiveAddWordsFlowUseCase,
    MarkAddWordsImageReviewStartedUseCase,
    RegenerateAddWordsDraftUseCase,
    SaveApprovedAddWordsDraftUseCase,
    StartAddWordsFlowUseCase,
)
from englishbot.application.content_pack_image_use_cases import (
    GenerateContentPackImagesUseCase,
)
from englishbot.application.image_review_flow import ImageReviewFlowHarness
from englishbot.application.image_review_use_cases import (
    AttachUploadedImageUseCase,
    GenerateImageReviewCandidatesUseCase,
    GetActiveImageReviewUseCase,
    PublishImageReviewUseCase,
    SelectImageCandidateUseCase,
    SkipImageReviewItemUseCase,
    StartImageReviewUseCase,
    StartPublishedWordImageEditUseCase,
    UpdateImageReviewPromptUseCase,
)
from englishbot.application.published_content_use_cases import (
    ListEditableTopicsUseCase,
    ListEditableWordsUseCase,
    UpdateEditableWordUseCase,
)
from englishbot.application.services import (
    AnswerOutcome,
    ApplicationError,
    InvalidSessionStateError,
    TrainingFacade,
)
from englishbot.bootstrap import build_lesson_import_pipeline, build_training_service
from englishbot.config import Settings
from englishbot.domain.models import Topic, TrainingMode, TrainingQuestion
from englishbot.image_generation.clients import ComfyUIImageGenerationClient
from englishbot.image_generation.paths import resolve_existing_image_path
from englishbot.image_generation.pipeline import ContentPackImageEnricher
from englishbot.image_generation.review import ComfyUIImageCandidateGenerator
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.draft_io import draft_to_data
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import (
    InMemoryAddWordsFlowRepository,
    InMemoryImageReviewFlowRepository,
)
from englishbot.presentation.add_words_text import (
    format_draft_edit_text,
    format_draft_preview,
    parse_edited_vocabulary_line,
)

logger = logging.getLogger(__name__)

_ADD_WORDS_AWAITING_TEXT = "awaiting_raw_text"
_ADD_WORDS_AWAITING_EDIT_TEXT = "awaiting_edit_text"
_IMAGE_REVIEW_AWAITING_PROMPT_TEXT = "awaiting_image_review_prompt_text"
_IMAGE_REVIEW_AWAITING_PHOTO = "awaiting_image_review_photo"
_PUBLISHED_WORD_AWAITING_EDIT_TEXT = "awaiting_published_word_edit_text"


def build_application(settings: Settings) -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    app.bot_data["training_service"] = build_training_service()
    lesson_import_pipeline = build_lesson_import_pipeline(
        ollama_model=settings.ollama_model,
        ollama_base_url=settings.ollama_base_url,
        ollama_temperature=settings.ollama_temperature,
        ollama_top_p=settings.ollama_top_p,
        ollama_num_predict=settings.ollama_num_predict,
        ollama_extract_line_prompt_path=settings.ollama_extract_line_prompt_path,
        ollama_image_prompt_path=settings.ollama_image_prompt_path,
    )
    add_words_flow_repository = InMemoryAddWordsFlowRepository()
    add_words_harness = AddWordsFlowHarness(
        pipeline=lesson_import_pipeline,
    )
    image_review_repository = InMemoryImageReviewFlowRepository()
    image_review_harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=ComfyUIImageCandidateGenerator(),
        assets_dir=Path("assets"),
    )
    content_pack_image_enricher = ContentPackImageEnricher(
        ComfyUIImageGenerationClient()
    )
    app.bot_data["lesson_import_pipeline"] = lesson_import_pipeline
    app.bot_data["editor_user_ids"] = set(settings.editor_user_ids)
    app.bot_data["add_words_start_use_case"] = StartAddWordsFlowUseCase(
        harness=add_words_harness,
        flow_repository=add_words_flow_repository,
    )
    app.bot_data["add_words_get_active_use_case"] = GetActiveAddWordsFlowUseCase(
        add_words_flow_repository
    )
    app.bot_data["add_words_apply_edit_use_case"] = ApplyAddWordsEditUseCase(
        harness=add_words_harness,
        flow_repository=add_words_flow_repository,
    )
    app.bot_data["add_words_regenerate_use_case"] = RegenerateAddWordsDraftUseCase(
        harness=add_words_harness,
        flow_repository=add_words_flow_repository,
    )
    app.bot_data["add_words_approve_use_case"] = ApproveAddWordsDraftUseCase(
        harness=add_words_harness,
        flow_repository=add_words_flow_repository,
    )
    app.bot_data["add_words_save_approved_draft_use_case"] = SaveApprovedAddWordsDraftUseCase(
        harness=add_words_harness,
        flow_repository=add_words_flow_repository,
    )
    app.bot_data["add_words_generate_image_prompts_use_case"] = (
        GenerateAddWordsImagePromptsUseCase(
            harness=add_words_harness,
            flow_repository=add_words_flow_repository,
        )
    )
    app.bot_data["add_words_mark_image_review_started_use_case"] = (
        MarkAddWordsImageReviewStartedUseCase(
            harness=add_words_harness,
            flow_repository=add_words_flow_repository,
        )
    )
    app.bot_data["add_words_cancel_use_case"] = CancelAddWordsFlowUseCase(
        add_words_flow_repository
    )
    app.bot_data["image_review_start_use_case"] = StartImageReviewUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_start_published_word_use_case"] = (
        StartPublishedWordImageEditUseCase(
            harness=image_review_harness,
            repository=image_review_repository,
            content_dir=Path("content/custom"),
        )
    )
    app.bot_data["image_review_get_active_use_case"] = GetActiveImageReviewUseCase(
        image_review_repository
    )
    app.bot_data["image_review_generate_use_case"] = GenerateImageReviewCandidatesUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_select_use_case"] = SelectImageCandidateUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_skip_use_case"] = SkipImageReviewItemUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_publish_use_case"] = PublishImageReviewUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_update_prompt_use_case"] = UpdateImageReviewPromptUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_attach_uploaded_image_use_case"] = AttachUploadedImageUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_assets_dir"] = Path("assets")
    app.bot_data["content_pack_generate_images_use_case"] = GenerateContentPackImagesUseCase(
        enricher=content_pack_image_enricher
    )
    app.bot_data["word_import_preview_message_ids"] = {}
    app.bot_data["list_editable_topics_use_case"] = ListEditableTopicsUseCase(
        content_dir=Path("content/custom")
    )
    app.bot_data["list_editable_words_use_case"] = ListEditableWordsUseCase(
        content_dir=Path("content/custom")
    )
    app.bot_data["update_editable_word_use_case"] = UpdateEditableWordUseCase(
        content_dir=Path("content/custom")
    )

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("words", words_menu_handler))
    app.add_handler(CommandHandler("add_words", add_words_start_handler))
    app.add_handler(CommandHandler("cancel", add_words_cancel_handler))
    app.add_handler(CallbackQueryHandler(continue_session_handler, pattern=r"^session:continue$"))
    app.add_handler(CallbackQueryHandler(restart_session_handler, pattern=r"^session:restart$"))
    app.add_handler(CallbackQueryHandler(topic_selected_handler, pattern=r"^topic:"))
    app.add_handler(CallbackQueryHandler(lesson_selected_handler, pattern=r"^lesson:"))
    app.add_handler(CallbackQueryHandler(mode_selected_handler, pattern=r"^mode:"))
    app.add_handler(CallbackQueryHandler(choice_answer_handler, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(words_menu_callback_handler, pattern=r"^words:menu$"))
    app.add_handler(
        CallbackQueryHandler(words_topics_callback_handler, pattern=r"^words:topics$")
    )
    app.add_handler(
        CallbackQueryHandler(words_add_words_callback_handler, pattern=r"^words:add_words$")
    )
    app.add_handler(
        CallbackQueryHandler(
            words_edit_images_callback_handler,
            pattern=r"^words:edit_images$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(words_edit_words_callback_handler, pattern=r"^words:edit_words$")
    )
    app.add_handler(
        CallbackQueryHandler(
            words_edit_topic_callback_handler,
            pattern=r"^words:edit_topic:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            words_edit_item_callback_handler,
            pattern=r"^words:edit_item:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            add_words_approve_auto_images_handler,
            pattern=r"^words:approve_auto_images:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            add_words_publish_without_images_handler,
            pattern=r"^words:approve_draft:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            add_words_approve_draft_handler,
            pattern=r"^words:start_image_review:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            add_words_regenerate_draft_handler,
            pattern=r"^words:regenerate_draft:",
        )
    )
    app.add_handler(CallbackQueryHandler(add_words_edit_text_handler, pattern=r"^words:edit_text:"))
    app.add_handler(CallbackQueryHandler(add_words_show_json_handler, pattern=r"^words:show_json:"))
    app.add_handler(
        CallbackQueryHandler(
            published_images_menu_handler,
            pattern=r"^words:edit_images_menu:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            published_image_item_handler,
            pattern=r"^words:edit_published_image:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(image_review_pick_handler, pattern=r"^words:image_pick:")
    )
    app.add_handler(
        CallbackQueryHandler(
            image_review_generate_handler,
            pattern=r"^words:image_generate:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(image_review_skip_handler, pattern=r"^words:image_skip:")
    )
    app.add_handler(
        CallbackQueryHandler(
            image_review_edit_prompt_handler,
            pattern=r"^words:image_edit_prompt:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            image_review_attach_photo_handler,
            pattern=r"^words:image_attach_photo:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            add_words_cancel_callback_handler,
            pattern=r"^words:cancel:",
        )
    )
    app.add_handler(
        MessageHandler(filters.PHOTO, image_review_photo_handler),
        group=0,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, add_words_text_handler),
        group=0,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_answer_handler),
        group=1,
    )
    app.add_error_handler(error_handler)
    app.post_init = _post_init
    return app


def _service(context: ContextTypes.DEFAULT_TYPE) -> TrainingFacade:
    return context.application.bot_data["training_service"]


def _lesson_import_pipeline(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["lesson_import_pipeline"]


def _start_add_words_flow(context: ContextTypes.DEFAULT_TYPE) -> StartAddWordsFlowUseCase:
    return context.application.bot_data["add_words_start_use_case"]


def _get_active_add_words_flow(context: ContextTypes.DEFAULT_TYPE) -> GetActiveAddWordsFlowUseCase:
    return context.application.bot_data["add_words_get_active_use_case"]


def _apply_add_words_edit(context: ContextTypes.DEFAULT_TYPE) -> ApplyAddWordsEditUseCase:
    return context.application.bot_data["add_words_apply_edit_use_case"]


def _regenerate_add_words_draft(
    context: ContextTypes.DEFAULT_TYPE,
) -> RegenerateAddWordsDraftUseCase:
    return context.application.bot_data["add_words_regenerate_use_case"]


def _approve_add_words_draft(context: ContextTypes.DEFAULT_TYPE) -> ApproveAddWordsDraftUseCase:
    return context.application.bot_data["add_words_approve_use_case"]


def _save_approved_add_words_draft(
    context: ContextTypes.DEFAULT_TYPE,
) -> SaveApprovedAddWordsDraftUseCase:
    return context.application.bot_data["add_words_save_approved_draft_use_case"]


def _generate_add_words_image_prompts(
    context: ContextTypes.DEFAULT_TYPE,
) -> GenerateAddWordsImagePromptsUseCase:
    return context.application.bot_data["add_words_generate_image_prompts_use_case"]


def _mark_add_words_image_review_started(
    context: ContextTypes.DEFAULT_TYPE,
) -> MarkAddWordsImageReviewStartedUseCase:
    return context.application.bot_data["add_words_mark_image_review_started_use_case"]


def _cancel_add_words_flow(context: ContextTypes.DEFAULT_TYPE) -> CancelAddWordsFlowUseCase:
    return context.application.bot_data["add_words_cancel_use_case"]


def _start_image_review(context: ContextTypes.DEFAULT_TYPE) -> StartImageReviewUseCase:
    return context.application.bot_data["image_review_start_use_case"]


def _start_published_word_image_review(
    context: ContextTypes.DEFAULT_TYPE,
) -> StartPublishedWordImageEditUseCase:
    return context.application.bot_data["image_review_start_published_word_use_case"]


def _get_active_image_review(context: ContextTypes.DEFAULT_TYPE) -> GetActiveImageReviewUseCase:
    return context.application.bot_data["image_review_get_active_use_case"]


def _generate_image_review_candidates(
    context: ContextTypes.DEFAULT_TYPE,
) -> GenerateImageReviewCandidatesUseCase:
    return context.application.bot_data["image_review_generate_use_case"]


def _select_image_review_candidate(
    context: ContextTypes.DEFAULT_TYPE,
) -> SelectImageCandidateUseCase:
    return context.application.bot_data["image_review_select_use_case"]


def _skip_image_review_item(context: ContextTypes.DEFAULT_TYPE) -> SkipImageReviewItemUseCase:
    return context.application.bot_data["image_review_skip_use_case"]


def _publish_image_review(context: ContextTypes.DEFAULT_TYPE) -> PublishImageReviewUseCase:
    return context.application.bot_data["image_review_publish_use_case"]


def _update_image_review_prompt(
    context: ContextTypes.DEFAULT_TYPE,
) -> UpdateImageReviewPromptUseCase:
    return context.application.bot_data["image_review_update_prompt_use_case"]


def _attach_uploaded_image(
    context: ContextTypes.DEFAULT_TYPE,
) -> AttachUploadedImageUseCase:
    return context.application.bot_data["image_review_attach_uploaded_image_use_case"]


def _generate_content_pack_images(
    context: ContextTypes.DEFAULT_TYPE,
) -> GenerateContentPackImagesUseCase:
    return context.application.bot_data["content_pack_generate_images_use_case"]


def _list_editable_topics(context: ContextTypes.DEFAULT_TYPE) -> ListEditableTopicsUseCase:
    return context.application.bot_data["list_editable_topics_use_case"]


def _list_editable_words(context: ContextTypes.DEFAULT_TYPE) -> ListEditableWordsUseCase:
    return context.application.bot_data["list_editable_words_use_case"]


def _update_editable_word(context: ContextTypes.DEFAULT_TYPE) -> UpdateEditableWordUseCase:
    return context.application.bot_data["update_editable_word_use_case"]


def _image_review_assets_dir(context: ContextTypes.DEFAULT_TYPE) -> Path:
    return context.application.bot_data["image_review_assets_dir"]


def _is_editor(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return user_id in context.application.bot_data.get("editor_user_ids", set())


def _preview_message_ids(context: ContextTypes.DEFAULT_TYPE) -> dict[int, int]:
    return context.application.bot_data["word_import_preview_message_ids"]


def _active_word_flow_for_user(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    return _get_active_add_words_flow(context).execute(user_id=user_id)


def _set_preview_message_id(
    user_id: int,
    message_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    _preview_message_ids(context)[user_id] = message_id


def _get_preview_message_id(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    return _preview_message_ids(context).get(user_id)


def _clear_active_word_flow(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    _cancel_add_words_flow(context).execute(user_id=user_id)
    _preview_message_ids(context).pop(user_id, None)


def _draft_item_count(result) -> int | None:
    draft = result.draft
    return len(draft.vocabulary_items) if hasattr(draft, "vocabulary_items") else None


def _draft_prompt_count(result) -> int | None:
    draft = result.draft
    if not hasattr(draft, "vocabulary_items"):
        return None
    return sum(1 for item in draft.vocabulary_items if getattr(item, "image_prompt", None))


def _draft_status_text(result) -> str:
    item_count = _draft_item_count(result)
    prompt_count = _draft_prompt_count(result)
    rendered_item_count = item_count if item_count is not None else "-"
    lines = [
        "Parsing draft... done",
        f"Items found: {rendered_item_count}",
        f"Validation errors: {len(result.validation.errors)}",
    ]
    if prompt_count is not None and prompt_count > 0:
        lines.insert(2, f"Image prompts: {prompt_count}")
    return "\n".join(lines)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    user = update.effective_user
    if user is not None:
        logger.info("User %s opened /start", user.id)
        active_session = _service(context).get_active_session(user_id=user.id)
        if active_session is not None:
            context.user_data["awaiting_text_answer"] = active_session.mode in {
                TrainingMode.MEDIUM,
                TrainingMode.HARD,
            }
            await message.reply_text(
                "You already have an active session.\n"
                f"Topic: {active_session.topic_id}\n"
                f"Lesson: {active_session.lesson_id or 'all topic words'}\n"
                f"Mode: {active_session.mode.value}\n"
                f"Progress: {active_session.current_position}/{active_session.total_items}\n"
                "Do you want to continue or start over?",
                reply_markup=_active_session_keyboard(),
            )
            await message.reply_text(
                "Quick actions:",
                reply_markup=_chat_menu_keyboard(
                    is_editor=bool(user and _is_editor(user.id, context))
                ),
            )
            return
    topics = _service(context).list_topics()
    await message.reply_text(
        "Choose a topic to start training.\nUse /help to see commands.",
        reply_markup=_topic_keyboard(topics),
    )
    await message.reply_text(
        "Quick actions:",
        reply_markup=_chat_menu_keyboard(
            is_editor=bool(user and _is_editor(user.id, context))
        ),
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    commands = [
        "/start - choose a topic and start training",
        "/help - show commands",
        "/words - open the words menu",
    ]
    if user is not None and _is_editor(user.id, context):
        commands.extend(
            [
                "/add_words - send raw lesson text for draft extraction",
                "/cancel - cancel the current add-words flow",
            ]
        )
    await message.reply_text(
        "Available commands:\n" + "\n".join(commands),
        reply_markup=_chat_menu_keyboard(
            is_editor=bool(user and _is_editor(user.id, context))
        ),
    )


async def words_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    await message.reply_text(
        "Words menu.",
        reply_markup=_words_menu_keyboard(is_editor=bool(user and _is_editor(user.id, context))),
    )
    await message.reply_text(
        "Quick actions:",
        reply_markup=_chat_menu_keyboard(
            is_editor=bool(user and _is_editor(user.id, context))
        ),
    )


async def words_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    try:
        await query.edit_message_text(
            "Words menu.",
            reply_markup=_words_menu_keyboard(
                is_editor=bool(
                    update.effective_user and _is_editor(update.effective_user.id, context)
                )
            ),
        )
    except BadRequest as error:
        if "message is not modified" in str(error).lower():
            logger.debug("Words menu message unchanged")
            return
        raise


async def words_topics_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    topics = _service(context).list_topics()
    await query.edit_message_text(
        "Choose a topic to start training.",
        reply_markup=_topic_keyboard(topics),
    )


async def words_add_words_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not _is_editor(user.id, context):
        await query.edit_message_text("Only editors can add words.")
        return
    context.user_data["words_flow_mode"] = _ADD_WORDS_AWAITING_TEXT
    await query.edit_message_text(
        "Send the raw lesson text in one message. The format can be messy.\n"
        "Use /cancel to stop."
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
    if not _is_editor(user.id, context):
        await query.edit_message_text("Only editors can edit published words.")
        return
    topics = _list_editable_topics(context).execute()
    await query.edit_message_text(
        "Choose a topic to edit words.",
        reply_markup=_editable_topics_keyboard(topics),
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
    if not _is_editor(user.id, context):
        await query.edit_message_text("Only editors can edit published word images.")
        return
    topics = _list_editable_topics(context).execute()
    await query.edit_message_text(
        "Choose a topic to edit word images.",
        reply_markup=_published_image_topics_keyboard(topics),
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
    words = _list_editable_words(context).execute(topic_id=topic_id)
    await query.edit_message_text(
        "Choose a word to edit.",
        reply_markup=_editable_words_keyboard(topic_id=topic_id, words=words),
    )


async def words_edit_item_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, topic_id, item_index = query.data.split(":")
    words = _list_editable_words(context).execute(topic_id=topic_id)
    try:
        selected_word = words[int(item_index)]
    except (ValueError, IndexError):
        await query.edit_message_text("Selected word is no longer available.")
        return
    context.user_data["words_flow_mode"] = _PUBLISHED_WORD_AWAITING_EDIT_TEXT
    context.user_data["published_edit_topic_id"] = topic_id
    context.user_data["published_edit_item_id"] = selected_word.id
    await query.edit_message_text(
        "Send the updated word as one line.\n"
        "Format: English: Translation"
    )
    await query.message.reply_text(
        f"Current value:\n{selected_word.english_word}: {selected_word.translation}",
        reply_markup=ForceReply(selective=True),
    )


async def add_words_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    if not _is_editor(user.id, context):
        await message.reply_text("You do not have permission to add words.")
        return
    existing_flow = _active_word_flow_for_user(user.id, context)
    if existing_flow is not None:
        await message.reply_text(
            "You already have an active add-words flow. Send the text now or use /cancel."
        )
        context.user_data["words_flow_mode"] = _ADD_WORDS_AWAITING_TEXT
        return
    context.user_data["words_flow_mode"] = _ADD_WORDS_AWAITING_TEXT
    await message.reply_text(
        "Send the raw lesson text in one message. The format can be messy. Use /cancel to stop.",
        reply_markup=_chat_menu_keyboard(is_editor=True),
    )


async def add_words_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    _clear_active_word_flow(user.id, context)
    context.user_data.pop("words_flow_mode", None)
    await message.reply_text(
        "Add-words flow cancelled.",
        reply_markup=_chat_menu_keyboard(is_editor=_is_editor(user.id, context)),
    )


async def add_words_cancel_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = _active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text("This draft is no longer active.")
        return
    _clear_active_word_flow(user.id, context)
    context.user_data.pop("words_flow_mode", None)
    await query.edit_message_text("Add-words flow cancelled.")
    await query.message.reply_text(
        "Quick actions:",
        reply_markup=_chat_menu_keyboard(is_editor=_is_editor(user.id, context)),
    )


async def add_words_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    words_flow_mode = context.user_data.get("words_flow_mode")
    if words_flow_mode not in {
        _ADD_WORDS_AWAITING_TEXT,
        _ADD_WORDS_AWAITING_EDIT_TEXT,
        _IMAGE_REVIEW_AWAITING_PROMPT_TEXT,
        _IMAGE_REVIEW_AWAITING_PHOTO,
        _PUBLISHED_WORD_AWAITING_EDIT_TEXT,
    }:
        return
    message = update.effective_message
    user = update.effective_user
    if message is None or message.text is None or user is None:
        return
    if not _is_editor(user.id, context):
        context.user_data.pop("words_flow_mode", None)
        return
    if words_flow_mode == _PUBLISHED_WORD_AWAITING_EDIT_TEXT:
        topic_id = context.user_data.get("published_edit_topic_id")
        item_id = context.user_data.get("published_edit_item_id")
        if not isinstance(topic_id, str) or not isinstance(item_id, str):
            context.user_data.pop("words_flow_mode", None)
            context.user_data.pop("published_edit_topic_id", None)
            context.user_data.pop("published_edit_item_id", None)
            await message.reply_text("This word edit task is no longer active.")
            return
        parsed_pair = parse_edited_vocabulary_line(message.text)
        if parsed_pair is None:
            await message.reply_text(
                "Send one line in the format: English: Translation"
            )
            return
        english_word, translation = parsed_pair
        try:
            updated_word = await asyncio.to_thread(
                _update_editable_word(context).execute,
                topic_id=topic_id,
                item_id=item_id,
                english_word=english_word,
                translation=translation,
            )
        except ValueError as error:
            await message.reply_text(str(error))
            return
        context.application.bot_data["training_service"] = build_training_service()
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("published_edit_topic_id", None)
        context.user_data.pop("published_edit_item_id", None)
        await message.reply_text(
            "Word updated.\n"
            f"{updated_word.english_word} — {updated_word.translation}\n"
            "Changes are now available in training."
        )
        await message.reply_text(
            "Quick actions:",
            reply_markup=_chat_menu_keyboard(is_editor=_is_editor(user.id, context)),
        )
        return
    if words_flow_mode == _IMAGE_REVIEW_AWAITING_PROMPT_TEXT:
        review_flow_id = context.user_data.get("image_review_flow_id")
        review_item_id = context.user_data.get("image_review_item_id")
        review_flow = _get_active_image_review(context).execute(user_id=user.id)
        if (
            review_flow is None
            or review_flow.flow_id != review_flow_id
            or review_flow.current_item is None
            or review_flow.current_item.item_id != review_item_id
        ):
            context.user_data.pop("words_flow_mode", None)
            context.user_data.pop("image_review_flow_id", None)
            context.user_data.pop("image_review_item_id", None)
            await message.reply_text("This image review task is no longer active.")
            return
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("image_review_flow_id", None)
        context.user_data.pop("image_review_item_id", None)
        status_message = await message.reply_text("Updating image prompt and regenerating... 0/1")
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _run_status_heartbeat(
                status_message,
                stage="Updating image prompt and regenerating",
                stop_event=stop_event,
            )
        )
        try:
            updated_flow = await asyncio.to_thread(
                _update_image_review_prompt(context).execute,
                user_id=user.id,
                flow_id=review_flow.flow_id,
                item_id=review_item_id,
                prompt=message.text,
            )
        except Exception:  # noqa: BLE001
            stop_event.set()
            await heartbeat_task
            logger.exception("Image review prompt update failed for user=%s", user.id)
            await status_message.edit_text(
                "Updating image prompt... failed\n"
                "Could not update this prompt. Please try again."
            )
            return
        stop_event.set()
        await heartbeat_task
        await status_message.edit_text("Prompt updated. Regenerating image candidates...")
        await _prepare_and_send_image_review_step(message, context, user.id, updated_flow)
        return
    if words_flow_mode == _IMAGE_REVIEW_AWAITING_PHOTO:
        await message.reply_text("Send a photo, not text, for this image review step.")
        return
    if words_flow_mode == _ADD_WORDS_AWAITING_EDIT_TEXT:
        active_flow_id = context.user_data.get("edit_flow_id")
        flow = _active_word_flow_for_user(user.id, context)
        if flow is None or flow.flow_id != active_flow_id:
            context.user_data.pop("words_flow_mode", None)
            context.user_data.pop("edit_flow_id", None)
            await message.reply_text("This draft is no longer active.")
            return
        flow = _apply_add_words_edit(context).execute(
            user_id=user.id,
            flow_id=flow.flow_id,
            edited_text=message.text,
        )
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("edit_flow_id", None)
        await message.reply_text(
            "Draft updated from edited text.",
            reply_markup=_draft_review_keyboard(
                flow.flow_id,
                flow.draft_result.validation.is_valid,
            ),
        )
        preview_message_id = _get_preview_message_id(user.id, context)
        if preview_message_id is not None:
            try:
                await context.bot.edit_message_text(
                    chat_id=message.chat_id,
                    message_id=preview_message_id,
                    text=format_draft_preview(flow.draft_result),
                    reply_markup=_draft_review_keyboard(
                        flow.flow_id,
                        flow.draft_result.validation.is_valid,
                    ),
                )
            except BadRequest as error:
                if "message is not modified" in str(error).lower():
                    logger.debug(
                        "Preview message unchanged after edit flow_id=%s message_id=%s",
                        flow.flow_id,
                        preview_message_id,
                    )
                else:
                    logger.debug("Failed to update preview message after edit", exc_info=True)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to update preview message after edit", exc_info=True)
        return
    logger.info("User %s submitted raw text for add-words flow", user.id)
    status_message = await message.reply_text("Parsing draft... 0/1")
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _run_status_heartbeat(
            status_message,
            stage="Parsing draft",
            stop_event=stop_event,
        )
    )
    try:
        flow = await asyncio.to_thread(
            _start_add_words_flow(context).execute,
            user_id=user.id,
            raw_text=message.text,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Add-words draft extraction failed for user=%s", user.id)
        await status_message.edit_text(
            "Parsing draft... failed\n"
            "Could not parse this text. Please try again or simplify the input."
        )
        context.user_data.pop("words_flow_mode", None)
        return
    finally:
        stop_event.set()
        await heartbeat_task
    context.user_data.pop("words_flow_mode", None)
    await status_message.edit_text(_draft_status_text(flow.draft_result))
    preview_message = await message.reply_text(
        format_draft_preview(flow.draft_result),
        reply_markup=_draft_review_keyboard(flow.flow_id, flow.draft_result.validation.is_valid),
    )
    _set_preview_message_id(user.id, preview_message.message_id, context)


async def add_words_edit_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = _active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text("This draft is no longer active.")
        return
    context.user_data["words_flow_mode"] = _ADD_WORDS_AWAITING_EDIT_TEXT
    context.user_data["edit_flow_id"] = flow.flow_id
    await query.message.reply_text(
        "Edit only the word list below, then send the full edited version back as one message.\n"
        "Use one line per item in the format: English: Translation",
        reply_markup=ForceReply(selective=True),
    )
    await query.message.reply_text(format_draft_edit_text(flow.draft_result.draft))


async def add_words_show_json_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = _active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text("This draft is no longer active.")
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
    flow = _active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text("This draft is no longer active.")
        return
    await query.edit_message_text("Re-recognizing draft... 0/1")
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _run_status_heartbeat(
            query,
            stage="Re-recognizing draft",
            stop_event=stop_event,
        )
    )
    try:
        flow = await asyncio.to_thread(
            _regenerate_add_words_draft(context).execute,
            user_id=user.id,
            flow_id=flow.flow_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Add-words draft regeneration failed for user=%s", user.id)
        await query.edit_message_text(
            "Re-recognizing draft... failed\n"
            "Could not parse this text. Please try again or simplify the input."
        )
        return
    finally:
        stop_event.set()
        await heartbeat_task
    await query.edit_message_text(
        format_draft_preview(flow.draft_result),
        reply_markup=_draft_review_keyboard(flow.flow_id, flow.draft_result.validation.is_valid),
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
    flow = _active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text("This draft is no longer active.")
        return
    result = flow.draft_result
    if not result.validation.is_valid:
        await query.edit_message_text(
            format_draft_preview(result),
            reply_markup=_draft_review_keyboard(flow.flow_id, False),
        )
        return
    await query.edit_message_text(
        "Publishing content pack...\n"
        "Validated items: "
        f"{len(result.draft.vocabulary_items)}/{len(result.draft.vocabulary_items)}"
    )
    approved = _approve_add_words_draft(context).execute(
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    finalized = approved.import_result
    if not finalized.validation.is_valid or finalized.canonicalization is None:
        await query.edit_message_text("Draft finalization failed.")
        return
    context.application.bot_data["training_service"] = build_training_service()
    _preview_message_ids(context).pop(user.id, None)
    await query.edit_message_text(
        "Draft approved and published.\n"
        f"Saved to: {approved.output_path}\n"
        f"Added words: {len(finalized.draft.vocabulary_items)}\n"
        "New words are now available in the bot."
    )
    await query.message.reply_text(
        "Quick actions:",
        reply_markup=_chat_menu_keyboard(is_editor=_is_editor(user.id, context)),
    )


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
    flow = _active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text("This draft is no longer active.")
        return
    result = flow.draft_result
    if not result.validation.is_valid:
        await query.edit_message_text(
            format_draft_preview(result),
            reply_markup=_draft_review_keyboard(flow.flow_id, False),
        )
        return
    await query.edit_message_text("Saving approved draft... 0/1")
    saved_flow = await asyncio.to_thread(
        _save_approved_add_words_draft(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await query.edit_message_text(
        "Approved draft saved.\n"
        f"Draft path: {saved_flow.draft_output_path}\n"
        "Generating image prompts... 0/1"
    )
    prompt_flow = await asyncio.to_thread(
        _generate_add_words_image_prompts(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await query.edit_message_text(
        "Image prompts generated.\n"
        f"Draft path: {prompt_flow.draft_output_path}\n"
        f"Image prompts: {_draft_prompt_count(prompt_flow.draft_result) or 0}\n"
        "Starting image review..."
    )
    image_review_flow = await asyncio.to_thread(
        _start_image_review(context).execute,
        user_id=user.id,
        draft=prompt_flow.draft_result.draft,
    )
    await asyncio.to_thread(
        _mark_add_words_image_review_started(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
        image_review_flow_id=image_review_flow.flow_id,
    )
    await _prepare_and_send_image_review_step(query.message, context, user.id, image_review_flow)


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
    flow = _active_word_flow_for_user(user.id, context)
    if flow is None or flow.flow_id != flow_id:
        await query.edit_message_text("This draft is no longer active.")
        return
    result = flow.draft_result
    if not result.validation.is_valid:
        await query.edit_message_text(
            format_draft_preview(result),
            reply_markup=_draft_review_keyboard(flow.flow_id, False),
        )
        return

    await query.edit_message_text("Saving approved draft... 0/1")
    saved_flow = await asyncio.to_thread(
        _save_approved_add_words_draft(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await query.edit_message_text(
        "Approved draft saved.\n"
        f"Draft path: {saved_flow.draft_output_path}\n"
        "Generating image prompts... 0/1"
    )
    prompt_flow = await asyncio.to_thread(
        _generate_add_words_image_prompts(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await query.edit_message_text(
        "Image prompts generated.\n"
        f"Draft path: {prompt_flow.draft_output_path}\n"
        f"Image prompts: {_draft_prompt_count(prompt_flow.draft_result) or 0}\n"
        "Publishing content pack... 0/1"
    )
    approved = await asyncio.to_thread(
        _approve_add_words_draft(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await query.edit_message_text(
        "Content pack published.\n"
        f"Saved to: {approved.output_path}\n"
        f"Added words: {len(approved.import_result.draft.vocabulary_items)}\n"
        "Generating images... 0/1"
    )
    enriched_pack = await asyncio.to_thread(
        _generate_content_pack_images(context).execute,
        input_path=approved.output_path,
        assets_dir=Path("assets"),
    )
    context.application.bot_data["training_service"] = build_training_service()
    _preview_message_ids(context).pop(user.id, None)
    topic = enriched_pack.get("topic", {})
    topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
    generated_image_count = sum(
        1 for item in enriched_pack.get("vocabulary_items", []) if item.get("image_ref")
    )
    await query.edit_message_text(
        "Draft approved and images generated.\n"
        f"Saved to: {approved.output_path}\n"
        f"Generated images: {generated_image_count}\n"
        "You can edit the image for a specific word if needed.",
        reply_markup=(
            _published_images_menu_keyboard(topic_id=topic_id)
            if topic_id
            else None
        ),
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
    content_path = Path("content/custom") / f"{topic_id}.json"
    if not content_path.exists():
        await query.edit_message_text("Published content pack not found.")
        return
    content_pack = json.loads(content_path.read_text(encoding="utf-8"))
    raw_items = content_pack.get("vocabulary_items", [])
    if not isinstance(raw_items, list) or not raw_items:
        await query.edit_message_text("No vocabulary items found in this content pack.")
        return
    await query.edit_message_text(
        "Choose a word to edit its image.",
        reply_markup=_published_image_items_keyboard(
            topic_id=topic_id,
            raw_items=raw_items,
        ),
    )


async def published_image_item_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, topic_id, item_index = query.data.split(":")
    content_path = Path("content/custom") / f"{topic_id}.json"
    if not content_path.exists():
        await query.edit_message_text("Published content pack not found.")
        return
    content_pack = json.loads(content_path.read_text(encoding="utf-8"))
    raw_items = content_pack.get("vocabulary_items", [])
    if not isinstance(raw_items, list):
        await query.edit_message_text("No vocabulary items found in this content pack.")
        return
    try:
        selected_item = raw_items[int(item_index)]
    except (ValueError, IndexError):
        await query.edit_message_text("Selected word is no longer available.")
        return
    if not isinstance(selected_item, dict):
        await query.edit_message_text("Selected word is no longer available.")
        return
    item_id = str(selected_item.get("id", "")).strip()
    if not item_id:
        await query.edit_message_text("Selected word is no longer available.")
        return
    review_flow = await asyncio.to_thread(
        _start_published_word_image_review(context).execute,
        user_id=user.id,
        topic_id=topic_id,
        item_id=item_id,
    )
    await _send_current_published_image_preview(query.message, review_flow)
    await query.message.reply_text(
        "Choose what to do next.\n"
        f"Word: {review_flow.current_item.english_word} — {review_flow.current_item.translation}\n"
        f"Prompt: {review_flow.current_item.prompt}",
        reply_markup=_published_image_review_start_keyboard(flow_id=review_flow.flow_id),
    )


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
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text("This image review flow is no longer active.")
        return
    await query.edit_message_text("Starting image generation...")
    await _prepare_and_send_image_review_step(query.message, context, user.id, flow)


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
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text("This image review flow is no longer active.")
        return
    updated_flow = await asyncio.to_thread(
        _select_image_review_candidate(context).execute,
        user_id=user.id,
        flow_id=flow_id,
        item_id=flow.current_item.item_id,
        candidate_index=int(candidate_index),
    )
    if updated_flow.completed:
        output_path = build_publish_output_path(
            updated_flow.content_pack,
            custom_content_dir=Path("content/custom"),
        )
        await asyncio.to_thread(
            _publish_image_review(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            output_path=output_path,
        )
        context.application.bot_data["training_service"] = build_training_service()
        _clear_active_word_flow(user.id, context)
        await query.edit_message_text(
            "Image review completed and content pack published.\n"
            f"Saved to: {output_path}\n"
            "New words are now available in the bot."
        )
        return
    await query.edit_message_text("Image selected.")
    await _prepare_and_send_image_review_step(query.message, context, user.id, updated_flow)


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
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text("This image review flow is no longer active.")
        return
    updated_flow = await asyncio.to_thread(
        _skip_image_review_item(context).execute,
        user_id=user.id,
        flow_id=flow_id,
        item_id=flow.current_item.item_id,
    )
    if updated_flow.completed:
        output_path = build_publish_output_path(
            updated_flow.content_pack,
            custom_content_dir=Path("content/custom"),
        )
        await asyncio.to_thread(
            _publish_image_review(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            output_path=output_path,
        )
        context.application.bot_data["training_service"] = build_training_service()
        _clear_active_word_flow(user.id, context)
        await query.edit_message_text(
            "Image review completed and content pack published.\n"
            f"Saved to: {output_path}\n"
            "New words are now available in the bot."
        )
        return
    await query.edit_message_text("Image skipped.")
    await _prepare_and_send_image_review_step(query.message, context, user.id, updated_flow)


async def image_review_edit_prompt_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, flow_id = query.data.split(":")
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if (
        flow is None
        or flow.flow_id != flow_id
        or flow.current_item is None
    ):
        await query.edit_message_text("This image review flow is no longer active.")
        return
    context.user_data["words_flow_mode"] = _IMAGE_REVIEW_AWAITING_PROMPT_TEXT
    context.user_data["image_review_flow_id"] = flow_id
    context.user_data["image_review_item_id"] = flow.current_item.item_id
    await query.message.reply_text(
        "Send a new full image prompt for this word as one message.",
        reply_markup=ForceReply(selective=True),
    )
    await query.message.reply_text(
        f"Current prompt:\n{flow.current_item.prompt}",
    )


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
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if (
        flow is None
        or flow.flow_id != flow_id
        or flow.current_item is None
    ):
        await query.edit_message_text("This image review flow is no longer active.")
        return
    context.user_data["words_flow_mode"] = _IMAGE_REVIEW_AWAITING_PHOTO
    context.user_data["image_review_flow_id"] = flow_id
    context.user_data["image_review_item_id"] = flow.current_item.item_id
    await query.message.reply_text(
        "Attach one photo for this word.",
        reply_markup=ForceReply(selective=True),
    )


async def image_review_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("words_flow_mode") != _IMAGE_REVIEW_AWAITING_PHOTO:
        return
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None or not getattr(message, "photo", None):
        return
    flow_id = context.user_data.get("image_review_flow_id")
    item_id = context.user_data.get("image_review_item_id")
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if (
        flow is None
        or flow.flow_id != flow_id
        or flow.current_item is None
        or flow.current_item.item_id != item_id
    ):
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("image_review_flow_id", None)
        context.user_data.pop("image_review_item_id", None)
        await message.reply_text("This image review task is no longer active.")
        return
    context.user_data.pop("words_flow_mode", None)
    context.user_data.pop("image_review_flow_id", None)
    context.user_data.pop("image_review_item_id", None)
    status_message = await message.reply_text("Saving uploaded photo... 0/1")
    photo = message.photo[-1]
    telegram_file = await photo.get_file()
    topic = flow.content_pack.get("topic", {})
    topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
    output_path = (
        _image_review_assets_dir(context)
        / topic_id
        / "review"
        / f"{item_id}--user-upload.jpg"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await telegram_file.download_to_drive(custom_path=str(output_path))
    image_ref = output_path.as_posix()
    updated_flow = await asyncio.to_thread(
        _attach_uploaded_image(context).execute,
        user_id=user.id,
        flow_id=flow_id,
        item_id=item_id,
        image_ref=image_ref,
        output_path=output_path,
    )
    await status_message.edit_text("Uploaded photo attached.")
    if updated_flow.completed:
        output_path = build_publish_output_path(
            updated_flow.content_pack,
            custom_content_dir=Path("content/custom"),
        )
        await asyncio.to_thread(
            _publish_image_review(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            output_path=output_path,
        )
        context.application.bot_data["training_service"] = build_training_service()
        _clear_active_word_flow(user.id, context)
        await message.reply_text(
            "Image review completed and content pack published.\n"
            f"Saved to: {output_path}\n"
            "New words are now available in the bot."
        )
        return
    await _prepare_and_send_image_review_step(message, context, user.id, updated_flow)


async def continue_session_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    logger.info("User %s chose to continue the active session", user.id)
    try:
        question = _service(context).get_current_question(user_id=user.id)
    except InvalidSessionStateError:
        context.user_data["awaiting_text_answer"] = False
        await query.edit_message_text("There is no active session anymore. Send /start.")
        return
    context.user_data["awaiting_text_answer"] = question.mode in {
        TrainingMode.MEDIUM,
        TrainingMode.HARD,
    }
    await query.edit_message_text("Continuing your current session.")
    await _send_question(update, context, question)


async def restart_session_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    logger.info("User %s chose to discard the active session", user.id)
    _service(context).discard_active_session(user_id=user.id)
    context.user_data["awaiting_text_answer"] = False
    await query.edit_message_text("Previous session discarded.")
    await query.message.reply_text(
        "Choose a topic to start training.",
        reply_markup=_topic_keyboard(_service(context).list_topics()),
    )


async def topic_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    topic_id = query.data.removeprefix("topic:")
    lesson_selection = _service(context).list_lessons_by_topic(topic_id=topic_id)
    if lesson_selection.has_lessons:
        await query.edit_message_text(
            "Choose all words in the topic or a specific lesson.",
            reply_markup=_lesson_keyboard(topic_id, lesson_selection.lessons),
        )
        return
    await query.edit_message_text(
        "Choose a training mode.",
        reply_markup=_mode_keyboard(topic_id, None),
    )


async def lesson_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _, topic_id, lesson_id = query.data.split(":")
    selected_lesson_id = None if lesson_id == "all" else lesson_id
    await query.edit_message_text(
        "Choose a training mode.",
        reply_markup=_mode_keyboard(topic_id, selected_lesson_id),
    )


async def mode_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _, topic_id, lesson_id, mode_value = query.data.split(":")
    service = _service(context)
    user = update.effective_user
    if user is None:
        return
    selected_lesson_id = None if lesson_id == "all" else lesson_id
    try:
        question = service.start_session(
            user_id=user.id,
            topic_id=topic_id,
            lesson_id=selected_lesson_id,
            mode=TrainingMode(mode_value),
        )
    except ApplicationError as error:
        await query.edit_message_text(str(error))
        return
    context.user_data["awaiting_text_answer"] = question.mode in {
        TrainingMode.MEDIUM,
        TrainingMode.HARD,
    }
    await query.edit_message_text("Session started.")
    await _send_question(update, context, question)


async def choice_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    answer = query.data.removeprefix("answer:")
    await _process_answer(update, context, answer)


async def text_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("awaiting_text_answer"):
        return
    message = update.effective_message
    if message is None or message.text is None:
        return
    await _process_answer(update, context, message.text)


async def _process_answer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    answer: str,
) -> None:
    service = _service(context)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    try:
        outcome = service.submit_answer(user_id=user.id, answer=answer)
    except InvalidSessionStateError:
        context.user_data["awaiting_text_answer"] = False
        await message.reply_text("No active session. Send /start to begin.")
        return
    except ApplicationError as error:
        await message.reply_text(str(error))
        return
    context.user_data["awaiting_text_answer"] = bool(
        outcome.next_question is not None
        and outcome.next_question.mode in {TrainingMode.MEDIUM, TrainingMode.HARD}
    )
    await _send_feedback(message, outcome)
    if outcome.next_question is not None:
        await _send_question(update, context, outcome.next_question)


async def _send_feedback(message, outcome: AnswerOutcome) -> None:
    if outcome.result.is_correct:
        text = "Correct."
    else:
        text = f"Not quite. Correct answer: {outcome.result.expected_answer}."
    if outcome.summary is not None:
        text += (
            f"\nSession complete: {outcome.summary.correct_answers}/"
            f"{outcome.summary.total_questions} correct."
        )
    await message.reply_text(text)


async def _send_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,  # noqa: ARG001
    question: TrainingQuestion,
) -> None:
    message = update.effective_message
    if message is None:
        return
    reply_markup = None
    if question.options:
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(option, callback_data=f"answer:{option}")]
                for option in question.options
            ]
        )
    image_path = resolve_existing_image_path(question.image_ref)
    if image_path is not None:
        with image_path.open("rb") as photo_file:
            await message.reply_photo(
                photo=photo_file,
                caption=question.prompt,
                reply_markup=reply_markup,
            )
        return
    await message.reply_text(question.prompt, reply_markup=reply_markup)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram update error. Update=%r", update, exc_info=context.error)


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Start training"),
            BotCommand("help", "Show commands"),
            BotCommand("words", "Open words menu"),
            BotCommand("add_words", "Add words from raw text"),
            BotCommand("cancel", "Cancel current add-words flow"),
        ]
    )


async def _run_status_heartbeat(
    status_target,
    *,
    stage: str,
    stop_event: asyncio.Event,
    interval_seconds: float = 10.0,
) -> None:
    elapsed_seconds = 0
    while not stop_event.is_set():
        await asyncio.sleep(interval_seconds)
        if stop_event.is_set():
            break
        elapsed_seconds += int(interval_seconds)
        try:
            await status_target.edit_text(f"{stage}... still working ({elapsed_seconds}s)")
        except Exception:  # noqa: BLE001
            logger.debug("Failed to update status heartbeat stage=%s", stage, exc_info=True)


async def _prepare_and_send_image_review_step(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    flow,
) -> None:
    current_item = flow.current_item
    if current_item is None:
        await message.reply_text("Image review completed.")
        return
    total_items = len(flow.items)
    current_position = flow.current_index + 1
    status_message = await message.reply_text(
        f"Generating image candidates {current_position}/{total_items}..."
    )
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _run_status_heartbeat(
            status_message,
            stage=f"Generating image candidates {current_position}/{total_items}",
            stop_event=stop_event,
        )
    )
    try:
        prepared_flow = await asyncio.to_thread(
            _generate_image_review_candidates(context).execute,
            user_id=user_id,
            flow_id=flow.flow_id,
        )
    finally:
        stop_event.set()
        await heartbeat_task
    await status_message.edit_text(
        f"Image candidates ready {current_position}/{total_items}"
    )
    await _send_image_review_step(message, prepared_flow)


async def _send_current_published_image_preview(message, flow) -> None:
    current_item = flow.current_item
    if current_item is None:
        return
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
    image_path = resolve_existing_image_path(image_ref)
    if image_path is None:
        await message.reply_text(
            "No current image is saved for this word yet.\n"
            "You can generate new variants, edit the prompt, or attach your own photo."
        )
        return
    with image_path.open("rb") as photo_file:
        await message.reply_photo(
            photo=photo_file,
            caption=(
                "Current image.\n"
                "You can keep it, generate new variants, edit the prompt, or attach your own photo."
            ),
        )


async def _send_image_review_step(message, flow) -> None:
    current_item = flow.current_item
    if current_item is None:
        await message.reply_text("Image review completed.")
        return
    total_items = len(flow.items)
    current_position = flow.current_index + 1
    await message.reply_text(
        "Reviewing images "
        f"{current_position}/{total_items}\n"
        f"{current_item.english_word} — {current_item.translation}\n"
        f"Prompt: {current_item.prompt}",
        reply_markup=_image_review_keyboard(
            flow_id=flow.flow_id,
            item_id=current_item.item_id,
            candidate_count=len(current_item.candidates),
        ),
    )
    for index, candidate in enumerate(current_item.candidates):
        with candidate.output_path.open("rb") as photo_file:
            await message.reply_photo(
                photo=photo_file,
                caption=f"{_candidate_label(index)}. {_model_label(candidate.model_name)}",
            )


def _candidate_label(index: int) -> str:
    return chr(ord("A") + index)


def _model_label(model_name: str) -> str:
    if model_name == "sd15":
        return "SD 1.5"
    return model_name.replace("-", " ").title()


def _draft_review_keyboard(flow_id: str, is_valid: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                "Approve + Auto Images",
                callback_data=f"words:approve_auto_images:{flow_id}",
            ),
            InlineKeyboardButton(
                "Manual Image Review",
                callback_data=f"words:start_image_review:{flow_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "Publish Without Images",
                callback_data=f"words:approve_draft:{flow_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "Re-recognize Draft",
                callback_data=f"words:regenerate_draft:{flow_id}",
            ),
            InlineKeyboardButton(
                "Edit Text",
                callback_data=f"words:edit_text:{flow_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "Show JSON",
                callback_data=f"words:show_json:{flow_id}",
            ),
            InlineKeyboardButton(
                "Cancel",
                callback_data=f"words:cancel:{flow_id}",
            ),
        ],
    ]
    if not is_valid:
        rows[0][0] = InlineKeyboardButton("Approve Disabled", callback_data="words:menu")
        rows[0][1] = InlineKeyboardButton("Review Disabled", callback_data="words:menu")
        rows[1][0] = InlineKeyboardButton("Publish Disabled", callback_data="words:menu")
    return InlineKeyboardMarkup(rows)


def _image_review_keyboard(
    *,
    flow_id: str,
    item_id: str,
    candidate_count: int,
) -> InlineKeyboardMarkup:
    pick_buttons = [
        InlineKeyboardButton(
            f"Use {_candidate_label(index)}",
            callback_data=f"words:image_pick:{flow_id}:{index}",
        )
        for index in range(candidate_count)
    ]
    rows = [pick_buttons]
    rows.append(
        [
            InlineKeyboardButton(
                "Edit Prompt",
                callback_data=f"words:image_edit_prompt:{flow_id}",
            ),
            InlineKeyboardButton(
                "Attach Photo",
                callback_data=f"words:image_attach_photo:{flow_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "Skip",
                callback_data=f"words:image_skip:{flow_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def _published_image_review_start_keyboard(*, flow_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Generate Variants",
                    callback_data=f"words:image_generate:{flow_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "Edit Prompt",
                    callback_data=f"words:image_edit_prompt:{flow_id}",
                ),
                InlineKeyboardButton(
                    "Attach Photo",
                    callback_data=f"words:image_attach_photo:{flow_id}",
                ),
            ],
        ]
    )


def _words_menu_keyboard(*, is_editor: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("Training Topics", callback_data="words:topics")]]
    if is_editor:
        rows.append([InlineKeyboardButton("Add Words", callback_data="words:add_words")])
        rows.append([InlineKeyboardButton("Edit Words", callback_data="words:edit_words")])
        rows.append([InlineKeyboardButton("Edit Word Image", callback_data="words:edit_images")])
    return InlineKeyboardMarkup(rows)


def _published_images_menu_keyboard(*, topic_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Edit Word Image",
                    callback_data=f"words:edit_images_menu:{topic_id}",
                )
            ]
        ]
    )


def _published_image_topics_keyboard(topics) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                topic.title,
                callback_data=f"words:edit_images_menu:{topic.id}",
            )
        ]
        for topic in topics
    ]
    if not rows:
        rows = [[InlineKeyboardButton("No topics", callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def _published_image_items_keyboard(
    *,
    topic_id: str,
    raw_items: list[object],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            continue
        item_id = str(raw_item.get("id", "")).strip()
        english_word = str(raw_item.get("english_word", "")).strip()
        translation = str(raw_item.get("translation", "")).strip()
        if not item_id or not english_word:
            continue
        label = f"{english_word} — {translation}" if translation else english_word
        rows.append(
            [
                InlineKeyboardButton(
                    label[:64],
                    callback_data=f"words:edit_published_image:{topic_id}:{index}",
                )
            ]
        )
    if not rows:
        rows = [[InlineKeyboardButton("No items", callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def _editable_topics_keyboard(topics) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(topic.title, callback_data=f"words:edit_topic:{topic.id}")]
        for topic in topics
    ]
    if not rows:
        rows = [[InlineKeyboardButton("No topics", callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def _editable_words_keyboard(*, topic_id: str, words) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                (
                    f"{word.english_word} — {word.translation}"
                    if word.translation
                    else word.english_word
                )[:64],
                callback_data=f"words:edit_item:{topic_id}:{index}",
            )
        ]
        for index, word in enumerate(words)
    ]
    if not rows:
        rows = [[InlineKeyboardButton("No words", callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def _chat_menu_keyboard(*, is_editor: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("/start"), KeyboardButton("/help")],
        [KeyboardButton("/words")],
    ]
    if is_editor:
        rows.append([KeyboardButton("/add_words"), KeyboardButton("/cancel")])
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def _topic_keyboard(topics: list[Topic]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(topic.title, callback_data=f"topic:{topic.id}")] for topic in topics]
    )


def _active_session_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Continue", callback_data="session:continue"),
                InlineKeyboardButton("Start Over", callback_data="session:restart"),
            ]
        ]
    )


def _lesson_keyboard(topic_id: str, lessons) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("All Topic Words", callback_data=f"lesson:{topic_id}:all")]]
    rows.extend(
        [
            [InlineKeyboardButton(lesson.title, callback_data=f"lesson:{topic_id}:{lesson.id}")]
            for lesson in lessons
        ]
    )
    return InlineKeyboardMarkup(rows)


def _mode_keyboard(topic_id: str, lesson_id: str | None) -> InlineKeyboardMarkup:
    lesson_part = lesson_id or "all"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Easy",
                    callback_data=f"mode:{topic_id}:{lesson_part}:{TrainingMode.EASY.value}",
                ),
                InlineKeyboardButton(
                    "Medium",
                    callback_data=f"mode:{topic_id}:{lesson_part}:{TrainingMode.MEDIUM.value}",
                ),
                InlineKeyboardButton(
                    "Hard",
                    callback_data=f"mode:{topic_id}:{lesson_part}:{TrainingMode.HARD.value}",
                ),
            ]
        ]
    )
