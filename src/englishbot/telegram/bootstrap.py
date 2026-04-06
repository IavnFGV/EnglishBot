from __future__ import annotations

import random
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from englishbot.application.add_words_flow import AddWordsFlowHarness
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
from englishbot.application.content_pack_image_use_cases import GenerateContentPackImagesUseCase
from englishbot.application.homework_progress_use_cases import (
    AssignGoalToUsersUseCase,
    GetAdminGoalDetailUseCase,
    GetAdminUserGoalsUseCase,
    GetAdminUsersProgressOverviewUseCase,
    GetGoalWordCandidatesUseCase,
    GetLearnerAssignmentLaunchSummaryUseCase,
    GetUserProgressSummaryUseCase,
    HomeworkProgressUseCase,
    ListUserGoalsUseCase,
    StartAssignmentRoundUseCase,
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
from englishbot.application.services import QuestionFactory
from englishbot.bootstrap import build_lesson_import_pipeline, build_training_service
from englishbot.config import RuntimeConfigService, Settings
from englishbot.image_generation.clients import (
    ComfyUIImageGenerationClient,
    LocalPlaceholderImageGenerationClient,
)
from englishbot.image_generation.pipeline import ContentPackImageEnricher
from englishbot.image_generation.pixabay import PixabayImageSearchClient, RemoteImageDownloader
from englishbot.image_generation.resilient import ResilientImageGenerator
from englishbot.image_generation.review import ComfyUIImageCandidateGenerator
from englishbot.image_generation.smart_generation import (
    ComfyUIImageGenerationGateway,
    DisabledImageGenerationGateway,
)
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import OllamaLessonExtractionClient
from englishbot.importing.smart_parsing import (
    DisabledSmartLessonParsingGateway,
    OllamaSmartLessonParsingGateway,
)
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.sqlite_store import (
    SQLiteAddWordsFlowRepository,
    SQLiteContentStore,
    SQLiteImageReviewFlowRepository,
    SQLitePendingTelegramNotificationRepository,
    SQLiteSessionRepository,
    SQLiteTelegramFlowMessageRepository,
    SQLiteTelegramUserLoginRepository,
    SQLiteTelegramUserRoleRepository,
    SQLiteUserProgressRepository,
    SQLiteVocabularyRepository,
)
from englishbot.runtime_version import get_runtime_version_info


def build_application(
    settings: Settings,
    *,
    config_service: RuntimeConfigService,
) -> Application:
    from englishbot import bot as bot_module

    app = Application.builder().token(settings.telegram_token).build()
    content_store = SQLiteContentStore(db_path=settings.content_db_path)
    content_store.initialize()
    app.bot_data["content_store"] = content_store
    app.bot_data["config_service"] = config_service
    app.bot_data["settings"] = settings
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
    app.bot_data["telegram_ui_language"] = bot_module._normalize_telegram_ui_language(
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
    app.bot_data["get_user_progress_summary_use_case"] = GetUserProgressSummaryUseCase(
        store=content_store
    )
    app.bot_data["learner_assignment_launch_summary_use_case"] = (
        GetLearnerAssignmentLaunchSummaryUseCase(store=content_store)
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

    app.add_handler(TypeHandler(Update, bot_module.raw_update_logger_handler), group=-1)
    app.add_handler(CommandHandler("start", bot_module.start_handler))
    app.add_handler(CommandHandler("help", bot_module.help_handler))
    app.add_handler(CommandHandler("version", bot_module.version_handler))
    app.add_handler(CommandHandler("words", bot_module.words_menu_handler))
    app.add_handler(CommandHandler("assign", bot_module.assign_menu_handler))
    app.add_handler(CommandHandler("add_words", bot_module.add_words_start_handler))
    app.add_handler(CommandHandler("cancel", bot_module.add_words_cancel_handler))
    app.add_handler(CommandHandler("makeadmin", bot_module.makeadmin_handler))
    app.add_handler(CommandHandler("clearuser", bot_module.clear_user_handler))
    app.add_handler(
        ChatMemberHandler(bot_module.chat_member_logger_handler, ChatMemberHandler.ANY_CHAT_MEMBER)
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.continue_session_handler, pattern=r"^session:continue$")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.restart_session_handler, pattern=r"^session:restart$")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.start_menu_callback_handler, pattern=r"^start:menu$")
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.start_assignment_round_callback_handler,
            pattern=r"^start:launch:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.start_assignment_unavailable_callback_handler,
            pattern=r"^start:disabled:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.game_mode_placeholder_callback_handler, pattern=r"^start:game$")
    )
    app.add_handler(CallbackQueryHandler(bot_module.topic_selected_handler, pattern=r"^topic:"))
    app.add_handler(CallbackQueryHandler(bot_module.lesson_selected_handler, pattern=r"^lesson:"))
    app.add_handler(
        CallbackQueryHandler(bot_module.game_mode_placeholder_callback_handler, pattern=r"^gameentry:")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.game_mode_placeholder_callback_handler, pattern=r"^gamemode:")
    )
    app.add_handler(CallbackQueryHandler(bot_module.game_next_round_handler, pattern=r"^game:next_round$"))
    app.add_handler(CallbackQueryHandler(bot_module.game_repeat_handler, pattern=r"^game:repeat$"))
    app.add_handler(CallbackQueryHandler(bot_module.mode_selected_handler, pattern=r"^mode:"))
    app.add_handler(CallbackQueryHandler(bot_module.tts_current_handler, pattern=r"^tts:current$"))
    app.add_handler(CallbackQueryHandler(bot_module.tts_voice_menu_handler, pattern=r"^tts:voices$"))
    app.add_handler(
        CallbackQueryHandler(bot_module.tts_voice_select_handler, pattern=r"^tts:voice:(?:\d+|back)$")
    )
    app.add_handler(CallbackQueryHandler(bot_module.hard_skip_handler, pattern=r"^hard:skip:"))
    app.add_handler(CallbackQueryHandler(bot_module.medium_answer_callback_handler, pattern=r"^medium:"))
    app.add_handler(CallbackQueryHandler(bot_module.choice_answer_handler, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(bot_module.words_menu_callback_handler, pattern=r"^words:menu$"))
    app.add_handler(CallbackQueryHandler(bot_module.assign_menu_callback_handler, pattern=r"^assign:menu$"))
    app.add_handler(CallbackQueryHandler(bot_module.noop_callback_handler, pattern=r"^assign:noop$"))
    app.add_handler(
        CallbackQueryHandler(
            bot_module.notification_dismiss_callback_handler,
            pattern=rf"^{bot_module._NOTIFICATION_DISMISS_CALLBACK}$",
        )
    )
    app.add_handler(CallbackQueryHandler(bot_module.words_goals_callback_handler, pattern=r"^assign:goals$"))
    app.add_handler(
        CallbackQueryHandler(bot_module.words_progress_callback_handler, pattern=r"^assign:progress$")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.goal_setup_disabled_callback_handler, pattern=r"^assign:goal_setup$")
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.goal_setup_disabled_callback_handler,
            pattern=r"^assign:goal_target_menu$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.goal_setup_disabled_callback_handler, pattern=r"^words:goal_period:")
    )
    app.add_handler(CallbackQueryHandler(bot_module.goal_type_callback_handler, pattern=r"^words:goal_type:"))
    app.add_handler(
        CallbackQueryHandler(bot_module.goal_setup_disabled_callback_handler, pattern=r"^words:goal_target:")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.goal_setup_disabled_callback_handler, pattern=r"^words:goal_source:")
    )
    app.add_handler(CallbackQueryHandler(bot_module.goal_reset_callback_handler, pattern=r"^words:goal_reset:"))
    app.add_handler(
        CallbackQueryHandler(bot_module.admin_assign_goal_start_handler, pattern=r"^assign:admin_assign_goal$")
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.admin_goal_target_menu_callback_handler,
            pattern=r"^assign:admin_goal_target_menu$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.admin_goal_source_menu_callback_handler,
            pattern=r"^assign:admin_goal_source_menu$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.admin_goal_period_callback_handler, pattern=r"^words:admin_goal_period:")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.admin_goal_target_callback_handler, pattern=r"^words:admin_goal_target:")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.admin_goal_source_callback_handler, pattern=r"^words:admin_goal_source:")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.admin_goal_deadline_callback_handler, pattern=r"^words:admin_goal_deadline:")
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.admin_goal_manual_toggle_callback_handler,
            pattern=r"^words:admin_goal_manual:toggle:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.admin_goal_manual_toggle_callback_handler,
            pattern=r"^words:admin_goal_manual:page:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.admin_goal_manual_done_callback_handler,
            pattern=r"^words:admin_goal_manual:done$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.admin_goal_recipients_callback_handler,
            pattern=r"^assign:admin_goal_recipients:",
        )
    )
    app.add_handler(CallbackQueryHandler(bot_module.admin_users_progress_callback_handler, pattern=r"^assign:users$"))
    app.add_handler(CallbackQueryHandler(bot_module.assign_user_detail_callback_handler, pattern=r"^assign:user:"))
    app.add_handler(CallbackQueryHandler(bot_module.assign_goal_detail_callback_handler, pattern=r"^assign:goal:"))
    app.add_handler(CallbackQueryHandler(bot_module.words_topics_callback_handler, pattern=r"^words:topics$"))
    app.add_handler(CallbackQueryHandler(bot_module.words_add_words_callback_handler, pattern=r"^words:add_words$"))
    app.add_handler(
        CallbackQueryHandler(bot_module.words_edit_images_callback_handler, pattern=r"^words:edit_images$")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.words_edit_words_callback_handler, pattern=r"^words:edit_words$")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.words_edit_topic_callback_handler, pattern=r"^words:edit_topic:")
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.words_edit_cancel_callback_handler,
            pattern=r"^words:edit_item_cancel:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.words_edit_item_callback_handler, pattern=r"^words:edit_item:")
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.add_words_approve_auto_images_handler,
            pattern=r"^words:approve_auto_images:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.add_words_publish_without_images_handler,
            pattern=r"^words:approve_draft:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.add_words_approve_draft_handler,
            pattern=r"^words:start_image_review:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.add_words_regenerate_draft_handler,
            pattern=r"^words:regenerate_draft:",
        )
    )
    app.add_handler(CallbackQueryHandler(bot_module.add_words_edit_text_handler, pattern=r"^words:edit_text:"))
    app.add_handler(CallbackQueryHandler(bot_module.add_words_show_json_handler, pattern=r"^words:show_json:"))
    app.add_handler(
        CallbackQueryHandler(bot_module.published_images_menu_handler, pattern=r"^words:edit_images_menu:")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.published_image_item_handler, pattern=r"^words:edit_published_image:")
    )
    app.add_handler(CallbackQueryHandler(bot_module.image_review_pick_handler, pattern=r"^words:image_pick:"))
    app.add_handler(
        CallbackQueryHandler(bot_module.image_review_generate_handler, pattern=r"^words:image_generate:")
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.image_review_search_handler, pattern=r"^words:image_search:")
    )
    app.add_handler(CallbackQueryHandler(bot_module.image_review_next_handler, pattern=r"^words:image_next:"))
    app.add_handler(
        CallbackQueryHandler(bot_module.image_review_previous_handler, pattern=r"^words:image_previous:")
    )
    app.add_handler(CallbackQueryHandler(bot_module.image_review_skip_handler, pattern=r"^words:image_skip:"))
    app.add_handler(
        CallbackQueryHandler(
            bot_module.image_review_edit_prompt_handler,
            pattern=r"^words:image_edit_prompt:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.image_review_edit_search_query_handler,
            pattern=r"^words:image_edit_search_query:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.image_review_show_json_handler, pattern=r"^words:image_show_json:")
    )
    app.add_handler(
        CallbackQueryHandler(
            bot_module.image_review_attach_photo_handler,
            pattern=r"^words:image_attach_photo:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(bot_module.add_words_cancel_callback_handler, pattern=r"^words:cancel:")
    )
    app.add_handler(MessageHandler(filters.PHOTO, bot_module.image_review_photo_handler), group=0)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_module.add_words_text_handler),
        group=0,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_module.goal_text_handler),
        group=0,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_module.text_answer_handler),
        group=1,
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
            bot_module.group_text_observer_handler,
        ),
        group=2,
    )
    app.add_error_handler(bot_module.error_handler)
    app.post_init = bot_module._post_init
    return app
