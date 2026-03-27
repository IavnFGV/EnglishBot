from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
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
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from englishbot.application.add_words_flow import (
    AddWordsFlowHarness,
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
    CancelImageReviewFlowUseCase,
    GenerateImageReviewCandidatesUseCase,
    GetActiveImageReviewUseCase,
    LoadNextImageReviewCandidatesUseCase,
    LoadPreviousImageReviewCandidatesUseCase,
    PublishImageReviewUseCase,
    SearchImageReviewCandidatesUseCase,
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
from englishbot.config import RuntimeConfigService, Settings
from englishbot.domain.models import Topic, TrainingMode, TrainingQuestion
from englishbot.image_generation.clients import ComfyUIImageGenerationClient
from englishbot.image_generation.clients import LocalPlaceholderImageGenerationClient
from englishbot.image_generation.pixabay import PixabayImageSearchClient, RemoteImageDownloader
from englishbot.image_generation.paths import resolve_existing_image_path
from englishbot.image_generation.pipeline import ContentPackImageEnricher
from englishbot.image_generation.previews import ensure_numbered_candidate_strip
from englishbot.image_generation.resilient import ResilientImageGenerator
from englishbot.image_generation.review import ComfyUIImageCandidateGenerator
from englishbot.image_generation.smart_generation import ComfyUIImageGenerationGateway
from englishbot.image_generation.smart_generation import DisabledImageGenerationGateway
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import OllamaLessonExtractionClient
from englishbot.importing.draft_io import draft_to_data
from englishbot.importing.smart_parsing import OllamaSmartLessonParsingGateway
from englishbot.importing.smart_parsing import DisabledSmartLessonParsingGateway
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.sqlite_store import SQLiteContentStore
from englishbot.infrastructure.sqlite_store import (
    SQLiteAddWordsFlowRepository,
    SQLiteImageReviewFlowRepository,
    SQLiteTelegramFlowMessageRepository,
)
from englishbot.presentation.add_words_text import (
    format_draft_edit_text,
    parse_edited_vocabulary_line,
)
from englishbot.presentation.telegram_views import (
    TelegramTextView,
    build_active_session_exists_view,
    build_answer_feedback_view,
    build_current_image_preview_view,
    build_draft_preview_view,
    build_editable_topics_view,
    build_editable_words_view,
    build_help_view,
    build_image_review_attach_photo_view,
    build_image_review_prompt_edit_view,
    build_image_review_search_query_edit_view,
    build_image_review_step_view,
    build_lesson_selection_view,
    build_mode_selection_view,
    build_published_word_edit_prompt_view,
    build_quick_actions_view,
    build_status_view,
    build_topic_selection_view,
    build_training_question_view,
    build_words_menu_view,
    edit_telegram_text_view,
    send_telegram_view,
)
from englishbot.presentation.telegram_ui_text import (
    DEFAULT_TELEGRAM_UI_LANGUAGE,
    supported_telegram_ui_languages,
    telegram_ui_text,
)
from englishbot.runtime_version import RuntimeVersionInfo, get_runtime_version_info

logger = logging.getLogger(__name__)

_ADD_WORDS_AWAITING_TEXT = "awaiting_raw_text"
_ADD_WORDS_AWAITING_EDIT_TEXT = "awaiting_edit_text"
_IMAGE_REVIEW_AWAITING_PROMPT_TEXT = "awaiting_image_review_prompt_text"
_IMAGE_REVIEW_AWAITING_SEARCH_QUERY_TEXT = "awaiting_image_review_search_query_text"
_IMAGE_REVIEW_AWAITING_PHOTO = "awaiting_image_review_photo"
_PUBLISHED_WORD_AWAITING_EDIT_TEXT = "awaiting_published_word_edit_text"
_IMAGE_REVIEW_STEP_TAG = "image_review_step"
_IMAGE_REVIEW_CONTEXT_TAG = "image_review_context"
_PUBLISHED_WORD_EDIT_TAG = "published_word_edit"


def _draft_checkpoint_text(flow) -> str:
    if flow.draft_output_path is not None:
        return f"Draft checkpoint: {flow.draft_output_path}"
    return telegram_ui_text("draft_checkpoint_saved_db")


def _normalize_telegram_ui_language(language: str | None) -> str:
    normalized = (language or "").strip().lower()
    if not normalized:
        return DEFAULT_TELEGRAM_UI_LANGUAGE
    primary = normalized.split("-", maxsplit=1)[0]
    if primary == "ua":
        primary = "uk"
    if primary in supported_telegram_ui_languages():
        return primary
    return DEFAULT_TELEGRAM_UI_LANGUAGE


def _telegram_ui_language(context: ContextTypes.DEFAULT_TYPE | None, user=None) -> str:
    configured = DEFAULT_TELEGRAM_UI_LANGUAGE
    if context is not None:
        configured = _normalize_telegram_ui_language(
            context.application.bot_data.get("telegram_ui_language")
        )
    if user is not None:
        user_language_code = getattr(user, "language_code", None)
        user_primary = (user_language_code or "").strip().lower().split("-", maxsplit=1)[0]
        if user_primary == "ua":
            user_primary = "uk"
        if user_primary in supported_telegram_ui_languages():
            return user_primary
    return configured


def _runtime_version_info(context: ContextTypes.DEFAULT_TYPE) -> RuntimeVersionInfo:
    return context.application.bot_data["runtime_version_info"]


def _tg(
    key: str,
    *,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    user=None,
    language: str | None = None,
    **kwargs: object,
) -> str:
    resolved_language = (
        _normalize_telegram_ui_language(language)
        if language is not None
        else _telegram_ui_language(context, user)
    )
    return telegram_ui_text(key, language=resolved_language, **kwargs)


def build_application(
    settings: Settings,
    *,
    config_service: RuntimeConfigService,
) -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    content_store = SQLiteContentStore(db_path=settings.content_db_path)
    content_store.initialize()
    app.bot_data["content_store"] = content_store
    app.bot_data["config_service"] = config_service
    app.bot_data["runtime_version_info"] = get_runtime_version_info()
    app.bot_data["smart_parsing_gateway"] = (
        DisabledSmartLessonParsingGateway()
        if not settings.ollama_enabled
        else OllamaSmartLessonParsingGateway(
            OllamaLessonExtractionClient(
                config_service=config_service,
                model=settings.ollama_model,
                model_file_path=settings.ollama_model_file_path,
                base_url=settings.ollama_base_url,
                timeout=settings.ollama_timeout_sec,
                trace_file_path=settings.ollama_trace_file_path,
                extraction_mode=settings.ollama_extraction_mode,
                temperature=settings.ollama_temperature,
                top_p=settings.ollama_top_p,
                num_predict=settings.ollama_num_predict,
                extract_line_prompt_path=settings.ollama_extract_line_prompt_path,
                extract_text_prompt_path=settings.ollama_extract_text_prompt_path,
            )
        )
    )
    app.bot_data["image_generation_gateway"] = (
        DisabledImageGenerationGateway()
        if not settings.comfyui_enabled
        else ComfyUIImageGenerationGateway(
            ComfyUIImageGenerationClient(config_service=config_service)
        )
    )
    app.bot_data["training_service"] = build_training_service(db_path=settings.content_db_path)
    lesson_import_pipeline = build_lesson_import_pipeline(
        config_service=config_service,
        ollama_enabled=settings.ollama_enabled,
        ollama_model=settings.ollama_model,
        ollama_model_file_path=settings.ollama_model_file_path,
        ollama_base_url=settings.ollama_base_url,
        ollama_timeout_sec=settings.ollama_timeout_sec,
        ollama_trace_file_path=settings.ollama_trace_file_path,
        ollama_extraction_mode=settings.ollama_extraction_mode,
        ollama_temperature=settings.ollama_temperature,
        ollama_top_p=settings.ollama_top_p,
        ollama_num_predict=settings.ollama_num_predict,
        ollama_extract_line_prompt_path=settings.ollama_extract_line_prompt_path,
        ollama_extract_text_prompt_path=settings.ollama_extract_text_prompt_path,
        ollama_image_prompt_path=settings.ollama_image_prompt_path,
    )
    add_words_flow_repository = SQLiteAddWordsFlowRepository(content_store)
    add_words_harness = AddWordsFlowHarness(
        pipeline=lesson_import_pipeline,
        content_store=content_store,
    )
    image_review_repository = SQLiteImageReviewFlowRepository(content_store)
    telegram_flow_message_repository = SQLiteTelegramFlowMessageRepository(content_store)
    image_review_harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=ComfyUIImageCandidateGenerator(),
        image_search_client=(
            PixabayImageSearchClient(
                config_service=config_service,
                api_key=settings.pixabay_api_key,
                base_url=settings.pixabay_base_url,
            )
            if settings.pixabay_api_key
            else None
        ),
        remote_image_downloader=RemoteImageDownloader(),
        assets_dir=Path("assets"),
        content_store=content_store,
    )
    content_pack_image_enricher = ContentPackImageEnricher(
        ResilientImageGenerator(
            external_gateway=(
                DisabledImageGenerationGateway()
                if not settings.comfyui_enabled
                else ComfyUIImageGenerationGateway(
                    ComfyUIImageGenerationClient(config_service=config_service)
                )
            ),
            fallback_client=LocalPlaceholderImageGenerationClient(),
        )
    )
    app.bot_data["lesson_import_pipeline"] = lesson_import_pipeline
    app.bot_data["editor_user_ids"] = set(settings.editor_user_ids)
    app.bot_data["telegram_ui_language"] = _normalize_telegram_ui_language(
        settings.telegram_ui_language
    )
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
            db_path=settings.content_db_path,
        )
    )
    app.bot_data["image_review_get_active_use_case"] = GetActiveImageReviewUseCase(
        image_review_repository
    )
    app.bot_data["image_review_cancel_use_case"] = CancelImageReviewFlowUseCase(
        image_review_repository
    )
    app.bot_data["image_review_generate_use_case"] = GenerateImageReviewCandidatesUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_search_use_case"] = SearchImageReviewCandidatesUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_next_use_case"] = LoadNextImageReviewCandidatesUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_previous_use_case"] = LoadPreviousImageReviewCandidatesUseCase(
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
    app.bot_data["telegram_flow_message_repository"] = telegram_flow_message_repository
    app.bot_data["content_pack_generate_images_use_case"] = GenerateContentPackImagesUseCase(
        enricher=content_pack_image_enricher,
        db_path=settings.content_db_path,
    )
    app.bot_data["word_import_preview_message_ids"] = {}
    app.bot_data["list_editable_topics_use_case"] = ListEditableTopicsUseCase(
        db_path=settings.content_db_path
    )
    app.bot_data["list_editable_words_use_case"] = ListEditableWordsUseCase(
        db_path=settings.content_db_path
    )
    app.bot_data["update_editable_word_use_case"] = UpdateEditableWordUseCase(
        db_path=settings.content_db_path
    )

    app.add_handler(TypeHandler(Update, raw_update_logger_handler), group=-1)
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("version", version_handler))
    app.add_handler(CommandHandler("words", words_menu_handler))
    app.add_handler(CommandHandler("add_words", add_words_start_handler))
    app.add_handler(CommandHandler("cancel", add_words_cancel_handler))
    app.add_handler(ChatMemberHandler(chat_member_logger_handler, ChatMemberHandler.ANY_CHAT_MEMBER))
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
            words_edit_cancel_callback_handler,
            pattern=r"^words:edit_item_cancel:",
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
        CallbackQueryHandler(
            image_review_search_handler,
            pattern=r"^words:image_search:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            image_review_next_handler,
            pattern=r"^words:image_next:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            image_review_previous_handler,
            pattern=r"^words:image_previous:",
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
            image_review_edit_search_query_handler,
            pattern=r"^words:image_edit_search_query:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            image_review_show_json_handler,
            pattern=r"^words:image_show_json:",
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
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
            group_text_observer_handler,
        ),
        group=2,
    )
    app.add_error_handler(error_handler)
    app.post_init = _post_init
    return app


def _service(context: ContextTypes.DEFAULT_TYPE) -> TrainingFacade:
    return context.application.bot_data["training_service"]


def _content_store(context: ContextTypes.DEFAULT_TYPE) -> SQLiteContentStore:
    return context.application.bot_data["content_store"]


def _reload_training_service(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.application.bot_data["training_service"] = build_training_service(
        db_path=_content_store(context).db_path
    )


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


def _cancel_image_review(context: ContextTypes.DEFAULT_TYPE) -> CancelImageReviewFlowUseCase:
    return context.application.bot_data["image_review_cancel_use_case"]


def _generate_image_review_candidates(
    context: ContextTypes.DEFAULT_TYPE,
) -> GenerateImageReviewCandidatesUseCase:
    return context.application.bot_data["image_review_generate_use_case"]


def _search_image_review_candidates(
    context: ContextTypes.DEFAULT_TYPE,
) -> SearchImageReviewCandidatesUseCase:
    return context.application.bot_data["image_review_search_use_case"]


def _load_next_image_review_candidates(
    context: ContextTypes.DEFAULT_TYPE,
) -> LoadNextImageReviewCandidatesUseCase:
    return context.application.bot_data["image_review_next_use_case"]


def _load_previous_image_review_candidates(
    context: ContextTypes.DEFAULT_TYPE,
) -> LoadPreviousImageReviewCandidatesUseCase:
    return context.application.bot_data["image_review_previous_use_case"]


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


def _telegram_flow_messages(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data.get("telegram_flow_message_repository")


def _is_editor(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return user_id in context.application.bot_data.get("editor_user_ids", set())


def _preview_message_ids(context: ContextTypes.DEFAULT_TYPE) -> dict[int, int]:
    return context.application.bot_data["word_import_preview_message_ids"]


@dataclass(frozen=True)
class _EditorAICapabilities:
    smart_parsing_available: bool
    local_image_generation_available: bool


def _smart_parsing_available(context: ContextTypes.DEFAULT_TYPE) -> bool:
    override = context.application.bot_data.get("smart_parsing_available")
    if isinstance(override, bool):
        return override
    gateway = context.application.bot_data.get("smart_parsing_gateway")
    if gateway is None:
        return True
    try:
        return bool(gateway.check_availability().is_available)
    except Exception:  # noqa: BLE001
        logger.exception("Smart parsing availability check failed")
        return False


def _local_image_generation_available(context: ContextTypes.DEFAULT_TYPE) -> bool:
    override = context.application.bot_data.get("local_image_generation_available")
    if isinstance(override, bool):
        return override
    gateway = context.application.bot_data.get("image_generation_gateway")
    if gateway is None:
        return True
    try:
        return bool(gateway.check_availability().is_available)
    except Exception:  # noqa: BLE001
        logger.exception("Image generation availability check failed")
        return False


def _editor_ai_capabilities(context: ContextTypes.DEFAULT_TYPE) -> _EditorAICapabilities:
    return _EditorAICapabilities(
        smart_parsing_available=_smart_parsing_available(context),
        local_image_generation_available=_local_image_generation_available(context),
    )


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
    lines = ["Parsing draft... done"]
    extraction_metadata = getattr(result, "extraction_metadata", None)
    if extraction_metadata is not None:
        lines.extend(extraction_metadata.status_messages)
    lines.extend(
        [
            f"Items found: {rendered_item_count}",
            f"Validation errors: {len(result.validation.errors)}",
        ]
    )
    if prompt_count is not None and prompt_count > 0:
        lines.insert(2, f"Image prompts: {prompt_count}")
    return "\n".join(lines)


def _draft_failure_message(result) -> str | None:
    error_codes = {error.code for error in result.validation.errors}
    if "malformed_result" not in error_codes:
        return None
    draft = result.draft
    if isinstance(draft, dict):
        raw_error = str(draft.get("error", "")).strip()
        lowered = raw_error.lower()
        if "timed out" in lowered or "read timeout" in lowered or "timeout" in lowered:
            return _tg("parsing_draft_failed_timeout")
    return _tg("parsing_draft_failed_generic")


def _draft_review_markup(
    *,
    flow_id: str,
    is_valid: bool,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> InlineKeyboardMarkup:
    capabilities = _editor_ai_capabilities(context)
    return _draft_review_keyboard(
        flow_id,
        is_valid,
        show_auto_image_button=capabilities.local_image_generation_available,
        show_regenerate_button=capabilities.smart_parsing_available,
        language=_telegram_ui_language(context, user),
    )


def _draft_review_view(
    *,
    flow_id: str,
    result,
    is_valid: bool,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return build_draft_preview_view(
        result,
        reply_markup=_draft_review_markup(
            flow_id=flow_id,
            is_valid=is_valid,
            context=context,
            user=user,
        ),
    )


def _image_review_markup(
    *,
    flow_id: str,
    current_item,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> InlineKeyboardMarkup:
    capabilities = _editor_ai_capabilities(context)
    return _image_review_keyboard(
        flow_id=flow_id,
        current_item=current_item,
        show_generate_image_button=capabilities.local_image_generation_available,
        language=_telegram_ui_language(context, user),
    )


def _quick_actions_view(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return build_quick_actions_view(
        text=_tg("quick_actions_title", context=context, user=user),
        reply_markup=_chat_menu_keyboard(
            is_editor=bool(user and _is_editor(user.id, context))
        ),
    )


def _topic_selection_view(
    *,
    text: str,
    topics,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    topic_item_counts = _topic_item_counts(
        context,
        [topic.id for topic in topics],
    )
    return build_topic_selection_view(
        text=text,
        reply_markup=_topic_keyboard(
            topics,
            topic_item_counts=topic_item_counts,
            language=_telegram_ui_language(context, user),
        ),
    )


def _lesson_selection_view(
    *,
    text: str,
    topic_id: str,
    lessons,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return build_lesson_selection_view(
        text=text,
        reply_markup=_lesson_keyboard(
            topic_id,
            lessons,
            language=_telegram_ui_language(context, user),
        ),
    )


def _mode_selection_view(
    *,
    text: str,
    topic_id: str,
    lesson_id: str | None,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return build_mode_selection_view(
        text=text,
        reply_markup=_mode_keyboard(
            topic_id,
            lesson_id,
            language=_telegram_ui_language(context, user),
        ),
    )


def _words_menu_view(
    *,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return build_words_menu_view(
        text=text,
        reply_markup=_words_menu_keyboard(
            is_editor=bool(user and _is_editor(user.id, context)),
            language=_telegram_ui_language(context, user),
        ),
    )


def _help_view(
    *,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return build_help_view(
        text=text,
        reply_markup=_chat_menu_keyboard(
            is_editor=bool(user and _is_editor(user.id, context))
        ),
    )


def _editable_topics_view(
    *,
    text: str,
    topics,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    for_images: bool = False,
) -> TelegramTextView:
    topic_item_counts = _topic_item_counts(
        context,
        [topic.id for topic in topics],
    )
    markup = (
        _published_image_topics_keyboard(
            topics,
            topic_item_counts=topic_item_counts,
            language=_telegram_ui_language(context, user),
        )
        if for_images
        else _editable_topics_keyboard(
            topics,
            topic_item_counts=topic_item_counts,
            language=_telegram_ui_language(context, user),
        )
    )
    return build_editable_topics_view(text=text, reply_markup=markup)


def _editable_words_view(
    *,
    text: str,
    topic_id: str,
    words,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return build_editable_words_view(
        text=text,
        reply_markup=_editable_words_keyboard(
            topic_id=topic_id,
            words=words,
            language=_telegram_ui_language(context, user),
        ),
    )


def _status_view(*, text: str, reply_markup=None) -> TelegramTextView:
    return build_status_view(text=text, reply_markup=reply_markup)


def _resolve_image_review_publish_output_path(flow) -> Path | None:
    return getattr(flow, "output_path", None)


def _publish_destination_text(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    output_path: Path | None,
    topic_id: str | None = None,
) -> str:
    if output_path is None or output_path == _content_store(context).db_path:
        if topic_id:
            return f"Database: {_content_store(context).db_path}\nTopic: {topic_id}"
        return f"Database: {_content_store(context).db_path}"
    return f"Saved to: {output_path}"


def _image_review_origin(flow) -> str:
    metadata = flow.content_pack.get("metadata", {})
    if not isinstance(metadata, dict):
        return "draft_review"
    origin = metadata.get("image_review_origin")
    return str(origin).strip() if origin else "draft_review"


def _is_group_chat(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in {"group", "supergroup"})


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
            await send_telegram_view(
                message,
                build_active_session_exists_view(
                    text=_tg(
                        "active_session_exists",
                        context=context,
                        user=user,
                        topic_id=active_session.topic_id,
                        lesson_id=active_session.lesson_id
                        or _tg("all_topic_words", context=context, user=user),
                        mode=active_session.mode.value,
                        current_position=active_session.current_position,
                        total_items=active_session.total_items,
                    ),
                    reply_markup=_active_session_keyboard(
                        language=_telegram_ui_language(context, user),
                    ),
                ),
            )
            await send_telegram_view(message, _quick_actions_view(context=context, user=user))
            return
    topics = _service(context).list_topics()
    await send_telegram_view(
        message,
        _topic_selection_view(
            text=_tg("choose_topic_start_training_help", context=context, user=user),
            topics=topics,
            context=context,
            user=user,
        ),
    )
    await send_telegram_view(message, _quick_actions_view(context=context, user=user))


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    commands = [
        "/start - choose a topic and start training",
        "/help - show commands",
        "/version - show the current bot version",
        "/words - open the words menu",
    ]
    if user is not None and _is_editor(user.id, context):
        commands.extend(
            [
                "/add_words - send raw lesson text for draft extraction",
                "/cancel - cancel the current add-words flow",
            ]
        )
    await send_telegram_view(
        message,
        _help_view(
            text=_tg("help_title", context=context, user=user, commands="\n".join(commands)),
            context=context,
            user=user,
        ),
    )


async def version_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    version_info = _runtime_version_info(context)
    lines = [
        _tg("version_title", context=context, user=user),
        _tg(
            "version_line",
            context=context,
            user=user,
            version=version_info.package_version,
        ),
    ]
    if version_info.build_number:
        lines.append(
            _tg(
                "build_line",
                context=context,
                user=user,
                build_number=version_info.build_number,
            )
        )
    if version_info.git_sha:
        lines.append(
            _tg(
                "git_sha_line",
                context=context,
                user=user,
                git_sha=version_info.git_sha,
            )
        )
    if version_info.git_branch:
        lines.append(
            _tg(
                "git_branch_line",
                context=context,
                user=user,
                branch=version_info.git_branch,
            )
        )
    await send_telegram_view(
        message,
        build_status_view(text="\n".join(lines)),
    )


async def words_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    await send_telegram_view(
        message,
        _words_menu_view(
            text=_tg("words_menu_prompt", context=context, user=user),
            context=context,
            user=user,
        ),
    )
    await send_telegram_view(message, _quick_actions_view(context=context, user=user))


async def words_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    try:
        await edit_telegram_text_view(
            query,
            _words_menu_view(
                text=_tg("words_menu_title", context=context, user=update.effective_user),
                context=context,
                user=update.effective_user,
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
    topic_view = _topic_selection_view(
        text="Choose a topic to start training.",
        topics=topics,
        context=context,
        user=update.effective_user,
    )
    await edit_telegram_text_view(query, topic_view)


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
        await query.edit_message_text(_tg("only_editors_add_words", context=context, user=user))
        return
    context.user_data["words_flow_mode"] = _ADD_WORDS_AWAITING_TEXT
    await query.edit_message_text(
        _tg("send_raw_lesson_text", context=context, user=user)
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
        await query.edit_message_text(_tg("only_editors_edit_words", context=context, user=user))
        return
    topics = _list_editable_topics(context).execute()
    topics_view = _editable_topics_view(
        text=_tg("choose_topic_edit_words", context=context, user=user),
        topics=topics,
        context=context,
        user=update.effective_user,
    )
    await query.edit_message_text(topics_view.text, reply_markup=topics_view.reply_markup)


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
        await query.edit_message_text(_tg("only_editors_edit_images", context=context, user=user))
        return
    topics = _list_editable_topics(context).execute()
    topics_view = _editable_topics_view(
        text=_tg("choose_topic_edit_images", context=context, user=user),
        topics=topics,
        context=context,
        user=update.effective_user,
        for_images=True,
    )
    await query.edit_message_text(topics_view.text, reply_markup=topics_view.reply_markup)


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
    words_view = _editable_words_view(
        text=_tg("choose_word_to_edit", context=context, user=update.effective_user),
        topic_id=topic_id,
        words=words,
        context=context,
        user=update.effective_user,
    )
    await query.edit_message_text(words_view.text, reply_markup=words_view.reply_markup)


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
        await query.edit_message_text(
            _tg("selected_word_unavailable", context=context, user=user)
        )
        return
    registry = _telegram_flow_messages(context)
    flow_id = _published_word_edit_flow_id(user_id=user.id)
    if registry is not None:
        await _delete_tracked_messages(
            context,
            tracked_messages=registry.list(flow_id=flow_id, tag=_PUBLISHED_WORD_EDIT_TAG),
        )
    context.user_data["words_flow_mode"] = _PUBLISHED_WORD_AWAITING_EDIT_TEXT
    context.user_data["published_edit_topic_id"] = topic_id
    context.user_data["published_edit_item_id"] = selected_word.id
    _track_flow_message(
        context,
        flow_id=flow_id,
        tag=_PUBLISHED_WORD_EDIT_TAG,
        message=query.message,
    )
    instruction_view, current_value_view = build_published_word_edit_prompt_view(
        instruction_text=_tg("send_updated_word_format", context=context, user=user),
        current_value_text=_tg(
            "current_value",
            context=context,
            user=user,
            value=f"{selected_word.english_word}: {selected_word.translation}",
        ),
        instruction_markup=_published_word_edit_keyboard(
            topic_id=topic_id,
            language=_telegram_ui_language(context, update.effective_user),
        ),
        current_value_markup=ForceReply(selective=True),
    )
    await query.edit_message_text(
        instruction_view.text,
        reply_markup=instruction_view.reply_markup,
    )
    helper_message = await send_telegram_view(query.message, current_value_view)
    _track_flow_message(
        context,
        flow_id=flow_id,
        tag=_PUBLISHED_WORD_EDIT_TAG,
        message=helper_message,
        fallback_chat_id=_message_chat_id(query.message),
    )


async def words_edit_cancel_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _, _, topic_id = query.data.split(":")
    registry = _telegram_flow_messages(context)
    flow_id = _published_word_edit_flow_id(user_id=user.id)
    if registry is not None:
        await _delete_tracked_messages(
            context,
            tracked_messages=_tracked_messages_except_source_message(
                tracked_messages=registry.list(
                    flow_id=flow_id,
                    tag=_PUBLISHED_WORD_EDIT_TAG,
                ),
                message=query.message,
            ),
        )
    context.user_data.pop("words_flow_mode", None)
    context.user_data.pop("published_edit_topic_id", None)
    context.user_data.pop("published_edit_item_id", None)
    words = _list_editable_words(context).execute(topic_id=topic_id)
    await query.edit_message_text(
        "Edit cancelled. Choose a word to edit.",
        reply_markup=_editable_words_keyboard(topic_id=topic_id, words=words),
    )
    if registry is not None:
        registry.clear(flow_id=flow_id, tag=_PUBLISHED_WORD_EDIT_TAG)


async def add_words_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    if not _is_editor(user.id, context):
        await message.reply_text(_tg("no_permission_add_words", context=context, user=user))
        return
    existing_flow = _active_word_flow_for_user(user.id, context)
    if existing_flow is not None:
        await message.reply_text(
            _tg("active_add_words_flow_exists", context=context, user=user)
        )
        context.user_data["words_flow_mode"] = _ADD_WORDS_AWAITING_TEXT
        return
    context.user_data["words_flow_mode"] = _ADD_WORDS_AWAITING_TEXT
    await message.reply_text(
        _tg("send_raw_lesson_text_with_menu", context=context, user=user),
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
        _tg("add_words_flow_cancelled", context=context, user=user),
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
        await query.edit_message_text(_tg("add_words_flow_inactive", context=context, user=user))
        return
    _clear_active_word_flow(user.id, context)
    context.user_data.pop("words_flow_mode", None)
    await query.edit_message_text(_tg("add_words_flow_cancelled", context=context, user=user))
    await query.message.reply_text(
        _tg("quick_actions_title", context=context, user=user),
        reply_markup=_chat_menu_keyboard(is_editor=_is_editor(user.id, context)),
    )


async def add_words_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    words_flow_mode = context.user_data.get("words_flow_mode")
    if words_flow_mode not in {
        _ADD_WORDS_AWAITING_TEXT,
        _ADD_WORDS_AWAITING_EDIT_TEXT,
        _IMAGE_REVIEW_AWAITING_PROMPT_TEXT,
        _IMAGE_REVIEW_AWAITING_SEARCH_QUERY_TEXT,
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
            await message.reply_text(_tg("word_edit_task_inactive", context=context, user=user))
            return
        parsed_pair = parse_edited_vocabulary_line(message.text)
        if parsed_pair is None:
            await message.reply_text(
                _tg("send_one_line_word_format", context=context, user=user)
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
        _reload_training_service(context)
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("published_edit_topic_id", None)
        context.user_data.pop("published_edit_item_id", None)
        registry = _telegram_flow_messages(context)
        flow_id = _published_word_edit_flow_id(user_id=user.id)
        if registry is not None:
            await _delete_tracked_messages(
                context,
                tracked_messages=registry.list(
                    flow_id=flow_id,
                    tag=_PUBLISHED_WORD_EDIT_TAG,
                ),
            )
        words = _list_editable_words(context).execute(topic_id=topic_id)
        await message.reply_text(
            _tg(
                "word_updated",
                context=context,
                user=user,
                word=updated_word.english_word,
                translation=updated_word.translation,
            )
        )
        await message.reply_text(
            _tg("choose_another_word_to_edit", context=context, user=user),
            reply_markup=_editable_words_keyboard(
                topic_id=topic_id,
                words=words,
                language=_telegram_ui_language(context, user),
            ),
        )
        if registry is not None:
            registry.clear(flow_id=flow_id, tag=_PUBLISHED_WORD_EDIT_TAG)
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
            await message.reply_text(_tg("image_review_task_inactive", context=context, user=user))
            return
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("image_review_flow_id", None)
        context.user_data.pop("image_review_item_id", None)
        status_message = await message.reply_text(_tg("updating_image_prompt", context=context, user=user))
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _run_status_heartbeat(
                status_message,
                stage="Updating image prompt",
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
                _status_view(
                    text=_tg("updating_image_prompt_failed", context=context, user=user)
                ).text
            )
            return
        stop_event.set()
        await heartbeat_task
        await status_message.edit_text(
            _status_view(text=_tg("prompt_updated", context=context, user=user)).text
        )
        await _send_image_review_step(message, context, updated_flow)
        return
    if words_flow_mode == _IMAGE_REVIEW_AWAITING_SEARCH_QUERY_TEXT:
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
            await message.reply_text(_tg("image_review_task_inactive", context=context, user=user))
            return
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("image_review_flow_id", None)
        context.user_data.pop("image_review_item_id", None)
        status_message = await message.reply_text(_tg("searching_pixabay", context=context, user=user))
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _run_status_heartbeat(
                status_message,
                stage="Searching Pixabay",
                stop_event=stop_event,
            )
        )
        try:
            updated_flow = await asyncio.to_thread(
                _search_image_review_candidates(context).execute,
                user_id=user.id,
                flow_id=review_flow.flow_id,
                query=message.text,
            )
        except Exception:  # noqa: BLE001
            stop_event.set()
            await heartbeat_task
            logger.exception("Image review Pixabay search update failed for user=%s", user.id)
            await status_message.edit_text(
                _status_view(
                    text=_tg("searching_pixabay_failed", context=context, user=user)
                ).text
            )
            return
        stop_event.set()
        await heartbeat_task
        await status_message.edit_text(
            _status_view(text=_tg("pixabay_candidates_updated", context=context, user=user)).text
        )
        await _send_image_review_step(message, context, updated_flow)
        return
    if words_flow_mode == _IMAGE_REVIEW_AWAITING_PHOTO:
        await message.reply_text(_tg("send_photo_not_text", context=context, user=user))
        return
    if words_flow_mode == _ADD_WORDS_AWAITING_EDIT_TEXT:
        active_flow_id = context.user_data.get("edit_flow_id")
        flow = _active_word_flow_for_user(user.id, context)
        if flow is None or flow.flow_id != active_flow_id:
            context.user_data.pop("words_flow_mode", None)
            context.user_data.pop("edit_flow_id", None)
            await message.reply_text(_tg("add_words_flow_inactive", context=context, user=user))
            return
        flow = _apply_add_words_edit(context).execute(
            user_id=user.id,
            flow_id=flow.flow_id,
            edited_text=message.text,
        )
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("edit_flow_id", None)
        preview_view = _draft_review_view(
            flow_id=flow.flow_id,
            result=flow.draft_result,
            is_valid=flow.draft_result.validation.is_valid,
            context=context,
            user=user,
        )
        preview_message_id = _get_preview_message_id(user.id, context)
        await message.reply_text(
            f"{_tg('draft_updated_from_text', context=context, user=user)}\n\n{preview_view.text}",
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
    status_message = await message.reply_text(_tg("parsing_draft", context=context, user=user))
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
            _status_view(text=_tg("parsing_draft_failed_generic", context=context, user=user)).text
        )
        context.user_data.pop("words_flow_mode", None)
        return
    finally:
        stop_event.set()
        await heartbeat_task
    context.user_data.pop("words_flow_mode", None)
    failure_message = _draft_failure_message(flow.draft_result)
    if failure_message is not None:
        await status_message.edit_text(_status_view(text=failure_message).text)
        return
    await status_message.edit_text(
        _status_view(text=_draft_status_text(flow.draft_result)).text
    )
    preview_view = _draft_review_view(
        flow_id=flow.flow_id,
        result=flow.draft_result,
        is_valid=flow.draft_result.validation.is_valid,
        context=context,
        user=user,
    )
    preview_message = await send_telegram_view(message, preview_view)
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
        await query.edit_message_text(_tg("add_words_flow_inactive", context=context, user=user))
        return
    context.user_data["words_flow_mode"] = _ADD_WORDS_AWAITING_EDIT_TEXT
    context.user_data["edit_flow_id"] = flow.flow_id
    await query.message.reply_text(
        _tg("edit_word_list_instruction", context=context, user=user),
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
        await query.edit_message_text(_tg("add_words_flow_inactive", context=context, user=user))
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
        await query.edit_message_text(_tg("add_words_flow_inactive", context=context, user=user))
        return
    if not _smart_parsing_available(context):
        await edit_telegram_text_view(
            query,
            _status_view(text=_tg("smart_parsing_unavailable", context=context, user=user)),
        )
        return
    await edit_telegram_text_view(
        query,
        _status_view(text=_tg("re_recognizing_draft", context=context, user=user)),
    )
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
        await edit_telegram_text_view(
            query,
            _status_view(text=_tg("parsing_draft_failed_generic", context=context, user=user)),
        )
        return
    finally:
        stop_event.set()
        await heartbeat_task
    await query.edit_message_text(
        _draft_review_view(
            flow_id=flow.flow_id,
            result=flow.draft_result,
            is_valid=flow.draft_result.validation.is_valid,
            context=context,
            user=user,
        ).text,
        reply_markup=_draft_review_view(
            flow_id=flow.flow_id,
            result=flow.draft_result,
            is_valid=flow.draft_result.validation.is_valid,
            context=context,
            user=user,
        ).reply_markup,
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
        await query.edit_message_text(_tg("add_words_flow_inactive", context=context, user=user))
        return
    result = flow.draft_result
    if not result.validation.is_valid:
        await query.edit_message_text(
            _draft_review_view(
                flow_id=flow.flow_id,
                result=result,
                is_valid=False,
                context=context,
                user=user,
            ).text,
            reply_markup=_draft_review_view(
                flow_id=flow.flow_id,
                result=result,
                is_valid=False,
                context=context,
                user=user,
            ).reply_markup,
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
        await query.edit_message_text(_tg("draft_finalization_failed", context=context, user=user))
        return
    topic_id = approved.published_topic_id
    _reload_training_service(context)
    _preview_message_ids(context).pop(user.id, None)
    await query.edit_message_text(
        _tg(
            "draft_approved_published",
            context=context,
            user=user,
            destination=_publish_destination_text(context, output_path=approved.output_path, topic_id=topic_id),
            item_count=len(finalized.draft.vocabulary_items),
        )
    )
    await query.message.reply_text(
        _tg("quick_actions_title", context=context, user=user),
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
        await query.edit_message_text(_tg("add_words_flow_inactive", context=context, user=user))
        return
    result = flow.draft_result
    if not result.validation.is_valid:
        await query.edit_message_text(
            _draft_review_view(
                flow_id=flow.flow_id,
                result=result,
                is_valid=False,
                context=context,
                user=user,
            ).text,
            reply_markup=_draft_review_view(
                flow_id=flow.flow_id,
                result=result,
                is_valid=False,
                context=context,
                user=user,
            ).reply_markup,
        )
        return
    await edit_telegram_text_view(
        query,
        _status_view(text=_tg("saving_approved_draft", context=context, user=user)),
    )
    saved_flow = await asyncio.to_thread(
        _save_approved_add_words_draft(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
                "approved_draft_saved_generating_prompts",
                context=context,
                user=user,
                checkpoint=_draft_checkpoint_text(saved_flow),
            )
        ),
    )
    prompt_flow = await asyncio.to_thread(
        _generate_add_words_image_prompts(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
                "image_prompts_generated_starting_review",
                context=context,
                user=user,
                checkpoint=_draft_checkpoint_text(prompt_flow),
                prompt_count=_draft_prompt_count(prompt_flow.draft_result) or 0,
            )
        ),
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
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
                "image_prompts_generated_saved_continue_review",
                context=context,
                user=user,
                checkpoint=_draft_checkpoint_text(prompt_flow),
                prompt_count=_draft_prompt_count(prompt_flow.draft_result) or 0,
            )
        ),
    )
    await _send_image_review_step(query.message, context, image_review_flow)


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
        await query.edit_message_text(_tg("add_words_flow_inactive", context=context, user=user))
        return
    if not _local_image_generation_available(context):
        await query.edit_message_text(_tg("auto_images_unavailable", context=context, user=user))
        return
    result = flow.draft_result
    if not result.validation.is_valid:
        await query.edit_message_text(
            _draft_review_view(
                flow_id=flow.flow_id,
                result=result,
                is_valid=False,
                context=context,
                user=user,
            ).text,
            reply_markup=_draft_review_view(
                flow_id=flow.flow_id,
                result=result,
                is_valid=False,
                context=context,
                user=user,
            ).reply_markup,
        )
        return

    await edit_telegram_text_view(
        query,
        _status_view(text=_tg("saving_approved_draft", context=context, user=user)),
    )
    saved_flow = await asyncio.to_thread(
        _save_approved_add_words_draft(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
                "approved_draft_saved_generating_prompts",
                context=context,
                user=user,
                checkpoint=_draft_checkpoint_text(saved_flow),
            )
        ),
    )
    prompt_flow = await asyncio.to_thread(
        _generate_add_words_image_prompts(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
                "image_prompts_generated_publishing",
                context=context,
                user=user,
                checkpoint=_draft_checkpoint_text(prompt_flow),
                prompt_count=_draft_prompt_count(prompt_flow.draft_result) or 0,
            )
        ),
    )
    approved = await asyncio.to_thread(
        _approve_add_words_draft(context).execute,
        user_id=user.id,
        flow_id=flow.flow_id,
    )
    total_items = len(approved.import_result.draft.vocabulary_items)
    rendered_total_items = total_items if total_items > 0 else 1
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
                "content_pack_published_generating_images",
                context=context,
                user=user,
                destination=_publish_destination_text(context, output_path=approved.output_path, topic_id=approved.published_topic_id),
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
                _status_view(
                    text=_tg(
                        "content_pack_published_generating_images",
                        context=context,
                        user=user,
                        destination=_publish_destination_text(context, output_path=approved.output_path, topic_id=approved.published_topic_id),
                        item_count=len(approved.import_result.draft.vocabulary_items),
                        processed=processed_count,
                        total=total_count,
                    )
                ),
            )

    progress_task = asyncio.create_task(_report_generation_progress())
    try:
        topic_id = approved.published_topic_id
        enrichment_result = await asyncio.to_thread(
            _generate_content_pack_images(context).execute,
            topic_id=topic_id,
            assets_dir=Path("assets"),
            progress_callback=lambda processed_count, total_count: loop.call_soon_threadsafe(
                progress_queue.put_nowait,
                (processed_count, total_count),
            ),
        )
    finally:
        await progress_queue.put(None)
        await progress_task
    _reload_training_service(context)
    _preview_message_ids(context).pop(user.id, None)
    enriched_pack = enrichment_result.content_pack
    topic = enriched_pack.get("topic", {})
    topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else topic_id
    generated_image_count = sum(
        1 for item in enriched_pack.get("vocabulary_items", []) if item.get("image_ref")
    )
    generation_notice = ""
    generation_metadata = getattr(enrichment_result, "generation_metadata", None)
    if generation_metadata is not None and generation_metadata.status_messages:
        generation_notice = "\n" + "\n".join(generation_metadata.status_messages)
    await query.edit_message_text(
        _tg(
            "draft_approved_images_generated",
            context=context,
            user=user,
            destination=_publish_destination_text(context, output_path=approved.output_path, topic_id=topic_id),
            generated_count=generated_image_count,
        )
        + generation_notice,
        reply_markup=(
            _published_images_menu_keyboard(
                topic_id=topic_id,
                language=_telegram_ui_language(context, user),
            )
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
    try:
        content_pack = _content_store(context).get_content_pack(topic_id)
    except ValueError:
        await query.edit_message_text(_tg("published_content_not_found", context=context, user=user))
        return
    raw_items = content_pack.get("vocabulary_items", [])
    if not isinstance(raw_items, list) or not raw_items:
        await query.edit_message_text(_tg("no_vocabulary_items_found", context=context, user=user))
        return
    await query.edit_message_text(
        _tg("choose_word_edit_image", context=context, user=user),
        reply_markup=_published_image_items_keyboard(
            topic_id=topic_id,
            raw_items=raw_items,
            language=_telegram_ui_language(context, user),
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
    try:
        content_pack = _content_store(context).get_content_pack(topic_id)
    except ValueError:
        await query.edit_message_text(_tg("published_content_not_found", context=context, user=user))
        return
    raw_items = content_pack.get("vocabulary_items", [])
    if not isinstance(raw_items, list):
        await query.edit_message_text(_tg("no_vocabulary_items_found", context=context, user=user))
        return
    try:
        selected_item = raw_items[int(item_index)]
    except (ValueError, IndexError):
        await query.edit_message_text(_tg("selected_word_unavailable", context=context, user=user))
        return
    if not isinstance(selected_item, dict):
        await query.edit_message_text(_tg("selected_word_unavailable", context=context, user=user))
        return
    item_id = str(selected_item.get("id", "")).strip()
    if not item_id:
        await query.edit_message_text(_tg("selected_word_unavailable", context=context, user=user))
        return
    review_flow = await asyncio.to_thread(
        _start_published_word_image_review(context).execute,
        user_id=user.id,
        topic_id=topic_id,
        item_id=item_id,
    )
    await _send_current_published_image_preview(query.message, context, review_flow)
    await _send_image_review_step(query.message, context, review_flow)
    await _delete_message_if_possible(context, message=query.message)


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
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
        return
    if not _local_image_generation_available(context):
        await query.edit_message_text(
            _tg("image_generation_unavailable", context=context, user=user)
        )
        return
    await edit_telegram_text_view(
        query,
        _status_view(text=_tg("start_image_generation", context=context, user=user)),
    )
    await _prepare_and_send_image_review_step(query.message, context, user.id, flow)


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
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
        return
    current_position = flow.current_index + 1
    total_items = len(flow.items)
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
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
            _search_image_review_candidates(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            query=flow.current_item.search_query,
        )
    except ValueError as error:
        await query.edit_message_text(str(error))
        return
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
                "pixabay_candidates_ready",
                context=context,
                user=user,
                current=current_position,
                total=total_items,
            )
        ),
    )
    await _send_image_review_step(query.message, context, updated_flow)


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
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
        return
    current_position = flow.current_index + 1
    total_items = len(flow.items)
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
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
            _load_next_image_review_candidates(context).execute,
            user_id=user.id,
            flow_id=flow_id,
        )
    except ValueError as error:
        await query.edit_message_text(str(error))
        return
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
                "pixabay_candidates_ready",
                context=context,
                user=user,
                current=current_position,
                total=total_items,
            )
        ),
    )
    await _send_image_review_step(query.message, context, updated_flow)


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
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
        return
    current_position = flow.current_index + 1
    total_items = len(flow.items)
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
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
            _load_previous_image_review_candidates(context).execute,
            user_id=user.id,
            flow_id=flow_id,
        )
    except ValueError as error:
        await query.edit_message_text(str(error))
        return
    await edit_telegram_text_view(
        query,
        _status_view(
            text=_tg(
                "pixabay_candidates_ready",
                context=context,
                user=user,
                current=current_position,
                total=total_items,
            )
        ),
    )
    await _send_image_review_step(query.message, context, updated_flow)


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
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
        return
    updated_flow = await asyncio.to_thread(
        _select_image_review_candidate(context).execute,
        user_id=user.id,
        flow_id=flow_id,
        item_id=flow.current_item.item_id,
        candidate_index=int(candidate_index),
    )
    if updated_flow.completed:
        if _image_review_origin(updated_flow) == "published_word_edit":
            registry = _telegram_flow_messages(context)
            tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
            await _delete_tracked_messages(
                context,
                tracked_messages=_tracked_messages_except_source_message(
                    tracked_messages=tracked_messages,
                    message=query.message,
                ),
            )
            _cancel_image_review(context).execute(user_id=user.id)
            topic = updated_flow.content_pack.get("topic", {})
            topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
            raw_items = updated_flow.content_pack.get("vocabulary_items", [])
            await query.edit_message_text(
                _tg("no_changes_choose_another_word", context=context, user=user),
                reply_markup=_published_image_items_keyboard(
                    topic_id=topic_id,
                    raw_items=raw_items if isinstance(raw_items, list) else [],
                    language=_telegram_ui_language(context, user),
                ),
            )
            if registry is not None:
                registry.clear(flow_id=flow_id)
            return
        output_path = _resolve_image_review_publish_output_path(updated_flow)
        topic = updated_flow.content_pack.get("topic", {})
        topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
        registry = _telegram_flow_messages(context)
        tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
        await _delete_tracked_messages(
            context,
            tracked_messages=_tracked_messages_except_source_message(
                tracked_messages=tracked_messages,
                message=query.message,
            ),
        )
        await asyncio.to_thread(
            _publish_image_review(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            output_path=output_path,
        )
        _reload_training_service(context)
        _clear_active_word_flow(user.id, context)
        await query.edit_message_text(
            _tg(
                "image_review_completed_published",
                context=context,
                user=user,
                destination=_publish_destination_text(context, output_path=output_path, topic_id=topic_id),
            )
        )
        if registry is not None:
            registry.clear(flow_id=flow_id)
        return
    await query.edit_message_text(_tg("image_selected", context=context, user=user))
    await _send_image_review_step(query.message, context, updated_flow)


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
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
        return
    updated_flow = await asyncio.to_thread(
        _skip_image_review_item(context).execute,
        user_id=user.id,
        flow_id=flow_id,
        item_id=flow.current_item.item_id,
    )
    if updated_flow.completed:
        if _image_review_origin(updated_flow) == "published_word_edit":
            registry = _telegram_flow_messages(context)
            tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
            await _delete_tracked_messages(
                context,
                tracked_messages=_tracked_messages_except_source_message(
                    tracked_messages=tracked_messages,
                    message=query.message,
                ),
            )
            _cancel_image_review(context).execute(user_id=user.id)
            topic = updated_flow.content_pack.get("topic", {})
            topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
            raw_items = updated_flow.content_pack.get("vocabulary_items", [])
            await query.edit_message_text(
                _tg("no_changes_choose_another_word", context=context, user=user),
                reply_markup=_published_image_items_keyboard(
                    topic_id=topic_id,
                    raw_items=raw_items if isinstance(raw_items, list) else [],
                    language=_telegram_ui_language(context, user),
                ),
            )
            if registry is not None:
                registry.clear(flow_id=flow_id)
            return
        output_path = _resolve_image_review_publish_output_path(updated_flow)
        topic = updated_flow.content_pack.get("topic", {})
        topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
        registry = _telegram_flow_messages(context)
        tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
        await _delete_tracked_messages(
            context,
            tracked_messages=_tracked_messages_except_source_message(
                tracked_messages=tracked_messages,
                message=query.message,
            ),
        )
        await asyncio.to_thread(
            _publish_image_review(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            output_path=output_path,
        )
        _reload_training_service(context)
        _clear_active_word_flow(user.id, context)
        await query.edit_message_text(
            _tg(
                "image_review_completed_published",
                context=context,
                user=user,
                destination=_publish_destination_text(context, output_path=output_path, topic_id=topic_id),
            )
        )
        if registry is not None:
            registry.clear(flow_id=flow_id)
        return
    await query.edit_message_text(_tg("image_skipped", context=context, user=user))
    await _send_image_review_step(query.message, context, updated_flow)


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
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
        return
    context.user_data["words_flow_mode"] = _IMAGE_REVIEW_AWAITING_PROMPT_TEXT
    context.user_data["image_review_flow_id"] = flow_id
    context.user_data["image_review_item_id"] = flow.current_item.item_id
    instruction_view, current_prompt_view = build_image_review_prompt_edit_view(
        instruction_text=_tg("send_new_full_prompt", context=context, user=user),
        current_prompt_text=_tg(
            "current_prompt",
            context=context,
            user=user,
            prompt=flow.current_item.prompt,
        ),
        instruction_markup=ForceReply(selective=True),
    )
    await send_telegram_view(query.message, instruction_view)
    await send_telegram_view(query.message, current_prompt_view)


async def image_review_edit_search_query_handler(
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
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
        return
    context.user_data["words_flow_mode"] = _IMAGE_REVIEW_AWAITING_SEARCH_QUERY_TEXT
    context.user_data["image_review_flow_id"] = flow_id
    context.user_data["image_review_item_id"] = flow.current_item.item_id
    current_query = flow.current_item.search_query or flow.current_item.english_word
    instruction_view, current_query_view = build_image_review_search_query_edit_view(
        instruction_text=_tg("send_new_search_query", context=context, user=user),
        current_query_text=_tg(
            "current_query",
            context=context,
            user=user,
            query=current_query,
        ),
        instruction_markup=ForceReply(selective=True),
    )
    await send_telegram_view(query.message, instruction_view)
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
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if flow is None or flow.flow_id != flow_id or flow.current_item is None:
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
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
    flow = _get_active_image_review(context).execute(user_id=user.id)
    if (
        flow is None
        or flow.flow_id != flow_id
        or flow.current_item is None
    ):
        await query.edit_message_text(_tg("image_review_flow_inactive", context=context, user=user))
        return
    context.user_data["words_flow_mode"] = _IMAGE_REVIEW_AWAITING_PHOTO
    context.user_data["image_review_flow_id"] = flow_id
    context.user_data["image_review_item_id"] = flow.current_item.item_id
    await send_telegram_view(
        query.message,
        build_image_review_attach_photo_view(
            instruction_text=_tg("attach_one_photo", context=context, user=user),
            instruction_markup=ForceReply(selective=True),
        ),
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
        await message.reply_text(_tg("image_review_task_inactive", context=context, user=user))
        return
    context.user_data.pop("words_flow_mode", None)
    context.user_data.pop("image_review_flow_id", None)
    context.user_data.pop("image_review_item_id", None)
    status_message = await message.reply_text(_tg("saving_uploaded_photo", context=context, user=user))
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
    await status_message.edit_text(
        _status_view(text=_tg("uploaded_photo_attached", context=context, user=user)).text
    )
    if updated_flow.completed:
        output_path = _resolve_image_review_publish_output_path(updated_flow)
        topic = updated_flow.content_pack.get("topic", {})
        topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
        registry = _telegram_flow_messages(context)
        tracked_messages = registry.list(flow_id=flow_id) if registry is not None else []
        await _delete_tracked_messages(context, tracked_messages=tracked_messages)
        await asyncio.to_thread(
            _publish_image_review(context).execute,
            user_id=user.id,
            flow_id=flow_id,
            output_path=output_path,
        )
        _reload_training_service(context)
        _clear_active_word_flow(user.id, context)
        await message.reply_text(
            _tg(
                "image_review_completed_published",
                context=context,
                user=user,
                destination=_publish_destination_text(context, output_path=output_path, topic_id=topic_id),
            )
        )
        return
    await _send_image_review_step(message, context, updated_flow)


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
        await query.edit_message_text(_tg("no_active_session_send_start", context=context, user=user))
        return
    context.user_data["awaiting_text_answer"] = question.mode in {
        TrainingMode.MEDIUM,
        TrainingMode.HARD,
    }
    await query.edit_message_text(_tg("continue_current_session", context=context, user=user))
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
    await query.edit_message_text(_tg("previous_session_discarded", context=context, user=user))
    await send_telegram_view(
        query.message,
        _topic_selection_view(
            text=_tg("choose_topic_start_training", context=context, user=user),
            topics=_service(context).list_topics(),
            context=context,
            user=user,
        ),
    )


async def topic_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    topic_id = query.data.removeprefix("topic:")
    lesson_selection = _service(context).list_lessons_by_topic(topic_id=topic_id)
    if lesson_selection.has_lessons:
        lesson_view = _lesson_selection_view(
            text=_tg("choose_lesson", context=context, user=update.effective_user),
            topic_id=topic_id,
            lessons=lesson_selection.lessons,
            context=context,
            user=update.effective_user,
        )
        await query.edit_message_text(
            lesson_view.text,
            reply_markup=lesson_view.reply_markup,
        )
        return
    mode_view = _mode_selection_view(
        text=_tg("choose_mode", context=context, user=update.effective_user),
        topic_id=topic_id,
        lesson_id=None,
        context=context,
        user=update.effective_user,
    )
    await query.edit_message_text(
        mode_view.text,
        reply_markup=mode_view.reply_markup,
    )


async def lesson_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _, topic_id, lesson_id = query.data.split(":")
    selected_lesson_id = None if lesson_id == "all" else lesson_id
    mode_view = _mode_selection_view(
        text=_tg("choose_mode", context=context, user=update.effective_user),
        topic_id=topic_id,
        lesson_id=selected_lesson_id,
        context=context,
        user=update.effective_user,
    )
    await query.edit_message_text(
        mode_view.text,
        reply_markup=mode_view.reply_markup,
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
    await query.edit_message_text(_tg("session_started", context=context, user=user))
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
    user = update.effective_user
    if message is None or message.text is None or user is None:
        return
    if _service(context).get_active_session(user_id=user.id) is None:
        context.user_data["awaiting_text_answer"] = False
        await message.reply_text(_tg("no_active_session_begin", context=context, user=user))
        return
    await _process_answer(update, context, message.text)


async def group_text_observer_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not _is_group_chat(update):
        return
    if context.user_data.get("awaiting_text_answer"):
        return
    if context.user_data.get("words_flow_mode") is not None:
        return
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or message.text is None or user is None or chat is None:
        return
    logger.info(
        "Received group message chat_id=%s chat_type=%s user_id=%s text=%r",
        chat.id,
        chat.type,
        user.id,
        message.text,
    )


async def raw_update_logger_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    logger.info("Received Telegram update %s", _describe_update(update))


async def chat_member_logger_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,  # noqa: ARG001
) -> None:
    chat_member_update = update.my_chat_member or update.chat_member
    if chat_member_update is None:
        return
    logger.info(
        "Received chat member update chat_id=%s chat_type=%s user_id=%s old_status=%s new_status=%s",
        chat_member_update.chat.id,
        chat_member_update.chat.type,
        chat_member_update.from_user.id,
        chat_member_update.old_chat_member.status,
        chat_member_update.new_chat_member.status,
    )


def _describe_update(update: Update) -> str:
    message = update.effective_message
    if message is not None and message.text is not None:
        chat = update.effective_chat
        user = update.effective_user
        chat_id = chat.id if chat is not None else "?"
        chat_type = chat.type if chat is not None else "?"
        user_id = user.id if user is not None else "?"
        return (
            f"message chat_id={chat_id} chat_type={chat_type} "
            f"user_id={user_id} text={message.text!r}"
        )
    if update.callback_query is not None:
        query = update.callback_query
        user_id = query.from_user.id if query.from_user is not None else "?"
        return f"callback_query user_id={user_id} data={query.data!r}"
    if update.my_chat_member is not None:
        member = update.my_chat_member
        return (
            f"my_chat_member chat_id={member.chat.id} chat_type={member.chat.type} "
            f"user_id={member.from_user.id} old_status={member.old_chat_member.status} "
            f"new_status={member.new_chat_member.status}"
        )
    if update.chat_member is not None:
        member = update.chat_member
        return (
            f"chat_member chat_id={member.chat.id} chat_type={member.chat.type} "
            f"user_id={member.from_user.id} old_status={member.old_chat_member.status} "
            f"new_status={member.new_chat_member.status}"
        )
    return "unknown"


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
        await message.reply_text(_tg("no_active_session_begin", context=context, user=user))
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
    view = build_answer_feedback_view(
        outcome,
        translate=_tg,
        user=getattr(message, "from_user", None),
    )
    await send_telegram_view(message, view)


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
    view = build_training_question_view(
        question,
        image_path=image_path,
        reply_markup=reply_markup,
    )
    await send_telegram_view(message, view)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram update error. Update=%r", update, exc_info=context.error)


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Start training"),
            BotCommand("help", "Show commands"),
            BotCommand("version", "Show bot version"),
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
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
        if stop_event.is_set():
            break
        elapsed_seconds += int(interval_seconds)
        try:
            await status_target.edit_text(f"{stage}... still working ({elapsed_seconds}s)")
        except Exception:  # noqa: BLE001
            logger.debug("Failed to update status heartbeat stage=%s", stage, exc_info=True)


def _message_chat_id(message) -> int | None:
    chat_id = getattr(message, "chat_id", None)
    if isinstance(chat_id, int):
        return chat_id
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if isinstance(chat_id, int):
        return chat_id
    return None


async def _delete_tracked_messages(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    tracked_messages,
) -> None:
    registry = _telegram_flow_messages(context)
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


async def _delete_message_if_possible(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
) -> None:
    bot = getattr(context, "bot", None)
    chat_id = _message_chat_id(message)
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


def _tracked_messages_except_source_message(*, tracked_messages, message) -> list:
    source_chat_id = _message_chat_id(message)
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


def _track_flow_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    tag: str,
    message,
    fallback_chat_id: int | None = None,
) -> None:
    registry = _telegram_flow_messages(context)
    if registry is None:
        return
    message_id = getattr(message, "message_id", None)
    if not isinstance(message_id, int):
        return
    chat_id = _message_chat_id(message)
    if chat_id is None:
        chat_id = fallback_chat_id
    if not isinstance(chat_id, int):
        return
    registry.track(flow_id=flow_id, chat_id=chat_id, message_id=message_id, tag=tag)


def _published_word_edit_flow_id(*, user_id: int) -> str:
    return f"published-word-edit:{user_id}"


async def _prepare_and_send_image_review_step(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    flow,
) -> None:
    current_item = flow.current_item
    if current_item is None:
        await message.reply_text(_tg("image_review_completed", user=getattr(message, "from_user", None)))
        return
    total_items = len(flow.items)
    current_position = flow.current_index + 1
    status_message = await message.reply_text(
        _tg(
            "local_candidates_generating",
            user=getattr(message, "from_user", None),
            current=current_position,
            total=total_items,
        )
    )
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
            _run_status_heartbeat(
                status_message,
                stage=f"Generating local image candidates {current_position}/{total_items}",
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
        _status_view(
            text=_tg(
                "local_candidates_ready",
                user=getattr(message, "from_user", None),
                current=current_position,
                total=total_items,
            )
        ).text
    )
    await _send_image_review_step(message, context, prepared_flow)


async def _send_current_published_image_preview(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    flow,
) -> None:
    current_item = flow.current_item
    if current_item is None:
        return
    registry = _telegram_flow_messages(context)
    if registry is not None:
        await _delete_tracked_messages(
            context,
            tracked_messages=registry.list(
                flow_id=flow.flow_id,
                tag=_IMAGE_REVIEW_CONTEXT_TAG,
            ),
        )
    fallback_chat_id = _message_chat_id(message)
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
    preview_view = build_current_image_preview_view(
        image_path=image_path,
        current_image_intro=_tg("current_image_intro", user=getattr(message, "from_user", None)),
        no_current_image_intro=_tg("no_current_image_intro", user=getattr(message, "from_user", None)),
    )
    preview_message = await send_telegram_view(message, preview_view)
    _track_flow_message(
        context,
        flow_id=flow.flow_id,
        tag=_IMAGE_REVIEW_CONTEXT_TAG,
        message=preview_message,
        fallback_chat_id=fallback_chat_id,
    )


async def _send_image_review_step(message, context: ContextTypes.DEFAULT_TYPE, flow) -> None:
    current_item = flow.current_item
    if current_item is None:
        await message.reply_text("Image review completed.")
        return
    registry = _telegram_flow_messages(context)
    tracked_before = (
        registry.list(flow_id=flow.flow_id, tag=_IMAGE_REVIEW_STEP_TAG)
        if registry is not None
        else []
    )
    fallback_chat_id = _message_chat_id(message)
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
        reply_markup=_image_review_markup(
            flow_id=flow.flow_id,
            current_item=current_item,
            context=context,
            user=getattr(message, "from_user", None),
        ),
        translate=_tg,
        user=getattr(message, "from_user", None),
    )
    summary_message = await send_telegram_view(message, summary_view)
    _track_flow_message(
        context,
        flow_id=flow.flow_id,
        tag=_IMAGE_REVIEW_STEP_TAG,
        message=summary_message,
        fallback_chat_id=fallback_chat_id,
    )
    if current_item.candidates:
        strip_path = _build_image_review_candidate_strip(
            flow=flow,
            item_id=current_item.item_id,
            candidate_paths=[candidate.output_path for candidate in current_item.candidates],
        )
        with strip_path.open("rb") as photo_file:
            sent_photo = await message.reply_photo(photo=photo_file)
        _track_flow_message(
            context,
            flow_id=flow.flow_id,
            tag=_IMAGE_REVIEW_STEP_TAG,
            message=sent_photo,
            fallback_chat_id=fallback_chat_id,
        )
    await _delete_tracked_messages(context, tracked_messages=tracked_before)


def _candidate_label(index: int) -> str:
    return chr(ord("A") + index)


def _model_label(model_name: str) -> str:
    if model_name == "sd15":
        return "SD 1.5"
    if model_name == "pixabay":
        return "Pixabay"
    return model_name.replace("-", " ").title()


def _candidate_caption(index: int, candidate) -> str:
    parts = [f"{_candidate_label(index)}. {_model_label(candidate.model_name)}"]
    source_id = getattr(candidate, "source_id", None)
    if source_id:
        parts.append(f"ID {source_id}")
    width = getattr(candidate, "width", None)
    height = getattr(candidate, "height", None)
    if width and height:
        parts.append(f"{width}x{height}")
    return " | ".join(parts)


def _build_image_review_candidate_strip(*, flow, item_id: str, candidate_paths: list[Path]) -> Path:
    review_dir = candidate_paths[0].parent
    output_path = review_dir / f"{flow.flow_id}-{item_id}--review-strip-256.jpg"
    return ensure_numbered_candidate_strip(
        source_paths=candidate_paths,
        output_path=output_path,
        tile_size=256,
    )


def _draft_review_keyboard(
    flow_id: str,
    is_valid: bool,
    *,
    show_auto_image_button: bool = True,
    show_regenerate_button: bool = True,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    action_row: list[InlineKeyboardButton] = []
    if show_auto_image_button:
        action_row.append(
            InlineKeyboardButton(
                _tg("approve_auto_images", language=language),
                callback_data=f"words:approve_auto_images:{flow_id}",
            )
        )
    action_row.append(
        InlineKeyboardButton(
            _tg("manual_image_review", language=language),
            callback_data=f"words:start_image_review:{flow_id}",
        )
    )
    rows = []
    if action_row:
        rows.append(action_row)
    rows.append(
        [
            InlineKeyboardButton(
                _tg("publish_without_images", language=language),
                callback_data=f"words:approve_draft:{flow_id}",
            ),
        ]
    )
    edit_row: list[InlineKeyboardButton] = []
    if show_regenerate_button:
        edit_row.append(
            InlineKeyboardButton(
                _tg("re_recognize_draft", language=language),
                callback_data=f"words:regenerate_draft:{flow_id}",
            )
        )
    edit_row.append(
        InlineKeyboardButton(
            _tg("edit_text", language=language),
            callback_data=f"words:edit_text:{flow_id}",
        )
    )
    rows.append(edit_row)
    rows.append(
        [
            InlineKeyboardButton(
                _tg("show_json", language=language),
                callback_data=f"words:show_json:{flow_id}",
            ),
            InlineKeyboardButton(
                _tg("cancel", language=language),
                callback_data=f"words:cancel:{flow_id}",
            ),
        ]
    )
    if not is_valid:
        if action_row:
            if show_auto_image_button:
                rows[0][0] = InlineKeyboardButton(
                    _tg("approve_disabled", language=language),
                    callback_data="words:menu",
                )
                if len(rows[0]) > 1:
                    rows[0][1] = InlineKeyboardButton(
                        _tg("review_disabled", language=language),
                        callback_data="words:menu",
                    )
            else:
                rows[0][0] = InlineKeyboardButton(
                    _tg("review_disabled", language=language),
                    callback_data="words:menu",
                )
        publish_row_index = 1 if action_row else 0
        rows[publish_row_index][0] = InlineKeyboardButton(
            _tg("publish_disabled", language=language),
            callback_data="words:menu",
        )
    return InlineKeyboardMarkup(rows)


def _image_review_keyboard(
    *,
    flow_id: str,
    current_item,
    show_generate_image_button: bool = True,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    candidate_count = len(current_item.candidates)
    pick_buttons = [
        InlineKeyboardButton(
            _tg("use_n", language=language, index=index + 1),
            callback_data=f"words:image_pick:{flow_id}:{index}",
        )
        for index in range(candidate_count)
    ]
    rows = [pick_buttons[index : index + 3] for index in range(0, len(pick_buttons), 3)]
    action_row = [
        InlineKeyboardButton(
            _tg("search_images", language=language),
            callback_data=f"words:image_search:{flow_id}",
        ),
    ]
    if show_generate_image_button:
        action_row.append(
            InlineKeyboardButton(
                _tg("generate_image", language=language),
                callback_data=f"words:image_generate:{flow_id}",
            )
        )
    rows.append(action_row)
    if current_item.search_query:
        pagination_row: list[InlineKeyboardButton] = []
        if current_item.search_page > 1:
            pagination_row.append(
                InlineKeyboardButton(
                    _tg("previous_6", language=language),
                    callback_data=f"words:image_previous:{flow_id}",
                )
            )
        pagination_row.append(
            InlineKeyboardButton(
                _tg("next_6", language=language),
                callback_data=f"words:image_next:{flow_id}",
            )
        )
        rows.append(pagination_row)
    rows.append(
        [
            InlineKeyboardButton(
                _tg("edit_search_query", language=language),
                callback_data=f"words:image_edit_search_query:{flow_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                _tg("edit_prompt", language=language),
                callback_data=f"words:image_edit_prompt:{flow_id}",
            ),
            InlineKeyboardButton(
                _tg("attach_photo", language=language),
                callback_data=f"words:image_attach_photo:{flow_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                _tg("show_json", language=language),
                callback_data=f"words:image_show_json:{flow_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                _tg("skip_for_now", language=language),
                callback_data=f"words:image_skip:{flow_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def _words_menu_keyboard(
    *,
    is_editor: bool,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(_tg("training_topics", language=language), callback_data="words:topics")]]
    if is_editor:
        rows.append([InlineKeyboardButton(_tg("add_words", language=language), callback_data="words:add_words")])
        rows.append([InlineKeyboardButton(_tg("edit_words", language=language), callback_data="words:edit_words")])
        rows.append([InlineKeyboardButton(_tg("edit_word_image", language=language), callback_data="words:edit_images")])
    return InlineKeyboardMarkup(rows)


def _published_images_menu_keyboard(
    *,
    topic_id: str,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _tg("edit_word_image", language=language),
                    callback_data=f"words:edit_images_menu:{topic_id}",
                )
            ]
        ]
    )


def _published_image_topics_keyboard(
    topics,
    *,
    topic_item_counts: dict[str, int] | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                _topic_button_label(
                    title=topic.title,
                    item_count=(topic_item_counts or {}).get(topic.id),
                ),
                callback_data=f"words:edit_images_menu:{topic.id}",
            )
        ]
        for topic in topics
    ]
    if not rows:
        rows = [[InlineKeyboardButton(_tg("no_topics", language=language), callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def _published_image_items_keyboard(
    *,
    topic_id: str,
    raw_items: list[object],
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
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
        rows = [[InlineKeyboardButton(_tg("no_items", language=language), callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def _editable_topics_keyboard(
    topics,
    *,
    topic_item_counts: dict[str, int] | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                _topic_button_label(
                    title=topic.title,
                    item_count=(topic_item_counts or {}).get(topic.id),
                ),
                callback_data=f"words:edit_topic:{topic.id}",
            )
        ]
        for topic in topics
    ]
    if not rows:
        rows = [[InlineKeyboardButton(_tg("no_topics", language=language), callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def _editable_words_keyboard(
    *,
    topic_id: str,
    words,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
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
        rows = [[InlineKeyboardButton(_tg("no_words", language=language), callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def _published_word_edit_keyboard(
    *,
    topic_id: str,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _tg("cancel", language=language),
                    callback_data=f"words:edit_item_cancel:{topic_id}",
                )
            ]
        ]
    )


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


def _topic_keyboard(
    topics: list[Topic],
    *,
    topic_item_counts: dict[str, int] | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _topic_button_label(
                        title=topic.title,
                        item_count=(topic_item_counts or {}).get(topic.id),
                    ),
                    callback_data=f"topic:{topic.id}",
                )
            ]
            for topic in topics
        ]
    )


def _topic_item_counts(
    context: ContextTypes.DEFAULT_TYPE,
    topic_ids: list[str],
) -> dict[str, int]:
    store = context.application.bot_data.get("content_store")
    if store is None:
        return {}
    counts: dict[str, int] = {}
    for topic_id in topic_ids:
        try:
            counts[topic_id] = len(store.list_vocabulary_by_topic(topic_id))
        except Exception:  # noqa: BLE001
            logger.debug("Failed to count topic items for topic_id=%s", topic_id, exc_info=True)
    return counts


def _topic_button_label(*, title: str, item_count: int | None) -> str:
    if item_count is None:
        return title
    return f"{title} ({item_count})"


def _active_session_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_tg("continue", language=language), callback_data="session:continue"),
                InlineKeyboardButton(_tg("start_over", language=language), callback_data="session:restart"),
            ]
        ]
    )


def _lesson_keyboard(
    topic_id: str,
    lessons,
    *,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(_tg("all_topic_words", language=language), callback_data=f"lesson:{topic_id}:all")]]
    rows.extend(
        [
            [InlineKeyboardButton(lesson.title, callback_data=f"lesson:{topic_id}:{lesson.id}")]
            for lesson in lessons
        ]
    )
    return InlineKeyboardMarkup(rows)


def _mode_keyboard(
    topic_id: str,
    lesson_id: str | None,
    *,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    lesson_part = lesson_id or "all"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _tg("easy", language=language),
                    callback_data=f"mode:{topic_id}:{lesson_part}:{TrainingMode.EASY.value}",
                ),
                InlineKeyboardButton(
                    _tg("medium", language=language),
                    callback_data=f"mode:{topic_id}:{lesson_part}:{TrainingMode.MEDIUM.value}",
                ),
                InlineKeyboardButton(
                    _tg("hard", language=language),
                    callback_data=f"mode:{topic_id}:{lesson_part}:{TrainingMode.HARD.value}",
                ),
            ]
        ]
    )
