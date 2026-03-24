from __future__ import annotations

from dataclasses import dataclass

from englishbot.application.errors import InvalidTopicLessonSelectionError
from englishbot.domain.models import Lesson
from englishbot.domain.repositories import LessonRepository


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
            return
        lesson = self._lesson_repository.get_by_id(lesson_id)
        if lesson is None or lesson.topic_id != topic_id:
            raise InvalidTopicLessonSelectionError(
                "The selected lesson does not belong to the selected topic."
            )
