from __future__ import annotations

import asyncio
import json
import logging

from telegram import (
    BotCommand,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
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
)
from englishbot.application.add_words_use_cases import (
    ApplyAddWordsEditUseCase,
    ApproveAddWordsDraftUseCase,
    CancelAddWordsFlowUseCase,
    GetActiveAddWordsFlowUseCase,
    RegenerateAddWordsDraftUseCase,
    StartAddWordsFlowUseCase,
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
from englishbot.image_generation.paths import resolve_existing_image_path
from englishbot.importing.draft_io import draft_to_data
from englishbot.infrastructure.repositories import InMemoryAddWordsFlowRepository
from englishbot.presentation.add_words_text import (
    format_draft_edit_text,
    format_draft_preview,
)

logger = logging.getLogger(__name__)

_ADD_WORDS_AWAITING_TEXT = "awaiting_raw_text"
_ADD_WORDS_AWAITING_EDIT_TEXT = "awaiting_edit_text"


def build_application(settings: Settings) -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    app.bot_data["training_service"] = build_training_service()
    lesson_import_pipeline = build_lesson_import_pipeline(
        ollama_model=settings.ollama_model,
        ollama_base_url=settings.ollama_base_url,
    )
    add_words_flow_repository = InMemoryAddWordsFlowRepository()
    add_words_harness = AddWordsFlowHarness(
        pipeline=lesson_import_pipeline,
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
    app.bot_data["add_words_cancel_use_case"] = CancelAddWordsFlowUseCase(
        add_words_flow_repository
    )
    app.bot_data["word_import_preview_message_ids"] = {}

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
        CallbackQueryHandler(
            add_words_approve_draft_handler,
            pattern=r"^words:approve_draft:",
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
            add_words_cancel_callback_handler,
            pattern=r"^words:cancel:",
        )
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


def _cancel_add_words_flow(context: ContextTypes.DEFAULT_TYPE) -> CancelAddWordsFlowUseCase:
    return context.application.bot_data["add_words_cancel_use_case"]


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
    await query.edit_message_text(
        "Words menu.",
        reply_markup=_words_menu_keyboard(
            is_editor=bool(update.effective_user and _is_editor(update.effective_user.id, context))
        ),
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
    if words_flow_mode not in {_ADD_WORDS_AWAITING_TEXT, _ADD_WORDS_AWAITING_EDIT_TEXT}:
        return
    message = update.effective_message
    user = update.effective_user
    if message is None or message.text is None or user is None:
        return
    if not _is_editor(user.id, context):
        context.user_data.pop("words_flow_mode", None)
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
    finally:
        stop_event.set()
        await heartbeat_task
    context.user_data.pop("words_flow_mode", None)
    await status_message.edit_text(
        "Parsing draft... done\n"
        f"Items found: {len(flow.draft_result.draft.vocabulary_items)}\n"
        f"Validation errors: {len(flow.draft_result.validation.errors)}"
    )
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
    await query.edit_message_text("Regenerating draft... 0/1")
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _run_status_heartbeat(
            query,
            stage="Regenerating draft",
            stop_event=stop_event,
        )
    )
    try:
        flow = await asyncio.to_thread(
            _regenerate_add_words_draft(context).execute,
            user_id=user.id,
            flow_id=flow.flow_id,
        )
    finally:
        stop_event.set()
        await heartbeat_task
    await query.edit_message_text(
        format_draft_preview(flow.draft_result),
        reply_markup=_draft_review_keyboard(flow.flow_id, flow.draft_result.validation.is_valid),
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
    interval_seconds: float = 3.0,
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

def _draft_review_keyboard(flow_id: str, is_valid: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                "Approve Draft",
                callback_data=f"words:approve_draft:{flow_id}",
            ),
            InlineKeyboardButton(
                "Regenerate Draft",
                callback_data=f"words:regenerate_draft:{flow_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "Edit Text",
                callback_data=f"words:edit_text:{flow_id}",
            ),
            InlineKeyboardButton(
                "Show JSON",
                callback_data=f"words:show_json:{flow_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "Cancel",
                callback_data=f"words:cancel:{flow_id}",
            ),
        ],
    ]
    if not is_valid:
        rows[0][0] = InlineKeyboardButton("Approve Disabled", callback_data="words:menu")
    return InlineKeyboardMarkup(rows)


def _words_menu_keyboard(*, is_editor: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("Training Topics", callback_data="words:menu")]]
    if is_editor:
        rows.append([InlineKeyboardButton("Add Words", callback_data="words:menu")])
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
