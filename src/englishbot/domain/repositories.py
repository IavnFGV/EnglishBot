from __future__ import annotations

from typing import Protocol

from englishbot.domain.models import Lesson, Topic, TrainingSession, UserProgress, VocabularyItem


class TopicRepository(Protocol):
    def list_topics(self) -> list[Topic]:
        ...

    def get_by_id(self, topic_id: str) -> Topic | None:
        ...


class VocabularyRepository(Protocol):
    def list_by_topic(self, topic_id: str, lesson_id: str | None = None) -> list[VocabularyItem]:
        ...

    def list_all(self) -> list[VocabularyItem]:
        ...

    def get_by_id(self, item_id: str) -> VocabularyItem | None:
        ...


class LessonRepository(Protocol):
    def list_by_topic(self, topic_id: str) -> list[Lesson]:
        ...

    def get_by_id(self, lesson_id: str) -> Lesson | None:
        ...


class UserProgressRepository(Protocol):
    def get(self, user_id: int, item_id: str) -> UserProgress | None:
        ...

    def save(self, progress: UserProgress) -> None:
        ...

    def list_by_user(self, user_id: int) -> list[UserProgress]:
        ...


class SessionRepository(Protocol):
    def save(self, session: TrainingSession) -> None:
        ...

    def get_active_by_user(self, user_id: int) -> TrainingSession | None:
        ...

    def get_by_id(self, session_id: str) -> TrainingSession | None:
        ...
