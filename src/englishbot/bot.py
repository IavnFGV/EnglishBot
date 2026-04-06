from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode

from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.error import BadRequest, NetworkError, RetryAfter
from telegram.ext import (
    Application,
    ContextTypes,
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
    GoalProgressView,
    GoalWordSource,
    HomeworkProgressUseCase,
    LearnerProgressSummary,
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
    TrainingFacade,
)
from englishbot.bootstrap import build_training_service
from englishbot.bot_assignments_admin_ui import admin_goal_manual_keyboard as ui_admin_goal_manual_keyboard
from englishbot.bot_assignments_admin_ui import admin_goal_recipients_keyboard as ui_admin_goal_recipients_keyboard
from englishbot.bot_assignments_admin_ui import assignment_goal_detail_keyboard as ui_assignment_goal_detail_keyboard
from englishbot.bot_assignments_admin_ui import assignment_user_goals_keyboard as ui_assignment_user_goals_keyboard
from englishbot.bot_assignments_admin_ui import assignment_users_keyboard as ui_assignment_users_keyboard
from englishbot.bot_assignments_admin_ui import render_assignment_goal_detail_text as ui_render_assignment_goal_detail_text
from englishbot.bot_assignments_admin_ui import render_assignment_user_detail_text as ui_render_assignment_user_detail_text
from englishbot.bot_assignments_ui import admin_goal_custom_target_keyboard as ui_admin_goal_custom_target_keyboard
from englishbot.bot_assignments_ui import admin_goal_deadline_keyboard as ui_admin_goal_deadline_keyboard
from englishbot.bot_assignments_ui import admin_goal_period_keyboard as ui_admin_goal_period_keyboard
from englishbot.bot_assignments_ui import admin_goal_source_keyboard as ui_admin_goal_source_keyboard
from englishbot.bot_assignments_ui import admin_goal_target_keyboard as ui_admin_goal_target_keyboard
from englishbot.bot_assignments_ui import assign_menu_keyboard as ui_assign_menu_keyboard
from englishbot.bot_assignments_ui import assignment_kind_label as ui_assignment_kind_label
from englishbot.bot_assignments_ui import assignment_round_complete_keyboard as ui_assignment_round_complete_keyboard
from englishbot.bot_assignments_ui import goal_list_keyboard as ui_goal_list_keyboard
from englishbot.bot_assignments_ui import goal_setup_keyboard as ui_goal_setup_keyboard
from englishbot.bot_assignments_ui import goal_source_keyboard as ui_goal_source_keyboard
from englishbot.bot_assignments_ui import goal_target_keyboard as ui_goal_target_keyboard
from englishbot.bot_assignments_ui import render_goal_progress_line as ui_render_goal_progress_line
from englishbot.bot_assignments_ui import render_progress_text as ui_render_progress_text
from englishbot.bot_assignments_ui import render_start_menu_text as ui_render_start_menu_text
from englishbot.bot_assignments_ui import start_menu_keyboard as ui_start_menu_keyboard
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
from englishbot.bot_editor_ui import topic_keyboard as ui_topic_keyboard
from englishbot.bot_editor_ui import topic_selection_view as ui_topic_selection_view
from englishbot.bot_editor_ui import words_menu_keyboard as ui_words_menu_keyboard
from englishbot.bot_editor_ui import words_menu_view as ui_words_menu_view
from englishbot.config import RuntimeConfigService, Settings
from englishbot.domain.models import GoalPeriod, GoalStatus, GoalType, Topic, TrainingMode, TrainingQuestion
from englishbot.image_generation.paths import resolve_existing_image_path
from englishbot.image_generation.paths import (
    build_item_audio_path as _build_item_audio_path_impl,
)
from englishbot.image_generation.paths import (
    build_item_audio_ref as _build_item_audio_ref_impl,
)
from englishbot.image_generation.paths import (
    resolve_existing_audio_path as _resolve_existing_audio_path_impl,
)
from englishbot.image_generation.previews import ensure_numbered_candidate_strip
from englishbot.infrastructure.sqlite_store import SQLiteContentStore
from englishbot.infrastructure.sqlite_store import (
    SQLiteTelegramUserLoginRepository,
    SQLiteTelegramUserRoleRepository,
)
from englishbot.presentation.telegram_views import (
    TelegramPhotoView,
    TelegramTextView,
    build_assignment_menu_view,
    build_answer_feedback_view,
    build_current_image_preview_view,
    build_image_review_step_view,
    build_start_menu_view,
    build_status_view,
    edit_telegram_text_view,
    send_telegram_view,
)
from englishbot.presentation.telegram_ui_text import (
    DEFAULT_TELEGRAM_UI_LANGUAGE,
    supported_telegram_ui_languages,
    telegram_ui_text,
)
from englishbot.telegram_buttons import InlineKeyboardButton
from englishbot.telegram_answer_handlers import (
    choice_answer_handler as telegram_choice_answer_handler,
    hard_skip_handler as telegram_hard_skip_handler,
    medium_answer_callback_handler as telegram_medium_answer_callback_handler,
    text_answer_handler as telegram_text_answer_handler,
)
from englishbot.telegram_answer_processing import (
    process_answer as delivery_process_answer,
    send_feedback as delivery_send_feedback,
)
from englishbot.telegram_question_delivery import (
    build_medium_question_view as delivery_build_medium_question_view,
    edit_training_question_view as delivery_edit_training_question_view,
    medium_task_answer_text as delivery_medium_task_answer_text,
    medium_task_is_complete as delivery_medium_task_is_complete,
    send_question as delivery_send_question,
)
from englishbot.telegram_command_menu import (
    chat_menu_keyboard as menu_chat_menu_keyboard,
    post_init_command_setup,
    visible_command_rows as menu_visible_command_rows,
    visible_command_specs as menu_visible_command_specs,
)
from englishbot.telegram_entry_handlers import (
    help_handler as telegram_help_handler,
    start_handler as telegram_start_handler,
    version_handler as telegram_version_handler,
)
from englishbot.telegram_learner_entry_handlers import (
    continue_session_handler as telegram_continue_session_handler,
    game_mode_placeholder_callback_handler as telegram_game_mode_placeholder_callback_handler,
    lesson_selected_handler as telegram_lesson_selected_handler,
    mode_selected_handler as telegram_mode_selected_handler,
    restart_session_handler as telegram_restart_session_handler,
    topic_selected_handler as telegram_topic_selected_handler,
)
from englishbot.telegram_navigation_handlers import (
    assign_menu_callback_handler as telegram_assign_menu_callback_handler,
    assign_menu_handler as telegram_assign_menu_handler,
    start_assignment_round_callback_handler as telegram_start_assignment_round_callback_handler,
    start_assignment_unavailable_callback_handler as telegram_start_assignment_unavailable_callback_handler,
    start_menu_callback_handler as telegram_start_menu_callback_handler,
    words_menu_callback_handler as telegram_words_menu_callback_handler,
    words_menu_handler as telegram_words_menu_handler,
    words_topics_callback_handler as telegram_words_topics_callback_handler,
)
from englishbot.presentation.telegram_menu_access import (
    PERMISSION_WORD_IMAGES_EDIT,
    PERMISSION_WORDS_ADD,
    PERMISSION_WORDS_EDIT,
    TelegramCommandSpec,
    TelegramMenuAccessPolicy,
)
from englishbot.runtime_version import RuntimeVersionInfo

logger = logging.getLogger(__name__)

_ADD_WORDS_AWAITING_TEXT = "awaiting_raw_text"
_ADD_WORDS_AWAITING_EDIT_TEXT = "awaiting_edit_text"
_IMAGE_REVIEW_AWAITING_PROMPT_TEXT = "awaiting_image_review_prompt_text"
_IMAGE_REVIEW_AWAITING_SEARCH_QUERY_TEXT = "awaiting_image_review_search_query_text"
_IMAGE_REVIEW_AWAITING_PHOTO = "awaiting_image_review_photo"
_PUBLISHED_WORD_AWAITING_EDIT_TEXT = "awaiting_published_word_edit_text"
_GOAL_AWAITING_TARGET_TEXT = "awaiting_goal_target_text"
_ADMIN_GOAL_AWAITING_TARGET_TEXT = "awaiting_admin_goal_target_text"
_ADMIN_GOAL_AWAITING_DEADLINE_TEXT = "awaiting_admin_goal_deadline_text"
_EXPECTED_USER_INPUT_STATE_KEY = "expected_user_input_state"
_IMAGE_REVIEW_STEP_TAG = "image_review_step"
_IMAGE_REVIEW_CONTEXT_TAG = "image_review_context"
_PUBLISHED_WORD_EDIT_TAG = "published_word_edit"
_TRAINING_QUESTION_TAG = "training_question"
_TRAINING_FEEDBACK_TAG = "training_feedback"
_TTS_VOICE_TAG = "tts_voice"
_ASSIGNMENT_PROGRESS_TAG = "assignment_progress"
_CHAT_MENU_TAG = "chat_menu"
_NOTIFICATION_DISMISS_CALLBACK = "notification:dismiss"
_TELEGRAM_UI_LANGUAGE_KEY = "telegram_ui_language"
_GAME_STATE_KEY = "game_mode_state"
_MEDIUM_TASK_STATE_KEY = "medium_task_state"
_MEDIUM_TASK_LOCK_KEY = "medium_task_lock"
_TTS_TASK_LOCK_KEY = "tts_task_lock"
_TTS_TASK_RECENT_KEY = "tts_task_recent"
_TTS_REPEAT_COOLDOWN_SEC = 2.5
_TTS_SELECTED_VOICE_KEY = "tts_selected_voice_by_item"
_TTS_VOICE_LABEL_KEYS = {
    "en_US-libritts-high": "tts_voice_label_en_US_libritts_high",
    "en_US-ryan-high": "tts_voice_label_en_US_ryan_high",
    "en_GB-cori-high": "tts_voice_label_en_GB_cori_high",
    "en_US-libritts_r-medium": "tts_voice_label_en_US_libritts_r_medium",
    "en_GB-alan-medium": "tts_voice_label_en_GB_alan_medium",
    "en_US-lessac-medium": "tts_voice_label_en_US_lessac_medium",
}
_GAME_STAR_REWARD_CORRECT = 10
_GAME_CHEST_REWARDS: tuple[int, ...] = (30, 50, 50, 100)
_NOTIFICATION_ACTIVE_SESSION_ACTIVITY_WINDOW = timedelta(minutes=5)
_NOTIFICATION_RECENT_ANSWER_GRACE_PERIOD = timedelta(minutes=1)
_NOTIFICATION_DELAY_AFTER_RECENT_ANSWER = timedelta(minutes=2)
_DAILY_ASSIGNMENT_REMINDER_TIME = time(hour=13, minute=0, tzinfo=UTC)
_CALLBACK_TOKEN_TTL_SECONDS = 48 * 60 * 60
_HARD_SKIP_CALLBACK_ACTION = "hard_skip"
_EDITABLE_WORD_CALLBACK_ACTION = "editable_word"
_PUBLISHED_IMAGE_ITEM_CALLBACK_ACTION = "published_image_item"
_HELP_COMMAND_TEXT: dict[str, str] = {
    "start": "open your personal start menu",
    "help": "show commands",
    "version": "show the current bot version",
    "words": "open the words menu",
    "assign": "open the homework menu",
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
            _optional_bot_data(context, "telegram_ui_language")
        )
        maybe_user_data = _user_data_or_none(context)
        if maybe_user_data is not None:
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
    return _required_bot_data(context, "runtime_version_info")


def _required_bot_data(context: ContextTypes.DEFAULT_TYPE, key: str):
    return context.application.bot_data[key]


def _optional_bot_data(
    context: ContextTypes.DEFAULT_TYPE | None,
    key: str,
    *,
    default=None,
):
    if context is None or getattr(context, "application", None) is None:
        return default
    bot_data = getattr(context.application, "bot_data", None)
    if not isinstance(bot_data, dict):
        return default
    return bot_data.get(key, default)


def _mutable_bot_data_dict(
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
    *,
    fallback_key: str | None = None,
):
    stored = _optional_bot_data(context, key)
    if stored is None and fallback_key is not None:
        stored = _optional_bot_data(context, fallback_key)
    if isinstance(stored, dict):
        context.application.bot_data[key] = stored
        return stored
    replacement: dict = {}
    context.application.bot_data[key] = replacement
    return replacement


def _set_bot_data(
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
    value,
):
    context.application.bot_data[key] = value
    return value


def _user_data_or_none(context: ContextTypes.DEFAULT_TYPE | None) -> dict | None:
    if context is None:
        return None
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        return user_data
    return None


def _optional_user_data(
    context: ContextTypes.DEFAULT_TYPE | None,
    key: str,
    *,
    default=None,
):
    user_data = _user_data_or_none(context)
    if user_data is None:
        return default
    return user_data.get(key, default)


def _set_user_data(
    context: ContextTypes.DEFAULT_TYPE | None,
    key: str,
    value,
) -> bool:
    user_data = _user_data_or_none(context)
    if user_data is None:
        return False
    user_data[key] = value
    return True


def _pop_user_data(
    context: ContextTypes.DEFAULT_TYPE | None,
    key: str,
    *,
    default=None,
):
    user_data = _user_data_or_none(context)
    if user_data is None:
        return default
    return user_data.pop(key, default)


def _game_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    current = _optional_user_data(context, _GAME_STATE_KEY, default={})
    if isinstance(current, dict):
        return current
    created: dict = {}
    _set_user_data(context, _GAME_STATE_KEY, created)
    return created


def _admin_goal_user_state(context: ContextTypes.DEFAULT_TYPE, key: str, *, default=None):
    return _optional_user_data(context, key, default=default)


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
    from englishbot.telegram.bootstrap import build_application as bootstrap_build_application

    return bootstrap_build_application(settings, config_service=config_service)


def _service(context: ContextTypes.DEFAULT_TYPE) -> TrainingFacade:
    return _required_bot_data(context, "training_service")


def _content_store(context: ContextTypes.DEFAULT_TYPE) -> SQLiteContentStore:
    return _required_bot_data(context, "content_store")


def _active_training_session(context: ContextTypes.DEFAULT_TYPE, *, user_id: int):
    store = _optional_bot_data(context, "content_store")
    if store is None or not hasattr(store, "get_active_session_by_user"):
        return None
    return store.get_active_session_by_user(user_id)


def _job_queue_or_none(application) -> object | None:
    if application is None:
        return None
    raw_job_queue = getattr(application, "_job_queue", None)
    if raw_job_queue is not None:
        return raw_job_queue
    return getattr(application, "job_queue", None)


def build_item_audio_path(*, assets_dir: Path, topic_id: str, item_id: str, voice_name: str | None = None):
    return _build_item_audio_path_impl(
        assets_dir=assets_dir,
        topic_id=topic_id,
        item_id=item_id,
        voice_name=voice_name,
    )


def build_item_audio_ref(*, assets_dir: Path, topic_id: str, item_id: str, voice_name: str | None = None):
    return _build_item_audio_ref_impl(
        assets_dir=assets_dir,
        topic_id=topic_id,
        item_id=item_id,
        voice_name=voice_name,
    )


def resolve_existing_audio_path(audio_ref: str):
    return _resolve_existing_audio_path_impl(audio_ref)


def _settings_or_none(context: ContextTypes.DEFAULT_TYPE):
    return _optional_bot_data(context, "settings")


def _tts_service_enabled(context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = _settings_or_none(context)
    return bool(settings is not None and getattr(settings, "tts_service_enabled", False))


def _tts_primary_voice_name(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    settings = _settings_or_none(context)
    if settings is None:
        return None
    raw_voice_name = getattr(settings, "tts_voice_name", None)
    if isinstance(raw_voice_name, str) and raw_voice_name.strip():
        return raw_voice_name.strip()
    return None


def _tts_voice_variants(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, ...]:
    primary_voice_name = _tts_primary_voice_name(context)
    settings = _settings_or_none(context)
    raw_variants = getattr(settings, "tts_voice_variants", ()) if settings is not None else ()
    if isinstance(raw_variants, str):
        raw_variants = (raw_variants,)
    ordered: list[str] = []
    for candidate in (primary_voice_name, *raw_variants):
        if not isinstance(candidate, str):
            continue
        normalized = candidate.strip()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return tuple(ordered)


def _tts_has_multiple_voices(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return len(_tts_voice_variants(context)) > 1


def _tts_voice_label(context: ContextTypes.DEFAULT_TYPE, *, user, voice_name: str) -> str:
    label_key = _TTS_VOICE_LABEL_KEYS.get(voice_name)
    if label_key is not None:
        return _tg(label_key, context=context, user=user)
    return voice_name


def _tts_client_or_none(context: ContextTypes.DEFAULT_TYPE) -> object | None:
    if not _tts_service_enabled(context):
        return None
    cached_client = _optional_bot_data(context, "tts_service_client")
    if cached_client is not None:
        return cached_client
    settings = _settings_or_none(context)
    if settings is None:
        return None
    from englishbot.tts_service import TtsServiceClient

    client = TtsServiceClient(
        base_url=getattr(settings, "tts_service_base_url"),
        timeout_sec=getattr(settings, "tts_service_timeout_sec", 15),
    )
    return _set_bot_data(context, "tts_service_client", client)


def _extract_sent_voice_file_id(sent_message) -> str | None:
    voice = getattr(sent_message, "voice", None)
    file_id = getattr(voice, "file_id", None)
    if isinstance(file_id, str) and file_id.strip():
        return file_id.strip()
    return None


def _telegram_user_login_repository(context: ContextTypes.DEFAULT_TYPE) -> SQLiteTelegramUserLoginRepository:
    return _required_bot_data(context, "telegram_user_login_repository")


def _telegram_user_role_repository(context: ContextTypes.DEFAULT_TYPE) -> SQLiteTelegramUserRoleRepository:
    return _required_bot_data(context, "telegram_user_role_repository")


def _telegram_ui_language_for_user_id(context: ContextTypes.DEFAULT_TYPE, *, user_id: int) -> str:
    login = next(
        (item for item in _telegram_user_login_repository(context).list() if item.user_id == user_id),
        None,
    )
    if login is not None and login.language_code is not None:
        return _normalize_telegram_ui_language(login.language_code)
    return _telegram_ui_language(context)


def _reload_training_service(context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_bot_data(
        context,
        "training_service",
        build_training_service(db_path=_content_store(context).db_path),
    )


def _start_add_words_flow(context: ContextTypes.DEFAULT_TYPE) -> StartAddWordsFlowUseCase:
    return _required_bot_data(context, "add_words_start_use_case")


def _get_active_add_words_flow(context: ContextTypes.DEFAULT_TYPE) -> GetActiveAddWordsFlowUseCase:
    return _required_bot_data(context, "add_words_get_active_use_case")


def _apply_add_words_edit(context: ContextTypes.DEFAULT_TYPE) -> ApplyAddWordsEditUseCase:
    return _required_bot_data(context, "add_words_apply_edit_use_case")


def _regenerate_add_words_draft(
    context: ContextTypes.DEFAULT_TYPE,
) -> RegenerateAddWordsDraftUseCase:
    return _required_bot_data(context, "add_words_regenerate_use_case")


def _approve_add_words_draft(context: ContextTypes.DEFAULT_TYPE) -> ApproveAddWordsDraftUseCase:
    return _required_bot_data(context, "add_words_approve_use_case")


def _save_approved_add_words_draft(
    context: ContextTypes.DEFAULT_TYPE,
) -> SaveApprovedAddWordsDraftUseCase:
    return _required_bot_data(context, "add_words_save_approved_draft_use_case")


def _generate_add_words_image_prompts(
    context: ContextTypes.DEFAULT_TYPE,
) -> GenerateAddWordsImagePromptsUseCase:
    return _required_bot_data(context, "add_words_generate_image_prompts_use_case")


def _mark_add_words_image_review_started(
    context: ContextTypes.DEFAULT_TYPE,
) -> MarkAddWordsImageReviewStartedUseCase:
    return _required_bot_data(context, "add_words_mark_image_review_started_use_case")


def _cancel_add_words_flow(context: ContextTypes.DEFAULT_TYPE) -> CancelAddWordsFlowUseCase:
    return _required_bot_data(context, "add_words_cancel_use_case")


def _start_image_review(context: ContextTypes.DEFAULT_TYPE) -> StartImageReviewUseCase:
    return _required_bot_data(context, "image_review_start_use_case")


def _homework_progress_use_case(context: ContextTypes.DEFAULT_TYPE) -> HomeworkProgressUseCase:
    return _required_bot_data(context, "homework_progress_use_case")


def _learner_assignment_launch_summary_use_case(
    context: ContextTypes.DEFAULT_TYPE,
) -> GetLearnerAssignmentLaunchSummaryUseCase:
    return _required_bot_data(context, "learner_assignment_launch_summary_use_case")


def _list_goal_history(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    include_history: bool,
) -> list[GoalProgressView]:
    use_case = _optional_bot_data(context, "list_user_goals_use_case")
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
    goal_id: str | None = None,
    active_session=None,
) -> _AssignmentRoundProgressView | None:
    from englishbot.telegram_assignment_progress import assignment_round_progress_view

    return assignment_round_progress_view(
        context=context,
        user_id=user_id,
        kind=kind,
        goal_id=goal_id,
        active_session=active_session,
    )


def _assignment_progress_variant_index(*, variant_key: str, variant_count: int) -> int:
    from englishbot.telegram_assignment_progress import assignment_progress_variant_index

    return assignment_progress_variant_index(
        variant_key=variant_key,
        variant_count=variant_count,
    )


def _render_assignment_progress_track(
    *,
    completed: int,
    total: int,
    variant_key: str,
    steps: int = 17,
) -> str:
    from englishbot.telegram_assignment_progress import render_assignment_progress_track

    return render_assignment_progress_track(
        completed=completed,
        total=total,
        variant_key=variant_key,
        steps=steps,
    )


def _render_assignment_round_progress_text(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    kind: AssignmentSessionKind,
    progress: _AssignmentRoundProgressView,
) -> str:
    from englishbot.telegram_assignment_progress import render_assignment_round_progress_text

    return render_assignment_round_progress_text(
        context=context,
        user=user,
        kind=kind,
        progress=progress,
    )


def _assignment_progress_flow_id(
    *,
    user_id: int,
    kind: AssignmentSessionKind,
    goal_id: str | None = None,
) -> str:
    from englishbot.telegram_assignment_progress import assignment_progress_flow_id

    return assignment_progress_flow_id(
        user_id=user_id,
        kind=kind,
        goal_id=goal_id,
    )


def _assignment_periods_for_kind(kind: AssignmentSessionKind) -> tuple[GoalPeriod, ...]:
    from englishbot.telegram_assignment_progress import assignment_periods_for_kind

    return assignment_periods_for_kind(kind)


def _build_assignment_progress_snapshot(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    kind: AssignmentSessionKind,
    user,
    goal_id: str | None = None,
    active_session=None,
):
    from englishbot.telegram_assignment_progress import build_assignment_progress_snapshot

    return build_assignment_progress_snapshot(
        context=context,
        user_id=user_id,
        kind=kind,
        user=user,
        goal_id=goal_id,
        active_session=active_session,
    )


def _assignment_word_progress_value(
    *,
    store: SQLiteContentStore,
    user_id: int,
    goal,
    row: dict[str, object],
) -> float:
    from englishbot.telegram_assignment_progress import assignment_word_progress_value

    return assignment_word_progress_value(
        store=store,
        user_id=user_id,
        goal=goal,
        row=row,
    )


def _assignment_progress_image_path(*, user_id: int, kind: AssignmentSessionKind) -> Path:
    from englishbot.telegram_assignment_progress import assignment_progress_image_path

    return assignment_progress_image_path(user_id=user_id, kind=kind)


def _session_combo_target_word_id(active_session) -> str | None:
    from englishbot.telegram_assignment_progress import session_combo_target_word_id

    return session_combo_target_word_id(active_session)


def _assignment_progress_caption(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    snapshot,
    kind: AssignmentSessionKind,
    user,
    remaining_word_count: int,
) -> str:
    from englishbot.telegram_assignment_progress import assignment_progress_caption

    return assignment_progress_caption(
        context=context,
        snapshot=snapshot,
        kind=kind,
        user=user,
        remaining_word_count=remaining_word_count,
    )


def _compact_assignment_feedback_text(
    *,
    base_text: str,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    feedback_update: _GoalFeedbackUpdate | None,
) -> str:
    compact_text = " ".join(line.strip() for line in base_text.splitlines() if line.strip())
    if feedback_update is not None and feedback_update.weekly_points_delta > 0:
        compact_text = (
            f"{compact_text} "
            f"{_tg('feedback_weekly_points_delta', context=context, user=user, delta=feedback_update.weekly_points_delta)}"
        )
    return compact_text


async def _send_or_update_assignment_progress_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
    user,
    kind: AssignmentSessionKind,
    active_session=None,
) -> None:
    from englishbot.telegram_assignment_progress import (
        send_or_update_assignment_progress_message,
    )

    await send_or_update_assignment_progress_message(
        context,
        message=message,
        user=user,
        kind=kind,
        active_session=active_session,
    )


def _start_assignment_round_use_case(
    context: ContextTypes.DEFAULT_TYPE,
) -> StartAssignmentRoundUseCase:
    return _required_bot_data(context, "start_assignment_round_use_case")


def _start_assignment_round_use_case_or_none(
    context: ContextTypes.DEFAULT_TYPE,
) -> StartAssignmentRoundUseCase | None:
    return _optional_bot_data(context, "start_assignment_round_use_case")


def _execute_assignment_start_use_case(
    use_case,
    *,
    user_id: int,
    kind: AssignmentSessionKind,
    ui_language: str,
    goal_id: str | None = None,
    combo_correct_streak: int = 0,
    combo_hard_active: bool = False,
):
    try:
        return use_case.execute(
            user_id=user_id,
            kind=kind,
            goal_id=goal_id,
            combo_correct_streak=combo_correct_streak,
            combo_hard_active=combo_hard_active,
            ui_language=ui_language,
        )
    except TypeError:
        try:
            return use_case.execute(
                user_id=user_id,
                kind=kind,
                goal_id=goal_id,
                combo_correct_streak=combo_correct_streak,
                combo_hard_active=combo_hard_active,
            )
        except TypeError:
            return use_case.execute(
                user_id=user_id,
                kind=kind,
            )


def _start_training_session_with_ui_language(
    service,
    *,
    user_id: int,
    topic_id: str,
    mode: TrainingMode,
    ui_language: str,
    lesson_id: str | None = None,
    adaptive_per_word: bool = False,
):
    try:
        return service.start_session(
            user_id=user_id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=mode,
            adaptive_per_word=adaptive_per_word,
            ui_language=ui_language,
        )
    except TypeError:
        return service.start_session(
            user_id=user_id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=mode,
            adaptive_per_word=adaptive_per_word,
        )


def _assign_goal_to_users_use_case(context: ContextTypes.DEFAULT_TYPE) -> AssignGoalToUsersUseCase:
    return _required_bot_data(context, "assign_goal_to_users_use_case")


def _admin_users_progress_overview_use_case(
    context: ContextTypes.DEFAULT_TYPE,
) -> GetAdminUsersProgressOverviewUseCase:
    return _required_bot_data(context, "admin_users_progress_overview_use_case")


def _admin_user_goals_use_case(context: ContextTypes.DEFAULT_TYPE) -> GetAdminUserGoalsUseCase:
    return _required_bot_data(context, "admin_user_goals_use_case")


def _admin_goal_detail_use_case(context: ContextTypes.DEFAULT_TYPE) -> GetAdminGoalDetailUseCase:
    return _required_bot_data(context, "admin_goal_detail_use_case")


def _start_published_word_image_review(
    context: ContextTypes.DEFAULT_TYPE,
) -> StartPublishedWordImageEditUseCase:
    return _required_bot_data(context, "image_review_start_published_word_use_case")


def _get_active_image_review(context: ContextTypes.DEFAULT_TYPE) -> GetActiveImageReviewUseCase:
    return _required_bot_data(context, "image_review_get_active_use_case")


def _cancel_image_review(context: ContextTypes.DEFAULT_TYPE) -> CancelImageReviewFlowUseCase:
    return _required_bot_data(context, "image_review_cancel_use_case")


def _generate_image_review_candidates(
    context: ContextTypes.DEFAULT_TYPE,
) -> GenerateImageReviewCandidatesUseCase:
    return _required_bot_data(context, "image_review_generate_use_case")


def _search_image_review_candidates(
    context: ContextTypes.DEFAULT_TYPE,
) -> SearchImageReviewCandidatesUseCase:
    return _required_bot_data(context, "image_review_search_use_case")


def _load_next_image_review_candidates(
    context: ContextTypes.DEFAULT_TYPE,
) -> LoadNextImageReviewCandidatesUseCase:
    return _required_bot_data(context, "image_review_next_use_case")


def _load_previous_image_review_candidates(
    context: ContextTypes.DEFAULT_TYPE,
) -> LoadPreviousImageReviewCandidatesUseCase:
    return _required_bot_data(context, "image_review_previous_use_case")


def _select_image_review_candidate(
    context: ContextTypes.DEFAULT_TYPE,
) -> SelectImageCandidateUseCase:
    return _required_bot_data(context, "image_review_select_use_case")


def _skip_image_review_item(context: ContextTypes.DEFAULT_TYPE) -> SkipImageReviewItemUseCase:
    return _required_bot_data(context, "image_review_skip_use_case")


def _publish_image_review(context: ContextTypes.DEFAULT_TYPE) -> PublishImageReviewUseCase:
    return _required_bot_data(context, "image_review_publish_use_case")


def _update_image_review_prompt(
    context: ContextTypes.DEFAULT_TYPE,
) -> UpdateImageReviewPromptUseCase:
    return _required_bot_data(context, "image_review_update_prompt_use_case")


def _attach_uploaded_image(
    context: ContextTypes.DEFAULT_TYPE,
) -> AttachUploadedImageUseCase:
    return _required_bot_data(context, "image_review_attach_uploaded_image_use_case")


def _generate_content_pack_images(
    context: ContextTypes.DEFAULT_TYPE,
) -> GenerateContentPackImagesUseCase:
    return _required_bot_data(context, "content_pack_generate_images_use_case")


def _list_editable_topics(context: ContextTypes.DEFAULT_TYPE) -> ListEditableTopicsUseCase:
    return _required_bot_data(context, "list_editable_topics_use_case")


def _list_editable_words(context: ContextTypes.DEFAULT_TYPE) -> ListEditableWordsUseCase:
    return _required_bot_data(context, "list_editable_words_use_case")


def _update_editable_word(context: ContextTypes.DEFAULT_TYPE) -> UpdateEditableWordUseCase:
    return _required_bot_data(context, "update_editable_word_use_case")


def _image_review_assets_dir(context: ContextTypes.DEFAULT_TYPE) -> Path:
    return _required_bot_data(context, "image_review_assets_dir")


def _telegram_flow_messages(context: ContextTypes.DEFAULT_TYPE):
    return _optional_bot_data(context, "telegram_flow_message_repository")


def _menu_access_policy(context: ContextTypes.DEFAULT_TYPE) -> TelegramMenuAccessPolicy:
    configured_policy = _optional_bot_data(context, "telegram_menu_access_policy")
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


def _is_admin(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return "admin" in _menu_access_policy(context).roles_for_user(user_id)


def _visible_command_specs(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int | None,
    only_chat_menu: bool = False,
) -> tuple[TelegramCommandSpec, ...]:
    return menu_visible_command_specs(
        context.application.bot_data,
        user_id=user_id,
        only_chat_menu=only_chat_menu,
    )


def _visible_command_rows(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int | None,
) -> list[list[str]]:
    return menu_visible_command_rows(context.application.bot_data, user_id=user_id)


def _preview_message_ids(context: ContextTypes.DEFAULT_TYPE) -> dict[int, int]:
    return _required_bot_data(context, "word_import_preview_message_ids")


def _admin_web_app_url(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user,
) -> str | None:
    user_id = getattr(user, "id", None)
    if user_id is None or not _is_admin(user_id, context):
        return None
    configured_url = _optional_bot_data(context, "web_app_base_url")
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
    configured_url = _optional_bot_data(context, "web_app_base_url")
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
    override = _optional_bot_data(context, "smart_parsing_available")
    if isinstance(override, bool):
        return override
    gateway = _optional_bot_data(context, "smart_parsing_gateway")
    if gateway is None:
        return True
    try:
        return bool(gateway.check_availability().is_available)
    except Exception:  # noqa: BLE001
        logger.exception("Smart parsing availability check failed")
        return False


def _local_image_generation_available(context: ContextTypes.DEFAULT_TYPE) -> bool:
    override = _optional_bot_data(context, "local_image_generation_available")
    if isinstance(override, bool):
        return override
    gateway = _optional_bot_data(context, "image_generation_gateway")
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
    _set_user_data(context, _EXPECTED_USER_INPUT_STATE_KEY, {
        "chat_id": chat_id,
        "message_id": message_id,
    })


def _clear_expected_user_input(context: ContextTypes.DEFAULT_TYPE) -> None:
    _pop_user_data(context, _EXPECTED_USER_INPUT_STATE_KEY, default=None)


async def _edit_expected_user_input_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    text: str,
    reply_markup,
) -> bool:
    stored = _optional_user_data(context, _EXPECTED_USER_INPUT_STATE_KEY)
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
            context=context,
            user_id=int(user.id),
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
    await telegram_start_handler(
        update,
        context,
        send_view=send_telegram_view,
        telegram_user_login_repository=_telegram_user_login_repository,
        service=_service,
        tg=_tg,
        active_session_topic_label=_active_session_topic_label,
        active_session_lesson_label=_active_session_lesson_label,
        active_session_keyboard=_active_session_keyboard,
        telegram_ui_language=_telegram_ui_language,
        start_menu_view=_start_menu_view,
        ensure_chat_menu_message=_ensure_chat_menu_message,
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_help_handler(
        update,
        context,
        send_view=send_telegram_view,
        visible_command_specs=_visible_command_specs,
        help_command_text=_HELP_COMMAND_TEXT,
        tg=_tg,
        help_view=_help_view,
        ensure_chat_menu_message=_ensure_chat_menu_message,
    )


async def version_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_version_handler(
        update,
        context,
        send_view=send_telegram_view,
        runtime_version_info=_runtime_version_info,
        tg=_tg,
    )


async def makeadmin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_admin_utils import (
        makeadmin_handler as telegram_makeadmin_handler,
    )

    await telegram_makeadmin_handler(update, context)


async def clear_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_admin_utils import (
        clear_user_handler as telegram_clear_user_handler,
    )

    await telegram_clear_user_handler(update, context)


async def assign_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_assign_menu_handler(
        update,
        context,
        send_view=send_telegram_view,
        telegram_user_login_repository=_telegram_user_login_repository,
        tg=_tg,
        assign_menu_view=_assign_menu_view,
        ensure_chat_menu_message=_ensure_chat_menu_message,
    )


async def words_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_words_menu_handler(
        update,
        context,
        send_view=send_telegram_view,
        tg=_tg,
        words_menu_view=_words_menu_view,
        ensure_chat_menu_message=_ensure_chat_menu_message,
    )


async def assign_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_assign_menu_callback_handler(
        update,
        context,
        edit_text_view=edit_telegram_text_view,
        tg=_tg,
        assign_menu_view=_assign_menu_view,
    )


async def noop_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    query = update.callback_query
    if query is None:
        return
    await query.answer()


async def notification_dismiss_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_notifications import (
        notification_dismiss_callback_handler as telegram_notification_dismiss_callback_handler,
    )

    await telegram_notification_dismiss_callback_handler(update, context)


async def words_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_words_menu_callback_handler(
        update,
        context,
        edit_text_view=edit_telegram_text_view,
        tg=_tg,
        words_menu_view=_words_menu_view,
    )


def _goal_setup_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_goal_setup_keyboard(tg=_tg, language=language)


def _goal_target_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_goal_target_keyboard(tg=_tg, language=language)


def _goal_source_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_goal_source_keyboard(tg=_tg, language=language)


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


def _admin_goal_deadline_keyboard(*, language: str = DEFAULT_TELEGRAM_UI_LANGUAGE) -> InlineKeyboardMarkup:
    return ui_admin_goal_deadline_keyboard(tg=_tg, language=language)


def _render_progress_text(*, context: ContextTypes.DEFAULT_TYPE, user) -> str:
    summary = _homework_progress_use_case(context).get_summary(user_id=user.id)
    summary = LearnerProgressSummary(
        correct_answers=summary.correct_answers,
        incorrect_answers=summary.incorrect_answers,
        game_streak_days=summary.game_streak_days,
        weekly_points=summary.weekly_points,
        active_goals=[item for item in summary.active_goals if item.goal.goal_period is GoalPeriod.HOMEWORK],
    )
    history = _list_goal_history(context=context, user_id=user.id, include_history=True)
    history = [item for item in history if item.goal.goal_period is GoalPeriod.HOMEWORK]
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


def _assignment_kind_from_value(raw_value: str | None) -> AssignmentSessionKind | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if not normalized:
        return None
    if normalized == AssignmentSessionKind.HOMEWORK.value:
        return AssignmentSessionKind.HOMEWORK
    return None


def _assignment_kind_and_goal_id_from_source_tag(
    source_tag: str | None,
) -> tuple[AssignmentSessionKind | None, str | None]:
    if not isinstance(source_tag, str) or not source_tag.startswith("assignment:"):
        return None, None
    parts = source_tag.split(":", 2)
    kind = _assignment_kind_from_value(parts[1] if len(parts) > 1 else None)
    goal_id = parts[2] if len(parts) > 2 and parts[2] else None
    return kind, goal_id


def _active_session_topic_label(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    topic_id: str,
    source_tag: str | None = None,
    lesson_id: str | None = None,
) -> str:
    kind, _ = _assignment_kind_and_goal_id_from_source_tag(source_tag)
    if kind is not None:
        return _assignment_kind_label(kind, context=context, user=user)
    if topic_id.startswith("assignment:"):
        kind = _assignment_kind_from_value(topic_id.split(":", 1)[1])
        if kind is not None:
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
    kind, _ = _assignment_kind_and_goal_id_from_source_tag(source_tag)
    if kind is not None:
        return kind
    topic_id = getattr(active_session, "topic_id", None)
    if isinstance(topic_id, str) and topic_id.startswith("assignment:"):
        return _assignment_kind_from_value(topic_id.split(":", 1)[1])
    return None


def _raw_training_session_by_id(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    session_id: str | None,
):
    if not isinstance(session_id, str):
        return None
    store = _optional_bot_data(context, "content_store")
    if store is None or not hasattr(store, "get_session_by_id"):
        return None
    return store.get_session_by_id(session_id)


async def words_goals_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        words_goals_callback_handler as homework_words_goals_callback_handler,
    )

    await homework_words_goals_callback_handler(update, context)


async def words_progress_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        words_progress_callback_handler as homework_words_progress_callback_handler,
    )

    await homework_words_progress_callback_handler(update, context)


def _clear_self_goal_setup_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    _pop_user_data(context, "goal_period", default=None)
    _pop_user_data(context, "goal_type", default=None)
    _pop_user_data(context, "goal_target_count", default=None)
    if _optional_user_data(context, "words_flow_mode") == _GOAL_AWAITING_TARGET_TEXT:
        _pop_user_data(context, "words_flow_mode", default=None)


async def goal_setup_disabled_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        goal_setup_disabled_callback_handler as homework_goal_setup_disabled_callback_handler,
    )

    await homework_goal_setup_disabled_callback_handler(update, context)


async def goal_type_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        goal_type_callback_handler as homework_goal_type_callback_handler,
    )

    await homework_goal_type_callback_handler(update, context)


async def goal_reset_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        goal_reset_callback_handler as homework_goal_reset_callback_handler,
    )

    await homework_goal_reset_callback_handler(update, context)


async def admin_assign_goal_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_assign_goal_start_handler as homework_admin_assign_goal_start_handler,
    )

    await homework_admin_assign_goal_start_handler(update, context)


async def admin_goal_period_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_goal_period_callback_handler as homework_admin_goal_period_callback_handler,
    )

    await homework_admin_goal_period_callback_handler(update, context)


async def admin_goal_target_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_goal_target_menu_callback_handler as homework_admin_goal_target_menu_callback_handler,
    )

    await homework_admin_goal_target_menu_callback_handler(update, context)


async def admin_goal_target_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_goal_target_callback_handler as homework_admin_goal_target_callback_handler,
    )

    await homework_admin_goal_target_callback_handler(update, context)


async def admin_goal_source_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_goal_source_menu_callback_handler as homework_admin_goal_source_menu_callback_handler,
    )

    await homework_admin_goal_source_menu_callback_handler(update, context)


def _admin_goal_manual_keyboard(*, context: ContextTypes.DEFAULT_TYPE, user, page: int) -> InlineKeyboardMarkup:
    items = _content_store(context).list_all_vocabulary()
    selected = set(_admin_goal_user_state(context, "admin_goal_manual_word_ids", default=set()))
    keyboard, normalized_page = ui_admin_goal_manual_keyboard(
        tg=_tg,
        items=items,
        selected_word_ids=selected,
        page=page,
        language=_telegram_ui_language(context, user),
    )
    _set_user_data(context, "admin_goal_manual_page", normalized_page)
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
    selected = set(_admin_goal_user_state(context, "admin_goal_recipient_user_ids", default=set()))
    keyboard, normalized_page = ui_admin_goal_recipients_keyboard(
        tg=_tg,
        items=items,
        selected_user_ids=selected,
        page=page,
        language=_telegram_ui_language(context, user),
    )
    _set_user_data(context, "admin_goal_recipients_page", normalized_page)
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


async def admin_goal_source_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_goal_source_callback_handler as homework_admin_goal_source_callback_handler,
    )

    await homework_admin_goal_source_callback_handler(update, context)


async def admin_goal_manual_toggle_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_goal_manual_toggle_callback_handler as homework_admin_goal_manual_toggle_callback_handler,
    )

    await homework_admin_goal_manual_toggle_callback_handler(update, context)


async def admin_goal_manual_done_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_goal_manual_done_callback_handler as homework_admin_goal_manual_done_callback_handler,
    )

    await homework_admin_goal_manual_done_callback_handler(update, context)


async def admin_goal_recipients_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_goal_recipients_callback_handler as homework_admin_goal_recipients_callback_handler,
    )

    await homework_admin_goal_recipients_callback_handler(update, context)


async def admin_goal_deadline_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_goal_deadline_callback_handler as homework_admin_goal_deadline_callback_handler,
    )

    await homework_admin_goal_deadline_callback_handler(update, context)


def _create_admin_goals_from_context(*, context: ContextTypes.DEFAULT_TYPE) -> list:
    source_raw = str(_admin_goal_user_state(context, "admin_goal_source", default=GoalWordSource.RECENT.value))
    topic_id = source_raw.split(":", 1)[1] if source_raw.startswith("topic:") else None
    source = GoalWordSource.TOPIC if topic_id else GoalWordSource(source_raw)
    return _assign_goal_to_users_use_case(context).execute(
        user_ids=list(_admin_goal_user_state(context, "admin_goal_recipient_user_ids", default=[])),
        goal_period=GoalPeriod(str(_admin_goal_user_state(context, "admin_goal_period", default=GoalPeriod.HOMEWORK.value))),
        goal_type=GoalType(str(_admin_goal_user_state(context, "admin_goal_type", default=GoalType.WORD_LEVEL_HOMEWORK.value))),
        target_count=None,
        source=source,
        topic_id=topic_id,
        manual_word_ids=list(_admin_goal_user_state(context, "admin_goal_manual_word_ids", default=[])),
        deadline_date=_admin_goal_user_state(context, "admin_goal_deadline_date"),
    )


async def _create_admin_goal_from_context(*, query, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Backward-compatible wrapper kept for tests and older call sites."""
    await _finish_admin_goal_creation(query_or_message=query, context=context, user=user)


async def _finish_admin_goal_creation(*, query_or_message, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    created = _create_admin_goals_from_context(context=context)
    _schedule_assignment_assigned_notifications(context, goals=created)
    for recipient_user_id in {int(goal.user_id) for goal in created}:
        await _flush_pending_notifications_for_user(context, user_id=recipient_user_id)
    assigned_word_count = max((int(goal.target_count) for goal in created), default=0)
    if hasattr(query_or_message, "edit_message_text"):
        await query_or_message.edit_message_text(
            _tg(
                "admin_goal_created",
                context=context,
                user=user,
                user_count=len(created),
                target=assigned_word_count,
            )
        )
    else:
        await query_or_message.reply_text(
            _tg(
                "admin_goal_created",
                context=context,
                user=user,
                user_count=len(created),
                target=assigned_word_count,
            )
        )
    for key in (
        "admin_goal_period",
        "admin_goal_type",
        "admin_goal_target_count",
        "admin_goal_source",
        "admin_goal_deadline_date",
        "admin_goal_manual_word_ids",
        "admin_goal_recipient_user_ids",
        "admin_goal_recipients_page",
        "words_flow_mode",
    ):
        _pop_user_data(context, key, default=None)
    _clear_expected_user_input(context)


async def admin_users_progress_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        admin_users_progress_callback_handler as homework_admin_users_progress_callback_handler,
    )

    await homework_admin_users_progress_callback_handler(update, context)


async def assign_user_detail_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        assign_user_detail_callback_handler as homework_assign_user_detail_callback_handler,
    )

    await homework_assign_user_detail_callback_handler(update, context)


async def assign_goal_detail_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        assign_goal_detail_callback_handler as homework_assign_goal_detail_callback_handler,
    )

    await homework_assign_goal_detail_callback_handler(update, context)


async def words_topics_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await telegram_words_topics_callback_handler(
        update,
        context,
        service=_service,
        topic_selection_view=_topic_selection_view,
        edit_text_view=edit_telegram_text_view,
    )


async def words_add_words_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        words_add_words_callback_handler as editor_words_add_words_callback_handler,
    )

    await editor_words_add_words_callback_handler(update, context)


async def words_edit_words_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        words_edit_words_callback_handler as editor_words_edit_words_callback_handler,
    )

    await editor_words_edit_words_callback_handler(update, context)


async def words_edit_images_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        words_edit_images_callback_handler as editor_words_edit_images_callback_handler,
    )

    await editor_words_edit_images_callback_handler(update, context)


async def words_edit_topic_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        words_edit_topic_callback_handler as editor_words_edit_topic_callback_handler,
    )

    await editor_words_edit_topic_callback_handler(update, context)


async def words_edit_item_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        words_edit_item_callback_handler as editor_words_edit_item_callback_handler,
    )

    await editor_words_edit_item_callback_handler(update, context)


async def words_edit_cancel_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        words_edit_cancel_callback_handler as editor_words_edit_cancel_callback_handler,
    )

    await editor_words_edit_cancel_callback_handler(update, context)


async def add_words_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_start_handler as editor_add_words_start_handler,
    )

    await editor_add_words_start_handler(update, context)


async def add_words_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_cancel_handler as editor_add_words_cancel_handler,
    )

    await editor_add_words_cancel_handler(update, context)


async def add_words_cancel_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_cancel_callback_handler as editor_add_words_cancel_callback_handler,
    )

    await editor_add_words_cancel_callback_handler(update, context)


async def add_words_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_text_handler as editor_add_words_text_handler,
    )

    await editor_add_words_text_handler(update, context)


async def goal_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_homework_admin import (
        goal_text_handler as homework_goal_text_handler,
    )

    await homework_goal_text_handler(update, context)


async def add_words_edit_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_edit_text_handler as editor_add_words_edit_text_handler,
    )

    await editor_add_words_edit_text_handler(update, context)


async def add_words_show_json_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_show_json_handler as editor_add_words_show_json_handler,
    )

    await editor_add_words_show_json_handler(update, context)


async def add_words_regenerate_draft_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_regenerate_draft_handler as editor_add_words_regenerate_draft_handler,
    )

    await editor_add_words_regenerate_draft_handler(update, context)


async def add_words_publish_without_images_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_publish_without_images_handler as editor_add_words_publish_without_images_handler,
    )

    await editor_add_words_publish_without_images_handler(update, context)


async def add_words_approve_draft_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_approve_draft_handler as editor_add_words_approve_draft_handler,
    )

    await editor_add_words_approve_draft_handler(update, context)


async def add_words_approve_auto_images_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_add_words import (
        add_words_approve_auto_images_handler as editor_add_words_approve_auto_images_handler,
    )

    await editor_add_words_approve_auto_images_handler(update, context)


async def published_images_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        published_images_menu_handler as editor_published_images_menu_handler,
    )

    await editor_published_images_menu_handler(update, context)


async def published_image_item_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        published_image_item_handler as editor_published_image_item_handler,
    )

    await editor_published_image_item_handler(update, context)


async def image_review_generate_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_generate_handler as editor_image_review_generate_handler,
    )

    await editor_image_review_generate_handler(update, context)


async def image_review_search_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_search_handler as editor_image_review_search_handler,
    )

    await editor_image_review_search_handler(update, context)


async def image_review_next_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_next_handler as editor_image_review_next_handler,
    )

    await editor_image_review_next_handler(update, context)


async def image_review_previous_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_previous_handler as editor_image_review_previous_handler,
    )

    await editor_image_review_previous_handler(update, context)


async def image_review_pick_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_pick_handler as editor_image_review_pick_handler,
    )

    await editor_image_review_pick_handler(update, context)


async def image_review_skip_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_skip_handler as editor_image_review_skip_handler,
    )

    await editor_image_review_skip_handler(update, context)


async def image_review_edit_prompt_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_edit_prompt_handler as editor_image_review_edit_prompt_handler,
    )

    await editor_image_review_edit_prompt_handler(update, context)


async def image_review_edit_search_query_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_edit_search_query_handler as editor_image_review_edit_search_query_handler,
    )

    await editor_image_review_edit_search_query_handler(update, context)


async def image_review_show_json_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_show_json_handler as editor_image_review_show_json_handler,
    )

    await editor_image_review_show_json_handler(update, context)


async def image_review_attach_photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from englishbot.telegram_editor_images import (
        image_review_attach_photo_handler as editor_image_review_attach_photo_handler,
    )

    await editor_image_review_attach_photo_handler(update, context)


async def image_review_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_editor_images import (
        image_review_photo_handler as editor_image_review_photo_handler,
    )

    await editor_image_review_photo_handler(update, context)


async def continue_session_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_continue_session_handler(
        update,
        context,
        service=_service,
        clear_medium_task_state=_clear_medium_task_state,
        tg=_tg,
        expects_text_answer_for_question=_expects_text_answer_for_question,
        record_assignment_activity=_record_assignment_activity,
        assignment_kind_from_session=_assignment_kind_from_session,
        send_or_update_assignment_progress_message=_send_or_update_assignment_progress_message,
        send_question=_send_question,
    )


async def restart_session_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_restart_session_handler(
        update,
        context,
        service=_service,
        clear_medium_task_state=_clear_medium_task_state,
        tg=_tg,
        send_view=send_telegram_view,
        start_menu_view=_start_menu_view,
    )


async def start_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_start_menu_callback_handler(
        update,
        context,
        edit_text_view=edit_telegram_text_view,
        start_menu_view=_start_menu_view,
    )


async def start_assignment_round_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_start_assignment_round_callback_handler(
        update,
        context,
        start_assignment_round_use_case=_start_assignment_round_use_case,
        execute_assignment_start_use_case=_execute_assignment_start_use_case,
        telegram_ui_language=_telegram_ui_language,
        tg=_tg,
        start_submenu_keyboard=_start_submenu_keyboard,
        expects_text_answer_for_question=_expects_text_answer_for_question,
        send_or_update_assignment_progress_message=_send_or_update_assignment_progress_message,
        send_question=_send_question,
    )


async def start_assignment_unavailable_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await telegram_start_assignment_unavailable_callback_handler(
        update,
        context,
        tg=_tg,
        telegram_ui_language=_telegram_ui_language,
        start_submenu_keyboard=_start_submenu_keyboard,
    )


async def topic_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_topic_selected_handler(
        update,
        context,
        service=_service,
        lesson_selection_view=_lesson_selection_view,
        mode_selection_view=_mode_selection_view,
        tg=_tg,
    )


async def lesson_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_lesson_selected_handler(
        update,
        context,
        mode_selection_view=_mode_selection_view,
        tg=_tg,
    )


async def mode_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_mode_selected_handler(
        update,
        context,
        service=_service,
        start_training_session_with_ui_language=_start_training_session_with_ui_language,
        telegram_ui_language=_telegram_ui_language,
        tg=_tg,
        expects_text_answer_for_question=_expects_text_answer_for_question,
        send_question=_send_question,
    )


async def game_mode_placeholder_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await telegram_game_mode_placeholder_callback_handler(
        update,
        context,
        tg=_tg,
        start_submenu_keyboard=_start_submenu_keyboard,
        telegram_ui_language=_telegram_ui_language,
    )


async def game_next_round_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    game_state = _game_state(context)
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
        question = _start_training_session_with_ui_language(
            _service(context),
            user_id=user.id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=TrainingMode(str(mode_value)),
            adaptive_per_word=True,
            ui_language=_telegram_ui_language(context, user),
        )
    except (ApplicationError, ValueError) as error:
        await query.edit_message_text(str(error))
        return
    streak_days = _content_store(context).update_game_streak(user_id=user.id, played_at=datetime.now(UTC))
    _set_user_data(context, _GAME_STATE_KEY, {
        "active": True,
        "topic_id": topic_id,
        "lesson_id": lesson_id,
        "mode_value": mode_value,
        "session_stars": 0,
        "correct_answers": 0,
        "streak_days": streak_days,
    })
    _set_user_data(context, "awaiting_text_answer", _expects_text_answer_for_question(question))
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
    _pop_user_data(context, _GAME_STATE_KEY, default=None)
    _clear_medium_task_state(context)
    await query.edit_message_text(_tg("start_menu_title", context=context, user=user))
    await send_telegram_view(
        query.message,
        _start_menu_view(context=context, user=user),
    )


def _create_callback_token(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    action: str,
    payload: dict[str, object],
    fallback_value: str,
) -> str:
    creator = getattr(_content_store(context), "create_telegram_callback_token", None)
    if creator is None:
        return fallback_value
    return str(
        creator(
            user_id=user_id,
            action=action,
            payload=payload,
            ttl_seconds=_CALLBACK_TOKEN_TTL_SECONDS,
        )
    )


def _consume_callback_token(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    action: str,
    token: str,
    fallback_key: str,
    allow_colon_fallback: bool = False,
) -> dict[str, object] | None:
    consumer = getattr(_content_store(context), "consume_telegram_callback_token", None)
    if consumer is None:
        return {fallback_key: token}
    resolved = consumer(user_id=user_id, action=action, token=token)
    if resolved is None:
        if ":" in token and not allow_colon_fallback:
            return None
        return {fallback_key: token}
    return resolved


def _hard_skip_callback_data(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session_id: str,
) -> str:
    token = _create_callback_token(
        context=context,
        user_id=user_id,
        action=_HARD_SKIP_CALLBACK_ACTION,
        payload={"session_id": session_id},
        fallback_value=session_id,
    )
    return f"hard:skip:{token}"


def _editable_word_callback_data(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    topic_id: str,
    item_index: int,
) -> str:
    token = _create_callback_token(
        context=context,
        user_id=user_id,
        action=_EDITABLE_WORD_CALLBACK_ACTION,
        payload={"topic_id": topic_id, "item_index": item_index},
        fallback_value=f"{topic_id}:{item_index}",
    )
    return f"words:edit_item:{token}"


def _published_image_item_callback_data(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    topic_id: str,
    item_index: int,
) -> str:
    token = _create_callback_token(
        context=context,
        user_id=user_id,
        action=_PUBLISHED_IMAGE_ITEM_CALLBACK_ACTION,
        payload={"topic_id": topic_id, "item_index": item_index},
        fallback_value=f"{topic_id}:{item_index}",
    )
    return f"words:edit_published_image:{token}"


def _hard_skip_keyboard(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    session_id: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                _tg("hard_skip_button", context=context, user=user),
                callback_data=_hard_skip_callback_data(
                    context=context,
                    user_id=int(user.id),
                    session_id=session_id,
                ),
            )
        ]
    ]
    if _tts_service_enabled(context):
        tts_row = [
            InlineKeyboardButton(
                _tg("tts_play_button", context=context, user=user),
                callback_data="tts:current",
            )
        ]
        if _tts_has_multiple_voices(context):
            tts_row.append(
                InlineKeyboardButton(
                    _tg("tts_voice_menu_button", context=context, user=user),
                    callback_data="tts:voices",
                )
            )
        rows.append(tts_row)
    return InlineKeyboardMarkup(rows)


def _tts_buttons(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> list[InlineKeyboardButton]:
    row = [
        InlineKeyboardButton(
            _tg("tts_play_button", context=context, user=user),
            callback_data="tts:current",
        )
    ]
    if _tts_has_multiple_voices(context):
        row.append(
            InlineKeyboardButton(
                _tg("tts_voice_menu_button", context=context, user=user),
                callback_data="tts:voices",
            )
        )
    return row


def _question_reply_markup(
    question: TrainingQuestion,
    *,
    active_session,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> InlineKeyboardMarkup | None:
    if question.mode is TrainingMode.MEDIUM:
        state = _get_medium_task_state(context)
        if state is None or state.session_id != question.session_id or state.item_id != question.item_id:
            state = _build_medium_task_state(question)
        return _medium_task_keyboard(state, context=context, user=user)
    if question.options:
        rows = [[InlineKeyboardButton(option, callback_data=f"answer:{option}")] for option in question.options]
        if _tts_service_enabled(context):
            rows.append(_tts_buttons(context=context, user=user))
        return InlineKeyboardMarkup(rows)
    if (
        user is not None
        and active_session is not None
        and active_session.id == question.session_id
        and question.mode is TrainingMode.HARD
    ):
        return _hard_skip_keyboard(context=context, user=user, session_id=question.session_id)
    return None


def _tts_voice_menu_markup(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    item_id: str,
) -> InlineKeyboardMarkup:
    variants = _tts_voice_variants(context)
    selected_voice_name = _tts_selected_voice_name(context, item_id=item_id)
    rows: list[list[InlineKeyboardButton]] = []
    for index, voice_name in enumerate(variants):
        prefix = "✓ " if voice_name == selected_voice_name else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{prefix}{_tts_voice_label(context, user=user, voice_name=voice_name)}",
                    callback_data=f"tts:voice:{index}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                _tg("tts_voice_menu_back_button", context=context, user=user),
                callback_data="tts:voice:back",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


async def tts_voice_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_tts import (
        tts_voice_menu_handler as telegram_tts_voice_menu_handler,
    )

    await telegram_tts_voice_menu_handler(update, context)


async def tts_voice_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_tts import (
        tts_voice_select_handler as telegram_tts_voice_select_handler,
    )

    await telegram_tts_voice_select_handler(update, context)


async def tts_current_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_tts import (
        tts_current_handler as telegram_tts_current_handler,
    )

    await telegram_tts_current_handler(update, context)


async def tts_next_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_tts import (
        tts_next_handler as telegram_tts_next_handler,
    )

    await telegram_tts_next_handler(update, context)


async def hard_skip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_hard_skip_handler(
        update,
        context,
        tg=_tg,
        consume_callback_token=lambda **kwargs: _consume_callback_token(
            **kwargs,
            action=_HARD_SKIP_CALLBACK_ACTION,
        ),
        active_training_session=_active_training_session,
        service=_service,
        assignment_kind_from_session=_assignment_kind_from_session,
        process_answer=_process_answer,
        content_store=_content_store,
        send_question=_send_question,
    )


async def medium_answer_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_medium_answer_callback_handler(
        update,
        context,
        service=_service,
        medium_task_lock=_medium_task_lock,
        get_medium_task_state=_get_medium_task_state,
        set_medium_task_state=_set_medium_task_state,
        clear_medium_task_state=_clear_medium_task_state,
        medium_task_is_complete=_medium_task_is_complete,
        build_medium_question_view=_build_medium_question_view,
        edit_training_question_view=_edit_training_question_view,
        medium_task_answer_text=_medium_task_answer_text,
        process_answer=_process_answer,
        medium_task_state_type=_MediumTaskState,
    )


async def choice_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_choice_answer_handler(
        update,
        context,
        process_answer=_process_answer,
    )


async def text_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_text_answer_handler(
        update,
        context,
        service=_service,
        clear_medium_task_state=_clear_medium_task_state,
        tg=_tg,
        process_answer=_process_answer,
    )


async def group_text_observer_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not _is_group_chat(update):
        return
    if _optional_user_data(context, "awaiting_text_answer"):
        return
    if _optional_user_data(context, "words_flow_mode") is not None:
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
    await delivery_process_answer(
        update,
        context,
        answer,
        service=_service,
        clear_medium_task_state=_clear_medium_task_state,
        tg=_tg,
        assignment_kind_from_session=_assignment_kind_from_session,
        record_assignment_activity=_record_assignment_activity,
        delete_tracked_flow_messages=_delete_tracked_flow_messages,
        training_question_tag=_TRAINING_QUESTION_TAG,
        send_game_feedback=_send_game_feedback,
        expects_text_answer_for_question=_expects_text_answer_for_question,
        send_question=_send_question,
        finish_game_session=_finish_game_session,
        raw_training_session_by_id=_raw_training_session_by_id,
        assignment_kind_and_goal_id_from_source_tag=_assignment_kind_and_goal_id_from_source_tag,
        start_assignment_round_use_case_or_none=_start_assignment_round_use_case_or_none,
        execute_assignment_start_use_case=_execute_assignment_start_use_case,
        telegram_ui_language=_telegram_ui_language,
        collect_goal_feedback_update=_collect_goal_feedback_update,
        send_feedback=_send_feedback,
        send_or_update_assignment_progress_message=_send_or_update_assignment_progress_message,
        schedule_goal_completed_notifications=_schedule_goal_completed_notifications,
        flush_pending_notifications_for_user=_flush_pending_notifications_for_user,
        homework_progress_use_case=_homework_progress_use_case,
        answer_outcome_type=AnswerOutcome,
        invalid_session_state_error_type=InvalidSessionStateError,
        application_error_type=ApplicationError,
    )


async def _send_feedback(
    message,
    outcome: AnswerOutcome,
    *,
    context: ContextTypes.DEFAULT_TYPE,
    active_session=None,
    user=None,
    feedback_update: _GoalFeedbackUpdate | None = None,
) -> None:
    await delivery_send_feedback(
        message,
        outcome,
        context=context,
        active_session=active_session,
        user=user,
        feedback_update=feedback_update,
        build_answer_feedback_view=build_answer_feedback_view,
        assignment_kind_from_session=_assignment_kind_from_session,
        assignment_kind_and_goal_id_from_source_tag=_assignment_kind_and_goal_id_from_source_tag,
        assignment_round_progress_view=_assignment_round_progress_view,
        render_assignment_round_progress_text=_render_assignment_round_progress_text,
        assignment_round_complete_keyboard=_assignment_round_complete_keyboard,
        telegram_ui_language=_telegram_ui_language,
        compact_assignment_feedback_text=_compact_assignment_feedback_text,
        render_feedback_update_text=_render_feedback_update_text,
        delete_tracked_flow_messages=_delete_tracked_flow_messages,
        track_flow_message=_track_flow_message,
        training_feedback_tag=_TRAINING_FEEDBACK_TAG,
        message_chat_id=_message_chat_id,
        tg=_tg,
    )


async def _send_game_feedback(
    message,
    outcome: AnswerOutcome,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    game_state = _game_state(context)
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
    game_state = _game_state(context)
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
    _set_user_data(context, _GAME_STATE_KEY, {
        "active": False,
        "topic_id": game_state.get("topic_id"),
        "lesson_id": game_state.get("lesson_id"),
        "mode_value": game_state.get("mode_value"),
    })
    await _flush_pending_notifications_for_user(context, user_id=user.id)


def _expects_text_answer_for_question(question: TrainingQuestion) -> bool:
    return question.mode is TrainingMode.HARD


def _clear_medium_task_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    _pop_user_data(context, _MEDIUM_TASK_STATE_KEY, default=None)


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
    state = _optional_user_data(context, _MEDIUM_TASK_STATE_KEY)
    if isinstance(state, _MediumTaskState):
        return state
    return None


def _set_medium_task_state(context: ContextTypes.DEFAULT_TYPE, state: _MediumTaskState) -> None:
    _set_user_data(context, _MEDIUM_TASK_STATE_KEY, state)


def _medium_task_lock(context: ContextTypes.DEFAULT_TYPE) -> asyncio.Lock:
    user_data = _user_data_or_none(context)
    if user_data is None:
        return asyncio.Lock()
    lock = user_data.get(_MEDIUM_TASK_LOCK_KEY)
    if isinstance(lock, asyncio.Lock):
        return lock
    created_lock = asyncio.Lock()
    user_data[_MEDIUM_TASK_LOCK_KEY] = created_lock
    return created_lock


def _tts_task_lock(context: ContextTypes.DEFAULT_TYPE) -> asyncio.Lock:
    user_data = _user_data_or_none(context)
    if user_data is None:
        return asyncio.Lock()
    lock = user_data.get(_TTS_TASK_LOCK_KEY)
    if isinstance(lock, asyncio.Lock):
        return lock
    created_lock = asyncio.Lock()
    user_data[_TTS_TASK_LOCK_KEY] = created_lock
    return created_lock


def _tts_selected_voice_store(context: ContextTypes.DEFAULT_TYPE) -> dict[str, str]:
    user_data = _user_data_or_none(context)
    if user_data is None:
        return {}
    current = user_data.get(_TTS_SELECTED_VOICE_KEY)
    if isinstance(current, dict):
        return current
    created: dict[str, str] = {}
    user_data[_TTS_SELECTED_VOICE_KEY] = created
    return created


def _tts_selected_voice_name(context: ContextTypes.DEFAULT_TYPE, *, item_id: str) -> str | None:
    variants = _tts_voice_variants(context)
    if not variants:
        return None
    selected = _tts_selected_voice_store(context).get(item_id)
    if selected in variants:
        return selected
    selected = variants[0]
    _tts_selected_voice_store(context)[item_id] = selected
    return selected


def _advance_tts_selected_voice_name(context: ContextTypes.DEFAULT_TYPE, *, item_id: str) -> str | None:
    variants = _tts_voice_variants(context)
    if not variants:
        return None
    current = _tts_selected_voice_name(context, item_id=item_id)
    if current not in variants:
        next_voice_name = variants[0]
    else:
        next_voice_name = variants[(variants.index(current) + 1) % len(variants)]
    _tts_selected_voice_store(context)[item_id] = next_voice_name
    return next_voice_name


def _tts_recent_request(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, str, float] | None:
    value = _optional_user_data(context, _TTS_TASK_RECENT_KEY)
    if (
        isinstance(value, tuple)
        and len(value) == 3
        and isinstance(value[0], str)
        and isinstance(value[1], str)
        and isinstance(value[2], (int, float))
    ):
        return value[0], value[1], float(value[2])
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], (int, float))
    ):
        return value[0], "", float(value[1])
    return None


def _set_tts_recent_request(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    item_id: str,
    voice_name: str,
    sent_at: float,
) -> None:
    _set_user_data(context, _TTS_TASK_RECENT_KEY, (item_id, voice_name, sent_at))


def _medium_task_is_complete(state: _MediumTaskState) -> bool:
    return delivery_medium_task_is_complete(state)


def _medium_task_answer_text(state: _MediumTaskState) -> str:
    return delivery_medium_task_answer_text(state)


def _medium_task_keyboard(
    state: _MediumTaskState,
    *,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    user=None,
) -> InlineKeyboardMarkup:
    selected_indexes = set(state.selected_letter_indexes)
    buttons = [
        InlineKeyboardButton(
            "·" if index in selected_indexes else letter,
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
    check_callback = "medium:check" if _medium_task_is_complete(state) else "medium:noop:check"
    rows.append(
        [
            InlineKeyboardButton("⌫", callback_data="medium:backspace"),
        ]
    )
    if context is not None and _tts_service_enabled(context):
        rows[-1].extend(_tts_buttons(context=context, user=user))
    rows.append(
        [
            InlineKeyboardButton(
                (
                    _tg("medium_check_button", context=context, user=user)
                    if context is not None
                    else telegram_ui_text("medium_check_button")
                ),
                callback_data=check_callback,
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def _build_medium_question_view(
    question: TrainingQuestion,
    *,
    state: _MediumTaskState,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    user=None,
) -> TelegramTextView | TelegramPhotoView:
    return delivery_build_medium_question_view(
        question,
        state=state,
        context=context,
        user=user,
        resolve_existing_image_path=resolve_existing_image_path,
        tts_service_enabled=_tts_service_enabled,
        tts_buttons=_tts_buttons,
        tg=_tg,
        inline_keyboard_button_type=InlineKeyboardButton,
    )


async def _edit_training_question_view(
    query,
    *,
    view: TelegramTextView | TelegramPhotoView,
) -> None:
    await delivery_edit_training_question_view(query, view=view)


async def _send_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    question: TrainingQuestion,
) -> None:
    await delivery_send_question(
        update,
        context,
        question,
        delete_tracked_flow_messages=_delete_tracked_flow_messages,
        training_question_tag=_TRAINING_QUESTION_TAG,
        clear_medium_task_state=_clear_medium_task_state,
        active_training_session=_active_training_session,
        build_medium_task_state=_build_medium_task_state,
        build_medium_question_view=_build_medium_question_view,
        tts_service_enabled=_tts_service_enabled,
        tts_buttons=_tts_buttons,
        resolve_existing_image_path=resolve_existing_image_path,
        hard_skip_keyboard=_hard_skip_keyboard,
        set_medium_task_state=_set_medium_task_state,
        track_flow_message=_track_flow_message,
        message_chat_id=_message_chat_id,
        inline_keyboard_button_type=InlineKeyboardButton,
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, RetryAfter):
        logger.warning(
            "Telegram flood control requested retry_after=%s. Update=%r",
            getattr(error, "retry_after", None),
            update,
        )
        return
    if isinstance(error, NetworkError):
        logger.warning("Temporary Telegram network error. Update=%r error=%s", update, error)
        return
    logger.exception("Unhandled Telegram update error. Update=%r", update, exc_info=error)


async def _post_init(app: Application) -> None:
    await post_init_command_setup(
        app,
        deliver_pending_notification_job=_deliver_pending_notification_job,
        homework_assignment_reminder_job=_homework_assignment_reminder_job,
        daily_assignment_reminder_time=_DAILY_ASSIGNMENT_REMINDER_TIME,
        job_queue_or_none=_job_queue_or_none,
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
    from englishbot.telegram_notifications import pending_notifications

    return pending_notifications(context)


def _pending_notification_repository(context: ContextTypes.DEFAULT_TYPE):
    from englishbot.telegram_notifications import pending_notification_repository

    return pending_notification_repository(context)


def _recent_assignment_activity_by_user(context: ContextTypes.DEFAULT_TYPE) -> dict[int, datetime]:
    from englishbot.telegram_notifications import recent_assignment_activity_by_user

    return recent_assignment_activity_by_user(context)


def _notification_action_button_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification_key: str,
    user_id: int,
) -> InlineKeyboardButton:
    from englishbot.telegram_notifications import notification_action_button_for_user

    return notification_action_button_for_user(
        context,
        notification_key=notification_key,
        user_id=user_id,
    )


def _dismiss_notification_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification_key: str,
    user_id: int,
) -> InlineKeyboardMarkup:
    from englishbot.telegram_notifications import dismiss_notification_keyboard

    return dismiss_notification_keyboard(
        context,
        notification_key=notification_key,
        user_id=user_id,
    )


def _notification_wait_seconds(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> float:
    from englishbot.telegram_notifications import notification_wait_seconds

    return notification_wait_seconds(context, user_id=user_id)


def _notification_should_wait(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> bool:
    from englishbot.telegram_notifications import notification_should_wait

    return notification_should_wait(context, user_id=user_id)


def _record_assignment_activity(context: ContextTypes.DEFAULT_TYPE, *, user_id: int) -> None:
    from englishbot.telegram_notifications import record_assignment_activity

    record_assignment_activity(context, user_id=user_id)


def _schedule_notification(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification: _PendingNotification,
) -> None:
    from englishbot.telegram_notifications import schedule_notification

    schedule_notification(
        context,
        notification=notification,
    )


async def _deliver_notification_now(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notification_key: str,
    force: bool = False,
) -> bool:
    from englishbot.telegram_notifications import deliver_notification_now

    return await deliver_notification_now(
        context,
        notification_key=notification_key,
        force=force,
    )


async def _deliver_pending_notification_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_notifications import deliver_pending_notification_job

    await deliver_pending_notification_job(context)


async def _homework_assignment_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram_notifications import homework_assignment_reminder_job

    await homework_assignment_reminder_job(context)


async def _flush_pending_notifications_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
) -> None:
    from englishbot.telegram_notifications import flush_pending_notifications_for_user

    await flush_pending_notifications_for_user(context, user_id=user_id)


def _schedule_assignment_assigned_notifications(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    goals: list,
) -> None:
    from englishbot.telegram_notifications import schedule_assignment_assigned_notifications

    schedule_assignment_assigned_notifications(
        context,
        goals=goals,
    )


def _schedule_goal_completed_notifications(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    learner,
    completed_goals: tuple[GoalProgressView, ...],
) -> None:
    from englishbot.telegram_notifications import schedule_goal_completed_notifications

    schedule_goal_completed_notifications(
        context,
        learner=learner,
        completed_goals=completed_goals,
    )


async def _delete_tracked_messages(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    tracked_messages,
) -> None:
    from englishbot.telegram_flow_tracking import delete_tracked_messages

    await delete_tracked_messages(
        context,
        tracked_messages=tracked_messages,
    )


async def _delete_tracked_flow_messages(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    tag: str,
) -> None:
    from englishbot.telegram_flow_tracking import delete_tracked_flow_messages

    await delete_tracked_flow_messages(
        context,
        flow_id=flow_id,
        tag=tag,
    )


async def _ensure_chat_menu_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
    user,
) -> None:
    from englishbot.telegram_flow_tracking import ensure_chat_menu_message

    await ensure_chat_menu_message(
        context,
        message=message,
        user=user,
    )


async def _delete_message_if_possible(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
) -> None:
    from englishbot.telegram_flow_tracking import delete_message_if_possible

    await delete_message_if_possible(
        context,
        message=message,
    )


def _tracked_messages_except_source_message(*, tracked_messages, message) -> list:
    from englishbot.telegram_flow_tracking import tracked_messages_except_source_message

    return tracked_messages_except_source_message(
        tracked_messages=tracked_messages,
        message=message,
    )


def _track_flow_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow_id: str,
    tag: str,
    message,
    fallback_chat_id: int | None = None,
) -> None:
    from englishbot.telegram_flow_tracking import track_flow_message

    track_flow_message(
        context,
        flow_id=flow_id,
        tag=tag,
        message=message,
        fallback_chat_id=fallback_chat_id,
    )


def _published_word_edit_flow_id(*, user_id: int) -> str:
    from englishbot.telegram_flow_tracking import published_word_edit_flow_id

    return published_word_edit_flow_id(user_id=user_id)


def _tts_voice_flow_id(*, user_id: int) -> str:
    from englishbot.telegram_flow_tracking import tts_voice_flow_id

    return tts_voice_flow_id(user_id=user_id)


async def _reply_voice_replacing_previous_tts(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    message,
    voice,
):
    from englishbot.telegram_flow_tracking import reply_voice_replacing_previous_tts

    return await reply_voice_replacing_previous_tts(
        context=context,
        user_id=user_id,
        message=message,
        voice=voice,
    )


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
    round_batch_size: int | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return ui_assignment_round_complete_keyboard(
        kind,
        tg=_tg,
        has_more=has_more,
        remaining_word_count=remaining_word_count,
        round_batch_size=round_batch_size,
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
    context: ContextTypes.DEFAULT_TYPE | None = None,
    user_id: int | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    if context is not None and user_id is not None:
        rows: list[list[InlineKeyboardButton]] = []
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                continue
            english_word = str(raw_item.get("english_word", "")).strip() or str(
                raw_item.get("id", "")
            ).strip()
            translation = str(raw_item.get("translation", "")).strip()
            has_image = bool(str(raw_item.get("image_ref", "")).strip())
            label = _editable_word_button_label(
                english_word=english_word,
                translation=translation,
                has_image=has_image,
            )
            rows.append(
                [
                    InlineKeyboardButton(
                        label[:64],
                        callback_data=_published_image_item_callback_data(
                            context=context,
                            user_id=user_id,
                            topic_id=topic_id,
                            item_index=index,
                        ),
                    )
                ]
            )
        if not rows:
            rows = [[InlineKeyboardButton(_tg("no_items", language=language), callback_data="words:menu")]]
        return InlineKeyboardMarkup(rows)
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
    context: ContextTypes.DEFAULT_TYPE | None = None,
    user_id: int | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    if context is not None and user_id is not None:
        rows = [
            [
                InlineKeyboardButton(
                    _editable_word_button_label(
                        english_word=word.english_word,
                        translation=word.translation,
                        has_image=getattr(word, "has_image", False),
                    )[:64],
                    callback_data=_editable_word_callback_data(
                        context=context,
                        user_id=user_id,
                        topic_id=topic_id,
                        item_index=index,
                    ),
                )
            ]
            for index, word in enumerate(words)
        ]
        if not rows:
            rows = [[InlineKeyboardButton(_tg("no_words", language=language), callback_data="words:menu")]]
        return InlineKeyboardMarkup(rows)
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
    return menu_chat_menu_keyboard(command_rows=command_rows)


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
    store = _optional_bot_data(context, "content_store")
    if store is None:
        return {}
    counts: dict[str, int] = {}
    for topic_id in topic_ids:
        try:
            counts[topic_id] = len(store.list_vocabulary_by_topic(topic_id))
        except Exception:  # noqa: BLE001
            logger.debug("Failed to count topic items for topic_id=%s", topic_id, exc_info=True)
    return counts


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
