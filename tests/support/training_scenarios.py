from __future__ import annotations

import random

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
from englishbot.application.training_scenarios import TrainingScenarioController
from englishbot.domain.models import Lesson, Topic, TrainingMode, VocabularyItem
from englishbot.infrastructure.repositories import (
    InMemoryLessonRepository,
    InMemorySessionRepository,
    InMemoryTopicRepository,
    InMemoryUserProgressRepository,
    InMemoryVocabularyRepository,
)


def build_training_service() -> TrainingFacade:
    topics = [
        Topic(id="weather", title="Weather"),
        Topic(id="seasons", title="Seasons"),
    ]
    lessons = [
        Lesson(id="lesson-1", title="Lesson 1", topic_id="weather"),
        Lesson(id="lesson-2", title="Lesson 2", topic_id="weather"),
    ]
    items = [
        VocabularyItem(
            id="1",
            english_word="sun",
            translation="солнце",
            topic_id="weather",
            lesson_id="lesson-1",
        ),
        VocabularyItem(
            id="2",
            english_word="rain",
            translation="дождь",
            topic_id="weather",
            lesson_id="lesson-1",
        ),
        VocabularyItem(
            id="3",
            english_word="cloud",
            translation="облако",
            topic_id="weather",
            lesson_id="lesson-2",
        ),
        VocabularyItem(
            id="4",
            english_word="wind",
            translation="ветер",
            topic_id="weather",
            lesson_id="lesson-2",
        ),
        VocabularyItem(
            id="5",
            english_word="spring",
            translation="весна",
            topic_id="seasons",
        ),
        VocabularyItem(
            id="6",
            english_word="winter",
            translation="зима",
            topic_id="seasons",
        ),
    ]

    rng = random.Random(7)
    topic_repository = InMemoryTopicRepository(topics)
    lesson_repository = InMemoryLessonRepository(lessons)
    vocabulary_repository = InMemoryVocabularyRepository(items)
    progress_repository = InMemoryUserProgressRepository()
    session_repository = InMemorySessionRepository()
    question_factory = QuestionFactory(rng)
    get_current_question = GetCurrentQuestionUseCase(
        vocabulary_repository=vocabulary_repository,
        session_repository=session_repository,
        question_factory=question_factory,
    )
    return TrainingFacade(
        list_topics=ListTopicsUseCase(topic_repository),
        list_lessons_by_topic=ListLessonsByTopicUseCase(lesson_repository),
        start_training_session=StartTrainingSessionUseCase(
            topic_repository=topic_repository,
            vocabulary_repository=vocabulary_repository,
            progress_repository=progress_repository,
            session_repository=session_repository,
            validate_topic_lesson=ValidateTopicLessonUseCase(lesson_repository),
            word_selector=UnseenFirstWordSelector(rng),
            question_factory=question_factory,
        ),
        get_active_session=GetActiveSessionUseCase(session_repository),
        get_current_question=get_current_question,
        discard_active_session=DiscardActiveSessionUseCase(session_repository),
        submit_answer=SubmitAnswerUseCase(
            progress_repository=progress_repository,
            session_repository=session_repository,
            get_current_question=get_current_question,
            answer_checker=AnswerChecker(),
            summary_calculator=SessionSummaryCalculator(),
        ),
    )


class ScenarioDriver:
    def __init__(self) -> None:
        self.controller = TrainingScenarioController(build_training_service())
        self.screen = None

    def when_user_starts(self, *, user_id: int = 1) -> ScenarioDriver:
        self.screen = self.controller.start(user_id=user_id)
        return self

    def when_user_chooses_topic(self, topic_id: str) -> ScenarioDriver:
        self.screen = self.controller.choose_topic(topic_id=topic_id)
        return self

    def when_user_chooses_lesson(self, *, topic_id: str, lesson_id: str | None) -> ScenarioDriver:
        self.screen = self.controller.choose_lesson(topic_id=topic_id, lesson_id=lesson_id)
        return self

    def when_user_chooses_mode(
        self,
        *,
        user_id: int = 1,
        topic_id: str,
        lesson_id: str | None,
        mode: TrainingMode,
        session_size: int = 2,
    ) -> ScenarioDriver:
        self.screen = self.controller.choose_mode(
            user_id=user_id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=mode,
            session_size=session_size,
        )
        return self

    def when_user_answers(self, answer: str, *, user_id: int = 1) -> ScenarioDriver:
        self.screen = self.controller.answer(user_id=user_id, answer=answer)
        return self
