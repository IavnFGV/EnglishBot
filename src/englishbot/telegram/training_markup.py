from __future__ import annotations

from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes

from englishbot.domain.models import TrainingMode, TrainingQuestion
from englishbot.telegram.buttons import InlineKeyboardButton


def active_session_id(active_session) -> str | None:
    session_id = getattr(active_session, "session_id", None)
    if isinstance(session_id, str) and session_id.strip():
        return session_id
    legacy_id = getattr(active_session, "id", None)
    if isinstance(legacy_id, str) and legacy_id.strip():
        return legacy_id
    return None


def tts_buttons(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    tg,
    tts_has_multiple_voices,
) -> list[InlineKeyboardButton]:
    row = [
        InlineKeyboardButton(
            tg("tts_play_button", context=context, user=user),
            callback_data="tts:current",
        )
    ]
    if tts_has_multiple_voices(context):
        row.append(
            InlineKeyboardButton(
                tg("tts_voice_menu_button", context=context, user=user),
                callback_data="tts:voices",
            )
        )
    return row


def hard_skip_keyboard(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    session_id: str,
    tg,
    hard_skip_callback_data,
    tts_service_enabled,
    tts_has_multiple_voices,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                tg("hard_skip_button", context=context, user=user),
                callback_data=hard_skip_callback_data(
                    context=context,
                    user_id=int(user.id),
                    session_id=session_id,
                ),
            )
        ]
    ]
    if tts_service_enabled(context):
        rows.append(
            tts_buttons(
                context=context,
                user=user,
                tg=tg,
                tts_has_multiple_voices=tts_has_multiple_voices,
            )
        )
    return InlineKeyboardMarkup(rows)


def question_reply_markup(
    question: TrainingQuestion,
    *,
    active_session,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    get_medium_task_state,
    build_medium_task_state,
    medium_task_keyboard,
    tts_service_enabled,
    tts_buttons_builder,
    hard_skip_keyboard_builder,
) -> InlineKeyboardMarkup | None:
    if question.mode is TrainingMode.MEDIUM:
        state = get_medium_task_state(context)
        if state is None or state.session_id != question.session_id or state.item_id != question.item_id:
            state = build_medium_task_state(question)
        return medium_task_keyboard(state, context=context, user=user)
    if question.options:
        rows = [[InlineKeyboardButton(option, callback_data=f"answer:{option}")] for option in question.options]
        if tts_service_enabled(context):
            rows.append(tts_buttons_builder(context=context, user=user))
        return InlineKeyboardMarkup(rows)
    if (
        user is not None
        and active_session is not None
        and active_session_id(active_session) == question.session_id
        and question.mode is TrainingMode.HARD
    ):
        return hard_skip_keyboard_builder(context=context, user=user, session_id=question.session_id)
    return None


def tts_voice_menu_markup(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    item_id: str,
    tg,
    tts_voice_variants,
    tts_selected_voice_name,
    tts_voice_label,
) -> InlineKeyboardMarkup:
    variants = tts_voice_variants(context)
    selected_voice_name = tts_selected_voice_name(context, item_id=item_id)
    rows: list[list[InlineKeyboardButton]] = []
    for index, voice_name in enumerate(variants):
        prefix = "✓ " if voice_name == selected_voice_name else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{prefix}{tts_voice_label(context, user=user, voice_name=voice_name)}",
                    callback_data=f"tts:voice:{index}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                tg("tts_voice_menu_back_button", context=context, user=user),
                callback_data="tts:voice:back",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)
