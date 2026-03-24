from __future__ import annotations

import random

from englishbot.application.services import (
    AnswerChecker,
    QuestionFactory,
    TrainingApplicationService,
    WordSelectionService,
)
from englishbot.infrastructure.demo_data import TOPICS, VOCABULARY_ITEMS
from englishbot.infrastructure.repositories import (
    InMemorySessionRepository,
    InMemoryTopicRepository,
    InMemoryUserProgressRepository,
    InMemoryVocabularyRepository,
)


def build_training_service(seed: int = 42) -> TrainingApplicationService:
    rng = random.Random(seed)
    return TrainingApplicationService(
        topic_repository=InMemoryTopicRepository(TOPICS),
        vocabulary_repository=InMemoryVocabularyRepository(VOCABULARY_ITEMS),
        progress_repository=InMemoryUserProgressRepository(),
        session_repository=InMemorySessionRepository(),
        selection_service=WordSelectionService(rng),
        question_factory=QuestionFactory(rng),
        answer_checker=AnswerChecker(),
    )
