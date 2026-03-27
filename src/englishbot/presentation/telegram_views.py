from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

from englishbot.domain.models import TrainingMode, TrainingQuestion
from englishbot.importing.models import ImportLessonResult
from englishbot.presentation.add_words_text import format_draft_preview

if TYPE_CHECKING:
    from englishbot.application.services import AnswerOutcome

TelegramReplyMarkup = InlineKeyboardMarkup | ReplyKeyboardMarkup


@dataclass(frozen=True)
class TelegramTextView:
    text: str
    reply_markup: TelegramReplyMarkup | None = None
    parse_mode: str | None = None


@dataclass(frozen=True)
class TelegramPhotoView:
    photo_path: Path
    caption: str
    reply_markup: TelegramReplyMarkup | None = None
    parse_mode: str | None = None


TelegramView = TelegramTextView | TelegramPhotoView


def build_training_question_view(
    question: TrainingQuestion,
    *,
    image_path: Path | None,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramView:
    rendered_question = _render_compact_training_question(question)
    if image_path is not None:
        return TelegramPhotoView(
            photo_path=image_path,
            caption=rendered_question,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    return TelegramTextView(
        text=rendered_question,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


def build_answer_feedback_view(
    outcome: AnswerOutcome,
    *,
    translate: Callable[..., str],
    user=None,
) -> TelegramTextView:
    if outcome.result.is_correct:
        text = translate("correct", user=user)
    else:
        text = translate(
            "not_quite",
            user=user,
            expected_answer=outcome.result.expected_answer,
        )
    if outcome.summary is not None:
        text += translate(
            "session_complete",
            user=user,
            correct_answers=outcome.summary.correct_answers,
            total_questions=outcome.summary.total_questions,
        )
    return TelegramTextView(text=text)


def build_draft_preview_view(
    result: ImportLessonResult,
    *,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(
        text=format_draft_preview(result),
        reply_markup=reply_markup,
    )


def build_active_session_exists_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_topic_selection_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_lesson_selection_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_mode_selection_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_words_menu_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_quick_actions_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_status_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_help_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_editable_topics_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_editable_words_view(
    *,
    text: str,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=text, reply_markup=reply_markup)


def build_published_word_edit_prompt_view(
    *,
    instruction_text: str,
    current_value_text: str,
    instruction_markup: TelegramReplyMarkup | None = None,
    current_value_markup: TelegramReplyMarkup | None = None,
) -> tuple[TelegramTextView, TelegramTextView]:
    return (
        TelegramTextView(text=instruction_text, reply_markup=instruction_markup),
        TelegramTextView(text=current_value_text, reply_markup=current_value_markup),
    )


def build_image_review_prompt_edit_view(
    *,
    instruction_text: str,
    current_prompt_text: str,
    instruction_markup: TelegramReplyMarkup | None = None,
) -> tuple[TelegramTextView, TelegramTextView]:
    return (
        TelegramTextView(text=instruction_text, reply_markup=instruction_markup),
        TelegramTextView(text=current_prompt_text),
    )


def build_image_review_search_query_edit_view(
    *,
    instruction_text: str,
    current_query_text: str,
    instruction_markup: TelegramReplyMarkup | None = None,
) -> tuple[TelegramTextView, TelegramTextView]:
    return (
        TelegramTextView(text=instruction_text, reply_markup=instruction_markup),
        TelegramTextView(text=current_query_text),
    )


def build_image_review_attach_photo_view(
    *,
    instruction_text: str,
    instruction_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    return TelegramTextView(text=instruction_text, reply_markup=instruction_markup)


def build_current_image_preview_view(
    *,
    image_path: Path | None,
    current_image_intro: str,
    no_current_image_intro: str,
) -> TelegramView:
    if image_path is None:
        return TelegramTextView(text=no_current_image_intro)
    return TelegramPhotoView(
        photo_path=image_path,
        caption=current_image_intro,
    )


def build_image_review_step_view(
    *,
    current_position: int,
    total_items: int,
    english_word: str,
    translation: str,
    prompt: str,
    candidate_source_type: str,
    search_query: str | None,
    search_page: int,
    generation_status_messages: list[str] | None,
    reply_markup: TelegramReplyMarkup | None = None,
) -> TelegramTextView:
    search_line = "Pixabay search: word only by default."
    source_line = "No candidates loaded yet."
    if candidate_source_type == "pixabay":
        source_line = f"Pixabay candidates page {search_page}"
        if search_query:
            search_line = f"Pixabay search query: {search_query}"
    elif candidate_source_type == "generated":
        source_line = "Local AI candidates."
    text = (
        "Reviewing images "
        f"{current_position}/{total_items}\n"
        f"{english_word} — {translation}\n"
        f"Prompt: {prompt}\n"
        "Prompt is used for local AI generation.\n"
        f"{search_line}\n"
        f"{source_line}"
    )
    if generation_status_messages:
        text += "\n" + "\n".join(generation_status_messages)
    return TelegramTextView(
        text=text,
        reply_markup=reply_markup,
    )


async def send_telegram_view(message, view: TelegramView):
    if isinstance(view, TelegramPhotoView):
        with view.photo_path.open("rb") as photo_file:
            kwargs = {
                "photo": photo_file,
                "caption": view.caption,
                "reply_markup": view.reply_markup,
            }
            if view.parse_mode is not None:
                kwargs["parse_mode"] = view.parse_mode
            return await message.reply_photo(**kwargs)
    kwargs = {
        "text": view.text,
        "reply_markup": view.reply_markup,
    }
    if view.parse_mode is not None:
        kwargs["parse_mode"] = view.parse_mode
    return await message.reply_text(**kwargs)


async def edit_telegram_text_view(target, view: TelegramTextView):
    kwargs = {
        "text": view.text,
        "reply_markup": view.reply_markup,
    }
    if view.parse_mode is not None:
        kwargs["parse_mode"] = view.parse_mode
    return await target.edit_message_text(**kwargs)


def _extract_translation_from_prompt(prompt: str) -> str:
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped.startswith("Translation:"):
            return stripped.removeprefix("Translation:").strip()
    return prompt.strip()


def _render_compact_training_question(question: TrainingQuestion) -> str:
    translation = html.escape(_extract_translation_from_prompt(question.prompt))
    parts = [f"<b>{translation}</b>"]
    if question.mode is not TrainingMode.EASY and question.letter_hint:
        parts.append(f"<b>{html.escape(question.letter_hint)}</b>")
    return "\n\n".join(part for part in parts if part.strip())
