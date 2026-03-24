from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from englishbot.application.services import (
    AnswerOutcome,
    ApplicationError,
    InvalidSessionStateError,
    TrainingFacade,
)
from englishbot.bootstrap import build_training_service
from englishbot.domain.models import Topic, TrainingMode, TrainingQuestion

logger = logging.getLogger(__name__)


def build_application(token: str) -> Application:
    service = build_training_service()
    app = Application.builder().token(token).build()
    app.bot_data["training_service"] = service
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(continue_session_handler, pattern=r"^session:continue$"))
    app.add_handler(CallbackQueryHandler(restart_session_handler, pattern=r"^session:restart$"))
    app.add_handler(CallbackQueryHandler(topic_selected_handler, pattern=r"^topic:"))
    app.add_handler(CallbackQueryHandler(lesson_selected_handler, pattern=r"^lesson:"))
    app.add_handler(CallbackQueryHandler(mode_selected_handler, pattern=r"^mode:"))
    app.add_handler(CallbackQueryHandler(choice_answer_handler, pattern=r"^answer:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_answer_handler))
    app.add_error_handler(error_handler)
    return app


def _service(context: ContextTypes.DEFAULT_TYPE) -> TrainingFacade:
    return context.application.bot_data["training_service"]


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
            return
    topics = _service(context).list_topics()
    await message.reply_text(
        "Choose a topic to start training.",
        reply_markup=_topic_keyboard(topics),
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
    logger.info(
        "Continuing session for user %s session_id=%s item_id=%s mode=%s",
        user.id,
        question.session_id,
        question.item_id,
        question.mode.value,
    )
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
    if update.effective_user is not None:
        logger.info("User %s selected topic %s", update.effective_user.id, topic_id)
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
    if update.effective_user is not None:
        logger.info(
            "User %s selected topic %s lesson %s",
            update.effective_user.id,
            topic_id,
            selected_lesson_id or "all",
        )
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
    logger.info(
        "User %s is starting session topic=%s lesson=%s mode=%s",
        user.id,
        topic_id,
        selected_lesson_id or "all",
        mode_value,
    )
    try:
        question = service.start_session(
            user_id=user.id,
            topic_id=topic_id,
            lesson_id=selected_lesson_id,
            mode=TrainingMode(mode_value),
        )
    except ApplicationError as error:
        logger.warning(
            "Failed to start session for user %s topic=%s lesson=%s mode=%s: %s",
            user.id,
            topic_id,
            selected_lesson_id or "all",
            mode_value,
            error,
        )
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
    if update.effective_user is not None:
        logger.info("User %s answered via callback", update.effective_user.id)
    await _process_answer(update, context, answer)


async def text_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("awaiting_text_answer"):
        return
    message = update.effective_message
    if message is None or message.text is None:
        return
    if update.effective_user is not None:
        logger.info("User %s answered via text", update.effective_user.id)
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
        logger.warning("User %s has no active session while answering", user.id)
        await message.reply_text("No active session. Send /start to begin.")
        return
    except ApplicationError as error:
        logger.warning("Application error for user %s: %s", user.id, error)
        await message.reply_text(str(error))
        return
    context.user_data["awaiting_text_answer"] = bool(
        outcome.next_question is not None
        and outcome.next_question.mode in {TrainingMode.MEDIUM, TrainingMode.HARD}
    )
    await _send_feedback(message, outcome)
    if outcome.next_question is not None:
        await _send_question(update, context, outcome.next_question)
    else:
        logger.info("User %s completed the active session", user.id)


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
        logger.info(
            "Sending summary total=%s correct=%s",
            outcome.summary.total_questions,
            outcome.summary.correct_answers,
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
    logger.info(
        "Sending question session_id=%s item_id=%s mode=%s has_options=%s",
        question.session_id,
        question.item_id,
        question.mode.value,
        bool(question.options),
    )
    await message.reply_text(question.prompt, reply_markup=reply_markup)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram update error. Update=%r", update, exc_info=context.error)


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
