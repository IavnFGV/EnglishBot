from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class TrainingMode(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class GoalPeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    HOMEWORK = "homework"


class GoalType(StrEnum):
    NEW_WORDS = "new_words"
    ROUNDS = "rounds"
    TOPICS = "topics"
    ACTIVE_DAYS = "active_days"
    WORD_LEVEL_HOMEWORK = "word_level_homework"


class GoalStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


@dataclass(slots=True, frozen=True)
class Topic:
    id: str
    title: str


@dataclass(slots=True, frozen=True)
class Lesson:
    id: str
    title: str
    topic_id: str | None = None


@dataclass(slots=True, frozen=True)
class Lexeme:
    id: str
    headword: str
    normalized_headword: str
    part_of_speech: str | None = None
    notes: str | None = None


@dataclass(slots=True, frozen=True)
class VocabularyItem:
    id: str
    english_word: str
    translation: str
    lexeme_id: str | None = None
    topic_id: str | None = None
    lesson_id: str | None = None
    meaning_hint: str | None = None
    image_ref: str | None = None
    image_source: str | None = None
    image_prompt: str | None = None
    pixabay_search_query: str | None = None
    source_fragment: str | None = None
    is_active: bool = True


@dataclass(slots=True)
class UserProgress:
    user_id: int
    item_id: str
    times_seen: int = 0
    correct_answers: int = 0
    incorrect_answers: int = 0
    last_result: bool | None = None
    last_seen_at: datetime | None = None

    def record(self, is_correct: bool) -> None:
        self.times_seen += 1
        self.last_result = is_correct
        if is_correct:
            self.correct_answers += 1
        else:
            self.incorrect_answers += 1


@dataclass(slots=True, frozen=True)
class SessionItem:
    order: int
    vocabulary_item_id: str
    mode: TrainingMode | None = None


@dataclass(slots=True, frozen=True)
class SessionAnswer:
    item_id: str
    submitted_answer: str
    is_correct: bool


@dataclass(slots=True)
class TrainingSession:
    id: str
    user_id: int
    topic_id: str
    mode: TrainingMode
    items: list[SessionItem]
    lesson_id: str | None = None
    source_tag: str | None = None
    current_index: int = 0
    answer_history: list[SessionAnswer] = field(default_factory=list)
    completed: bool = False

    @property
    def total_items(self) -> int:
        return len(self.items)

    def current_item_id(self) -> str:
        if self.completed:
            raise ValueError("Session is already completed.")
        if self.current_index >= len(self.items):
            raise ValueError("Session has no current item.")
        return self.items[self.current_index].vocabulary_item_id

    def record_answer(self, *, answer: str, is_correct: bool) -> None:
        if self.completed:
            raise ValueError("Session is already completed.")
        if self.current_index >= len(self.items):
            raise ValueError("Session index is out of bounds.")
        self.answer_history.append(
            SessionAnswer(
                item_id=self.items[self.current_index].vocabulary_item_id,
                submitted_answer=answer.strip(),
                is_correct=is_correct,
            )
        )
        self.current_index += 1
        if self.current_index >= len(self.items):
            self.completed = True


@dataclass(slots=True, frozen=True)
class CheckResult:
    is_correct: bool
    expected_answer: str
    normalized_answer: str


@dataclass(slots=True, frozen=True)
class TrainingQuestion:
    session_id: str
    item_id: str
    mode: TrainingMode
    prompt: str
    image_ref: str | None
    correct_answer: str
    options: list[str] | None = None
    input_hint: str | None = None
    letter_hint: str | None = None


@dataclass(slots=True, frozen=True)
class SessionSummary:
    total_questions: int
    correct_answers: int

    @property
    def incorrect_answers(self) -> int:
        return self.total_questions - self.correct_answers


@dataclass(slots=True)
class WordStats:
    user_id: int
    word_id: str
    attempt_easy: int = 0
    attempt_medium: int = 0
    attempt_hard: int = 0
    success_easy: int = 0
    success_medium: int = 0
    success_hard: int = 0
    last_seen_at: datetime | None = None
    last_correct_at: datetime | None = None
    current_level: int = 0
    current_streak_success: int = 0
    current_streak_fail: int = 0
    review_interval_days: int = 0
    next_review_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class Goal:
    id: str
    user_id: int
    goal_period: GoalPeriod
    goal_type: GoalType
    target_count: int
    progress_count: int
    status: GoalStatus
    deadline_date: str | None = None
    reward_points: int | None = None
    required_level: int | None = None
    target_topic_id: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class GoalWordTarget:
    goal_id: str
    word_id: str


@dataclass(slots=True)
class HomeworkWordProgress:
    goal_id: str
    user_id: int
    word_id: str
    easy_success_count: int = 0
    medium_success_count: int = 0
    hard_success_count: int = 0
    easy_mastered: bool = False
    medium_mastered: bool = False
    hard_mastered: bool = False
    hard_skipped: bool = False
    hard_failed_streak: int = 0
