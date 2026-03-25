from __future__ import annotations

import logging

from englishbot.domain.models import Topic
from englishbot.domain.repositories import TopicRepository
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


class ListTopicsUseCase:
    def __init__(self, topic_repository: TopicRepository) -> None:
        self._topic_repository = topic_repository

    @logged_service_call(
        "ListTopicsUseCase.execute",
        result=lambda topics: {"topic_count": len(topics)},
    )
    def execute(self) -> list[Topic]:
        return self._topic_repository.list_topics()
