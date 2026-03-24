from __future__ import annotations

import random

from englishbot.application.services import (
    AnswerChecker,
    GetCurrentQuestionUseCase,
    ListTopicsUseCase,
    QuestionFactory,
    SessionSummaryCalculator,
    StartTrainingSessionUseCase,
    SubmitAnswerUseCase,
    TrainingFacade,
    UnseenFirstWordSelector,
)
from englishbot.infrastructure.demo_data import TOPICS, VOCABULARY_ITEMS
from englishbot.infrastructure.repositories import (
    InMemorySessionRepository,
    InMemoryTopicRepository,
    InMemoryUserProgressRepository,
    InMemoryVocabularyRepository,
)


def build_training_service(seed: int = 42) -> TrainingFacade:
    rng = random.Random(seed)
    topic_repository = InMemoryTopicRepository(TOPICS)
    vocabulary_repository = InMemoryVocabularyRepository(VOCABULARY_ITEMS)
    progress_repository = InMemoryUserProgressRepository()
    session_repository = InMemorySessionRepository()
    question_factory = QuestionFactory(rng)

    list_topics = ListTopicsUseCase(topic_repository)
    get_current_question = GetCurrentQuestionUseCase(
        vocabulary_repository=vocabulary_repository,
        session_repository=session_repository,
        question_factory=question_factory,
    )
    start_training_session = StartTrainingSessionUseCase(
        topic_repository=topic_repository,
        vocabulary_repository=vocabulary_repository,
        progress_repository=progress_repository,
        session_repository=session_repository,
        word_selector=UnseenFirstWordSelector(rng),
        question_factory=question_factory,
    )
    submit_answer = SubmitAnswerUseCase(
        progress_repository=progress_repository,
        session_repository=session_repository,
        get_current_question=get_current_question,
        answer_checker=AnswerChecker(),
        summary_calculator=SessionSummaryCalculator(),
    )
    return TrainingFacade(
        list_topics=list_topics,
        start_training_session=start_training_session,
        get_current_question=get_current_question,
        submit_answer=submit_answer,
    )
