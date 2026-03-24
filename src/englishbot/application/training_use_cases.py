from __future__ import annotations

from dataclasses import dataclass

from englishbot.application.answer_checker import AnswerChecker
from englishbot.application.errors import InvalidSessionStateError, TopicNotFoundError
from englishbot.application.question_factory import QuestionFactory
from englishbot.application.session_summary import SessionSummaryCalculator
from englishbot.application.topic_use_cases import ListTopicsUseCase
from englishbot.application.word_selection import WordSelector
from englishbot.domain.models import (
    CheckResult,
    SessionItem,
    SessionSummary,
    TrainingMode,
    TrainingQuestion,
    TrainingSession,
    UserProgress,
)
from englishbot.domain.repositories import (
    SessionRepository,
    TopicRepository,
    UserProgressRepository,
    VocabularyRepository,
)


@dataclass(slots=True, frozen=True)
class AnswerOutcome:
    result: CheckResult
    summary: SessionSummary | None
    next_question: TrainingQuestion | None

    @property
    def session_completed(self) -> bool:
        return self.summary is not None


class StartTrainingSessionUseCase:
    def __init__(
        self,
        *,
        topic_repository: TopicRepository,
        vocabulary_repository: VocabularyRepository,
        progress_repository: UserProgressRepository,
        session_repository: SessionRepository,
        word_selector: WordSelector,
        question_factory: QuestionFactory,
    ) -> None:
        self._topic_repository = topic_repository
        self._vocabulary_repository = vocabulary_repository
        self._progress_repository = progress_repository
        self._session_repository = session_repository
        self._word_selector = word_selector
        self._question_factory = question_factory

    def execute(
        self,
        *,
        user_id: int,
        topic_id: str,
        mode: TrainingMode,
        session_size: int = 5,
        lesson_id: str | None = None,
    ) -> TrainingQuestion:
        topic = self._topic_repository.get_by_id(topic_id)
        if topic is None:
            raise TopicNotFoundError(f"Unknown topic: {topic_id}")
        topic_items = self._vocabulary_repository.list_by_topic(topic_id, lesson_id)
        progress_items = self._progress_repository.list_by_user(user_id)
        selected_items = self._word_selector.select_words(
            user_id=user_id,
            items=topic_items,
            progress_items=progress_items,
            session_size=session_size,
        )
        session = TrainingSession(
            id=f"{user_id}:{topic_id}:{mode.value}",
            user_id=user_id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=mode,
            items=[
                SessionItem(order=index, vocabulary_item_id=item.id)
                for index, item in enumerate(selected_items)
            ],
        )
        self._session_repository.save(session)
        return self._question_factory.create_question(
            session=session,
            item=self._require_session_item(session),
            all_topic_items=topic_items,
        )

    def _require_session_item(self, session: TrainingSession):
        item = self._vocabulary_repository.get_by_id(session.current_item_id())
        if item is None:
            raise InvalidSessionStateError("Session references a missing vocabulary item.")
        return item


class GetCurrentQuestionUseCase:
    def __init__(
        self,
        *,
        vocabulary_repository: VocabularyRepository,
        session_repository: SessionRepository,
        question_factory: QuestionFactory,
    ) -> None:
        self._vocabulary_repository = vocabulary_repository
        self._session_repository = session_repository
        self._question_factory = question_factory

    def execute(self, *, user_id: int) -> TrainingQuestion:
        session = self._require_active_session(user_id)
        try:
            item_id = session.current_item_id()
        except ValueError as error:
            raise InvalidSessionStateError(str(error)) from error
        item = self._vocabulary_repository.get_by_id(item_id)
        if item is None:
            raise InvalidSessionStateError("Session references a missing vocabulary item.")
        topic_items = self._vocabulary_repository.list_by_topic(session.topic_id, session.lesson_id)
        return self._question_factory.create_question(
            session=session,
            item=item,
            all_topic_items=topic_items,
        )

    def _require_active_session(self, user_id: int) -> TrainingSession:
        session = self._session_repository.get_active_by_user(user_id)
        if session is None:
            raise InvalidSessionStateError("The user has no active training session.")
        return session


class SubmitAnswerUseCase:
    def __init__(
        self,
        *,
        progress_repository: UserProgressRepository,
        session_repository: SessionRepository,
        get_current_question: GetCurrentQuestionUseCase,
        answer_checker: AnswerChecker,
        summary_calculator: SessionSummaryCalculator,
    ) -> None:
        self._progress_repository = progress_repository
        self._session_repository = session_repository
        self._get_current_question = get_current_question
        self._answer_checker = answer_checker
        self._summary_calculator = summary_calculator

    def execute(self, *, user_id: int, answer: str) -> AnswerOutcome:
        session = self._require_active_session(user_id)
        question = self._get_current_question.execute(user_id=user_id)
        result = self._answer_checker.check(question=question, answer=answer)
        progress = self._progress_repository.get(user_id, question.item_id) or UserProgress(
            user_id=user_id,
            item_id=question.item_id,
        )
        progress.record(result.is_correct)
        self._progress_repository.save(progress)
        try:
            session.record_answer(answer=answer, is_correct=result.is_correct)
        except ValueError as error:
            raise InvalidSessionStateError(str(error)) from error
        self._session_repository.save(session)
        if session.completed:
            summary = self._summary_calculator.calculate(session)
            return AnswerOutcome(result=result, summary=summary, next_question=None)
        next_question = self._get_current_question.execute(user_id=user_id)
        return AnswerOutcome(result=result, summary=None, next_question=next_question)

    def _require_active_session(self, user_id: int) -> TrainingSession:
        session = self._session_repository.get_active_by_user(user_id)
        if session is None:
            raise InvalidSessionStateError("The user has no active training session.")
        return session


class TrainingFacade:
    """Thin facade used by Telegram adapters and tests."""

    def __init__(
        self,
        *,
        list_topics: ListTopicsUseCase,
        start_training_session: StartTrainingSessionUseCase,
        get_current_question: GetCurrentQuestionUseCase,
        submit_answer: SubmitAnswerUseCase,
    ) -> None:
        self._list_topics = list_topics
        self._start_training_session = start_training_session
        self._get_current_question = get_current_question
        self._submit_answer = submit_answer

    def list_topics(self):
        return self._list_topics.execute()

    def start_session(
        self,
        *,
        user_id: int,
        topic_id: str,
        mode: TrainingMode,
        session_size: int = 5,
        lesson_id: str | None = None,
    ) -> TrainingQuestion:
        return self._start_training_session.execute(
            user_id=user_id,
            topic_id=topic_id,
            mode=mode,
            session_size=session_size,
            lesson_id=lesson_id,
        )

    def get_current_question(self, *, user_id: int) -> TrainingQuestion:
        return self._get_current_question.execute(user_id=user_id)

    def submit_answer(self, *, user_id: int, answer: str) -> AnswerOutcome:
        return self._submit_answer.execute(user_id=user_id, answer=answer)
