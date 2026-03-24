from __future__ import annotations

import logging

from englishbot.domain.models import Topic
from englishbot.domain.repositories import TopicRepository

logger = logging.getLogger(__name__)


class ListTopicsUseCase:
    def __init__(self, topic_repository: TopicRepository) -> None:
        self._topic_repository = topic_repository

    def execute(self) -> list[Topic]:
        topics = self._topic_repository.list_topics()
        logger.info("ListTopicsUseCase returned %s topics", len(topics))
        return topics
