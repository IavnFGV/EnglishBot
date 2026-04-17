from __future__ import annotations

import logging
import random
import re

from englishbot.application.errors import NotEnoughOptionsError
from englishbot.domain.models import TrainingMode, TrainingQuestion, TrainingSession, VocabularyItem
from englishbot.logging_utils import logged_service_call
from englishbot.presentation.telegram_ui_text import (
    DEFAULT_TELEGRAM_UI_LANGUAGE,
    telegram_ui_text,
)

logger = logging.getLogger(__name__)


class QuestionFactory:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    @logged_service_call(
        "QuestionFactory.create_question",
        transforms={
            "session": lambda value: {
                "session_id": value.id,
                "mode": value.mode.value,
            },
            "item": lambda value: {"item_id": value.id},
            "all_topic_items": lambda value: {"topic_item_count": len(value)},
        },
        result=lambda question: {
            "question_mode": question.mode.value,
            "has_options": bool(question.options),
        },
    )
    def create_question(
        self,
        *,
        session: TrainingSession,
        item: VocabularyItem,
        all_topic_items: list[VocabularyItem],
    ) -> TrainingQuestion:
        language = session.ui_language or DEFAULT_TELEGRAM_UI_LANGUAGE
        context_hint_line = self._context_hint_line(item, language=language)
        is_bonus_hard = session.bonus_item_id == item.id and session.bonus_mode is not None
        question_mode = session.mode
        for session_item in session.items:
            if session_item.vocabulary_item_id == item.id and session_item.mode is not None:
                question_mode = session_item.mode
                break
        if is_bonus_hard:
            question_mode = session.bonus_mode
            first_letter = next((char for char in item.english_word if char.isalpha()), item.english_word[:1]).upper()
            prompt_lines = [
                telegram_ui_text("question_translation_line", language=language, translation=item.translation),
                *([context_hint_line] if context_hint_line else []),
                telegram_ui_text(
                    "question_visual_line",
                    language=language,
                    clue=self._image_line(item, language=language),
                ),
                telegram_ui_text("question_first_letter_line", language=language, first_letter=first_letter),
                telegram_ui_text("question_bonus_prompt", language=language),
            ]
            prompt = "\n".join(prompt_lines)
            return TrainingQuestion(
                session_id=session.id,
                item_id=item.id,
                mode=question_mode,
                prompt=prompt,
                image_ref=item.image_ref,
                correct_answer=item.english_word,
                input_hint=telegram_ui_text("question_bonus_input_hint", language=language),
                letter_hint=first_letter,
            )
        if session.combo_hard_active:
            question_mode = TrainingMode.HARD
        if question_mode is TrainingMode.EASY:
            options = self._build_choice_options(item, all_topic_items)
            prompt_lines = [
                telegram_ui_text("question_translation_line", language=language, translation=item.translation),
                *([context_hint_line] if context_hint_line else []),
                telegram_ui_text(
                    "question_visual_line",
                    language=language,
                    clue=self._image_line(item, language=language),
                ),
                telegram_ui_text("question_easy_prompt", language=language),
            ]
            prompt = "\n".join(prompt_lines)
            return TrainingQuestion(
                session_id=session.id,
                item_id=item.id,
                mode=question_mode,
                prompt=prompt,
                image_ref=item.image_ref,
                correct_answer=item.english_word,
                options=options,
            )
        if question_mode is TrainingMode.MEDIUM:
            scrambled = self._scramble_word(item.english_word)
            prompt_lines = [
                telegram_ui_text("question_translation_line", language=language, translation=item.translation),
                *([context_hint_line] if context_hint_line else []),
                telegram_ui_text(
                    "question_visual_line",
                    language=language,
                    clue=self._image_line(item, language=language),
                ),
                telegram_ui_text("question_shuffled_letters_line", language=language, letters=scrambled),
                telegram_ui_text("question_medium_prompt", language=language),
            ]
            prompt = "\n".join(prompt_lines)
            return TrainingQuestion(
                session_id=session.id,
                item_id=item.id,
                mode=question_mode,
                prompt=prompt,
                image_ref=item.image_ref,
                correct_answer=item.english_word,
                input_hint=telegram_ui_text("question_medium_input_hint", language=language),
                letter_hint=scrambled,
            )
        first_letter = next((char for char in item.english_word if char.isalpha()), item.english_word[:1]).upper()
        prompt_lines = [
            telegram_ui_text("question_translation_line", language=language, translation=item.translation),
            *([context_hint_line] if context_hint_line else []),
            telegram_ui_text(
                "question_visual_line",
                language=language,
                clue=self._image_line(item, language=language),
            ),
            telegram_ui_text("question_first_letter_line", language=language, first_letter=first_letter),
            telegram_ui_text("question_hard_prompt", language=language),
        ]
        prompt = "\n".join(prompt_lines)
        return TrainingQuestion(
            session_id=session.id,
            item_id=item.id,
            mode=question_mode,
            prompt=prompt,
            image_ref=item.image_ref,
            correct_answer=item.english_word,
            input_hint=telegram_ui_text("question_hard_input_hint", language=language),
            letter_hint=first_letter,
        )

    def _image_line(self, item: VocabularyItem, *, language: str) -> str:
        return telegram_ui_text(
            "question_visual_image_shown" if item.image_ref else "question_visual_no_image",
            language=language,
        )

    def _context_hint_line(self, item: VocabularyItem, *, language: str) -> str | None:
        if not item.meaning_hint:
            return None
        masked_hint = self._mask_hint_answer(item.meaning_hint, answer=item.english_word)
        return telegram_ui_text("question_context_hint_line", language=language, hint=masked_hint)

    def _mask_hint_answer(self, hint: str, *, answer: str) -> str:
        normalized_hint = hint.strip()
        normalized_answer = answer.strip()
        if not normalized_hint or not normalized_answer:
            return normalized_hint
        placeholder = "".join("*" if not character.isspace() else character for character in normalized_answer)
        pattern = re.compile(rf"(?<!\w){re.escape(normalized_answer)}(?!\w)", re.IGNORECASE)
        return pattern.sub(placeholder, normalized_hint)

    def _build_choice_options(
        self, correct_item: VocabularyItem, all_topic_items: list[VocabularyItem]
    ) -> list[str]:
        distractors = [
            item.english_word
            for item in all_topic_items
            if item.id != correct_item.id and item.english_word != correct_item.english_word
        ]
        unique_distractors = sorted(set(distractors))
        if len(unique_distractors) < 2:
            logger.warning(
                "QuestionFactory cannot build distractors for item_id=%s available=%s",
                correct_item.id,
                len(unique_distractors),
            )
            raise NotEnoughOptionsError(
                "At least three distinct words are required for multiple choice."
            )
        options = [correct_item.english_word, *self._rng.sample(unique_distractors, 2)]
        self._rng.shuffle(options)
        logger.debug(
            "QuestionFactory built options for item_id=%s options=%s",
            correct_item.id,
            options,
        )
        return options

    def _scramble_word(self, word: str) -> str:
        parts = re.split(r"(\s+)", word)
        scrambled_parts = [
            part if not part or part.isspace() else self._scramble_token(part)
            for part in parts
        ]
        scrambled = "".join(scrambled_parts)
        if scrambled.lower() != word.lower():
            return scrambled
        return word

    def _scramble_token(self, token: str) -> str:
        letters = list(token)
        if len(letters) <= 1:
            return token
        for _ in range(5):
            shuffled = letters[:]
            self._rng.shuffle(shuffled)
            scrambled = "".join(shuffled)
            if scrambled.lower() != token.lower():
                return scrambled
        return token[::-1]
