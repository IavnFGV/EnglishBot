from __future__ import annotations

import random
from pathlib import Path

from englishbot.application.services import (
    AnswerChecker,
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


def build_training_service(seed: int = 42) -> TrainingFacade:
    rng = random.Random(seed)
    loaded_content = JsonContentPackLoader().load_directory(Path("content/demo"))
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
    return TrainingFacade(
        list_topics=list_topics,
        list_lessons_by_topic=ListLessonsByTopicUseCase(lesson_repository),
        start_training_session=start_training_session,
        get_current_question=get_current_question,
        submit_answer=submit_answer,
    )
