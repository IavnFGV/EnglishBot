from __future__ import annotations

import logging
import random
from typing import Protocol

from englishbot.application.errors import EmptyTopicError
from englishbot.application.learning_progress import RecommendationInput, recommendation_score
from englishbot.domain.models import UserProgress, VocabularyItem
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


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

    def select_game_words(
        self,
        *,
        user_id: int,
        topic_id: str,
        items: list[VocabularyItem],
        progress_items: list[UserProgress],
        session_size: int,
    ) -> list[VocabularyItem]:
        ...


class WordSelectionContextProvider(Protocol):
    def list_recent_session_words(self, *, user_id: int, limit_sessions: int = 3) -> set[str]:
        ...

    def list_active_homework_words(self, *, user_id: int) -> dict[str, int]:
        ...

    def list_active_goal_words(self, *, user_id: int) -> set[str]:
        ...

    def list_due_review_words(self, *, user_id: int) -> set[str]:
        ...


class UnseenFirstWordSelector:
    """MVP strategy: unseen words first, then lightly reviewed words."""

    def __init__(
        self,
        rng: random.Random | None = None,
        context_provider: WordSelectionContextProvider | None = None,
    ) -> None:
        self._rng = rng or random.Random()
        self._context_provider = context_provider

    @logged_service_call(
        "UnseenFirstWordSelector.select_words",
        include=("user_id", "session_size"),
        transforms={
            "items": lambda value: {"candidate_count": len(value)},
            "progress_items": lambda value: {"progress_count": len(value)},
        },
        result=lambda items: {"selected_ids": [item.id for item in items]},
    )
    def select_words(
        self,
        *,
        user_id: int,
        items: list[VocabularyItem],
        progress_items: list[UserProgress],
        session_size: int,
    ) -> list[VocabularyItem]:
        if not items:
            logger.warning(
                "UnseenFirstWordSelector received empty topic item list for user_id=%s",
                user_id,
            )
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

    def select_game_words(
        self,
        *,
        user_id: int,
        topic_id: str,  # noqa: ARG002
        items: list[VocabularyItem],
        progress_items: list[UserProgress],
        session_size: int,
    ) -> list[VocabularyItem]:
        if not items:
            raise EmptyTopicError("The selected topic has no words.")
        if self._context_provider is None:
            return self.select_words(
                user_id=user_id,
                items=items,
                progress_items=progress_items,
                session_size=session_size,
            )
        progress_map = {progress.item_id: progress for progress in progress_items}
        recent_words = self._context_provider.list_recent_session_words(user_id=user_id, limit_sessions=3)
        homework_words = self._context_provider.list_active_homework_words(user_id=user_id)
        goal_words = self._context_provider.list_active_goal_words(user_id=user_id)
        review_due_words = self._context_provider.list_due_review_words(user_id=user_id)

        scored: list[tuple[int, VocabularyItem]] = []
        for item in items:
            progress = progress_map.get(item.id) or UserProgress(user_id=user_id, item_id=item.id)
            total_attempts = progress.times_seen
            total_success = progress.correct_answers
            days_since_seen = 14
            if progress.last_seen_at is not None:
                days_since_seen = max(0, (self._today() - progress.last_seen_at.date()).days)
            score = recommendation_score(
                RecommendationInput(
                    total_attempts=total_attempts,
                    total_success=total_success,
                    current_level=self._level_from_progress(progress),
                    days_since_seen=days_since_seen,
                    shown_in_last_3_sessions=item.id in recent_words,
                    in_active_homework=item.id in homework_words,
                    in_active_goal_targets=item.id in goal_words,
                    review_due_now=item.id in review_due_words,
                )
            )
            scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].english_word))
        selected: list[VocabularyItem] = []

        def _append_from(candidates: list[VocabularyItem], target_count: int) -> None:
            for candidate in candidates:
                if len(selected) >= target_count:
                    break
                if candidate.id not in {item.id for item in selected}:
                    selected.append(candidate)

        due_review_pool = [item for _, item in scored if item.id in review_due_words]
        homework_pool = [item for _, item in scored if item.id in homework_words]
        goal_pool = [item for _, item in scored if item.id in goal_words and item.id not in homework_words]
        review_pool = [item for _, item in scored if item.id not in homework_words and item.id not in goal_words]
        easiest_pool = sorted(
            items,
            key=lambda item: (progress_map.get(item.id).times_seen if item.id in progress_map else 0),
        )
        _append_from(homework_pool, min(session_size, 3 if homework_pool else 0))
        _append_from(due_review_pool, min(session_size, len(selected) + 2))
        _append_from(goal_pool, min(session_size, len(selected) + 1))
        _append_from(review_pool, min(session_size, len(selected) + 2))
        _append_from(easiest_pool, min(session_size, len(selected) + 1))
        shuffled_pool = [item for item in items if item.id not in {entry.id for entry in selected}]
        self._rng.shuffle(shuffled_pool)
        _append_from(shuffled_pool, session_size)
        return selected[:session_size]

    def _today(self):
        from datetime import datetime, UTC

        return datetime.now(UTC).date()

    @staticmethod
    def _level_from_progress(progress: UserProgress) -> int:
        if progress.correct_answers >= 6:
            return 3
        if progress.correct_answers >= 3:
            return 2
        if progress.correct_answers >= 1:
            return 1
        return 0
