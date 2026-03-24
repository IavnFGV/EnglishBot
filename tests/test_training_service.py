from __future__ import annotations

import random

import pytest

from englishbot.application.services import (
    AnswerChecker,
    EmptyTopicError,
    GetCurrentQuestionUseCase,
    InvalidSessionStateError,
    InvalidTopicLessonSelectionError,
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
from englishbot.domain.models import (
    Lesson,
    SessionAnswer,
    SessionItem,
    SessionSummary,
    Topic,
    TrainingMode,
    TrainingSession,
    UserProgress,
    VocabularyItem,
)
from englishbot.infrastructure.repositories import (
    InMemoryLessonRepository,
    InMemorySessionRepository,
    InMemoryTopicRepository,
    InMemoryUserProgressRepository,
    InMemoryVocabularyRepository,
)


def build_service(
    *,
    topics: list[Topic],
    lessons: list[Lesson],
    items: list[VocabularyItem],
) -> TrainingFacade:
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
        get_current_question=get_current_question,
        submit_answer=SubmitAnswerUseCase(
            progress_repository=progress_repository,
            session_repository=session_repository,
            get_current_question=get_current_question,
            answer_checker=AnswerChecker(),
            summary_calculator=SessionSummaryCalculator(),
        ),
    )


@pytest.fixture
def topics() -> list[Topic]:
    return [
        Topic(id="weather", title="Weather"),
        Topic(id="seasons", title="Seasons"),
    ]


@pytest.fixture
def lessons() -> list[Lesson]:
    return [
        Lesson(id="lesson-1", title="Lesson 1", topic_id="weather"),
        Lesson(id="lesson-2", title="Lesson 2", topic_id="weather"),
    ]


@pytest.fixture
def vocabulary_items() -> list[VocabularyItem]:
    return [
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
        VocabularyItem(
            id="7",
            english_word="summer",
            translation="лето",
            topic_id="seasons",
        ),
    ]


def test_selection_prefers_unseen_words(vocabulary_items: list[VocabularyItem]) -> None:
    selector = UnseenFirstWordSelector(random.Random(1))
    selected = selector.select_words(
        user_id=100,
        items=vocabulary_items[:4],
        progress_items=[
            UserProgress(user_id=100, item_id="1", times_seen=3, correct_answers=2),
            UserProgress(user_id=100, item_id="2", times_seen=1, correct_answers=1),
        ],
        session_size=2,
    )
    assert {item.id for item in selected} == {"3", "4"}


def test_listing_lessons_by_topic(lessons: list[Lesson]) -> None:
    use_case = ListLessonsByTopicUseCase(InMemoryLessonRepository(lessons))
    selection = use_case.execute(topic_id="weather")
    assert selection.has_lessons is True
    assert [lesson.id for lesson in selection.lessons] == ["lesson-1", "lesson-2"]


def test_fallback_when_topic_has_no_lessons(lessons: list[Lesson]) -> None:
    use_case = ListLessonsByTopicUseCase(InMemoryLessonRepository(lessons))
    selection = use_case.execute(topic_id="seasons")
    assert selection.has_lessons is False
    assert selection.lessons == []


def test_validate_topic_lesson_combination(lessons: list[Lesson]) -> None:
    validator = ValidateTopicLessonUseCase(InMemoryLessonRepository(lessons))
    validator.execute(topic_id="weather", lesson_id="lesson-1")
    with pytest.raises(InvalidTopicLessonSelectionError):
        validator.execute(topic_id="seasons", lesson_id="lesson-1")


def test_starting_session_for_specific_lesson_filters_items(
    topics: list[Topic],
    lessons: list[Lesson],
    vocabulary_items: list[VocabularyItem],
) -> None:
    service = build_service(topics=topics, lessons=lessons, items=vocabulary_items)
    question = service.start_session(
        user_id=10,
        topic_id="weather",
        lesson_id="lesson-1",
        mode=TrainingMode.HARD,
        session_size=2,
    )
    assert question.item_id in {"1", "2"}


def test_start_session_rejects_invalid_topic_lesson_combination(
    topics: list[Topic],
    lessons: list[Lesson],
    vocabulary_items: list[VocabularyItem],
) -> None:
    service = build_service(topics=topics, lessons=lessons, items=vocabulary_items)
    with pytest.raises(InvalidTopicLessonSelectionError):
        service.start_session(
            user_id=10,
            topic_id="seasons",
            lesson_id="lesson-1",
            mode=TrainingMode.HARD,
        )


def test_answer_checker_returns_normalized_lowercase_answer(
    vocabulary_items: list[VocabularyItem],
) -> None:
    factory = QuestionFactory(random.Random(4))
    checker = AnswerChecker()
    session = TrainingSession(
        id="session-1",
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.HARD,
        items=[SessionItem(order=0, vocabulary_item_id="1")],
    )
    question = factory.create_question(
        session=session,
        item=vocabulary_items[0],
        all_topic_items=vocabulary_items[:4],
    )
    result = checker.check(question=question, answer=" Sun ")
    assert result.is_correct is True
    assert result.normalized_answer == "sun"


def test_empty_topic_raises_error(topics: list[Topic], lessons: list[Lesson]) -> None:
    service = build_service(topics=topics, lessons=lessons, items=[])
    with pytest.raises(EmptyTopicError):
        service.start_session(user_id=10, topic_id="weather", mode=TrainingMode.EASY)


def test_session_summary_calculator_counts_answers() -> None:
    calculator = SessionSummaryCalculator()
    session = TrainingSession(
        id="session-1",
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.HARD,
        items=[
            SessionItem(order=0, vocabulary_item_id="1"),
            SessionItem(order=1, vocabulary_item_id="2"),
        ],
        current_index=2,
        completed=True,
        answer_history=[
            SessionAnswer(item_id="1", submitted_answer="sun", is_correct=True),
            SessionAnswer(item_id="2", submitted_answer="rainn", is_correct=False),
        ],
    )
    assert calculator.calculate(session) == SessionSummary(total_questions=2, correct_answers=1)


def test_get_current_question_rejects_completed_session(
    vocabulary_items: list[VocabularyItem],
) -> None:
    session_repository = InMemorySessionRepository()
    completed_session = TrainingSession(
        id="session-1",
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.HARD,
        items=[SessionItem(order=0, vocabulary_item_id="1")],
        current_index=1,
        completed=True,
        answer_history=[SessionAnswer(item_id="1", submitted_answer="sun", is_correct=True)],
    )
    session_repository._sessions[completed_session.id] = completed_session
    session_repository._active_by_user[1] = completed_session.id
    use_case = GetCurrentQuestionUseCase(
        vocabulary_repository=InMemoryVocabularyRepository(vocabulary_items),
        session_repository=session_repository,
        question_factory=QuestionFactory(random.Random(1)),
    )
    with pytest.raises(InvalidSessionStateError):
        use_case.execute(user_id=1)


def test_submit_answer_refuses_extra_answer_after_completion(
    topics: list[Topic],
    lessons: list[Lesson],
    vocabulary_items: list[VocabularyItem],
) -> None:
    service = build_service(topics=topics, lessons=lessons, items=vocabulary_items)
    question = service.start_session(
        user_id=88,
        topic_id="seasons",
        mode=TrainingMode.HARD,
        session_size=1,
    )
    outcome = service.submit_answer(user_id=88, answer=question.correct_answer)
    assert outcome.summary is not None
    with pytest.raises(InvalidSessionStateError):
        service.submit_answer(user_id=88, answer=question.correct_answer)


def test_training_flow_integration_for_medium_mode_and_unique_session_ids(
    topics: list[Topic],
    lessons: list[Lesson],
    vocabulary_items: list[VocabularyItem],
) -> None:
    service = build_service(topics=topics, lessons=lessons, items=vocabulary_items)
    first_question = service.start_session(
        user_id=77,
        topic_id="weather",
        lesson_id="lesson-1",
        mode=TrainingMode.MEDIUM,
        session_size=1,
    )
    second_question = service.start_session(
        user_id=78,
        topic_id="weather",
        lesson_id="lesson-1",
        mode=TrainingMode.MEDIUM,
        session_size=1,
    )
    assert first_question.mode is TrainingMode.MEDIUM
    assert first_question.options is None
    assert first_question.session_id != second_question.session_id
