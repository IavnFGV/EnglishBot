from __future__ import annotations

import logging
from dataclasses import dataclass

from englishbot.application.errors import InvalidTopicLessonSelectionError
from englishbot.domain.models import Lesson
from englishbot.domain.repositories import LessonRepository
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class LessonSelectionOption:
    topic_id: str
    has_lessons: bool
    lessons: list[Lesson]


class ListLessonsByTopicUseCase:
    def __init__(self, lesson_repository: LessonRepository) -> None:
        self._lesson_repository = lesson_repository

    @logged_service_call(
        "ListLessonsByTopicUseCase.execute",
        include=("topic_id",),
        result=lambda option: {
            "has_lessons": option.has_lessons,
            "lesson_count": len(option.lessons),
        },
    )
    def execute(self, *, topic_id: str) -> LessonSelectionOption:
        lessons = self._lesson_repository.list_by_topic(topic_id)
        return LessonSelectionOption(
            topic_id=topic_id,
            has_lessons=bool(lessons),
            lessons=lessons,
        )


class ValidateTopicLessonUseCase:
    def __init__(self, lesson_repository: LessonRepository) -> None:
        self._lesson_repository = lesson_repository

    @logged_service_call(
        "ValidateTopicLessonUseCase.execute",
        include=("topic_id", "lesson_id"),
    )
    def execute(self, *, topic_id: str, lesson_id: str | None) -> None:
        if lesson_id is None:
            return
        lesson = self._lesson_repository.get_by_id(lesson_id)
        if lesson is None or lesson.topic_id != topic_id:
            logger.warning(
                "ValidateTopicLessonUseCase rejected topic_id=%s lesson_id=%s",
                topic_id,
                lesson_id,
            )
            raise InvalidTopicLessonSelectionError(
                "The selected lesson does not belong to the selected topic."
            )
