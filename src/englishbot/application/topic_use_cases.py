from __future__ import annotations

from englishbot.domain.models import Topic
from englishbot.domain.repositories import TopicRepository


class ListTopicsUseCase:
    def __init__(self, topic_repository: TopicRepository) -> None:
        self._topic_repository = topic_repository

    def execute(self) -> list[Topic]:
        return self._topic_repository.list_topics()
