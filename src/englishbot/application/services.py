from __future__ import annotations

import random
from dataclasses import dataclass

from englishbot.domain.models import (
    CheckResult,
    SessionItem,
    SessionSummary,
    Topic,
    TrainingMode,
    TrainingQuestion,
    TrainingSession,
    UserProgress,
    VocabularyItem,
)
from englishbot.domain.repositories import (
    SessionRepository,
    TopicRepository,
    UserProgressRepository,
    VocabularyRepository,
)


class ApplicationError(Exception):
    """Base error for application-level failures."""


class TopicNotFoundError(ApplicationError):
    """Raised when a topic does not exist."""


class EmptyTopicError(ApplicationError):
    """Raised when a topic has no available words."""


class InvalidSessionStateError(ApplicationError):
    """Raised when the requested session action is invalid."""


class NotEnoughOptionsError(ApplicationError):
    """Raised when a multiple choice question cannot be formed."""


@dataclass(slots=True, frozen=True)
class AnswerOutcome:
    result: CheckResult
    summary: SessionSummary | None
    next_question: TrainingQuestion | None

    @property
    def session_completed(self) -> bool:
        return self.summary is not None


class WordSelectionService:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def select_words(
        self,
        *,
        user_id: int,
        items: list[VocabularyItem],
        progress_items: list[UserProgress],
        session_size: int,
    ) -> list[VocabularyItem]:
        if not items:
            raise EmptyTopicError("The selected topic has no words.")
        progress_map = {progress.item_id: progress for progress in progress_items}

        def score(item: VocabularyItem) -> tuple[int, int, str]:
            progress = progress_map.get(item.id)
            if progress is None:
                progress = UserProgress(user_id=user_id, item_id=item.id)
            return (
                progress.times_seen,
                progress.incorrect_answers - progress.correct_answers,
                item.english_word,
            )

        ordered = sorted(
            items,
            key=score,
        )
        selected = ordered[: min(session_size, len(ordered))]
        self._rng.shuffle(selected)
        return selected


class QuestionFactory:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def create_question(
        self,
        *,
        session: TrainingSession,
        item: VocabularyItem,
        all_topic_items: list[VocabularyItem],
    ) -> TrainingQuestion:
        image_line = item.image_ref or "No image yet. Use the translation clue."
        if session.mode is TrainingMode.EASY:
            options = self._build_choice_options(item, all_topic_items)
            prompt = (
                f"Translation: {item.translation}\n"
                f"Visual clue: {image_line}\n"
                "Choose the correct English word."
            )
            return TrainingQuestion(
                session_id=session.id,
                item_id=item.id,
                mode=session.mode,
                prompt=prompt,
                image_ref=item.image_ref,
                correct_answer=item.english_word,
                options=options,
            )
        if session.mode is TrainingMode.MEDIUM:
            options = self._build_choice_options(item, all_topic_items)
            scrambled = self._scramble_word(item.english_word)
            prompt = (
                f"Translation: {item.translation}\n"
                f"Visual clue: {image_line}\n"
                f"Scrambled letters: {scrambled}\n"
                "Pick the correct ordered word."
            )
            return TrainingQuestion(
                session_id=session.id,
                item_id=item.id,
                mode=session.mode,
                prompt=prompt,
                image_ref=item.image_ref,
                correct_answer=item.english_word,
                options=options,
            )
        prompt = (
            f"Translation: {item.translation}\n"
            f"Visual clue: {image_line}\n"
            "Type the English word."
        )
        return TrainingQuestion(
            session_id=session.id,
            item_id=item.id,
            mode=session.mode,
            prompt=prompt,
            image_ref=item.image_ref,
            correct_answer=item.english_word,
            input_hint="Type the word in English.",
        )

    def _build_choice_options(
        self, correct_item: VocabularyItem, all_topic_items: list[VocabularyItem]
    ) -> list[str]:
        distractors = [
            item.english_word
            for item in all_topic_items
            if item.id != correct_item.id and item.english_word != correct_item.english_word
        ]
        unique_distractors = sorted(set(distractors))
        if len(unique_distractors) < 2:
            raise NotEnoughOptionsError(
                "At least three distinct words are required for multiple choice."
            )
        options = [correct_item.english_word, *self._rng.sample(unique_distractors, 2)]
        self._rng.shuffle(options)
        return options

    def _scramble_word(self, word: str) -> str:
        letters = list(word)
        if len(letters) <= 1:
            return word
        for _ in range(5):
            shuffled = letters[:]
            self._rng.shuffle(shuffled)
            scrambled = "".join(shuffled)
            if scrambled.lower() != word.lower():
                return scrambled
        return word[::-1]


class AnswerChecker:
    def check(self, *, question: TrainingQuestion, answer: str) -> CheckResult:
        normalized_answer = answer.strip().lower()
        expected_answer = question.correct_answer.strip().lower()
        return CheckResult(
            is_correct=normalized_answer == expected_answer,
            expected_answer=question.correct_answer,
            normalized_answer=answer.strip(),
        )


class TrainingApplicationService:
    def __init__(
        self,
        *,
        topic_repository: TopicRepository,
        vocabulary_repository: VocabularyRepository,
        progress_repository: UserProgressRepository,
        session_repository: SessionRepository,
        selection_service: WordSelectionService,
        question_factory: QuestionFactory,
        answer_checker: AnswerChecker,
    ) -> None:
        self._topic_repository = topic_repository
        self._vocabulary_repository = vocabulary_repository
        self._progress_repository = progress_repository
        self._session_repository = session_repository
        self._selection_service = selection_service
        self._question_factory = question_factory
        self._answer_checker = answer_checker

    def list_topics(self) -> list[Topic]:
        return self._topic_repository.list_topics()

    def start_session(
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
        selected_items = self._selection_service.select_words(
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
        return self.get_current_question(user_id)

    def get_current_question(self, user_id: int) -> TrainingQuestion:
        session = self._require_active_session(user_id)
        item = self._vocabulary_repository.get_by_id(session.current_item_id())
        if item is None:
            raise InvalidSessionStateError("Session references a missing vocabulary item.")
        topic_items = self._vocabulary_repository.list_by_topic(session.topic_id, session.lesson_id)
        return self._question_factory.create_question(
            session=session,
            item=item,
            all_topic_items=topic_items,
        )

    def submit_answer(self, *, user_id: int, answer: str) -> AnswerOutcome:
        session = self._require_active_session(user_id)
        question = self.get_current_question(user_id)
        result = self._answer_checker.check(question=question, answer=answer)
        progress = self._progress_repository.get(user_id, question.item_id) or UserProgress(
            user_id=user_id,
            item_id=question.item_id,
        )
        progress.record(result.is_correct)
        self._progress_repository.save(progress)
        session.record_answer(result.is_correct)
        self._session_repository.save(session)
        if session.completed:
            summary = SessionSummary(
                total_questions=session.total_items,
                correct_answers=sum(session.answers),
            )
            return AnswerOutcome(result=result, summary=summary, next_question=None)
        next_question = self.get_current_question(user_id)
        return AnswerOutcome(result=result, summary=None, next_question=next_question)

    def _require_active_session(self, user_id: int) -> TrainingSession:
        session = self._session_repository.get_active_by_user(user_id)
        if session is None:
            raise InvalidSessionStateError("The user has no active training session.")
        return session
