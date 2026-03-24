from __future__ import annotations

import random
from typing import Protocol

from englishbot.application.errors import EmptyTopicError
from englishbot.domain.models import UserProgress, VocabularyItem


class WordSelector(Protocol):
    def select_words(
        self,
        *,
        user_id: int,
        items: list[VocabularyItem],
        progress_items: list[UserProgress],
        session_size: int,
    ) -> list[VocabularyItem]:
        ...


class UnseenFirstWordSelector:
    """MVP strategy: unseen words first, then lightly reviewed words."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def select_words(
        self,
        *,
        user_id: int,
        items: list[VocabularyItem],
        progress_items: list[UserProgress],
        session_size: int,
    ) -> list[VocabularyItem]:
        if not items:
            raise EmptyTopicError("The selected topic has no words.")
        progress_map = {progress.item_id: progress for progress in progress_items}

        def score(item: VocabularyItem) -> tuple[int, int, str]:
            progress = progress_map.get(item.id)
            if progress is None:
                progress = UserProgress(user_id=user_id, item_id=item.id)
            return (
                progress.times_seen,
                progress.incorrect_answers - progress.correct_answers,
                item.english_word,
            )

        ordered = sorted(items, key=score)
        selected = ordered[: min(session_size, len(ordered))]
        self._rng.shuffle(selected)
        return selected
