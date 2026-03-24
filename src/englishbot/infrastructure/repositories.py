from __future__ import annotations

from englishbot.domain.models import Topic, TrainingSession, UserProgress, VocabularyItem


class InMemoryTopicRepository:
    def __init__(self, topics: list[Topic]) -> None:
        self._topics = {topic.id: topic for topic in topics}

    def list_topics(self) -> list[Topic]:
        return list(self._topics.values())

    def get_by_id(self, topic_id: str) -> Topic | None:
        return self._topics.get(topic_id)


class InMemoryVocabularyRepository:
    def __init__(self, items: list[VocabularyItem]) -> None:
        self._items = {item.id: item for item in items}

    def list_by_topic(self, topic_id: str, lesson_id: str | None = None) -> list[VocabularyItem]:
        result = [
            item
            for item in self._items.values()
            if item.topic_id == topic_id
            and item.is_active
            and (lesson_id is None or item.lesson_id == lesson_id)
        ]
        return sorted(result, key=lambda item: item.english_word)

    def list_all(self) -> list[VocabularyItem]:
        return sorted(self._items.values(), key=lambda item: item.english_word)

    def get_by_id(self, item_id: str) -> VocabularyItem | None:
        return self._items.get(item_id)


class InMemoryUserProgressRepository:
    def __init__(self) -> None:
        self._storage: dict[tuple[int, str], UserProgress] = {}

    def get(self, user_id: int, item_id: str) -> UserProgress | None:
        return self._storage.get((user_id, item_id))

    def save(self, progress: UserProgress) -> None:
        self._storage[(progress.user_id, progress.item_id)] = progress

    def list_by_user(self, user_id: int) -> list[UserProgress]:
        return [
            progress
            for (progress_user_id, _), progress in self._storage.items()
            if progress_user_id == user_id
        ]


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, TrainingSession] = {}
        self._active_by_user: dict[int, str] = {}

    def save(self, session: TrainingSession) -> None:
        self._sessions[session.id] = session
        if session.completed:
            self._active_by_user.pop(session.user_id, None)
        else:
            self._active_by_user[session.user_id] = session.id

    def get_active_by_user(self, user_id: int) -> TrainingSession | None:
        session_id = self._active_by_user.get(user_id)
        if session_id is None:
            return None
        return self._sessions.get(session_id)

    def get_by_id(self, session_id: str) -> TrainingSession | None:
        return self._sessions.get(session_id)
