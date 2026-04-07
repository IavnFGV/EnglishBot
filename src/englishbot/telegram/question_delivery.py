from __future__ import annotations

import html
from collections.abc import Callable

from telegram import InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from englishbot.domain.models import TrainingMode
from englishbot.presentation.telegram_views import TelegramPhotoView, TelegramTextView
from englishbot.presentation.telegram_views import build_training_question_view
from englishbot.presentation.telegram_views import send_telegram_view
from englishbot.presentation.telegram_ui_text import telegram_ui_text


def medium_task_is_complete(state) -> bool:
    return len(state.selected_letter_indexes) >= sum(
        1 for character in state.target_word if not character.isspace()
    )


def medium_task_slots_text(state) -> str:
    selected_letters = [state.shuffled_letters[index] for index in state.selected_letter_indexes]
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


def medium_task_answer_text(state) -> str:
    selected_letters = iter(state.shuffled_letters[index] for index in state.selected_letter_indexes)
    assembled: list[str] = []
    for character in state.target_word:
        if character.isspace():
            assembled.append(character)
            continue
        assembled.append(next(selected_letters, ""))
    return "".join(assembled)


def medium_task_keyboard(
    state,
    *,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    user=None,
    tts_service_enabled: Callable,
    tts_buttons: Callable,
    tg: Callable,
    inline_keyboard_button_type,
) -> InlineKeyboardMarkup:
    selected_indexes = set(state.selected_letter_indexes)
    buttons = [
        inline_keyboard_button_type(
            "·" if index in selected_indexes else letter,
            callback_data=(
                f"medium:noop:{index}"
                if index in selected_indexes
                else f"medium:pick:{index}"
            ),
        )
        for index, letter in enumerate(state.shuffled_letters)
    ]
    rows: list[list[object]] = []
    row_width = 4
    for start in range(0, len(buttons), row_width):
        rows.append(buttons[start : start + row_width])
    check_callback = "medium:check" if medium_task_is_complete(state) else "medium:noop:check"
    rows.append([inline_keyboard_button_type("⌫", callback_data="medium:backspace")])
    if context is not None and tts_service_enabled(context):
        rows[-1].extend(tts_buttons(context=context, user=user))
    rows.append(
        [
            inline_keyboard_button_type(
                (
                    tg("medium_check_button", context=context, user=user)
                    if context is not None
                    else telegram_ui_text("medium_check_button")
                ),
                callback_data=check_callback,
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_medium_question_text(question, state) -> str:
    translation = question.prompt.strip()
    for line in question.prompt.splitlines():
        stripped = line.strip()
        if stripped.startswith("Translation:"):
            translation = stripped.removeprefix("Translation:").strip()
            break
    slots = html.escape(medium_task_slots_text(state))
    return f"🧩 <b>{html.escape(translation)}</b>\n\n<b>{slots}</b>"


def build_medium_question_view(
    question,
    *,
    state,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    user=None,
    resolve_existing_image_path: Callable,
    tts_service_enabled: Callable,
    tts_buttons: Callable,
    tg: Callable,
    inline_keyboard_button_type,
) -> TelegramTextView | TelegramPhotoView:
    image_path = resolve_existing_image_path(question.image_ref)
    return build_training_question_view(
        question,
        image_path=image_path,
        reply_markup=medium_task_keyboard(
            state,
            context=context,
            user=user,
            tts_service_enabled=tts_service_enabled,
            tts_buttons=tts_buttons,
            tg=tg,
            inline_keyboard_button_type=inline_keyboard_button_type,
        ),
        body_text_override=build_medium_question_text(question, state),
    )


async def edit_training_question_view(
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


async def send_question(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    question,
    *,
    delete_tracked_flow_messages: Callable,
    training_question_tag: str,
    clear_medium_task_state: Callable,
    active_training_session: Callable,
    build_medium_task_state: Callable,
    build_medium_question_view: Callable,
    tts_service_enabled: Callable,
    tts_buttons: Callable,
    resolve_existing_image_path: Callable,
    hard_skip_keyboard: Callable,
    set_medium_task_state: Callable,
    track_flow_message: Callable,
    message_chat_id: Callable,
    inline_keyboard_button_type,
) -> None:
    message = update.effective_message
    user = getattr(update, "effective_user", None)
    if message is None:
        return
    await delete_tracked_flow_messages(
        context,
        flow_id=question.session_id,
        tag=training_question_tag,
    )
    clear_medium_task_state(context)
    view: TelegramTextView | TelegramPhotoView
    reply_markup = None
    active_session = active_training_session(context, user_id=user.id) if user is not None else None
    if question.mode is TrainingMode.MEDIUM:
        view = build_medium_question_view(
            question,
            state=build_medium_task_state(question),
            context=context,
            user=user,
        )
    elif question.options:
        rows = [
            [inline_keyboard_button_type(option, callback_data=f"answer:{option}")]
            for option in question.options
        ]
        if tts_service_enabled(context):
            rows.append(tts_buttons(context=context, user=user))
        reply_markup = InlineKeyboardMarkup(rows)
        image_path = resolve_existing_image_path(question.image_ref)
        view = build_training_question_view(
            question,
            image_path=image_path,
            reply_markup=reply_markup,
        )
    else:
        if (
            user is not None
            and active_session is not None
            and active_session.id == question.session_id
            and question.mode is TrainingMode.HARD
        ):
            reply_markup = hard_skip_keyboard(
                context=context,
                user=user,
                session_id=question.session_id,
            )
        image_path = resolve_existing_image_path(question.image_ref)
        view = build_training_question_view(
            question,
            image_path=image_path,
            reply_markup=reply_markup,
        )
    sent_message = await send_telegram_view(message, view)
    if question.mode is TrainingMode.MEDIUM:
        set_medium_task_state(
            context,
            build_medium_task_state(question, message_id=getattr(sent_message, "message_id", None)),
        )
    track_flow_message(
        context,
        flow_id=question.session_id,
        tag=training_question_tag,
        message=sent_message,
        fallback_chat_id=message_chat_id(message),
    )
