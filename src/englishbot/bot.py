from __future__ import annotations

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
    TrainingApplicationService,
)
from englishbot.bootstrap import build_training_service
from englishbot.domain.models import Topic, TrainingMode, TrainingQuestion


def build_application(token: str) -> Application:
    service = build_training_service()
    app = Application.builder().token(token).build()
    app.bot_data["training_service"] = service
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(topic_selected_handler, pattern=r"^topic:"))
    app.add_handler(CallbackQueryHandler(mode_selected_handler, pattern=r"^mode:"))
    app.add_handler(CallbackQueryHandler(choice_answer_handler, pattern=r"^answer:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_answer_handler))
    return app


def _service(context: ContextTypes.DEFAULT_TYPE) -> TrainingApplicationService:
    return context.application.bot_data["training_service"]


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topics = _service(context).list_topics()
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "Choose a topic to start training.",
        reply_markup=_topic_keyboard(topics),
    )


async def topic_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    topic_id = query.data.removeprefix("topic:")
    await query.edit_message_text(
        "Choose a training mode.",
        reply_markup=_mode_keyboard(topic_id),
    )


async def mode_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _, topic_id, mode_value = query.data.split(":")
    service = _service(context)
    user = update.effective_user
    if user is None:
        return
    try:
        question = service.start_session(
            user_id=user.id,
            topic_id=topic_id,
            mode=TrainingMode(mode_value),
        )
    except ApplicationError as error:
        await query.edit_message_text(str(error))
        return
    context.user_data["awaiting_text_answer"] = question.mode is TrainingMode.HARD
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
        outcome.next_question is not None and outcome.next_question.mode is TrainingMode.HARD
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
    await message.reply_text(question.prompt, reply_markup=reply_markup)


def _topic_keyboard(topics: list[Topic]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(topic.title, callback_data=f"topic:{topic.id}")] for topic in topics]
    )


def _mode_keyboard(topic_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Easy", callback_data=f"mode:{topic_id}:{TrainingMode.EASY.value}"
                ),
                InlineKeyboardButton(
                    "Medium", callback_data=f"mode:{topic_id}:{TrainingMode.MEDIUM.value}"
                ),
                InlineKeyboardButton(
                    "Hard", callback_data=f"mode:{topic_id}:{TrainingMode.HARD.value}"
                ),
            ]
        ]
    )
