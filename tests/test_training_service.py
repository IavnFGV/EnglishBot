from __future__ import annotations

import random

import pytest

from englishbot.application.services import (
    AnswerChecker,
    EmptyTopicError,
    NotEnoughOptionsError,
    QuestionFactory,
    TrainingApplicationService,
    WordSelectionService,
)
from englishbot.domain.models import (
    SessionItem,
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


def build_service(items: list[VocabularyItem]) -> TrainingApplicationService:
    rng = random.Random(7)
    return TrainingApplicationService(
        topic_repository=InMemoryTopicRepository([Topic(id="weather", title="Weather")]),
        vocabulary_repository=InMemoryVocabularyRepository(items),
        progress_repository=InMemoryUserProgressRepository(),
        session_repository=InMemorySessionRepository(),
        selection_service=WordSelectionService(rng),
        question_factory=QuestionFactory(rng),
        answer_checker=AnswerChecker(),
    )


@pytest.fixture
def weather_items() -> list[VocabularyItem]:
    return [
        VocabularyItem(id="1", english_word="sun", translation="солнце", topic_id="weather"),
        VocabularyItem(id="2", english_word="rain", translation="дождь", topic_id="weather"),
        VocabularyItem(id="3", english_word="cloud", translation="облако", topic_id="weather"),
        VocabularyItem(id="4", english_word="wind", translation="ветер", topic_id="weather"),
    ]


def test_selection_prefers_unseen_words(weather_items: list[VocabularyItem]) -> None:
    service = WordSelectionService(random.Random(1))
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
    service = TrainingApplicationService(
        topic_repository=InMemoryTopicRepository([Topic(id="weather", title="Weather")]),
        vocabulary_repository=InMemoryVocabularyRepository(weather_items),
        progress_repository=progress_repository,
        session_repository=InMemorySessionRepository(),
        selection_service=WordSelectionService(rng),
        question_factory=QuestionFactory(rng),
        answer_checker=AnswerChecker(),
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
