from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from englishbot.application.clock import Clock, SystemClock
from englishbot.domain.models import VocabularyItem
from englishbot.domain.repositories import UserProgressRepository, VocabularyRepository
from englishbot.logging_utils import logged_service_call


@dataclass(slots=True, frozen=True)
class ReviewCheckResult:
    kind: str
    text: str
    due_item_ids: tuple[str, ...] = ()
    topic_ids: tuple[str, ...] = ()


class CheckMorningReviewUseCase:
    def __init__(
        self,
        *,
        progress_repository: UserProgressRepository,
        vocabulary_repository: VocabularyRepository,
        clock: Clock | None = None,
        review_after: timedelta = timedelta(hours=12),
    ) -> None:
        self._progress_repository = progress_repository
        self._vocabulary_repository = vocabulary_repository
        self._clock = clock or SystemClock()
        self._review_after = review_after

    @logged_service_call(
        "CheckMorningReviewUseCase.execute",
        include=("user_id",),
        result=lambda value: {
            "kind": value.kind,
            "due_count": len(value.due_item_ids),
        },
    )
    def execute(self, *, user_id: int) -> ReviewCheckResult:
        now = self._clock.now()
        vocabulary_by_id = {
            item.id: item for item in self._vocabulary_repository.list_all() if item.is_active
        }
        due_items: list[VocabularyItem] = []
        for progress in self._progress_repository.list_by_user(user_id):
            if progress.last_seen_at is None:
                continue
            if now < progress.last_seen_at + self._review_after:
                continue
            item = vocabulary_by_id.get(progress.item_id)
            if item is not None:
                due_items.append(item)

        if not due_items:
            return ReviewCheckResult(
                kind="noop",
                text="No review is due right now.",
            )

        topic_ids = tuple(sorted({item.topic_id for item in due_items}))
        return ReviewCheckResult(
            kind="review_proposal",
            text=f"Review is due for {len(due_items)} word(s).",
            due_item_ids=tuple(item.id for item in due_items),
            topic_ids=topic_ids,
        )
