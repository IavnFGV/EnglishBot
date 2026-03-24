from __future__ import annotations

import random

import pytest

from englishbot.application.services import (
    AnswerChecker,
    EmptyTopicError,
    GetCurrentQuestionUseCase,
    InvalidSessionStateError,
    ListTopicsUseCase,
    NotEnoughOptionsError,
    QuestionFactory,
    SessionSummaryCalculator,
    StartTrainingSessionUseCase,
    SubmitAnswerUseCase,
    TrainingFacade,
    UnseenFirstWordSelector,
)
from englishbot.domain.models import (
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
    InMemorySessionRepository,
    InMemoryTopicRepository,
    InMemoryUserProgressRepository,
    InMemoryVocabularyRepository,
)


def build_service(items: list[VocabularyItem]) -> TrainingFacade:
    rng = random.Random(7)
    topic_repository = InMemoryTopicRepository([Topic(id="weather", title="Weather")])
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
        start_training_session=StartTrainingSessionUseCase(
            topic_repository=topic_repository,
            vocabulary_repository=vocabulary_repository,
            progress_repository=progress_repository,
            session_repository=session_repository,
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
def weather_items() -> list[VocabularyItem]:
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
    ]


def test_selection_prefers_unseen_words(weather_items: list[VocabularyItem]) -> None:
    service = UnseenFirstWordSelector(random.Random(1))
    selected = service.select_words(
        user_id=100,
        items=weather_items,
        progress_items=[
            UserProgress(user_id=100, item_id="1", times_seen=3, correct_answers=2),
            UserProgress(user_id=100, item_id="2", times_seen=1, correct_answers=1),
        ],
        session_size=2,
    )
    selected_ids = {item.id for item in selected}
    assert selected_ids == {"3", "4"}


def test_selection_supports_lesson_filtering(weather_items: list[VocabularyItem]) -> None:
    repository = InMemoryVocabularyRepository(weather_items)
    lesson_items = repository.list_by_topic("weather", lesson_id="lesson-1")
    assert {item.id for item in lesson_items} == {"1", "2"}


def test_easy_question_contains_correct_answer_and_three_options(
    weather_items: list[VocabularyItem],
) -> None:
    factory = QuestionFactory(random.Random(2))
    session = TrainingSession(
        id="session-1",
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.EASY,
        items=[SessionItem(order=0, vocabulary_item_id="1")],
    )
    question = factory.create_question(
        session=session,
        item=weather_items[0],
        all_topic_items=weather_items,
    )
    assert question.correct_answer == "sun"
    assert len(question.options or []) == 3
    assert "sun" in (question.options or [])
    assert question.input_hint is None


def test_medium_question_uses_text_input_and_letter_hint(
    weather_items: list[VocabularyItem],
) -> None:
    factory = QuestionFactory(random.Random(5))
    session = TrainingSession(
        id="session-1",
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.MEDIUM,
        items=[SessionItem(order=0, vocabulary_item_id="1")],
    )
    question = factory.create_question(
        session=session,
        item=weather_items[0],
        all_topic_items=weather_items,
    )
    assert question.options is None
    assert question.input_hint is not None
    assert question.letter_hint is not None
    assert question.letter_hint.lower() != question.correct_answer.lower()


def test_easy_question_requires_enough_distractors() -> None:
    factory = QuestionFactory(random.Random(3))
    item = VocabularyItem(id="1", english_word="sun", translation="солнце", topic_id="weather")
    session = TrainingSession(
        id="session-1",
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.EASY,
        items=[SessionItem(order=0, vocabulary_item_id="1")],
    )
    with pytest.raises(NotEnoughOptionsError):
        factory.create_question(session=session, item=item, all_topic_items=[item])


def test_answer_checker_is_case_insensitive(weather_items: list[VocabularyItem]) -> None:
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
        item=weather_items[0],
        all_topic_items=weather_items,
    )
    result = checker.check(question=question, answer=" Sun ")
    assert result.is_correct is True
    assert result.normalized_answer == "Sun"


def test_progress_updates_and_summary_are_saved(weather_items: list[VocabularyItem]) -> None:
    service = build_service(weather_items)
    first_question = service.start_session(
        user_id=10,
        topic_id="weather",
        mode=TrainingMode.EASY,
        session_size=2,
    )
    first_outcome = service.submit_answer(user_id=10, answer=first_question.correct_answer)
    assert first_outcome.result.is_correct is True
    assert first_outcome.summary is None
    second_question = first_outcome.next_question
    assert second_question is not None
    second_outcome = service.submit_answer(user_id=10, answer="wrong")
    assert second_outcome.summary is not None
    assert second_outcome.summary.total_questions == 2
    assert second_outcome.summary.correct_answers == 1


def test_empty_topic_raises_error() -> None:
    service = build_service([])
    with pytest.raises(EmptyTopicError):
        service.start_session(user_id=10, topic_id="weather", mode=TrainingMode.EASY)


def test_repeated_word_updates_progress_counter(weather_items: list[VocabularyItem]) -> None:
    progress_repository = InMemoryUserProgressRepository()
    progress = UserProgress(
        user_id=22,
        item_id="1",
        times_seen=2,
        correct_answers=1,
        incorrect_answers=1,
    )
    progress_repository.save(progress)
    rng = random.Random(7)
    topic_repository = InMemoryTopicRepository([Topic(id="weather", title="Weather")])
    vocabulary_repository = InMemoryVocabularyRepository(weather_items)
    session_repository = InMemorySessionRepository()
    question_factory = QuestionFactory(rng)
    get_current_question = GetCurrentQuestionUseCase(
        vocabulary_repository=vocabulary_repository,
        session_repository=session_repository,
        question_factory=question_factory,
    )
    service = TrainingFacade(
        list_topics=ListTopicsUseCase(topic_repository),
        start_training_session=StartTrainingSessionUseCase(
            topic_repository=topic_repository,
            vocabulary_repository=vocabulary_repository,
            progress_repository=progress_repository,
            session_repository=session_repository,
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
    question = service.start_session(
        user_id=22,
        topic_id="weather",
        mode=TrainingMode.HARD,
        session_size=4,
    )
    service.submit_answer(user_id=22, answer=question.correct_answer)
    updated = progress_repository.get(22, question.item_id)
    assert updated is not None
    assert updated.times_seen == 3


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
    summary = calculator.calculate(session)
    assert summary == SessionSummary(total_questions=2, correct_answers=1)


def test_session_refuses_answers_after_completion() -> None:
    session = TrainingSession(
        id="session-1",
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.HARD,
        items=[SessionItem(order=0, vocabulary_item_id="1")],
    )
    session.record_answer(answer="sun", is_correct=True)
    with pytest.raises(ValueError):
        session.record_answer(answer="sun", is_correct=True)


def test_get_current_question_rejects_completed_session(
    weather_items: list[VocabularyItem],
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
    get_current_question = GetCurrentQuestionUseCase(
        vocabulary_repository=InMemoryVocabularyRepository(weather_items),
        session_repository=session_repository,
        question_factory=QuestionFactory(random.Random(1)),
    )
    with pytest.raises(InvalidSessionStateError):
        get_current_question.execute(user_id=1)


def test_submit_answer_refuses_extra_answer_after_session_completion(
    weather_items: list[VocabularyItem],
) -> None:
    service = build_service(weather_items)
    question = service.start_session(
        user_id=88,
        topic_id="weather",
        mode=TrainingMode.HARD,
        session_size=1,
    )
    outcome = service.submit_answer(user_id=88, answer=question.correct_answer)
    assert outcome.summary is not None
    with pytest.raises(InvalidSessionStateError):
        service.submit_answer(user_id=88, answer=question.correct_answer)


def test_training_flow_integration_for_medium_mode(weather_items: list[VocabularyItem]) -> None:
    service = build_service(weather_items)
    question = service.start_session(
        user_id=77,
        topic_id="weather",
        mode=TrainingMode.MEDIUM,
        session_size=1,
    )
    assert question.mode is TrainingMode.MEDIUM
    assert question.options is None
    outcome = service.submit_answer(user_id=77, answer=question.correct_answer)
    assert outcome.result.is_correct is True
    assert outcome.summary is not None
