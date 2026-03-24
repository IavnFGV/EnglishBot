from __future__ import annotations

import logging
import random
from pathlib import Path

from englishbot.application.services import (
    AnswerChecker,
    DiscardActiveSessionUseCase,
    GetActiveSessionUseCase,
    GetCurrentQuestionUseCase,
    ListLessonsByTopicUseCase,
    ListTopicsUseCase,
    QuestionFactory,
    SessionSummaryCalculator,
    StartTrainingSessionUseCase,
    SubmitAnswerUseCase,
    TrainingFacade,
    UnseenFirstWordSelector,
    ValidateTopicLessonUseCase,
)
from englishbot.infrastructure.content_loader import JsonContentPackLoader
from englishbot.infrastructure.repositories import (
    InMemoryLessonRepository,
    InMemorySessionRepository,
    InMemoryTopicRepository,
    InMemoryUserProgressRepository,
    InMemoryVocabularyRepository,
)

logger = logging.getLogger(__name__)


def build_training_service(seed: int = 42) -> TrainingFacade:
    logger.info("Building training service with seed=%s", seed)
    rng = random.Random(seed)
    content_dir = Path("content/demo")
    loaded_content = JsonContentPackLoader().load_directory(content_dir)
    logger.info(
        "Loaded content packs from %s: topics=%s lessons=%s vocabulary_items=%s",
        content_dir,
        len(loaded_content.topics),
        len(loaded_content.lessons),
        len(loaded_content.vocabulary_items),
    )
    topic_repository = InMemoryTopicRepository(loaded_content.topics)
    lesson_repository = InMemoryLessonRepository(loaded_content.lessons)
    vocabulary_repository = InMemoryVocabularyRepository(loaded_content.vocabulary_items)
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
        validate_topic_lesson=ValidateTopicLessonUseCase(lesson_repository),
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
    logger.info("Training service wiring completed")
    return TrainingFacade(
        list_topics=list_topics,
        list_lessons_by_topic=ListLessonsByTopicUseCase(lesson_repository),
        start_training_session=start_training_session,
        get_active_session=GetActiveSessionUseCase(session_repository),
        get_current_question=get_current_question,
        discard_active_session=DiscardActiveSessionUseCase(session_repository),
        submit_answer=submit_answer,
    )
