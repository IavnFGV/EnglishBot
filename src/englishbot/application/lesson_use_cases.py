from __future__ import annotations

import logging
from dataclasses import dataclass

from englishbot.application.errors import InvalidTopicLessonSelectionError
from englishbot.domain.models import Lesson
from englishbot.domain.repositories import LessonRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class LessonSelectionOption:
    topic_id: str
    has_lessons: bool
    lessons: list[Lesson]


class ListLessonsByTopicUseCase:
    def __init__(self, lesson_repository: LessonRepository) -> None:
        self._lesson_repository = lesson_repository

    def execute(self, *, topic_id: str) -> LessonSelectionOption:
        lessons = self._lesson_repository.list_by_topic(topic_id)
        logger.info(
            "ListLessonsByTopicUseCase topic_id=%s has_lessons=%s count=%s",
            topic_id,
            bool(lessons),
            len(lessons),
        )
        return LessonSelectionOption(
            topic_id=topic_id,
            has_lessons=bool(lessons),
            lessons=lessons,
        )


class ValidateTopicLessonUseCase:
    def __init__(self, lesson_repository: LessonRepository) -> None:
        self._lesson_repository = lesson_repository

    def execute(self, *, topic_id: str, lesson_id: str | None) -> None:
        if lesson_id is None:
            logger.debug("ValidateTopicLessonUseCase topic_id=%s lesson_id=None accepted", topic_id)
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
        logger.debug(
            "ValidateTopicLessonUseCase accepted topic_id=%s lesson_id=%s",
            topic_id,
            lesson_id,
        )
