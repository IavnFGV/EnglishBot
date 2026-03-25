from __future__ import annotations

import logging

from englishbot.domain.add_words_models import AddWordsFlowState
from englishbot.domain.models import Lesson, Topic, TrainingSession, UserProgress, VocabularyItem

logger = logging.getLogger(__name__)


class InMemoryTopicRepository:
    def __init__(self, topics: list[Topic]) -> None:
        self._topics = {topic.id: topic for topic in topics}

    def list_topics(self) -> list[Topic]:
        topics = list(self._topics.values())
        logger.debug("TopicRepository.list_topics returned %s topics", len(topics))
        return topics

    def get_by_id(self, topic_id: str) -> Topic | None:
        topic = self._topics.get(topic_id)
        logger.debug("TopicRepository.get_by_id topic_id=%s found=%s", topic_id, topic is not None)
        return topic


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
        sorted_result = sorted(result, key=lambda item: item.english_word)
        logger.debug(
            "VocabularyRepository.list_by_topic topic_id=%s lesson_id=%s returned=%s",
            topic_id,
            lesson_id,
            len(sorted_result),
        )
        return sorted_result

    def list_all(self) -> list[VocabularyItem]:
        return sorted(self._items.values(), key=lambda item: item.english_word)

    def get_by_id(self, item_id: str) -> VocabularyItem | None:
        item = self._items.get(item_id)
        logger.debug(
            "VocabularyRepository.get_by_id item_id=%s found=%s",
            item_id,
            item is not None,
        )
        return item


class InMemoryLessonRepository:
    def __init__(self, lessons: list[Lesson]) -> None:
        self._lessons = {lesson.id: lesson for lesson in lessons}

    def list_by_topic(self, topic_id: str) -> list[Lesson]:
        lessons = [lesson for lesson in self._lessons.values() if lesson.topic_id == topic_id]
        sorted_lessons = sorted(lessons, key=lambda lesson: lesson.title)
        logger.debug(
            "LessonRepository.list_by_topic topic_id=%s returned=%s",
            topic_id,
            len(sorted_lessons),
        )
        return sorted_lessons

    def get_by_id(self, lesson_id: str) -> Lesson | None:
        lesson = self._lessons.get(lesson_id)
        logger.debug(
            "LessonRepository.get_by_id lesson_id=%s found=%s",
            lesson_id,
            lesson is not None,
        )
        return lesson


class InMemoryUserProgressRepository:
    def __init__(self) -> None:
        self._storage: dict[tuple[int, str], UserProgress] = {}

    def get(self, user_id: int, item_id: str) -> UserProgress | None:
        progress = self._storage.get((user_id, item_id))
        logger.debug(
            "UserProgressRepository.get user_id=%s item_id=%s found=%s",
            user_id,
            item_id,
            progress is not None,
        )
        return progress

    def save(self, progress: UserProgress) -> None:
        self._storage[(progress.user_id, progress.item_id)] = progress
        logger.debug(
            "UserProgressRepository.save user_id=%s item_id=%s seen=%s correct=%s incorrect=%s",
            progress.user_id,
            progress.item_id,
            progress.times_seen,
            progress.correct_answers,
            progress.incorrect_answers,
        )

    def list_by_user(self, user_id: int) -> list[UserProgress]:
        progress_list = [
            progress
            for (progress_user_id, _), progress in self._storage.items()
            if progress_user_id == user_id
        ]
        logger.debug(
            "UserProgressRepository.list_by_user user_id=%s returned=%s",
            user_id,
            len(progress_list),
        )
        return progress_list


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
        logger.debug(
            "SessionRepository.save session_id=%s user_id=%s completed=%s "
            "current_index=%s total_items=%s",
            session.id,
            session.user_id,
            session.completed,
            session.current_index,
            session.total_items,
        )

    def get_active_by_user(self, user_id: int) -> TrainingSession | None:
        session_id = self._active_by_user.get(user_id)
        if session_id is None:
            logger.debug("SessionRepository.get_active_by_user user_id=%s found=False", user_id)
            return None
        session = self._sessions.get(session_id)
        logger.debug(
            "SessionRepository.get_active_by_user user_id=%s found=%s session_id=%s",
            user_id,
            session is not None,
            session_id,
        )
        return session

    def get_by_id(self, session_id: str) -> TrainingSession | None:
        session = self._sessions.get(session_id)
        logger.debug(
            "SessionRepository.get_by_id session_id=%s found=%s",
            session_id,
            session is not None,
        )
        return session

    def discard_active_by_user(self, user_id: int) -> None:
        session_id = self._active_by_user.pop(user_id, None)
        if session_id is not None:
            self._sessions.pop(session_id, None)
        logger.info(
            "SessionRepository.discard_active_by_user user_id=%s discarded=%s",
            user_id,
            session_id is not None,
        )


class InMemoryAddWordsFlowRepository:
    def __init__(self) -> None:
        self._flows: dict[str, AddWordsFlowState] = {}
        self._active_by_user: dict[int, str] = {}

    def save(self, flow: AddWordsFlowState) -> None:
        self._flows[flow.flow_id] = flow
        self._active_by_user[flow.editor_user_id] = flow.flow_id
        logger.debug(
            "AddWordsFlowRepository.save flow_id=%s user_id=%s items=%s",
            flow.flow_id,
            flow.editor_user_id,
            len(flow.draft_result.draft.vocabulary_items),
        )

    def get_active_by_user(self, user_id: int) -> AddWordsFlowState | None:
        flow_id = self._active_by_user.get(user_id)
        if flow_id is None:
            return None
        return self._flows.get(flow_id)

    def get_by_id(self, flow_id: str) -> AddWordsFlowState | None:
        return self._flows.get(flow_id)

    def discard_active_by_user(self, user_id: int) -> None:
        flow_id = self._active_by_user.pop(user_id, None)
        if flow_id is not None:
            self._flows.pop(flow_id, None)
