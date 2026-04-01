from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass

from englishbot.application.answer_checker import AnswerChecker
from englishbot.application.clock import Clock, SystemClock
from englishbot.application.errors import InvalidSessionStateError, TopicNotFoundError
from englishbot.application.learning_progress import apply_attempt, choose_word_mode
from englishbot.application.lesson_use_cases import (
    ListLessonsByTopicUseCase,
    ValidateTopicLessonUseCase,
)
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
    WordStats,
)
from englishbot.domain.repositories import (
    SessionRepository,
    TopicRepository,
    UserProgressRepository,
    VocabularyRepository,
)
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


def _homework_goal_id_from_source_tag(source_tag: str | None) -> str | None:
    if source_tag is None or not source_tag.startswith("assignment:homework:"):
        return None
    _, _, goal_id = source_tag.partition("assignment:homework:")
    return goal_id or None


@dataclass(slots=True, frozen=True)
class AnswerOutcome:
    result: CheckResult
    summary: SessionSummary | None
    next_question: TrainingQuestion | None

    @property
    def session_completed(self) -> bool:
        return self.summary is not None


@dataclass(slots=True, frozen=True)
class ActiveSessionInfo:
    session_id: str
    topic_id: str
    lesson_id: str | None
    source_tag: str | None
    mode: TrainingMode
    current_position: int
    total_items: int


class StartTrainingSessionUseCase:
    def __init__(
        self,
        *,
        topic_repository: TopicRepository,
        vocabulary_repository: VocabularyRepository,
        progress_repository: UserProgressRepository,
        session_repository: SessionRepository,
        validate_topic_lesson: ValidateTopicLessonUseCase,
        word_selector: WordSelector,
        question_factory: QuestionFactory,
    ) -> None:
        self._topic_repository = topic_repository
        self._vocabulary_repository = vocabulary_repository
        self._progress_repository = progress_repository
        self._session_repository = session_repository
        self._validate_topic_lesson = validate_topic_lesson
        self._word_selector = word_selector
        self._question_factory = question_factory

    @logged_service_call(
        "StartTrainingSessionUseCase.execute",
        include=("user_id", "topic_id", "lesson_id", "session_size"),
        transforms={"mode": lambda value: {"mode": value.value}},
        result=lambda question: {
            "session_id": question.session_id,
            "item_id": question.item_id,
        },
    )
    def execute(
        self,
        *,
        user_id: int,
        topic_id: str,
        mode: TrainingMode,
        session_size: int = 5,
        lesson_id: str | None = None,
        adaptive_per_word: bool = False,
    ) -> TrainingQuestion:
        topic = self._topic_repository.get_by_id(topic_id)
        if topic is None:
            logger.warning("StartTrainingSessionUseCase unknown topic_id=%s", topic_id)
            raise TopicNotFoundError(f"Unknown topic: {topic_id}")
        self._validate_topic_lesson.execute(topic_id=topic_id, lesson_id=lesson_id)
        topic_items = self._vocabulary_repository.list_by_topic(topic_id, lesson_id)
        progress_items = self._progress_repository.list_by_user(user_id)
        selected_items = (
            self._word_selector.select_game_words(
                user_id=user_id,
                topic_id=topic_id,
                items=topic_items,
                progress_items=progress_items,
                session_size=session_size,
            )
            if adaptive_per_word
            else self._word_selector.select_words(
                user_id=user_id,
                items=topic_items,
                progress_items=progress_items,
                session_size=session_size,
            )
        )
        item_modes = {}
        hard_limit = max(1, session_size // 4) if adaptive_per_word else 0
        hard_selected = 0
        if adaptive_per_word:
            for item in selected_items:
                homework_mode = None
                if hasattr(self._progress_repository, "get_homework_stage_mode"):
                    homework_mode = self._progress_repository.get_homework_stage_mode(
                        user_id=user_id,
                        item_id=item.id,
                    )
                if homework_mode is not None:
                    if homework_mode is TrainingMode.HARD and hard_selected >= hard_limit:
                        homework_mode = TrainingMode.MEDIUM
                    item_modes[item.id] = homework_mode
                    if homework_mode is TrainingMode.HARD:
                        hard_selected += 1
                    continue
                required_level = None
                if hasattr(self._progress_repository, "required_homework_level"):
                    required_level = self._progress_repository.required_homework_level(
                        user_id=user_id,
                        item_id=item.id,
                    )
                level = 0
                if hasattr(self._progress_repository, "get_word_stats"):
                    word_stats = self._progress_repository.get_word_stats(user_id, item.id)
                    if word_stats is not None:
                        level = word_stats.current_level
                item_modes[item.id] = choose_word_mode(
                    current_level=level,
                    rng=random.Random(f"{user_id}:{item.id}:{session_size}"),
                    min_required_level=required_level,
                )
                if item_modes[item.id] is TrainingMode.HARD:
                    hard_selected += 1
        session = TrainingSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=mode,
            items=[
                SessionItem(order=index, vocabulary_item_id=item.id, mode=item_modes.get(item.id))
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

    @logged_service_call(
        "GetCurrentQuestionUseCase.execute",
        include=("user_id",),
        result=lambda question: {
            "session_id": question.session_id,
            "item_id": question.item_id,
        },
    )
    def execute(self, *, user_id: int) -> TrainingQuestion:
        session = self._require_active_session(user_id)
        try:
            item_id = session.current_item_id()
        except ValueError as error:
            raise InvalidSessionStateError(str(error)) from error
        item = self._vocabulary_repository.get_by_id(item_id)
        if item is None:
            raise InvalidSessionStateError("Session references a missing vocabulary item.")
        topic_items = self._resolve_question_pool(session)
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

    def _resolve_question_pool(self, session: TrainingSession) -> list[VocabularyItem]:
        if session.source_tag is not None and session.source_tag.startswith("assignment:"):
            items: list[VocabularyItem] = []
            for session_item in session.items:
                item = self._vocabulary_repository.get_by_id(session_item.vocabulary_item_id)
                if item is not None:
                    items.append(item)
            return items
        return self._vocabulary_repository.list_by_topic(session.topic_id, session.lesson_id)


class SubmitAnswerUseCase:
    def __init__(
        self,
        *,
        progress_repository: UserProgressRepository,
        session_repository: SessionRepository,
        get_current_question: GetCurrentQuestionUseCase,
        answer_checker: AnswerChecker,
        summary_calculator: SessionSummaryCalculator,
        clock: Clock | None = None,
    ) -> None:
        self._progress_repository = progress_repository
        self._session_repository = session_repository
        self._get_current_question = get_current_question
        self._answer_checker = answer_checker
        self._summary_calculator = summary_calculator
        self._clock = clock or SystemClock()

    @logged_service_call(
        "SubmitAnswerUseCase.execute",
        include=("user_id",),
        transforms={"answer": lambda value: {"answer_length": len(value.strip())}},
        result=lambda outcome: {
            "is_correct": outcome.result.is_correct,
            "session_completed": outcome.session_completed,
            "next_item_id": (
                outcome.next_question.item_id if outcome.next_question is not None else None
            ),
        },
    )
    def execute(self, *, user_id: int, answer: str) -> AnswerOutcome:
        session = self._require_active_session(user_id)
        question = self._get_current_question.execute(user_id=user_id)
        result = self._answer_checker.check(question=question, answer=answer)
        progress = self._progress_repository.get(user_id, question.item_id) or UserProgress(
            user_id=user_id,
            item_id=question.item_id,
        )
        progress.record(result.is_correct)
        progress.last_seen_at = self._clock.now()
        self._progress_repository.save(progress)
        level_up_delta = 0
        bonus_hard_started = False
        assignment_goal_id = _homework_goal_id_from_source_tag(session.source_tag)
        if hasattr(self._progress_repository, "get_word_stats") and hasattr(
            self._progress_repository, "save_word_stats"
        ):
            word_stats = self._progress_repository.get_word_stats(user_id, question.item_id)
            if word_stats is None:
                word_stats = WordStats(user_id=user_id, word_id=question.item_id)
            previous_level, current_level = apply_attempt(
                stats=word_stats,
                mode=question.mode,
                is_correct=result.is_correct,
                seen_at=self._clock.now(),
            )
            level_up_delta = max(0, current_level - previous_level)
            self._progress_repository.save_word_stats(word_stats)
            if result.is_correct and hasattr(self._progress_repository, "award_weekly_points"):
                self._progress_repository.award_weekly_points(
                    user_id=user_id,
                    word_id=question.item_id,
                    mode=question.mode,
                    level_up_delta=level_up_delta,
                    awarded_at=self._clock.now(),
                )
            if hasattr(self._progress_repository, "update_goals_progress"):
                self._progress_repository.update_goals_progress(
                    user_id=user_id,
                    word_id=question.item_id,
                    topic_id=session.topic_id,
                    is_correct=result.is_correct,
                    current_level=word_stats.current_level,
                )
            if hasattr(self._progress_repository, "update_homework_word_progress"):
                progress_update = self._progress_repository.update_homework_word_progress(
                    user_id=user_id,
                    word_id=question.item_id,
                    mode=question.mode,
                    is_correct=result.is_correct,
                    current_level=word_stats.current_level,
                    goal_id=assignment_goal_id,
                    offer_bonus_hard=(
                        bool(result.is_correct)
                        and question.mode is TrainingMode.MEDIUM
                        and assignment_goal_id is not None
                        and random.random() < 0.25
                    ),
                )
                bonus_hard_started = bool(getattr(progress_update, "bonus_hard_unlocked", False))
        try:
            session.record_answer(
                answer=answer,
                is_correct=result.is_correct,
                start_bonus_for_item_id=(
                    question.item_id
                    if bonus_hard_started and result.is_correct and question.mode is TrainingMode.MEDIUM
                    else None
                ),
                bonus_mode=(TrainingMode.HARD if bonus_hard_started else None),
            )
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


class GetActiveSessionUseCase:
    def __init__(self, session_repository: SessionRepository) -> None:
        self._session_repository = session_repository

    @logged_service_call(
        "GetActiveSessionUseCase.execute",
        include=("user_id",),
        result=lambda session: {
            "found": session is not None,
            "session_id": session.session_id if session is not None else None,
            "current_position": session.current_position if session is not None else None,
            "total_items": session.total_items if session is not None else None,
        },
    )
    def execute(self, *, user_id: int) -> ActiveSessionInfo | None:
        session = self._session_repository.get_active_by_user(user_id)
        if session is None:
            return None
        current_position = min(session.current_index + 1, session.total_items) if session.total_items > 0 else 0
        return ActiveSessionInfo(
            session_id=session.id,
            topic_id=session.topic_id,
            lesson_id=session.lesson_id,
            source_tag=session.source_tag,
            mode=session.mode,
            current_position=current_position,
            total_items=session.total_items,
        )


class DiscardActiveSessionUseCase:
    def __init__(self, session_repository: SessionRepository) -> None:
        self._session_repository = session_repository

    @logged_service_call(
        "DiscardActiveSessionUseCase.execute",
        include=("user_id",),
    )
    def execute(self, *, user_id: int) -> None:
        self._session_repository.discard_active_by_user(user_id)


class TrainingFacade:
    """Thin facade used by Telegram adapters and tests."""

    def __init__(
        self,
        *,
        list_topics: ListTopicsUseCase,
        list_lessons_by_topic: ListLessonsByTopicUseCase,
        start_training_session: StartTrainingSessionUseCase,
        get_active_session: GetActiveSessionUseCase,
        get_current_question: GetCurrentQuestionUseCase,
        discard_active_session: DiscardActiveSessionUseCase,
        submit_answer: SubmitAnswerUseCase,
    ) -> None:
        self._list_topics = list_topics
        self._list_lessons_by_topic = list_lessons_by_topic
        self._start_training_session = start_training_session
        self._get_active_session = get_active_session
        self._get_current_question = get_current_question
        self._discard_active_session = discard_active_session
        self._submit_answer = submit_answer

    def list_topics(self):
        return self._list_topics.execute()

    def list_lessons_by_topic(self, *, topic_id: str):
        return self._list_lessons_by_topic.execute(topic_id=topic_id)

    def get_active_session(self, *, user_id: int) -> ActiveSessionInfo | None:
        return self._get_active_session.execute(user_id=user_id)

    def start_session(
        self,
        *,
        user_id: int,
        topic_id: str,
        mode: TrainingMode,
        session_size: int = 5,
        lesson_id: str | None = None,
        adaptive_per_word: bool = False,
    ) -> TrainingQuestion:
        return self._start_training_session.execute(
            user_id=user_id,
            topic_id=topic_id,
            mode=mode,
            session_size=session_size,
            lesson_id=lesson_id,
            adaptive_per_word=adaptive_per_word,
        )

    def get_current_question(self, *, user_id: int) -> TrainingQuestion:
        return self._get_current_question.execute(user_id=user_id)

    def discard_active_session(self, *, user_id: int) -> None:
        self._discard_active_session.execute(user_id=user_id)

    def submit_answer(self, *, user_id: int, answer: str) -> AnswerOutcome:
        return self._submit_answer.execute(user_id=user_id, answer=answer)
