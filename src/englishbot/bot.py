from __future__ import annotations

import asyncio
import html
import hashlib
import hmac
import json
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
from englishbot.application.homework_progress_use_cases import (
    AssignmentLaunchView,
    AssignmentSessionKind,
    AssignGoalToUsersUseCase,
    GetAdminGoalDetailUseCase,
    GetAdminUserGoalsUseCase,
    GetAdminUsersProgressOverviewUseCase,
    GetLearnerAssignmentLaunchSummaryUseCase,
    GetGoalWordCandidatesUseCase,
    GetUserProgressSummaryUseCase,
    GoalProgressView,
    GoalWordSource,
    HomeworkProgressUseCase,
    LearnerProgressSummary,
    ListUserGoalsUseCase,
    StartAssignmentRoundUseCase,
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
    QuestionFactory,
    TrainingFacade,
)
from englishbot.bootstrap import build_lesson_import_pipeline, build_training_service
from englishbot.bot_assignments_admin_ui import admin_goal_manual_keyboard as ui_admin_goal_manual_keyboard
from englishbot.bot_assignments_admin_ui import admin_goal_recipients_keyboard as ui_admin_goal_recipients_keyboard
from englishbot.bot_assignments_admin_ui import assignment_goal_detail_keyboard as ui_assignment_goal_detail_keyboard
from englishbot.bot_assignments_admin_ui import assignment_user_goals_keyboard as ui_assignment_user_goals_keyboard
from englishbot.bot_assignments_admin_ui import assignment_user_label as ui_assignment_user_label
from englishbot.bot_assignments_admin_ui import assignment_users_keyboard as ui_assignment_users_keyboard
from englishbot.bot_assignments_admin_ui import goal_source_topic_keyboard as ui_goal_source_topic_keyboard
from englishbot.bot_assignments_admin_ui import page_range_label as ui_page_range_label
from englishbot.bot_assignments_admin_ui import render_assignment_goal_detail_text as ui_render_assignment_goal_detail_text
from englishbot.bot_assignments_admin_ui import render_assignment_user_detail_text as ui_render_assignment_user_detail_text
from englishbot.bot_assignments_ui import admin_goal_custom_target_keyboard as ui_admin_goal_custom_target_keyboard
from englishbot.bot_assignments_ui import admin_goal_period_keyboard as ui_admin_goal_period_keyboard
from englishbot.bot_assignments_ui import admin_goal_source_keyboard as ui_admin_goal_source_keyboard
from englishbot.bot_assignments_ui import admin_goal_target_keyboard as ui_admin_goal_target_keyboard
from englishbot.bot_assignments_ui import assign_menu_keyboard as ui_assign_menu_keyboard
from englishbot.bot_assignments_ui import assignment_kind_label as ui_assignment_kind_label
from englishbot.bot_assignments_ui import assignment_round_complete_keyboard as ui_assignment_round_complete_keyboard
from englishbot.bot_assignments_ui import goal_custom_target_keyboard as ui_goal_custom_target_keyboard
from englishbot.bot_assignments_ui import goal_list_keyboard as ui_goal_list_keyboard
from englishbot.bot_assignments_ui import goal_period_label as ui_goal_period_label
from englishbot.bot_assignments_ui import goal_rule_text as ui_goal_rule_text
from englishbot.bot_assignments_ui import goal_setup_keyboard as ui_goal_setup_keyboard
from englishbot.bot_assignments_ui import goal_source_keyboard as ui_goal_source_keyboard
from englishbot.bot_assignments_ui import goal_target_keyboard as ui_goal_target_keyboard
from englishbot.bot_assignments_ui import goal_type_label as ui_goal_type_label
from englishbot.bot_assignments_ui import render_goal_progress_line as ui_render_goal_progress_line
from englishbot.bot_assignments_ui import render_progress_text as ui_render_progress_text
from englishbot.bot_assignments_ui import render_start_menu_text as ui_render_start_menu_text
from englishbot.bot_assignments_ui import start_assignment_button_label as ui_start_assignment_button_label
from englishbot.bot_assignments_ui import start_menu_keyboard as ui_start_menu_keyboard
from englishbot.bot_editor_ui import chat_menu_keyboard as ui_chat_menu_keyboard
from englishbot.bot_editor_ui import draft_review_keyboard as ui_draft_review_keyboard
from englishbot.bot_editor_ui import draft_review_view as ui_draft_review_view
from englishbot.bot_editor_ui import editable_topics_keyboard as ui_editable_topics_keyboard
from englishbot.bot_editor_ui import editable_topics_view as ui_editable_topics_view
from englishbot.bot_editor_ui import editable_word_button_label as ui_editable_word_button_label
from englishbot.bot_editor_ui import editable_words_keyboard as ui_editable_words_keyboard
from englishbot.bot_editor_ui import editable_words_view as ui_editable_words_view
from englishbot.bot_editor_ui import game_mode_keyboard as ui_game_mode_keyboard
from englishbot.bot_editor_ui import help_view as ui_help_view
from englishbot.bot_editor_ui import image_review_keyboard as ui_image_review_keyboard
from englishbot.bot_editor_ui import lesson_keyboard as ui_lesson_keyboard
from englishbot.bot_editor_ui import lesson_selection_view as ui_lesson_selection_view
from englishbot.bot_editor_ui import mode_keyboard as ui_mode_keyboard
from englishbot.bot_editor_ui import mode_selection_view as ui_mode_selection_view
from englishbot.bot_editor_ui import published_image_items_keyboard as ui_published_image_items_keyboard
from englishbot.bot_editor_ui import published_image_topics_keyboard as ui_published_image_topics_keyboard
from englishbot.bot_editor_ui import published_images_menu_keyboard as ui_published_images_menu_keyboard
from englishbot.bot_editor_ui import published_word_edit_keyboard as ui_published_word_edit_keyboard
from englishbot.bot_editor_ui import quick_actions_view as ui_quick_actions_view
from englishbot.bot_editor_ui import topic_button_label as ui_topic_button_label
from englishbot.bot_editor_ui import topic_keyboard as ui_topic_keyboard
from englishbot.bot_editor_ui import topic_selection_view as ui_topic_selection_view
from englishbot.bot_editor_ui import words_menu_keyboard as ui_words_menu_keyboard
from englishbot.bot_editor_ui import words_menu_view as ui_words_menu_view
from englishbot.config import RuntimeConfigService, Settings
from englishbot.domain.models import GoalPeriod, GoalStatus, GoalType, Topic, TrainingMode, TrainingQuestion
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
    SQLiteSessionRepository,
    SQLiteTelegramFlowMessageRepository,
    SQLiteTelegramUserLoginRepository,
    SQLitePendingTelegramNotificationRepository,
    SQLiteTelegramUserRoleRepository,
    SQLiteUserProgressRepository,
    SQLiteVocabularyRepository,
)
from englishbot.presentation.add_words_text import (
    format_draft_edit_text,
    parse_edited_vocabulary_line,
)
from englishbot.presentation.telegram_views import (
    TelegramPhotoView,
    TelegramTextView,
    build_active_session_exists_view,
    build_assignment_menu_view,
    build_answer_feedback_view,
    build_current_image_preview_view,
    build_image_review_attach_photo_view,
    build_image_review_prompt_edit_view,
    build_image_review_search_query_edit_view,
    build_image_review_step_view,
    build_published_word_edit_prompt_view,
    build_start_menu_view,
    build_status_view,
    build_training_question_view,
    edit_telegram_text_view,
    send_telegram_view,
)
from englishbot.presentation.telegram_ui_text import (
    DEFAULT_TELEGRAM_UI_LANGUAGE,
    supported_telegram_ui_languages,
    telegram_ui_text,
)
from englishbot.presentation.telegram_menu_access import (
    DEFAULT_TELEGRAM_COMMAND_SPECS,
    PERMISSION_WORD_IMAGES_EDIT,
    PERMISSION_WORDS_ADD,
    PERMISSION_WORDS_EDIT,
    TelegramCommandSpec,
    TelegramMenuAccessPolicy,
)
from englishbot.runtime_version import RuntimeVersionInfo, get_runtime_version_info

logger = logging.getLogger(__name__)

_ADD_WORDS_AWAITING_TEXT = "awaiting_raw_text"
_ADD_WORDS_AWAITING_EDIT_TEXT = "awaiting_edit_text"
_IMAGE_REVIEW_AWAITING_PROMPT_TEXT = "awaiting_image_review_prompt_text"
_IMAGE_REVIEW_AWAITING_SEARCH_QUERY_TEXT = "awaiting_image_review_search_query_text"
_IMAGE_REVIEW_AWAITING_PHOTO = "awaiting_image_review_photo"
_PUBLISHED_WORD_AWAITING_EDIT_TEXT = "awaiting_published_word_edit_text"
_GOAL_AWAITING_TARGET_TEXT = "awaiting_goal_target_text"
_ADMIN_GOAL_AWAITING_TARGET_TEXT = "awaiting_admin_goal_target_text"
_EXPECTED_USER_INPUT_STATE_KEY = "expected_user_input_state"
_IMAGE_REVIEW_STEP_TAG = "image_review_step"
_IMAGE_REVIEW_CONTEXT_TAG = "image_review_context"
_PUBLISHED_WORD_EDIT_TAG = "published_word_edit"
_TRAINING_QUESTION_TAG = "training_question"
_TRAINING_FEEDBACK_TAG = "training_feedback"
_CHAT_MENU_TAG = "chat_menu"
_NOTIFICATION_DISMISS_CALLBACK = "notification:dismiss"
_TELEGRAM_UI_LANGUAGE_KEY = "telegram_ui_language"
_GAME_STATE_KEY = "game_mode_state"
_MEDIUM_TASK_STATE_KEY = "medium_task_state"
_GAME_STAR_REWARD_CORRECT = 10
_GAME_CHEST_REWARDS: tuple[int, ...] = (30, 50, 50, 100)
_NOTIFICATION_ACTIVE_SESSION_ACTIVITY_WINDOW = timedelta(minutes=5)
_NOTIFICATION_RECENT_ANSWER_GRACE_PERIOD = timedelta(minutes=1)
_NOTIFICATION_DELAY_AFTER_RECENT_ANSWER = timedelta(minutes=2)
_DAILY_ASSIGNMENT_REMINDER_TIME = time(hour=13, minute=0, tzinfo=UTC)
_HELP_COMMAND_TEXT: dict[str, str] = {
    "start": "open your personal start menu",
    "help": "show commands",
    "version": "show the current bot version",
    "words": "open the words menu",
    "assign": "open the assignments menu",
    "add_words": "send raw lesson text for draft extraction",
    "cancel": "cancel the current add-words flow",
}


@dataclass(frozen=True, slots=True)
class _AssignmentUserView:
    user_id: int
    username: str | None
    roles: tuple[str, ...]
    active_goals_count: int
    completed_goals_count: int
    aggregate_percent: int
    last_activity_at: datetime | None
    last_seen_at: datetime | None


@dataclass(frozen=True, slots=True)
class _GoalFeedbackUpdate:
    weekly_points_delta: int
    progressed_goals: tuple[GoalProgressView, ...]
    completed_goals: tuple[GoalProgressView, ...]


@dataclass(frozen=True, slots=True)
class _AssignmentRoundProgressView:
    completed_word_count: int
    total_word_count: int
    remaining_word_count: int
    estimated_round_count: int
    variant_key: str


@dataclass(frozen=True, slots=True)
class _MediumTaskState:
    session_id: str
    item_id: str
    target_word: str
    shuffled_letters: tuple[str, ...]
    selected_letter_indexes: tuple[int, ...]
    message_id: int | None = None


@dataclass(frozen=True, slots=True)
class _PendingNotification:
    key: str
    recipient_user_id: int
    text: str


def _draft_checkpoint_text(flow) -> str:
    if flow.draft_output_path is not None:
        return f"Draft checkpoint: {flow.draft_output_path}"
    return telegram_ui_text("draft_checkpoint_saved_db")


def _normalize_telegram_ui_language(language: str | None) -> str:
    primary = _supported_telegram_ui_language_or_none(language)
    if primary is not None:
        return primary
    return DEFAULT_TELEGRAM_UI_LANGUAGE


def _supported_telegram_ui_language_or_none(language: str | None) -> str | None:
    normalized = (language or "").strip().lower()
    if not normalized:
        return None
    primary = normalized.replace("_", "-").split("-", maxsplit=1)[0]
    if primary == "ua":
        primary = "uk"
    if primary in supported_telegram_ui_languages():
        return primary
    return None


def _telegram_ui_language(context: ContextTypes.DEFAULT_TYPE | None, user=None) -> str:
    configured = DEFAULT_TELEGRAM_UI_LANGUAGE
    user_data = None
    if context is not None:
        configured = _normalize_telegram_ui_language(
            context.application.bot_data.get("telegram_ui_language")
        )
        maybe_user_data = getattr(context, "user_data", None)
        if isinstance(maybe_user_data, dict):
            user_data = maybe_user_data
            stored_language = _supported_telegram_ui_language_or_none(
                user_data.get(_TELEGRAM_UI_LANGUAGE_KEY)
            )
            if stored_language is not None:
                configured = stored_language
    if user is not None:
        user_language_code = getattr(user, "language_code", None)
        user_primary = _supported_telegram_ui_language_or_none(user_language_code)
        if user_primary is not None:
            if user_data is not None:
                user_data[_TELEGRAM_UI_LANGUAGE_KEY] = user_primary
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
    telegram_user_login_repository = SQLiteTelegramUserLoginRepository(content_store)
    pending_notification_repository = SQLitePendingTelegramNotificationRepository(content_store)
    telegram_user_role_repository = SQLiteTelegramUserRoleRepository(content_store)
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
    app.bot_data["admin_user_ids"] = set(settings.admin_user_ids)
    app.bot_data["editor_user_ids"] = set(settings.editor_user_ids)
    app.bot_data["telegram_user_role_repository"] = telegram_user_role_repository
    for user_id in settings.admin_user_ids:
        telegram_user_role_repository.grant(user_id=user_id, role="admin")
    for user_id in settings.editor_user_ids:
        telegram_user_role_repository.grant(user_id=user_id, role="editor")
    app.bot_data["telegram_ui_language"] = _normalize_telegram_ui_language(
        settings.telegram_ui_language
    )
    app.bot_data["web_app_base_url"] = settings.web_app_base_url.rstrip("/")
    app.bot_data["admin_bootstrap_secret"] = settings.admin_bootstrap_secret
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
    app.bot_data["telegram_user_login_repository"] = telegram_user_login_repository
    app.bot_data["pending_telegram_notification_repository"] = pending_notification_repository
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
    app.bot_data["homework_progress_use_case"] = HomeworkProgressUseCase(store=content_store)
    app.bot_data["list_user_goals_use_case"] = ListUserGoalsUseCase(store=content_store)
    app.bot_data["get_user_progress_summary_use_case"] = GetUserProgressSummaryUseCase(store=content_store)
    app.bot_data["learner_assignment_launch_summary_use_case"] = GetLearnerAssignmentLaunchSummaryUseCase(
        store=content_store
    )
    app.bot_data["start_assignment_round_use_case"] = StartAssignmentRoundUseCase(
        store=content_store,
        vocabulary_repository=SQLiteVocabularyRepository(content_store),
        progress_repository=SQLiteUserProgressRepository(content_store),
        session_repository=SQLiteSessionRepository(content_store),
        question_factory=QuestionFactory(random.Random(42)),
    )
    app.bot_data["assign_goal_to_users_use_case"] = AssignGoalToUsersUseCase(store=content_store)
    app.bot_data["goal_word_candidates_use_case"] = GetGoalWordCandidatesUseCase(store=content_store)
    app.bot_data["admin_user_goals_use_case"] = GetAdminUserGoalsUseCase(store=content_store)
    app.bot_data["admin_goal_detail_use_case"] = GetAdminGoalDetailUseCase(store=content_store)
    app.bot_data["admin_users_progress_overview_use_case"] = GetAdminUsersProgressOverviewUseCase(
        store=content_store
    )
    app.bot_data["recent_assignment_activity_by_user"] = {}

    app.add_handler(TypeHandler(Update, raw_update_logger_handler), group=-1)
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("version", version_handler))
    app.add_handler(CommandHandler("words", words_menu_handler))
    app.add_handler(CommandHandler("assign", assign_menu_handler))
    app.add_handler(CommandHandler("add_words", add_words_start_handler))
    app.add_handler(CommandHandler("cancel", add_words_cancel_handler))
    app.add_handler(CommandHandler("makeadmin", makeadmin_handler))
    app.add_handler(ChatMemberHandler(chat_member_logger_handler, ChatMemberHandler.ANY_CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(continue_session_handler, pattern=r"^session:continue$"))
    app.add_handler(CallbackQueryHandler(restart_session_handler, pattern=r"^session:restart$"))
    app.add_handler(CallbackQueryHandler(start_menu_callback_handler, pattern=r"^start:menu$"))
    app.add_handler(CallbackQueryHandler(start_assignment_round_callback_handler, pattern=r"^start:launch:"))
    app.add_handler(CallbackQueryHandler(start_assignment_unavailable_callback_handler, pattern=r"^start:disabled:"))
    app.add_handler(CallbackQueryHandler(game_mode_placeholder_callback_handler, pattern=r"^start:game$"))
    app.add_handler(CallbackQueryHandler(topic_selected_handler, pattern=r"^topic:"))
    app.add_handler(CallbackQueryHandler(lesson_selected_handler, pattern=r"^lesson:"))
    app.add_handler(CallbackQueryHandler(game_mode_placeholder_callback_handler, pattern=r"^gameentry:"))
    app.add_handler(CallbackQueryHandler(game_mode_placeholder_callback_handler, pattern=r"^gamemode:"))
    app.add_handler(CallbackQueryHandler(game_next_round_handler, pattern=r"^game:next_round$"))
    app.add_handler(CallbackQueryHandler(game_repeat_handler, pattern=r"^game:repeat$"))
    app.add_handler(CallbackQueryHandler(mode_selected_handler, pattern=r"^mode:"))
    app.add_handler(CallbackQueryHandler(medium_answer_callback_handler, pattern=r"^medium:"))
    app.add_handler(CallbackQueryHandler(choice_answer_handler, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(words_menu_callback_handler, pattern=r"^words:menu$"))
    app.add_handler(CallbackQueryHandler(assign_menu_callback_handler, pattern=r"^assign:menu$"))
    app.add_handler(CallbackQueryHandler(noop_callback_handler, pattern=r"^assign:noop$"))
    app.add_handler(CallbackQueryHandler(notification_dismiss_callback_handler, pattern=rf"^{_NOTIFICATION_DISMISS_CALLBACK}$"))
    app.add_handler(CallbackQueryHandler(words_goals_callback_handler, pattern=r"^assign:goals$"))
    app.add_handler(CallbackQueryHandler(words_progress_callback_handler, pattern=r"^assign:progress$"))
    app.add_handler(CallbackQueryHandler(goal_setup_disabled_callback_handler, pattern=r"^assign:goal_setup$"))
    app.add_handler(CallbackQueryHandler(goal_setup_disabled_callback_handler, pattern=r"^assign:goal_target_menu$"))
    app.add_handler(CallbackQueryHandler(goal_setup_disabled_callback_handler, pattern=r"^words:goal_period:"))
    app.add_handler(CallbackQueryHandler(goal_type_callback_handler, pattern=r"^words:goal_type:"))
    app.add_handler(CallbackQueryHandler(goal_setup_disabled_callback_handler, pattern=r"^words:goal_target:"))
    app.add_handler(CallbackQueryHandler(goal_setup_disabled_callback_handler, pattern=r"^words:goal_source:"))
    app.add_handler(CallbackQueryHandler(goal_reset_callback_handler, pattern=r"^words:goal_reset:"))
    app.add_handler(CallbackQueryHandler(admin_assign_goal_start_handler, pattern=r"^assign:admin_assign_goal$"))
    app.add_handler(CallbackQueryHandler(admin_goal_target_menu_callback_handler, pattern=r"^assign:admin_goal_target_menu$"))
    app.add_handler(CallbackQueryHandler(admin_goal_source_menu_callback_handler, pattern=r"^assign:admin_goal_source_menu$"))
    app.add_handler(CallbackQueryHandler(admin_goal_period_callback_handler, pattern=r"^words:admin_goal_period:"))
    app.add_handler(CallbackQueryHandler(admin_goal_target_callback_handler, pattern=r"^words:admin_goal_target:"))
    app.add_handler(CallbackQueryHandler(admin_goal_source_callback_handler, pattern=r"^words:admin_goal_source:"))
    app.add_handler(
        CallbackQueryHandler(admin_goal_manual_toggle_callback_handler, pattern=r"^words:admin_goal_manual:toggle:")
    )
    app.add_handler(
        CallbackQueryHandler(admin_goal_manual_toggle_callback_handler, pattern=r"^words:admin_goal_manual:page:")
    )
    app.add_handler(
        CallbackQueryHandler(admin_goal_manual_done_callback_handler, pattern=r"^words:admin_goal_manual:done$")
    )
    app.add_handler(
        CallbackQueryHandler(admin_goal_recipients_callback_handler, pattern=r"^assign:admin_goal_recipients:")
    )
    app.add_handler(
        CallbackQueryHandler(admin_users_progress_callback_handler, pattern=r"^assign:users$")
    )
    app.add_handler(
        CallbackQueryHandler(assign_user_detail_callback_handler, pattern=r"^assign:user:")
    )
    app.add_handler(
        CallbackQueryHandler(assign_goal_detail_callback_handler, pattern=r"^assign:goal:")
    )
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
        MessageHandler(filters.TEXT & ~filters.COMMAND, goal_text_handler),
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


def _telegram_user_login_repository(context: ContextTypes.DEFAULT_TYPE) -> SQLiteTelegramUserLoginRepository:
    return context.application.bot_data["telegram_user_login_repository"]


def _telegram_user_role_repository(context: ContextTypes.DEFAULT_TYPE) -> SQLiteTelegramUserRoleRepository:
    return context.application.bot_data["telegram_user_role_repository"]


def _telegram_ui_language_for_user_id(context: ContextTypes.DEFAULT_TYPE, *, user_id: int) -> str:
    login = next(
        (item for item in _telegram_user_login_repository(context).list() if item.user_id == user_id),
        None,
    )
    if login is not None and login.language_code is not None:
        return _normalize_telegram_ui_language(login.language_code)
    return _telegram_ui_language(context)


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


def _homework_progress_use_case(context: ContextTypes.DEFAULT_TYPE) -> HomeworkProgressUseCase:
    return context.application.bot_data["homework_progress_use_case"]


def _user_goals_use_case(context: ContextTypes.DEFAULT_TYPE) -> ListUserGoalsUseCase:
    return context.application.bot_data["list_user_goals_use_case"]


def _user_progress_summary_use_case(context: ContextTypes.DEFAULT_TYPE) -> GetUserProgressSummaryUseCase:
    return context.application.bot_data["get_user_progress_summary_use_case"]


def _learner_assignment_launch_summary_use_case(
    context: ContextTypes.DEFAULT_TYPE,
) -> GetLearnerAssignmentLaunchSummaryUseCase:
    return context.application.bot_data["learner_assignment_launch_summary_use_case"]


def _goal_period_label(*, context: ContextTypes.DEFAULT_TYPE, user, value: str) -> str:
    return ui_goal_period_label(tg=_tg, context=context, user=user, value=value)


def _goal_type_label(*, context: ContextTypes.DEFAULT_TYPE, user, value: str) -> str:
    return ui_goal_type_label(tg=_tg, context=context, user=user, value=value)


def _goal_rule_text(*, context: ContextTypes.DEFAULT_TYPE, user, goal_type: GoalType) -> str:
    return ui_goal_rule_text(tg=_tg, context=context, user=user, goal_type=goal_type)


def _list_goal_history(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    include_history: bool,
) -> list[GoalProgressView]:
    use_case = context.application.bot_data.get("list_user_goals_use_case")
    if use_case is None:
        return []
    return list(use_case.execute(user_id=user_id, include_history=include_history))


def _collect_goal_feedback_update(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    before_summary: LearnerProgressSummary,
) -> _GoalFeedbackUpdate:
    after_summary = _homework_progress_use_case(context).get_summary(user_id=user.id)
    before_active_by_id = {item.goal.id: item for item in before_summary.active_goals}
    after_active_by_id = {item.goal.id: item for item in after_summary.active_goals}
    progressed_goals = tuple(
        item
        for goal_id, item in after_active_by_id.items()
        if goal_id in before_active_by_id
        and item.goal.progress_count > before_active_by_id[goal_id].goal.progress_count
    )
    completed_candidates = _list_goal_history(context=context, user_id=user.id, include_history=True)
    completed_goals = tuple(
        item
        for item in completed_candidates
        if item.goal.status is GoalStatus.COMPLETED
        and item.goal.id in before_active_by_id
        and item.goal.id not in after_active_by_id
    )
    return _GoalFeedbackUpdate(
        weekly_points_delta=max(0, after_summary.weekly_points - before_summary.weekly_points),
        progressed_goals=progressed_goals,
        completed_goals=completed_goals,
    )


def _render_goal_progress_line(*, context: ContextTypes.DEFAULT_TYPE, user, goal_view: GoalProgressView) -> str:
    return ui_render_goal_progress_line(tg=_tg, context=context, user=user, goal_view=goal_view)


def _render_feedback_update_text(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    update: _GoalFeedbackUpdate,
) -> str:
    lines: list[str] = []
    if update.weekly_points_delta > 0:
        lines.append(
            _tg(
                "feedback_weekly_points_delta",
                context=context,
                user=user,
                delta=update.weekly_points_delta,
            )
        )
    if update.progressed_goals:
        lines.append(_tg("feedback_goal_progress_title", context=context, user=user))
        for goal in update.progressed_goals:
            lines.append(_render_goal_progress_line(context=context, user=user, goal_view=goal))
    if update.completed_goals:
        lines.append(_tg("feedback_goal_completed_title", context=context, user=user))
        for goal in update.completed_goals:
            lines.append(_render_goal_progress_line(context=context, user=user, goal_view=goal))
    return "\n".join(lines)


def _assignment_round_progress_view(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    kind: AssignmentSessionKind,
) -> _AssignmentRoundProgressView | None:
    launch_views = _learner_assignment_launch_summary_use_case(context).execute(user_id=user_id)
    launch_view = next((item for item in launch_views if item.kind is kind), None)
    if launch_view is None:
        return None
    return _AssignmentRoundProgressView(
        completed_word_count=launch_view.completed_word_count,
        total_word_count=launch_view.total_word_count,
        remaining_word_count=launch_view.remaining_word_count,
        estimated_round_count=launch_view.estimated_round_count,
        variant_key=launch_view.progress_variant_key,
    )


def _assignment_progress_variant_index(*, variant_key: str, variant_count: int) -> int:
    if variant_count <= 0:
        return 0
    digest = hashlib.sha256(variant_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % variant_count


def _render_assignment_progress_track(
    *,
    completed: int,
    total: int,
    variant_key: str,
    steps: int = 6,
) -> str:
    if total <= 0:
        return ""
    bounded_completed = min(max(completed, 0), total)
    if total == 1:
        runner_index = 0 if bounded_completed < total else steps - 1
    else:
        runner_index = round((bounded_completed / total) * (steps - 1))
    variants = (
        ("🐣", "⬜", "🏁"),
        ("🚗", "🛣️", "🏁"),
        ("🐛", "🍃", "🌼"),
        ("🐭", "🧀", "🏠"),
    )
    runner, trail, finish = variants[
        _assignment_progress_variant_index(
            variant_key=variant_key,
            variant_count=len(variants),
        )
    ]
    cells = [trail] * steps
    cells[runner_index] = runner
    return "".join(cells) + finish


def _render_assignment_round_progress_text(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    kind: AssignmentSessionKind,
    progress: _AssignmentRoundProgressView,
) -> str:
    if progress.total_word_count <= 0:
        return ""
    return "\n".join(
        [
            _tg(
                "assignment_round_progress_title",
                context=context,
                user=user,
                label=_assignment_kind_label(kind, context=context, user=user),
            ),
            _render_assignment_progress_track(
                completed=progress.completed_word_count,
                total=progress.total_word_count,
                variant_key=progress.variant_key,
            ),
            _tg(
                "assignment_round_progress_status",
                context=context,
                user=user,
                done=progress.completed_word_count,
                total=progress.total_word_count,
                left=progress.remaining_word_count,
                rounds=progress.estimated_round_count,
            ),
        ]
    )


def _start_assignment_round_use_case(
    context: ContextTypes.DEFAULT_TYPE,
) -> StartAssignmentRoundUseCase:
    return context.application.bot_data["start_assignment_round_use_case"]


def _assign_goal_to_users_use_case(context: ContextTypes.DEFAULT_TYPE) -> AssignGoalToUsersUseCase:
    return context.application.bot_data["assign_goal_to_users_use_case"]


def _goal_word_candidates_use_case(context: ContextTypes.DEFAULT_TYPE) -> GetGoalWordCandidatesUseCase:
    return context.application.bot_data["goal_word_candidates_use_case"]


def _admin_users_progress_overview_use_case(
    context: ContextTypes.DEFAULT_TYPE,
) -> GetAdminUsersProgressOverviewUseCase:
    return context.application.bot_data["admin_users_progress_overview_use_case"]


def _admin_user_goals_use_case(context: ContextTypes.DEFAULT_TYPE) -> GetAdminUserGoalsUseCase:
    return context.application.bot_data["admin_user_goals_use_case"]


def _admin_goal_detail_use_case(context: ContextTypes.DEFAULT_TYPE) -> GetAdminGoalDetailUseCase:
    return context.application.bot_data["admin_goal_detail_use_case"]


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
    application = getattr(context, "application", None)
    bot_data = getattr(application, "bot_data", None)
    if not isinstance(bot_data, dict):
        return None
    return bot_data.get("telegram_flow_message_repository")


def _menu_access_policy(context: ContextTypes.DEFAULT_TYPE) -> TelegramMenuAccessPolicy:
    configured_policy = context.application.bot_data.get("telegram_menu_access_policy")
    if isinstance(configured_policy, TelegramMenuAccessPolicy):
        return configured_policy
    return TelegramMenuAccessPolicy.from_bot_data(context.application.bot_data)


def _has_menu_permission(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int | None,
    permission: str,
) -> bool:
    return _menu_access_policy(context).has_permission(user_id, permission)


def _is_editor(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return any(
        _has_menu_permission(context, user_id=user_id, permission=permission)
        for permission in (
            PERMISSION_WORDS_ADD,
            PERMISSION_WORDS_EDIT,
            PERMISSION_WORD_IMAGES_EDIT,
        )
    )


def _is_admin(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return "admin" in _menu_access_policy(context).roles_for_user(user_id)


def _visible_command_specs(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int | None,
    only_chat_menu: bool = False,
) -> tuple[TelegramCommandSpec, ...]:
    return _menu_access_policy(context).visible_commands(
        user_id,
        command_specs=DEFAULT_TELEGRAM_COMMAND_SPECS,
        only_chat_menu=only_chat_menu,
    )


def _visible_command_rows(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int | None,
) -> list[list[str]]:
    commands = {spec.command for spec in _visible_command_specs(context, user_id=user_id, only_chat_menu=True)}
    rows = [
        ["/start", "/help"],
        ["/version", "/words"],
    ]
    if "assign" in commands:
        rows.append(["/assign"])
    if "add_words" in commands:
        rows.append(["/add_words", "/cancel"])
    return rows


def _preview_message_ids(context: ContextTypes.DEFAULT_TYPE) -> dict[int, int]:
    return context.application.bot_data["word_import_preview_message_ids"]


def _admin_web_app_url(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user,
) -> str | None:
    user_id = getattr(user, "id", None)
    if user_id is None or not _is_admin(user_id, context):
        return None
    configured_url = context.application.bot_data.get("web_app_base_url")
    if not isinstance(configured_url, str):
        return None
    normalized = configured_url.strip().rstrip("/")
    if not normalized:
        return None
    language = _telegram_ui_language(context, user)
    query = urlencode({"user_id": user_id, "lang": language})
    return f"{normalized}/webapp?{query}"


def _assignment_guide_web_app_url(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user,
) -> str | None:
    configured_url = context.application.bot_data.get("web_app_base_url")
    if not isinstance(configured_url, str):
        return None
    normalized = configured_url.strip().rstrip("/")
    if not normalized:
        return None
    language = _telegram_ui_language(context, user)
    query = urlencode({"lang": language})
    return f"{normalized}/webapp/help?{query}"


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
    return ui_draft_review_keyboard(
        flow_id,
        is_valid,
        tg=_tg,
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
    return ui_draft_review_view(
        result=result,
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
    return ui_image_review_keyboard(
        flow_id=flow_id,
        current_item=current_item,
        tg=_tg,
        show_generate_image_button=capabilities.local_image_generation_available,
        language=_telegram_ui_language(context, user),
    )


def _quick_actions_view(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return ui_quick_actions_view(
        tg=_tg,
        context=context,
        user=user,
        reply_markup=_chat_menu_keyboard(
            command_rows=_visible_command_rows(
                context,
                user_id=(user.id if user is not None else None),
            )
        ),
    )


def _chat_menu_flow_id(*, user_id: int) -> str:
    return f"chat-menu:{user_id}"


def _start_menu_view(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    summary = _learner_assignment_launch_summary_use_case(context).execute(user_id=user.id)
    return build_start_menu_view(
        text=_render_start_menu_text(context=context, user=user, summary=summary),
        reply_markup=_start_menu_keyboard(
            summary=summary,
            guide_web_app_url=_assignment_guide_web_app_url(context, user=user),
            admin_web_app_url=_admin_web_app_url(context, user=user),
            language=_telegram_ui_language(context, user),
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
    return ui_topic_selection_view(
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
    return ui_lesson_selection_view(
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
    return ui_mode_selection_view(
        text=text,
        reply_markup=_mode_keyboard(
            topic_id,
            lesson_id,
            language=_telegram_ui_language(context, user),
        ),
    )


def _game_mode_selection_view(
    *,
    text: str,
    topic_id: str,
    lesson_id: str | None,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return ui_mode_selection_view(
        text=text,
        reply_markup=_game_mode_keyboard(
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
    return ui_words_menu_view(
        text=text,
        reply_markup=_words_menu_keyboard(
            can_add_words=bool(
                user
                and _has_menu_permission(
                    context,
                    user_id=user.id,
                    permission=PERMISSION_WORDS_ADD,
                )
            ),
            can_edit_words=bool(
                user
                and _has_menu_permission(
                    context,
                    user_id=user.id,
                    permission=PERMISSION_WORDS_EDIT,
                )
            ),
            can_edit_images=bool(
                user
                and _has_menu_permission(
                    context,
                    user_id=user.id,
                    permission=PERMISSION_WORD_IMAGES_EDIT,
                )
            ),
            language=_telegram_ui_language(context, user),
        ),
    )


def _assign_menu_view(
    *,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return build_assignment_menu_view(
        text=text,
        reply_markup=_assign_menu_keyboard(
            is_admin=bool(user and _is_admin(user.id, context)),
            guide_web_app_url=_assignment_guide_web_app_url(context, user=user),
            admin_web_app_url=_admin_web_app_url(context, user=user),
            language=_telegram_ui_language(context, user),
        ),
    )


def _help_view(
    *,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return ui_help_view(
        text=text,
        reply_markup=_chat_menu_keyboard(
            command_rows=_visible_command_rows(
                context,
                user_id=(user.id if user is not None else None),
            )
        ),
    )


def _remember_expected_user_input(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int | None,
    message_id: int | None,
) -> None:
    if chat_id is None or message_id is None:
        return
    context.user_data[_EXPECTED_USER_INPUT_STATE_KEY] = {
        "chat_id": chat_id,
        "message_id": message_id,
    }


def _clear_expected_user_input(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_EXPECTED_USER_INPUT_STATE_KEY, None)


async def _edit_expected_user_input_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    text: str,
    reply_markup,
) -> bool:
    stored = context.user_data.get(_EXPECTED_USER_INPUT_STATE_KEY)
    if not isinstance(stored, dict):
        return False
    chat_id = stored.get("chat_id")
    message_id = stored.get("message_id")
    if not isinstance(chat_id, int) or not isinstance(message_id, int):
        return False
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except BadRequest as error:
        if "message is not modified" in str(error).lower():
            return True
        logger.debug("Failed to edit stored goal prompt message", exc_info=True)
        return False
    return True


def _known_assignment_users(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    viewer_user_id: int,
    viewer_username: str | None = None,
) -> list[_AssignmentUserView]:
    policy = _menu_access_policy(context)
    overview_by_user_id = {
        item.user_id: item
        for item in _admin_users_progress_overview_use_case(context).execute()
    }
    login_rows = _telegram_user_login_repository(context).list()
    login_by_user_id = {row.user_id: row for row in login_rows}
    visible_user_ids = set(login_by_user_id)
    visible_user_ids.add(viewer_user_id)
    if _is_admin(viewer_user_id, context):
        for role_user_ids in policy.role_memberships.values():
            visible_user_ids.update(role_user_ids)
    else:
        visible_user_ids = {viewer_user_id}

    users: list[_AssignmentUserView] = []
    for user_id in sorted(visible_user_ids):
        login = login_by_user_id.get(user_id)
        overview = overview_by_user_id.get(user_id)
        username = login.username if login is not None else None
        if user_id == viewer_user_id and viewer_username:
            username = viewer_username
        last_seen_at = (
            datetime.fromisoformat(login.last_seen_at)
            if login is not None and login.last_seen_at
            else None
        )
        users.append(
            _AssignmentUserView(
                user_id=user_id,
                username=username,
                roles=policy.roles_for_user(user_id),
                active_goals_count=(overview.active_goals_count if overview is not None else 0),
                completed_goals_count=(overview.completed_goals_count if overview is not None else 0),
                aggregate_percent=(overview.aggregate_percent if overview is not None else 0),
                last_activity_at=(overview.last_activity_at if overview is not None else None),
                last_seen_at=last_seen_at,
            )
        )
    users.sort(
        key=lambda item: (
            item.last_seen_at is not None,
            item.last_seen_at or datetime.min.replace(tzinfo=UTC),
            item.user_id,
        ),
        reverse=True,
    )
    return users


def _assignment_user_label(item: _AssignmentUserView) -> str:
    return ui_assignment_user_label(item)


def _render_assignment_user_detail_text(*, context: ContextTypes.DEFAULT_TYPE, user, item: _AssignmentUserView, goals) -> str:
    return ui_render_assignment_user_detail_text(
        tg=lambda key, **kwargs: _tg(key, context=context, user=user, **kwargs),
        item=item,
        goals=goals,
    )


def _render_assignment_goal_detail_text(*, context: ContextTypes.DEFAULT_TYPE, user, detail) -> str:
    return ui_render_assignment_goal_detail_text(
        tg=lambda key, **kwargs: _tg(key, context=context, user=user, **kwargs),
        detail=detail,
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
    return ui_editable_topics_view(text=text, reply_markup=markup)


def _editable_words_view(
    *,
    text: str,
    topic_id: str,
    words,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return ui_editable_words_view(
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
        _telegram_user_login_repository(context).record(
            user_id=user.id,
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
            language_code=getattr(user, "language_code", None),
        )
        logger.info("User %s opened /start", user.id)
        active_session = _service(context).get_active_session(user_id=user.id)
        if active_session is not None:
            context.user_data["awaiting_text_answer"] = active_session.mode is TrainingMode.HARD
            await send_telegram_view(
                message,
                build_active_session_exists_view(
                    text=_tg(
                        "active_session_exists",
                        context=context,
                        user=user,
                        topic_id=_active_session_topic_label(
                            context=context,
                            user=user,
                            topic_id=active_session.topic_id,
                            source_tag=active_session.source_tag,
                            lesson_id=active_session.lesson_id,
                        ),
                        lesson_id=_active_session_lesson_label(
                            context=context,
                            user=user,
                            topic_id=active_session.topic_id,
                            lesson_id=active_session.lesson_id,
                            source_tag=active_session.source_tag,
                        ),
                        mode=active_session.mode.value,
                        current_position=active_session.current_position,
                        total_items=active_session.total_items,
                    ),
                    reply_markup=_active_session_keyboard(
                        language=_telegram_ui_language(context, user),
                    ),
                ),
            )
            return
    await send_telegram_view(
        message,
        _start_menu_view(context=context, user=user),
    )
    if user is not None:
        await _ensure_chat_menu_message(context, message=message, user=user)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    visible_commands = _visible_command_specs(
        context,
        user_id=(user.id if user is not None else None),
    )
    commands = [
        f"/{spec.command} - {_HELP_COMMAND_TEXT.get(spec.command, spec.description.lower())}"
        for spec in visible_commands
    ]
    await send_telegram_view(
        message,
        _help_view(
            text=_tg("help_title", context=context, user=user, commands="\n".join(commands)),
            context=context,
            user=user,
        ),
    )
    if user is not None:
        await _ensure_chat_menu_message(context, message=message, user=user)


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


async def makeadmin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    _telegram_user_login_repository(context).record(
        user_id=user.id,
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
        language_code=getattr(user, "language_code", None),
    )

    if not context.args:
        await send_telegram_view(
            message,
            build_status_view(
                text="Usage: /makeadmin <telegram_id> [bootstrap_secret]"
            ),
        )
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await send_telegram_view(
            message,
            build_status_view(text="The target telegram_id must be an integer."),
        )
        return

    provided_secret = context.args[1] if len(context.args) > 1 else ""
    role_repository = _telegram_user_role_repository(context)
    admin_ids = role_repository.list_memberships().get("admin", frozenset())
    requester_is_admin = user.id in admin_ids
    bootstrap_secret = str(
        context.application.bot_data.get("admin_bootstrap_secret", "")
    ).strip()
    secret_is_valid = bool(
        bootstrap_secret and provided_secret and hmac.compare_digest(provided_secret, bootstrap_secret)
    )

    if not requester_is_admin and not secret_is_valid:
        await send_telegram_view(
            message,
            build_status_view(
                text=(
                    "Access denied. Current admins can use /makeadmin directly. "
                    "Otherwise provide a valid bootstrap secret."
                )
            ),
        )
        return

    try:
        role_repository.grant(user_id=target_user_id, role="admin")
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to grant admin role via /makeadmin target_user_id=%s requester_user_id=%s",
            target_user_id,
            user.id,
        )
        await send_telegram_view(
            message,
            build_status_view(text="Failed to grant the admin role."),
        )
        return

    updated_admin_ids = role_repository.list_memberships().get("admin", frozenset())
    if target_user_id not in updated_admin_ids:
        await send_telegram_view(
            message,
            build_status_view(text="Failed to grant the admin role."),
        )
        return

    await send_telegram_view(
        message,
        build_status_view(
            text=f"Admin role granted to Telegram user {target_user_id}."
        ),
    )


async def assign_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    _telegram_user_login_repository(context).record(
        user_id=user.id,
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
        language_code=getattr(user, "language_code", None),
    )
    await send_telegram_view(
        message,
        _assign_menu_view(
            text=_tg("assign_menu_prompt", context=context, user=user),
            context=context,
            user=user,
        ),
    )
    await _ensure_chat_menu_message(context, message=message, user=user)


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
    if user is not None:
        await _ensure_chat_menu_message(context, message=message, user=user)


async def assign_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    try:
        await edit_telegram_text_view(
            query,
            _assign_menu_view(
                text=_tg("assign_menu_title", context=context, user=update.effective_user),
                context=context,
                user=update.effective_user,
            ),
        )
    except BadRequest as error:
        if "message is not modified" in str(error).lower():
            logger.debug("Assign menu message unchanged")
            return
        raise


async def noop_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    query = update.callback_query
    if query is None:
        return
    await query.answer()


async def notification_dismiss_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    await _delete_message_if_possible(context, message=query.message)


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


def _goal_setup_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_goal_setup_keyboard(tg=_tg, language=language)


def _goal_target_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_goal_target_keyboard(tg=_tg, language=language)


def _goal_source_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_goal_source_keyboard(tg=_tg, language=language)


def _goal_custom_target_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_goal_custom_target_keyboard(tg=_tg, language=language)


def _goal_list_keyboard(*, goals, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_goal_list_keyboard(
        tg=_tg,
        goals=goals,
        language=language,
    )


def _admin_goal_period_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_admin_goal_period_keyboard(tg=_tg, language=language)


def _admin_goal_target_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_admin_goal_target_keyboard(tg=_tg, language=language)


def _admin_goal_custom_target_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_admin_goal_custom_target_keyboard(tg=_tg, language=language)


def _admin_goal_source_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_admin_goal_source_keyboard(tg=_tg, language=language)


def _render_progress_text(*, context: ContextTypes.DEFAULT_TYPE, user) -> str:
    summary = _homework_progress_use_case(context).get_summary(user_id=user.id)
    history = _list_goal_history(context=context, user_id=user.id, include_history=True)
    assignment_summary = _learner_assignment_launch_summary_use_case(context).execute(user_id=user.id)
    return ui_render_progress_text(
        tg=_tg,
        context=context,
        user=user,
        summary=summary,
        history=history,
        assignment_summary=assignment_summary,
    )


def _render_start_menu_text(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    summary: list[AssignmentLaunchView],
) -> str:
    return ui_render_start_menu_text(
        tg=_tg,
        context=context,
        user=user,
        summary=summary,
    )


def _assignment_kind_label(kind: AssignmentSessionKind, *, context: ContextTypes.DEFAULT_TYPE, user) -> str:
    return ui_assignment_kind_label(kind, tg=_tg, context=context, user=user)


def _start_assignment_button_label(
    kind: AssignmentSessionKind,
    *,
    available: bool,
    language: str,
) -> str:
    return ui_start_assignment_button_label(
        kind,
        tg=_tg,
        available=available,
        language=language,
    )


def _active_session_topic_label(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    topic_id: str,
    source_tag: str | None = None,
    lesson_id: str | None = None,
) -> str:
    if source_tag is not None and source_tag.startswith("assignment:"):
        kind = AssignmentSessionKind(source_tag.split(":", 1)[1])
        return _assignment_kind_label(kind, context=context, user=user)
    if topic_id.startswith("assignment:"):
        kind = AssignmentSessionKind(topic_id.split(":", 1)[1])
        return _assignment_kind_label(kind, context=context, user=user)
    return topic_id


def _active_session_lesson_label(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    topic_id: str,
    lesson_id: str | None,
    source_tag: str | None = None,
) -> str:
    if isinstance(source_tag, str) and source_tag.startswith("assignment:"):
        return _tg("assignment_round_session_label", context=context, user=user)
    return lesson_id or _tg("all_topic_words", context=context, user=user)


def _assignment_kind_from_session(active_session) -> AssignmentSessionKind | None:
    source_tag = getattr(active_session, "source_tag", None)
    if isinstance(source_tag, str) and source_tag.startswith("assignment:"):
        return AssignmentSessionKind(source_tag.split(":", 1)[1])
    topic_id = getattr(active_session, "topic_id", None)
    if isinstance(topic_id, str) and topic_id.startswith("assignment:"):
        return AssignmentSessionKind(topic_id.split(":", 1)[1])
    return None


async def words_goals_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    summary = _homework_progress_use_case(context).get_summary(user_id=user.id)
    try:
        await query.edit_message_text(
            _render_progress_text(context=context, user=user),
            reply_markup=_goal_list_keyboard(goals=summary.active_goals, language=_telegram_ui_language(context, user)),
        )
    except BadRequest as error:
        if "Message is not modified" not in str(error):
            raise


async def words_progress_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await words_goals_callback_handler(update, context)


def _clear_self_goal_setup_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("goal_period", None)
    context.user_data.pop("goal_type", None)
    context.user_data.pop("goal_target_count", None)
    if context.user_data.get("words_flow_mode") == _GOAL_AWAITING_TARGET_TEXT:
        context.user_data.pop("words_flow_mode", None)


async def goal_setup_disabled_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    _clear_self_goal_setup_state(context)
    await query.edit_message_text(
        _tg("self_goal_setup_disabled", context=context, user=user),
        reply_markup=_assign_menu_view(
            text=_tg("assign_menu_title", context=context, user=user),
            context=context,
            user=user,
        ).reply_markup,
    )


async def goal_type_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    return


async def goal_reset_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    goal_id = query.data.split(":")[-1]
    reset = _homework_progress_use_case(context).reset_goal(user_id=user.id, goal_id=goal_id)
    await query.edit_message_text(_tg("goal_reset_done" if reset else "goal_reset_not_found", context=context, user=user))


async def admin_assign_goal_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not _is_admin(user.id, context):
        await query.edit_message_text(_tg("admin_only", context=context, user=user))
        return
    for key in (
        "admin_goal_period",
        "admin_goal_type",
        "admin_goal_target_count",
        "admin_goal_source",
        "admin_goal_manual_word_ids",
        "admin_goal_recipient_user_ids",
        "admin_goal_recipients_page",
    ):
        context.user_data.pop(key, None)
    context.user_data["admin_goal_recipient_user_ids"] = set()
    await query.edit_message_text(
        _tg("assign_setup_intro", context=context, user=user),
        reply_markup=_admin_goal_period_keyboard(language=_telegram_ui_language(context, user)),
    )


async def admin_goal_period_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    raw_period = query.data.split(":")[-1]
    context.user_data["admin_goal_period"] = raw_period
    context.user_data["admin_goal_type"] = (
        GoalType.WORD_LEVEL_HOMEWORK.value if raw_period == GoalPeriod.HOMEWORK.value else GoalType.NEW_WORDS.value
    )
    await query.edit_message_text(
        _tg("goal_target_prompt", context=context, user=user),
        reply_markup=_admin_goal_target_keyboard(language=_telegram_ui_language(context, user)),
    )


async def admin_goal_target_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await query.edit_message_text(
        _tg("goal_target_prompt", context=context, user=user),
        reply_markup=_admin_goal_target_keyboard(language=_telegram_ui_language(context, user)),
    )


async def admin_goal_target_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    target = query.data.split(":")[-1]
    if target == "custom":
        context.user_data["words_flow_mode"] = _ADMIN_GOAL_AWAITING_TARGET_TEXT
        _remember_expected_user_input(
            context,
            chat_id=getattr(getattr(query, "message", None), "chat_id", None),
            message_id=getattr(getattr(query, "message", None), "message_id", None),
        )
        await query.edit_message_text(
            _tg("goal_target_custom_prompt", context=context, user=user),
            reply_markup=_admin_goal_custom_target_keyboard(language=_telegram_ui_language(context, user)),
        )
        return
    context.user_data["admin_goal_target_count"] = int(target)
    await query.edit_message_text(
        _tg("goal_source_prompt", context=context, user=user),
        reply_markup=_admin_goal_source_keyboard(language=_telegram_ui_language(context, user)),
    )


async def admin_goal_source_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await query.edit_message_text(
        _tg("goal_source_prompt", context=context, user=user),
        reply_markup=_admin_goal_source_keyboard(language=_telegram_ui_language(context, user)),
    )


def _admin_goal_manual_keyboard(*, context: ContextTypes.DEFAULT_TYPE, user, page: int) -> InlineKeyboardMarkup:
    items = _content_store(context).list_all_vocabulary()
    selected = set(context.user_data.get("admin_goal_manual_word_ids", set()))
    keyboard, normalized_page = ui_admin_goal_manual_keyboard(
        tg=_tg,
        items=items,
        selected_word_ids=selected,
        page=page,
        language=_telegram_ui_language(context, user),
    )
    context.user_data["admin_goal_manual_page"] = normalized_page
    return keyboard


def _admin_goal_recipients_keyboard(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    page: int,
) -> InlineKeyboardMarkup:
    items = _known_assignment_users(
        context,
        viewer_user_id=user.id,
        viewer_username=getattr(user, "username", None),
    )
    selected = set(context.user_data.get("admin_goal_recipient_user_ids", set()))
    keyboard, normalized_page = ui_admin_goal_recipients_keyboard(
        tg=_tg,
        items=items,
        selected_user_ids=selected,
        page=page,
        language=_telegram_ui_language(context, user),
    )
    context.user_data["admin_goal_recipients_page"] = normalized_page
    return keyboard


def _assignment_users_keyboard(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    users=None,
) -> InlineKeyboardMarkup:
    return ui_assignment_users_keyboard(
        tg=_tg,
        users=users,
        language=_telegram_ui_language(context, user),
    )


def _assignment_user_goals_keyboard(*, context: ContextTypes.DEFAULT_TYPE, user_id: int, goals, user) -> InlineKeyboardMarkup:
    return ui_assignment_user_goals_keyboard(
        tg=_tg,
        user_id=user_id,
        goals=goals,
        language=_telegram_ui_language(context, user),
    )


def _assignment_goal_detail_keyboard(*, context: ContextTypes.DEFAULT_TYPE, user_id: int, user) -> InlineKeyboardMarkup:
    return ui_assignment_goal_detail_keyboard(
        tg=_tg,
        user_id=user_id,
        language=_telegram_ui_language(context, user),
    )


def _page_range_label(*, page: int, page_size: int, total: int, language: str) -> str:
    return ui_page_range_label(
        tg=_tg,
        page=page,
        page_size=page_size,
        total=total,
        language=language,
    )


async def admin_goal_source_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    if query.data.startswith("words:admin_goal_source:topic:"):
        context.user_data["admin_goal_source"] = f"topic:{query.data.split(':', 4)[-1]}"
        await query.edit_message_text(
            _tg("assign_select_users_prompt", context=context, user=user),
            reply_markup=_admin_goal_recipients_keyboard(context=context, user=user, page=0),
        )
        return
    source = query.data.split(":")[-1]
    context.user_data["admin_goal_source"] = source
    if source == GoalWordSource.TOPIC.value:
        topics = _service(context).list_topics()
        keyboard = ui_goal_source_topic_keyboard(
            tg=_tg,
            topics=topics,
            language=_telegram_ui_language(context, user),
        )
        await query.edit_message_text(_tg("goal_source_topic_prompt", context=context, user=user), reply_markup=keyboard)
        return
    if source == GoalWordSource.MANUAL.value:
        context.user_data["admin_goal_manual_word_ids"] = set()
        await query.edit_message_text(_tg("goal_source_manual_prompt", context=context, user=user), reply_markup=_admin_goal_manual_keyboard(context=context, user=user, page=0))
        return
    await query.edit_message_text(
        _tg("assign_select_users_prompt", context=context, user=user),
        reply_markup=_admin_goal_recipients_keyboard(context=context, user=user, page=0),
    )


async def admin_goal_manual_toggle_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    if query.data.startswith("words:admin_goal_manual:page:"):
        page = int(query.data.split(":")[-1])
    else:
        word_id = query.data.split(":", 4)[-1]
        selected = set(context.user_data.get("admin_goal_manual_word_ids", set()))
        if word_id in selected:
            selected.remove(word_id)
        else:
            selected.add(word_id)
        context.user_data["admin_goal_manual_word_ids"] = selected
        page = int(context.user_data.get("admin_goal_manual_page", 0))
    await query.edit_message_text(_tg("goal_source_manual_prompt", context=context, user=user), reply_markup=_admin_goal_manual_keyboard(context=context, user=user, page=page))


async def admin_goal_manual_done_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not context.user_data.get("admin_goal_manual_word_ids"):
        await query.edit_message_text(_tg("goal_manual_empty", context=context, user=user))
        return
    await query.edit_message_text(
        _tg("assign_select_users_prompt", context=context, user=user),
        reply_markup=_admin_goal_recipients_keyboard(context=context, user=user, page=0),
    )


async def admin_goal_recipients_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    if query.data.startswith("assign:admin_goal_recipients:page:"):
        page = int(query.data.split(":")[-1])
    elif query.data == "assign:admin_goal_recipients:done":
        if not context.user_data.get("admin_goal_recipient_user_ids"):
            await query.edit_message_text(_tg("assign_select_users_empty", context=context, user=user))
            return
        await _create_admin_goal_from_context(query=query, context=context, user=user)
        return
    else:
        target_user_id = int(query.data.split(":")[-1])
        selected = set(context.user_data.get("admin_goal_recipient_user_ids", set()))
        if target_user_id in selected:
            selected.remove(target_user_id)
        else:
            selected.add(target_user_id)
        context.user_data["admin_goal_recipient_user_ids"] = selected
        page = int(context.user_data.get("admin_goal_recipients_page", 0))
    await query.edit_message_text(
        _tg("assign_select_users_prompt", context=context, user=user),
        reply_markup=_admin_goal_recipients_keyboard(context=context, user=user, page=page),
    )


async def _create_admin_goal_from_context(*, query, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    source_raw = str(context.user_data.get("admin_goal_source", GoalWordSource.RECENT.value))
    topic_id = source_raw.split(":", 1)[1] if source_raw.startswith("topic:") else None
    source = GoalWordSource.TOPIC if topic_id else GoalWordSource(source_raw)
    created = _assign_goal_to_users_use_case(context).execute(
        user_ids=list(context.user_data.get("admin_goal_recipient_user_ids", [])),
        goal_period=GoalPeriod(str(context.user_data.get("admin_goal_period", GoalPeriod.WEEKLY.value))),
        goal_type=GoalType(str(context.user_data.get("admin_goal_type", GoalType.NEW_WORDS.value))),
        target_count=int(context.user_data.get("admin_goal_target_count", 10)),
        source=source,
        topic_id=topic_id,
        manual_word_ids=list(context.user_data.get("admin_goal_manual_word_ids", [])),
    )
    _schedule_assignment_assigned_notifications(context, goals=created)
    for recipient_user_id in {int(goal.user_id) for goal in created}:
        await _flush_pending_notifications_for_user(context, user_id=recipient_user_id)
    await query.edit_message_text(_tg("admin_goal_created", context=context, user=user, user_count=len(created), target=int(context.user_data.get("admin_goal_target_count", 10))))
    for key in (
        "admin_goal_period",
        "admin_goal_type",
        "admin_goal_target_count",
        "admin_goal_source",
        "admin_goal_manual_word_ids",
        "admin_goal_recipient_user_ids",
        "admin_goal_recipients_page",
        "words_flow_mode",
    ):
        context.user_data.pop(key, None)


async def admin_users_progress_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    users = _known_assignment_users(
        context,
        viewer_user_id=user.id,
        viewer_username=getattr(user, "username", None),
    )
    if not users:
        await query.edit_message_text(_tg("assign_users_empty", context=context, user=user))
        return
    lines = [_tg("assign_users_title", context=context, user=user)]
    for item in users:
        lines.append(
            _tg(
                "assign_users_line",
                context=context,
                user=user,
                user_id=item.user_id,
                username=(f"@{item.username}" if item.username else "-"),
                roles=(", ".join(role for role in item.roles if role != "user") or "user"),
                active=item.active_goals_count,
                completed=item.completed_goals_count,
                percent=item.aggregate_percent,
                last_activity=(item.last_activity_at.date().isoformat() if item.last_activity_at else "-"),
            )
        )
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=_assignment_users_keyboard(context=context, user=user, users=users),
    )


async def assign_user_detail_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    target_user_id = int(query.data.split(":")[-1])
    users = _known_assignment_users(
        context,
        viewer_user_id=user.id,
        viewer_username=getattr(user, "username", None),
    )
    target = next((item for item in users if item.user_id == target_user_id), None)
    if target is None:
        await query.edit_message_text(_tg("assign_users_empty", context=context, user=user))
        return
    goals = _admin_user_goals_use_case(context).execute(user_id=target_user_id, include_history=True)
    await query.edit_message_text(
        _render_assignment_user_detail_text(context=context, user=user, item=target, goals=goals),
        reply_markup=_assignment_user_goals_keyboard(
            context=context,
            user_id=target_user_id,
            goals=goals,
            user=user,
        ),
    )


async def assign_goal_detail_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    _, _, user_id_raw, goal_id = query.data.split(":", 3)
    target_user_id = int(user_id_raw)
    detail = _admin_goal_detail_use_case(context).execute(user_id=target_user_id, goal_id=goal_id)
    if detail is None:
        await query.edit_message_text(_tg("assign_goal_detail_missing", context=context, user=user))
        return
    await query.edit_message_text(
        _render_assignment_goal_detail_text(context=context, user=user, detail=detail),
        reply_markup=_assignment_goal_detail_keyboard(context=context, user_id=target_user_id, user=user),
    )


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
    if not _has_menu_permission(context, user_id=user.id, permission=PERMISSION_WORDS_ADD):
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
    if not _has_menu_permission(context, user_id=user.id, permission=PERMISSION_WORDS_EDIT):
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
    if not _has_menu_permission(
        context,
        user_id=user.id,
        permission=PERMISSION_WORD_IMAGES_EDIT,
    ):
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
    _remember_expected_user_input(
        context,
        chat_id=_message_chat_id(query.message),
        message_id=getattr(query.message, "message_id", None),
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
    _clear_expected_user_input(context)
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
    if not _has_menu_permission(context, user_id=user.id, permission=PERMISSION_WORDS_ADD):
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
        reply_markup=_chat_menu_keyboard(
            command_rows=_visible_command_rows(context, user_id=user.id)
        ),
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
        reply_markup=_chat_menu_keyboard(
            command_rows=_visible_command_rows(context, user_id=user.id)
        ),
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
    await _ensure_chat_menu_message(context, message=query.message, user=user)


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
    if not _has_menu_permission(context, user_id=user.id, permission=PERMISSION_WORDS_ADD):
        context.user_data.pop("words_flow_mode", None)
        _clear_expected_user_input(context)
        return
    if words_flow_mode == _PUBLISHED_WORD_AWAITING_EDIT_TEXT:
        topic_id = context.user_data.get("published_edit_topic_id")
        item_id = context.user_data.get("published_edit_item_id")
        if not isinstance(topic_id, str) or not isinstance(item_id, str):
            context.user_data.pop("words_flow_mode", None)
            context.user_data.pop("published_edit_topic_id", None)
            context.user_data.pop("published_edit_item_id", None)
            _clear_expected_user_input(context)
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
        await _delete_message_if_possible(context, message=message)
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
            _clear_expected_user_input(context)
            await message.reply_text(_tg("image_review_task_inactive", context=context, user=user))
            return
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("image_review_flow_id", None)
        context.user_data.pop("image_review_item_id", None)
        _clear_expected_user_input(context)
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
        await _delete_message_if_possible(context, message=message)
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
            _clear_expected_user_input(context)
            await message.reply_text(_tg("image_review_task_inactive", context=context, user=user))
            return
        context.user_data.pop("words_flow_mode", None)
        context.user_data.pop("image_review_flow_id", None)
        context.user_data.pop("image_review_item_id", None)
        _clear_expected_user_input(context)
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
        await _delete_message_if_possible(context, message=message)
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


async def goal_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or message.text is None or user is None:
        return
    flow_mode = context.user_data.get("words_flow_mode")
    if flow_mode == _GOAL_AWAITING_TARGET_TEXT:
        _clear_self_goal_setup_state(context)
        await send_telegram_view(
            message,
            build_status_view(
                text=_tg("self_goal_setup_disabled", context=context, user=user),
                reply_markup=_assign_menu_view(
                    text=_tg("assign_menu_title", context=context, user=user),
                    context=context,
                    user=user,
                ).reply_markup,
            ),
        )
        return
    if flow_mode not in {
        _ADMIN_GOAL_AWAITING_TARGET_TEXT,
    }:
        return
    prompt_reply_markup = (
        _admin_goal_custom_target_keyboard(language=_telegram_ui_language(context, user))
    )
    try:
        target_count = int(message.text.strip())
    except ValueError:
        edited = await _edit_expected_user_input_prompt(
            context,
            text=_tg("goal_target_custom_prompt", context=context, user=user),
            reply_markup=prompt_reply_markup,
        )
        if not edited:
            await message.reply_text(
                _tg("goal_target_custom_prompt", context=context, user=user),
                reply_markup=prompt_reply_markup,
            )
        return
    if target_count <= 0:
        edited = await _edit_expected_user_input_prompt(
            context,
            text=_tg("goal_target_custom_prompt", context=context, user=user),
            reply_markup=prompt_reply_markup,
        )
        if not edited:
            await message.reply_text(
                _tg("goal_target_custom_prompt", context=context, user=user),
                reply_markup=prompt_reply_markup,
            )
        return
    context.user_data["admin_goal_target_count"] = target_count
    context.user_data.pop("words_flow_mode", None)
    next_reply_markup = _admin_goal_source_keyboard(language=_telegram_ui_language(context, user))
    edited = await _edit_expected_user_input_prompt(
        context,
        text=_tg("goal_source_prompt", context=context, user=user),
        reply_markup=next_reply_markup,
    )
    if not edited:
        await message.reply_text(
            _tg("goal_source_prompt", context=context, user=user),
            reply_markup=next_reply_markup,
        )
    await _delete_message_if_possible(context, message=message)
    _clear_expected_user_input(context)


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
    await _ensure_chat_menu_message(context, message=query.message, user=user)


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
    await _send_image_review_step(query.message, context, image_review_flow, user=user)


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
    await _send_current_published_image_preview(query.message, context, review_flow, user=user)
    await _send_image_review_step(query.message, context, review_flow, user=user)
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
    await _prepare_and_send_image_review_step(query.message, context, user.id, flow, user=user)


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
    await _send_image_review_step(query.message, context, updated_flow, user=user)


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
    await _send_image_review_step(query.message, context, updated_flow, user=user)


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
    await _send_image_review_step(query.message, context, updated_flow, user=user)


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
            await asyncio.to_thread(
                _publish_image_review(context).execute,
                user_id=user.id,
                flow_id=flow_id,
                output_path=None,
            )
            _reload_training_service(context)
            topic = updated_flow.content_pack.get("topic", {})
            topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
            raw_items = updated_flow.content_pack.get("vocabulary_items", [])
            await query.edit_message_text(
                "\n".join(
                    (
                        _tg("image_selected", context=context, user=user),
                        _tg("choose_another_word_to_edit", context=context, user=user),
                    )
                ),
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
    await _send_image_review_step(query.message, context, updated_flow, user=user)


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
    await _send_image_review_step(query.message, context, updated_flow, user=user)


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
    prompt_message = await send_telegram_view(query.message, instruction_view)
    _remember_expected_user_input(
        context,
        chat_id=_message_chat_id(prompt_message),
        message_id=getattr(prompt_message, "message_id", None),
    )
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
    prompt_message = await send_telegram_view(query.message, instruction_view)
    _remember_expected_user_input(
        context,
        chat_id=_message_chat_id(prompt_message),
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
        _clear_medium_task_state(context)
        await query.edit_message_text(_tg("no_active_session_send_start", context=context, user=user))
        return
    _record_assignment_activity(context, user_id=user.id)
    context.user_data["awaiting_text_answer"] = _expects_text_answer_for_question(question)
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
    _clear_medium_task_state(context)
    await query.edit_message_text(_tg("previous_session_discarded", context=context, user=user))
    await send_telegram_view(
        query.message,
        _start_menu_view(context=context, user=user),
    )


async def start_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await edit_telegram_text_view(query, _start_menu_view(context=context, user=user))


async def start_assignment_round_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    kind = AssignmentSessionKind(query.data.rsplit(":", 1)[-1])
    try:
        question = _start_assignment_round_use_case(context).execute(user_id=user.id, kind=kind)
    except ValueError:
        await query.edit_message_text(
            _tg("start_assignment_empty", context=context, user=user),
            reply_markup=_start_submenu_keyboard(language=_telegram_ui_language(context, user)),
        )
        return
    context.user_data["awaiting_text_answer"] = _expects_text_answer_for_question(question)
    await query.edit_message_text(
        _tg(
            "assignment_round_started",
            context=context,
            user=user,
            label=_assignment_kind_label(kind, context=context, user=user),
        )
    )
    await _send_question(update, context, question)


async def start_assignment_unavailable_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await query.edit_message_text(
        _tg("start_assignment_empty", context=context, user=user),
        reply_markup=_start_submenu_keyboard(language=_telegram_ui_language(context, user)),
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
    context.user_data["awaiting_text_answer"] = _expects_text_answer_for_question(question)
    await query.edit_message_text(_tg("session_started", context=context, user=user))
    await _send_question(update, context, question)


async def game_mode_placeholder_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await query.edit_message_text(
        _tg("game_mode_coming_soon", context=context, user=user),
        reply_markup=_start_submenu_keyboard(language=_telegram_ui_language(context, user)),
    )


async def game_next_round_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    game_state = context.user_data.get(_GAME_STATE_KEY, {})
    user = update.effective_user
    if user is None:
        return
    topic_id = game_state.get("topic_id")
    lesson_id = game_state.get("lesson_id")
    mode_value = game_state.get("mode_value")
    if not topic_id or not mode_value:
        await query.edit_message_text(_tg("no_active_session_send_start", context=context, user=user))
        return
    try:
        question = _service(context).start_session(
            user_id=user.id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=TrainingMode(str(mode_value)),
            adaptive_per_word=True,
        )
    except (ApplicationError, ValueError) as error:
        await query.edit_message_text(str(error))
        return
    streak_days = _content_store(context).update_game_streak(user_id=user.id, played_at=datetime.now(UTC))
    context.user_data[_GAME_STATE_KEY] = {
        "active": True,
        "topic_id": topic_id,
        "lesson_id": lesson_id,
        "mode_value": mode_value,
        "session_stars": 0,
        "correct_answers": 0,
        "streak_days": streak_days,
    }
    context.user_data["awaiting_text_answer"] = _expects_text_answer_for_question(question)
    await query.edit_message_text(
        _tg("game_round_started", context=context, user=user, streak_days=streak_days)
    )
    await _send_question(update, context, question)


async def game_repeat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    context.user_data.pop(_GAME_STATE_KEY, None)
    _clear_medium_task_state(context)
    await query.edit_message_text(_tg("start_menu_title", context=context, user=user))
    await send_telegram_view(
        query.message,
        _start_menu_view(context=context, user=user),
    )


async def medium_answer_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    state = _get_medium_task_state(context)
    message = getattr(query, "message", None)
    message_id = getattr(message, "message_id", None)
    if (
        state is None
        or state.message_id is None
        or message_id != state.message_id
        or _service(context).get_active_session(user_id=user.id) is None
    ):
        return
    current_question = _service(context).get_current_question(user_id=user.id)
    if (
        current_question.mode is not TrainingMode.MEDIUM
        or current_question.session_id != state.session_id
        or current_question.item_id != state.item_id
    ):
        _clear_medium_task_state(context)
        return
    if query.data == "medium:backspace":
        if not state.selected_letter_indexes:
            return
        state = _MediumTaskState(
            session_id=state.session_id,
            item_id=state.item_id,
            target_word=state.target_word,
            shuffled_letters=state.shuffled_letters,
            selected_letter_indexes=state.selected_letter_indexes[:-1],
            message_id=state.message_id,
        )
    elif query.data.startswith("medium:noop:"):
        return
    elif query.data.startswith("medium:pick:"):
        if _medium_task_is_complete(state):
            return
        try:
            picked_index = int(query.data.rsplit(":", 1)[-1])
        except ValueError:
            return
        if picked_index < 0 or picked_index >= len(state.shuffled_letters):
            return
        if picked_index in state.selected_letter_indexes:
            return
        state = _MediumTaskState(
            session_id=state.session_id,
            item_id=state.item_id,
            target_word=state.target_word,
            shuffled_letters=state.shuffled_letters,
            selected_letter_indexes=(*state.selected_letter_indexes, picked_index),
            message_id=state.message_id,
        )
    else:
        return
    _set_medium_task_state(context, state)
    if _medium_task_is_complete(state):
        _clear_medium_task_state(context)
        await _process_answer(update, context, _medium_task_answer_text(state))
        return
    await _edit_training_question_view(
        query,
        view=_build_medium_question_view(current_question, state=state),
    )


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
        _clear_medium_task_state(context)
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
    _clear_medium_task_state(context)
    active_session_before_submit = service.get_active_session(user_id=user.id)
    feedback_update: _GoalFeedbackUpdate | None = None
    if context.application.bot_data.get("homework_progress_use_case") is not None:
        before_summary = _homework_progress_use_case(context).get_summary(user_id=user.id)
    else:
        before_summary = None
    try:
        outcome = service.submit_answer(user_id=user.id, answer=answer)
    except InvalidSessionStateError:
        context.user_data["awaiting_text_answer"] = False
        _clear_medium_task_state(context)
        await message.reply_text(_tg("no_active_session_begin", context=context, user=user))
        return
    except ApplicationError as error:
        await message.reply_text(str(error))
        return
    if _assignment_kind_from_session(active_session_before_submit) is not None:
        _record_assignment_activity(context, user_id=user.id)
    active_session_id = getattr(active_session_before_submit, "session_id", None)
    if isinstance(active_session_id, str):
        await _delete_tracked_flow_messages(
            context,
            flow_id=active_session_id,
            tag=_TRAINING_QUESTION_TAG,
        )
    game_state = context.user_data.get(_GAME_STATE_KEY)
    if isinstance(game_state, dict) and game_state.get("active"):
        await _send_game_feedback(message, outcome, context)
        if outcome.next_question is not None:
            context.user_data["awaiting_text_answer"] = _expects_text_answer_for_question(
                outcome.next_question
            )
            await _send_question(update, context, outcome.next_question)
        else:
            context.user_data["awaiting_text_answer"] = False
            _clear_medium_task_state(context)
            await _finish_game_session(message, outcome, context)
        return
    context.user_data["awaiting_text_answer"] = bool(
        outcome.next_question is not None
        and _expects_text_answer_for_question(outcome.next_question)
    )
    if before_summary is not None:
        feedback_update = _collect_goal_feedback_update(
            context=context,
            user=user,
            before_summary=before_summary,
        )
    await _send_feedback(
        message,
        outcome,
        context=context,
        active_session=active_session_before_submit,
        feedback_update=feedback_update,
    )
    if feedback_update is not None and feedback_update.completed_goals:
        _schedule_goal_completed_notifications(
            context,
            learner=user,
            completed_goals=feedback_update.completed_goals,
        )
    if outcome.next_question is not None:
        await _send_question(update, context, outcome.next_question)
    else:
        await _flush_pending_notifications_for_user(context, user_id=user.id)


async def _send_feedback(
    message,
    outcome: AnswerOutcome,
    *,
    context: ContextTypes.DEFAULT_TYPE,
    active_session=None,
    feedback_update: _GoalFeedbackUpdate | None = None,
) -> None:
    feedback_user = getattr(message, "from_user", None)
    feedback_user_id = getattr(feedback_user, "id", None)
    if feedback_user_id is None:
        feedback_user_id = getattr(active_session, "user_id", None)
    view = build_answer_feedback_view(
        outcome,
        translate=_tg,
        user=feedback_user,
    )
    reply_markup = None
    assignment_progress_text = ""
    assignment_kind = _assignment_kind_from_session(active_session) if active_session is not None else None
    round_progress = None
    if assignment_kind is not None and feedback_user_id is not None:
        round_progress = _assignment_round_progress_view(
            context=context,
            user_id=feedback_user_id,
            kind=assignment_kind,
        )
        if round_progress is not None:
            assignment_progress_text = _render_assignment_round_progress_text(
                context=context,
                user=feedback_user,
                kind=assignment_kind,
                progress=round_progress,
            )
    if outcome.summary is not None and assignment_kind is not None and feedback_user_id is not None:
        has_more = bool(round_progress is not None and round_progress.remaining_word_count > 0)
        reply_markup = _assignment_round_complete_keyboard(
            assignment_kind,
            has_more=has_more,
            remaining_word_count=(
                round_progress.remaining_word_count
                if round_progress is not None and round_progress.remaining_word_count > 0
                else None
            ),
            language=_telegram_ui_language(context, feedback_user),
        )
    text = view.text
    if feedback_update is not None:
        update_text = _render_feedback_update_text(
            context=context,
            user=feedback_user,
            update=feedback_update,
        )
        if update_text:
            text = f"{text}\n\n{update_text}"
    if assignment_progress_text:
        text = f"{text}\n\n{assignment_progress_text}"
    flow_id = getattr(active_session, "session_id", None)
    if isinstance(flow_id, str):
        await _delete_tracked_flow_messages(
            context,
            flow_id=flow_id,
            tag=_TRAINING_FEEDBACK_TAG,
        )
    sent_message = await message.reply_text(text, reply_markup=reply_markup, parse_mode=view.parse_mode)
    if isinstance(flow_id, str):
        _track_flow_message(
            context,
            flow_id=flow_id,
            tag=_TRAINING_FEEDBACK_TAG,
            message=sent_message,
            fallback_chat_id=_message_chat_id(message),
        )


async def _send_game_feedback(
    message,
    outcome: AnswerOutcome,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    game_state = context.user_data.get(_GAME_STATE_KEY, {})
    if not isinstance(game_state, dict):
        return
    session_stars = int(game_state.get("session_stars", 0))
    correct_answers = int(game_state.get("correct_answers", 0))
    if outcome.result.is_correct:
        session_stars += _GAME_STAR_REWARD_CORRECT
        correct_answers += 1
        feedback = _tg("game_correct", context=context, user=getattr(message, "from_user", None))
    else:
        feedback = _tg("game_almost", context=context, user=getattr(message, "from_user", None))
    game_state["session_stars"] = session_stars
    game_state["correct_answers"] = correct_answers
    if outcome.summary is not None:
        progress = outcome.summary.total_questions
    else:
        active_session = _service(context).get_active_session(user_id=message.from_user.id)
        progress = 1 if active_session is None else max(1, active_session.current_position - 1)
    text = _tg(
        "game_feedback",
        context=context,
        user=getattr(message, "from_user", None),
        feedback=feedback,
        progress=progress,
        total=5,
        stars=session_stars,
    )
    await message.reply_text(text)


async def _finish_game_session(
    message,
    outcome: AnswerOutcome,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    user = getattr(message, "from_user", None)
    if user is None:
        return
    game_state = context.user_data.get(_GAME_STATE_KEY, {})
    if not isinstance(game_state, dict):
        return
    session_stars = int(game_state.get("session_stars", 0))
    chest_stars = random.choice(_GAME_CHEST_REWARDS)
    total_earned = session_stars + chest_stars
    total_stars = _content_store(context).add_game_stars(user_id=user.id, stars=total_earned)
    streak_days = _content_store(context).update_game_streak(user_id=user.id, played_at=datetime.now(UTC))
    await message.reply_text(
        _tg(
            "game_session_complete",
            context=context,
            user=user,
            session_stars=session_stars,
            chest_stars=chest_stars,
            total_earned=total_earned,
            total_stars=total_stars,
            streak_days=streak_days,
        ),
        reply_markup=_game_result_keyboard(language=_telegram_ui_language(context, user)),
    )
    context.user_data[_GAME_STATE_KEY] = {
        "active": False,
        "topic_id": game_state.get("topic_id"),
        "lesson_id": game_state.get("lesson_id"),
        "mode_value": game_state.get("mode_value"),
    }
    await _flush_pending_notifications_for_user(context, user_id=user.id)


def _expects_text_answer_for_question(question: TrainingQuestion) -> bool:
    return question.mode is TrainingMode.HARD


def _clear_medium_task_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data.pop(_MEDIUM_TASK_STATE_KEY, None)


def _build_medium_task_state(
    question: TrainingQuestion,
    *,
    message_id: int | None = None,
) -> _MediumTaskState:
    letter_source = question.letter_hint or question.correct_answer
    shuffled_letters = tuple(character for character in letter_source if not character.isspace())
    return _MediumTaskState(
        session_id=question.session_id,
        item_id=question.item_id,
        target_word=question.correct_answer,
        shuffled_letters=shuffled_letters,
        selected_letter_indexes=(),
        message_id=message_id,
    )


def _get_medium_task_state(context: ContextTypes.DEFAULT_TYPE) -> _MediumTaskState | None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return None
    state = user_data.get(_MEDIUM_TASK_STATE_KEY)
    if isinstance(state, _MediumTaskState):
        return state
    return None


def _set_medium_task_state(context: ContextTypes.DEFAULT_TYPE, state: _MediumTaskState) -> None:
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        user_data[_MEDIUM_TASK_STATE_KEY] = state


def _medium_task_slot_count(state: _MediumTaskState) -> int:
    return sum(1 for character in state.target_word if not character.isspace())


def _medium_task_is_complete(state: _MediumTaskState) -> bool:
    return len(state.selected_letter_indexes) >= _medium_task_slot_count(state)


def _medium_task_selected_letters(state: _MediumTaskState) -> list[str]:
    return [state.shuffled_letters[index] for index in state.selected_letter_indexes]


def _medium_task_slots_text(state: _MediumTaskState) -> str:
    selected_letters = _medium_task_selected_letters(state)
    selected_index = 0
    current_word_slots: list[str] = []
    rendered_words: list[str] = []
    for character in state.target_word:
        if character.isspace():
            if current_word_slots:
                rendered_words.append(" ".join(current_word_slots))
                current_word_slots = []
            continue
        slot_value = "_"
        if selected_index < len(selected_letters):
            slot_value = selected_letters[selected_index]
        current_word_slots.append(slot_value)
        selected_index += 1
    if current_word_slots:
        rendered_words.append(" ".join(current_word_slots))
    return "   ".join(rendered_words) or "_"


def _medium_task_answer_text(state: _MediumTaskState) -> str:
    selected_letters = iter(_medium_task_selected_letters(state))
    assembled: list[str] = []
    for character in state.target_word:
        if character.isspace():
            assembled.append(character)
            continue
        assembled.append(next(selected_letters, ""))
    return "".join(assembled)


def _medium_task_keyboard(state: _MediumTaskState) -> InlineKeyboardMarkup:
    selected_indexes = set(state.selected_letter_indexes)
    buttons = [
        InlineKeyboardButton(
            "".join(f"{character}\u0336" for character in letter)
            if index in selected_indexes
            else letter,
            callback_data=(
                f"medium:noop:{index}"
                if index in selected_indexes
                else f"medium:pick:{index}"
            ),
        )
        for index, letter in enumerate(state.shuffled_letters)
    ]
    rows: list[list[InlineKeyboardButton]] = []
    row_width = 4
    for start in range(0, len(buttons), row_width):
        rows.append(buttons[start : start + row_width])
    rows.append([InlineKeyboardButton("⌫", callback_data="medium:backspace")])
    return InlineKeyboardMarkup(rows)


def _extract_training_translation(prompt: str) -> str:
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped.startswith("Translation:"):
            return stripped.removeprefix("Translation:").strip()
    return prompt.strip()


def _build_medium_question_text(question: TrainingQuestion, state: _MediumTaskState) -> str:
    translation = html.escape(_extract_training_translation(question.prompt))
    slots = html.escape(_medium_task_slots_text(state))
    return f"🧩 <b>{translation}</b>\n\n<b>{slots}</b>"


def _build_medium_question_view(
    question: TrainingQuestion,
    *,
    state: _MediumTaskState,
) -> TelegramTextView | TelegramPhotoView:
    image_path = resolve_existing_image_path(question.image_ref)
    return build_training_question_view(
        question,
        image_path=image_path,
        reply_markup=_medium_task_keyboard(state),
        body_text_override=_build_medium_question_text(question, state),
    )


async def _edit_training_question_view(
    query,
    *,
    view: TelegramTextView | TelegramPhotoView,
) -> None:
    try:
        if isinstance(view, TelegramPhotoView):
            kwargs = {
                "caption": view.caption,
                "reply_markup": view.reply_markup,
            }
            if view.parse_mode is not None:
                kwargs["parse_mode"] = view.parse_mode
            await query.message.edit_caption(**kwargs)
            return
        await query.edit_message_text(
            view.text,
            reply_markup=view.reply_markup,
            parse_mode=view.parse_mode,
        )
    except BadRequest as error:
        if "Message is not modified" not in str(error):
            raise


async def _send_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    question: TrainingQuestion,
) -> None:
    message = update.effective_message
    if message is None:
        return
    await _delete_tracked_flow_messages(
        context,
        flow_id=question.session_id,
        tag=_TRAINING_QUESTION_TAG,
    )
    _clear_medium_task_state(context)
    view: TelegramTextView | TelegramPhotoView
    reply_markup = None
    if question.mode is TrainingMode.MEDIUM:
        view = _build_medium_question_view(
            question,
            state=_build_medium_task_state(question),
        )
    elif question.options:
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
    else:
        image_path = resolve_existing_image_path(question.image_ref)
        view = build_training_question_view(
            question,
            image_path=image_path,
            reply_markup=reply_markup,
        )
    sent_message = await send_telegram_view(message, view)
    if question.mode is TrainingMode.MEDIUM:
        _set_medium_task_state(
            context,
            _build_medium_task_state(question, message_id=getattr(sent_message, "message_id", None)),
        )
    _track_flow_message(
        context,
        flow_id=question.session_id,
        tag=_TRAINING_QUESTION_TAG,
        message=sent_message,
        fallback_chat_id=_message_chat_id(message),
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram update error. Update=%r", update, exc_info=context.error)


async def _post_init(app: Application) -> None:
    policy = TelegramMenuAccessPolicy.from_bot_data(app.bot_data)
    public_commands = [
        BotCommand(spec.command, spec.description)
        for spec in policy.visible_commands(user_id=None)
    ]
    await app.bot.set_my_commands(public_commands)

    elevated_user_ids: set[int] = set()
    for role_name, user_ids in policy.role_memberships.items():
        if role_name == "user":
            continue
        role_permissions = policy.role_permissions.get(role_name, frozenset())
        if "*" in role_permissions or PERMISSION_WORDS_ADD in role_permissions:
            elevated_user_ids.update(user_ids)
    for user_id in sorted(elevated_user_ids):
        scoped_commands = [
            BotCommand(spec.command, spec.description)
            for spec in policy.visible_commands(user_id=user_id)
        ]
        await app.bot.set_my_commands(scoped_commands, scope=BotCommandScopeChat(chat_id=user_id))
    notification_repository = app.bot_data.get("pending_telegram_notification_repository")
    job_queue = getattr(app, "job_queue", None)
    if notification_repository is not None and job_queue is not None:
        now = datetime.now(UTC)
        for notification in notification_repository.list():
            delay_seconds = max(0.0, (notification.not_before_at - now).total_seconds())
            job_queue.run_once(
                _deliver_pending_notification_job,
                when=delay_seconds,
                data={"notification_key": notification.key},
                name=notification.key,
            )
        job_queue.run_daily(
            _daily_assignment_reminder_job,
            time=_DAILY_ASSIGNMENT_REMINDER_TIME,
            name="daily-assignment-reminder",
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


def _assignment_assigned_notification_emoji(*, goal_id: str) -> str:
    emojis = ("🎒", "✨", "🚀", "🌟", "📚", "🧠")
    digest = hashlib.sha256(goal_id.encode("utf-8")).digest()
    return emojis[int.from_bytes(digest[:2], "big") % len(emojis)]


def _pending_notifications(context: ContextTypes.DEFAULT_TYPE) -> dict[str, _PendingNotification]:
    stored = context.application.bot_data.setdefault("pending_notifications", {})
    if isinstance(stored, dict):
        return stored
    replacement: dict[str, _PendingNotification] = {}
    context.application.bot_data["pending_notifications"] = replacement
    return replacement


def _pending_notification_repository(context: ContextTypes.DEFAULT_TYPE):
    application = getattr(context, "application", None)
    bot_data = getattr(application, "bot_data", None)
    if not isinstance(bot_data, dict):
        return None
    return bot_data.get("pending_telegram_notification_repository")


def _recent_assignment_activity_by_user(context: ContextTypes.DEFAULT_TYPE) -> dict[int, datetime]:
    stored = context.application.bot_data.get("recent_assignment_activity_by_user")
    if stored is None:
        stored = context.application.bot_data.get("recent_quiz_activity_by_user")
    if stored is None:
        stored = context.application.bot_data.setdefault("recent_assignment_activity_by_user", {})
    if isinstance(stored, dict):
        context.application.bot_data["recent_assignment_activity_by_user"] = stored
        return stored
    replacement: dict[int, datetime] = {}
    context.application.bot_data["recent_assignment_activity_by_user"] = replacement
    return replacement


def _notification_action_button(notification_key: str) -> InlineKeyboardButton:
    if notification_key.startswith("assignment-completed:"):
        return InlineKeyboardButton("Open users progress", callback_data="assign:users")
    if notification_key.startswith("assignment-assigned:homework:"):
        return InlineKeyboardButton("Start homework", callback_data="start:launch:homework")
    return InlineKeyboardButton("Open assignments", callback_data="assign:menu")


def _notification_action_button_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification_key: str,
    user_id: int,
) -> InlineKeyboardButton:
    language = _telegram_ui_language_for_user_id(context, user_id=user_id)
    if notification_key.startswith("assignment-completed:"):
        return InlineKeyboardButton(
            _tg("notification_open_users_progress", language=language),
            callback_data="assign:users",
        )
    if notification_key.startswith("assignment-assigned:homework:"):
        return InlineKeyboardButton(
            _tg("notification_start_homework", language=language),
            callback_data="start:launch:homework",
        )
    return InlineKeyboardButton(
        _tg("notification_open_assignments", language=language),
        callback_data="assign:menu",
    )


def _dismiss_notification_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification_key: str,
    user_id: int,
) -> InlineKeyboardMarkup:
    language = _telegram_ui_language_for_user_id(context, user_id=user_id)
    return InlineKeyboardMarkup(
        [[
            _notification_action_button_for_user(
                context,
                notification_key=notification_key,
                user_id=user_id,
            ),
            InlineKeyboardButton(
                _tg("notification_dismiss", language=language),
                callback_data=_NOTIFICATION_DISMISS_CALLBACK,
            ),
        ]]
    )


def _notification_wait_seconds(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> float:
    recent_activity_at = _recent_assignment_activity_by_user(context).get(user_id)
    if recent_activity_at is None:
        return 0.0
    now = datetime.now(UTC)
    elapsed = now - recent_activity_at
    active_session = _service(context).get_active_session(user_id=user_id)
    if active_session is not None and elapsed < _NOTIFICATION_ACTIVE_SESSION_ACTIVITY_WINDOW:
        remaining = _NOTIFICATION_ACTIVE_SESSION_ACTIVITY_WINDOW - elapsed
        return max(0.0, remaining.total_seconds())
    if elapsed < _NOTIFICATION_RECENT_ANSWER_GRACE_PERIOD:
        remaining = _NOTIFICATION_DELAY_AFTER_RECENT_ANSWER - elapsed
        return max(0.0, remaining.total_seconds())
    return 0.0


def _notification_should_wait(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> bool:
    return _notification_wait_seconds(context, user_id=user_id) > 0.0


def _record_assignment_activity(context: ContextTypes.DEFAULT_TYPE, *, user_id: int) -> None:
    _recent_assignment_activity_by_user(context)[user_id] = datetime.now(UTC)


def _schedule_notification(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification: _PendingNotification,
) -> None:
    delay_seconds = _notification_wait_seconds(context, user_id=notification.recipient_user_id)
    not_before_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
    repository = _pending_notification_repository(context)
    if repository is not None:
        repository.save(
            notification_key=notification.key,
            recipient_user_id=notification.recipient_user_id,
            text=notification.text,
            not_before_at=not_before_at,
        )
    else:
        pending = _pending_notifications(context)
        pending[notification.key] = _PendingNotification(
            key=notification.key,
            recipient_user_id=notification.recipient_user_id,
            text=notification.text,
            not_before_at=not_before_at,
            created_at=datetime.now(UTC),
        )
    job_queue = getattr(context.application, "job_queue", None)
    if job_queue is None:
        return
    job_queue.run_once(
        _deliver_pending_notification_job,
        when=delay_seconds,
        data={"notification_key": notification.key},
        name=notification.key,
    )


async def _deliver_notification_now(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification_key: str,
    force: bool = False,
) -> bool:
    repository = _pending_notification_repository(context)
    notification = (
        repository.get(notification_key=notification_key)
        if repository is not None
        else _pending_notifications(context).get(notification_key)
    )
    if notification is None:
        return False
    if not force and _notification_should_wait(context, user_id=notification.recipient_user_id):
        return False
    try:
        await context.bot.send_message(
            chat_id=notification.recipient_user_id,
            text=notification.text,
            reply_markup=_dismiss_notification_keyboard(
                context,
                notification_key=notification.key,
                user_id=notification.recipient_user_id,
            ),
        )
    except BadRequest:
        logger.debug("Failed to deliver notification key=%s", notification.key, exc_info=True)
    finally:
        if repository is not None:
            repository.remove(notification_key=notification_key)
        else:
            _pending_notifications(context).pop(notification_key, None)
    return True


async def _deliver_pending_notification_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = getattr(context, "job", None)
    data = getattr(job, "data", None)
    notification_key = data.get("notification_key") if isinstance(data, dict) else None
    if not isinstance(notification_key, str):
        return
    delivered = await _deliver_notification_now(context, notification_key=notification_key)
    if delivered:
        return
    repository = _pending_notification_repository(context)
    if repository is not None:
        if repository.get(notification_key=notification_key) is None:
            return
    elif notification_key not in _pending_notifications(context):
        return
    job_queue = getattr(context.application, "job_queue", None)
    if job_queue is None:
        return
    job_queue.run_once(
        _deliver_pending_notification_job,
        when=_notification_wait_seconds(
            context,
            user_id=(
                repository.get(notification_key=notification_key).recipient_user_id
                if repository is not None
                else _pending_notifications(context)[notification_key].recipient_user_id
            ),
        ),
        data={"notification_key": notification_key},
        name=notification_key,
    )


async def _daily_assignment_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = _content_store(context).list_users_goal_overview()
    today = datetime.now(UTC).date().isoformat()
    for row in rows:
        user_id = int(row["user_id"])
        active_goals_count = int(row["active_goals_count"])
        if active_goals_count <= 0:
            continue
        _schedule_notification(
            context,
            notification=_PendingNotification(
                key=f"assignment-reminder:{today}:{user_id}",
                recipient_user_id=user_id,
                text=_tg(
                    "daily_assignment_reminder"
                    if active_goals_count != 1
                    else "daily_assignment_reminder_one",
                    language=_telegram_ui_language_for_user_id(context, user_id=user_id),
                    goal_count=active_goals_count,
                ),
            ),
        )


async def _flush_pending_notifications_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> None:
    repository = _pending_notification_repository(context)
    pending_keys = (
        [item.key for item in repository.list(recipient_user_id=user_id)]
        if repository is not None
        else [
            key
            for key, notification in _pending_notifications(context).items()
            if notification.recipient_user_id == user_id
        ]
    )
    for notification_key in pending_keys:
        await _deliver_notification_now(context, notification_key=notification_key, force=True)


def _schedule_assignment_assigned_notifications(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    goals: list,
) -> None:
    for goal in goals:
        language = _telegram_ui_language_for_user_id(context, user_id=int(goal.user_id))
        period_key = {
            GoalPeriod.DAILY.value: "goal_period_daily",
            GoalPeriod.WEEKLY.value: "goal_period_weekly",
            GoalPeriod.HOMEWORK.value: "goal_period_homework",
        }.get(goal.goal_period.value)
        goal_type_key = {
            GoalType.NEW_WORDS.value: "goal_type_new_words",
            GoalType.WORD_LEVEL_HOMEWORK.value: "goal_type_word_level_homework",
        }.get(goal.goal_type.value)
        period_label = _tg(period_key, language=language) if period_key is not None else goal.goal_period.value
        goal_type_label = _tg(goal_type_key, language=language) if goal_type_key is not None else goal.goal_type.value
        emoji = _assignment_assigned_notification_emoji(goal_id=str(goal.id))
        text = "\n".join(
            [
                _tg("assignment_assigned_title", language=language, emoji=emoji),
                _tg(
                    (
                        "assignment_assigned_word_level_homework"
                        if goal.goal_type.value == GoalType.WORD_LEVEL_HOMEWORK.value
                        else "assignment_assigned_new_words"
                    ),
                    language=language,
                    period=period_label,
                    goal_type=goal_type_label,
                    target=int(goal.target_count),
                ),
            ]
        )
        notification = _PendingNotification(
            key=f"assignment-assigned:{goal.goal_period.value}:{goal.id}:{goal.user_id}",
            recipient_user_id=goal.user_id,
            text=text,
        )
        _schedule_notification(context, notification=notification)


def _schedule_goal_completed_notifications(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    learner,
    completed_goals: tuple[GoalProgressView, ...],
) -> None:
    role_repository = context.application.bot_data.get("telegram_user_role_repository")
    if role_repository is None:
        return
    memberships = role_repository.list_memberships()
    admin_ids = memberships.get("admin", frozenset())
    learner_name = getattr(learner, "username", None) or getattr(learner, "first_name", None) or str(learner.id)
    for admin_user_id in admin_ids:
        for goal in completed_goals:
            notification = _PendingNotification(
                key=f"assignment-completed:{goal.goal.id}:{admin_user_id}",
                recipient_user_id=admin_user_id,
                text=(
                    "Assignment completed: "
                    f"{learner_name} finished "
                    f"{goal.goal.goal_period.value}/{goal.goal.goal_type.value} "
                    f"{goal.goal.progress_count}/{goal.goal.target_count}."
                ),
            )
            _schedule_notification(context, notification=notification)


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


async def _delete_tracked_flow_messages(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    tag: str,
) -> None:
    registry = _telegram_flow_messages(context)
    if registry is None:
        return
    await _delete_tracked_messages(
        context,
        tracked_messages=registry.list(flow_id=flow_id, tag=tag),
    )


async def _ensure_chat_menu_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
    user,
) -> None:
    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        return
    flow_id = _chat_menu_flow_id(user_id=user_id)
    await _delete_tracked_flow_messages(
        context,
        flow_id=flow_id,
        tag=_CHAT_MENU_TAG,
    )
    sent_message = await send_telegram_view(
        message,
        _quick_actions_view(context=context, user=user),
    )
    if sent_message is None:
        return
    _track_flow_message(
        context,
        flow_id=flow_id,
        tag=_CHAT_MENU_TAG,
        message=sent_message,
        fallback_chat_id=_message_chat_id(message),
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
    *,
    user=None,
) -> None:
    resolved_user = user or getattr(message, "from_user", None)
    current_item = flow.current_item
    if current_item is None:
        await message.reply_text(
            _tg(
                "image_review_completed",
                context=context,
                user=resolved_user,
            )
        )
        return
    total_items = len(flow.items)
    current_position = flow.current_index + 1
    status_message = await message.reply_text(
        _tg(
            "local_candidates_generating",
            context=context,
            user=resolved_user,
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
                context=context,
                user=resolved_user,
                current=current_position,
                total=total_items,
            )
        ).text
    )
    await _send_image_review_step(
        message,
        context,
        prepared_flow,
        user=resolved_user,
    )


async def _send_current_published_image_preview(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    flow,
    *,
    user=None,
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
    resolved_user = user or getattr(message, "from_user", None)
    image_path = resolve_existing_image_path(image_ref)
    preview_view = build_current_image_preview_view(
        image_path=image_path,
        current_image_intro=_tg(
            "current_image_intro",
            context=context,
            user=resolved_user,
        ),
        no_current_image_intro=_tg(
            "no_current_image_intro",
            context=context,
            user=resolved_user,
        ),
    )
    preview_message = await send_telegram_view(message, preview_view)
    _track_flow_message(
        context,
        flow_id=flow.flow_id,
        tag=_IMAGE_REVIEW_CONTEXT_TAG,
        message=preview_message,
        fallback_chat_id=fallback_chat_id,
    )


async def _send_image_review_step(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    flow,
    *,
    user=None,
) -> None:
    resolved_user = user or getattr(message, "from_user", None)
    current_item = flow.current_item
    if current_item is None:
        await message.reply_text(
            _tg(
                "image_review_completed",
                context=context,
                user=resolved_user,
            )
        )
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
            user=resolved_user,
        ),
        translate=_tg,
        user=resolved_user,
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
    return ui_draft_review_keyboard(
        flow_id,
        is_valid,
        tg=_tg,
        show_auto_image_button=show_auto_image_button,
        show_regenerate_button=show_regenerate_button,
        language=language,
    )


def _image_review_keyboard(
    *,
    flow_id: str,
    current_item,
    show_generate_image_button: bool = True,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_image_review_keyboard(
        tg=_tg,
        flow_id=flow_id,
        current_item=current_item,
        show_generate_image_button=show_generate_image_button,
        language=language,
    )


def _words_menu_keyboard(
    *,
    can_add_words: bool,
    can_edit_words: bool,
    can_edit_images: bool,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_words_menu_keyboard(
        tg=_tg,
        can_add_words=can_add_words,
        can_edit_words=can_edit_words,
        can_edit_images=can_edit_images,
        language=language,
    )


def _start_menu_keyboard(
    *,
    summary: list[AssignmentLaunchView],
    guide_web_app_url: str | None = None,
    admin_web_app_url: str | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_start_menu_keyboard(
        tg=_tg,
        summary=summary,
        guide_web_app_url=guide_web_app_url,
        admin_web_app_url=admin_web_app_url,
        language=language,
    )


def _start_submenu_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(_tg("back", language=language), callback_data="start:menu")]]
    )


def _assignment_round_complete_keyboard(
    kind: AssignmentSessionKind,
    *,
    has_more: bool,
    remaining_word_count: int | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_assignment_round_complete_keyboard(
        kind,
        tg=_tg,
        has_more=has_more,
        remaining_word_count=remaining_word_count,
        language=language,
    )


def _assign_menu_keyboard(
    *,
    is_admin: bool,
    guide_web_app_url: str | None = None,
    admin_web_app_url: str | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_assign_menu_keyboard(
        tg=_tg,
        is_admin=is_admin,
        guide_web_app_url=guide_web_app_url,
        admin_web_app_url=admin_web_app_url,
        language=language,
    )


def _published_images_menu_keyboard(
    *,
    topic_id: str,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_published_images_menu_keyboard(
        tg=_tg,
        topic_id=topic_id,
        language=language,
    )


def _published_image_topics_keyboard(
    topics,
    *,
    topic_item_counts: dict[str, int] | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_published_image_topics_keyboard(
        topics,
        tg=_tg,
        topic_item_counts=topic_item_counts,
        language=language,
    )


def _published_image_items_keyboard(
    *,
    topic_id: str,
    raw_items: list[object],
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_published_image_items_keyboard(
        tg=_tg,
        topic_id=topic_id,
        raw_items=raw_items,
        language=language,
    )


def _editable_topics_keyboard(
    topics,
    *,
    topic_item_counts: dict[str, int] | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_editable_topics_keyboard(
        topics,
        tg=_tg,
        topic_item_counts=topic_item_counts,
        language=language,
    )


def _editable_words_keyboard(
    *,
    topic_id: str,
    words,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_editable_words_keyboard(
        tg=_tg,
        topic_id=topic_id,
        words=words,
        language=language,
    )


def _published_word_edit_keyboard(
    *,
    topic_id: str,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_published_word_edit_keyboard(
        tg=_tg,
        topic_id=topic_id,
        language=language,
    )


def _editable_word_button_label(
    *,
    english_word: str,
    translation: str,
    has_image: bool,
) -> str:
    return ui_editable_word_button_label(
        english_word=english_word,
        translation=translation,
        has_image=has_image,
    )


def _chat_menu_keyboard(*, command_rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ui_chat_menu_keyboard(command_rows=command_rows)


def _topic_keyboard(
    topics: list[Topic],
    *,
    topic_item_counts: dict[str, int] | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_topic_keyboard(
        topics,
        topic_item_counts=topic_item_counts,
        language=language,
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
    return ui_topic_button_label(title=title, item_count=item_count)


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
    return ui_lesson_keyboard(
        topic_id,
        lessons,
        tg=_tg,
        language=language,
    )


def _mode_keyboard(
    topic_id: str,
    lesson_id: str | None,
    *,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_mode_keyboard(
        topic_id,
        lesson_id,
        tg=_tg,
        language=language,
    )


def _game_mode_keyboard(
    topic_id: str,
    lesson_id: str | None,
    *,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_game_mode_keyboard(
        topic_id,
        lesson_id,
        tg=_tg,
        language=language,
    )


def _game_result_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_tg("next_round", language=language), callback_data="game:next_round")],
            [InlineKeyboardButton(_tg("repeat", language=language), callback_data="game:repeat")],
            [InlineKeyboardButton(_tg("menu", language=language), callback_data="session:restart")],
        ]
    )
