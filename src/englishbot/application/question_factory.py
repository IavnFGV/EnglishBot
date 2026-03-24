from __future__ import annotations

import random

from englishbot.application.errors import NotEnoughOptionsError
from englishbot.domain.models import TrainingMode, TrainingQuestion, TrainingSession, VocabularyItem


class QuestionFactory:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def create_question(
        self,
        *,
        session: TrainingSession,
        item: VocabularyItem,
        all_topic_items: list[VocabularyItem],
    ) -> TrainingQuestion:
        image_line = item.image_ref or "No image yet. Use the translation clue."
        if session.mode is TrainingMode.EASY:
            options = self._build_choice_options(item, all_topic_items)
            prompt = (
                f"Translation: {item.translation}\n"
                f"Visual clue: {image_line}\n"
                "Choose the correct English word."
            )
            return TrainingQuestion(
                session_id=session.id,
                item_id=item.id,
                mode=session.mode,
                prompt=prompt,
                image_ref=item.image_ref,
                correct_answer=item.english_word,
                options=options,
            )
        if session.mode is TrainingMode.MEDIUM:
            scrambled = self._scramble_word(item.english_word)
            prompt = (
                f"Translation: {item.translation}\n"
                f"Visual clue: {image_line}\n"
                f"Shuffled letters hint: {scrambled}\n"
                "Type the English word."
            )
            return TrainingQuestion(
                session_id=session.id,
                item_id=item.id,
                mode=session.mode,
                prompt=prompt,
                image_ref=item.image_ref,
                correct_answer=item.english_word,
                input_hint="Use the shuffled letters as a hint and type the word.",
                letter_hint=scrambled,
            )
        prompt = (
            f"Translation: {item.translation}\n"
            f"Visual clue: {image_line}\n"
            "Type the English word."
        )
        return TrainingQuestion(
            session_id=session.id,
            item_id=item.id,
            mode=session.mode,
            prompt=prompt,
            image_ref=item.image_ref,
            correct_answer=item.english_word,
            input_hint="Type the word in English.",
        )

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
            raise NotEnoughOptionsError(
                "At least three distinct words are required for multiple choice."
            )
        options = [correct_item.english_word, *self._rng.sample(unique_distractors, 2)]
        self._rng.shuffle(options)
        return options

    def _scramble_word(self, word: str) -> str:
        letters = list(word)
        if len(letters) <= 1:
            return word
        for _ in range(5):
            shuffled = letters[:]
            self._rng.shuffle(shuffled)
            scrambled = "".join(shuffled)
            if scrambled.lower() != word.lower():
                return scrambled
        return word[::-1]
