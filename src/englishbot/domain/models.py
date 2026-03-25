from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class TrainingMode(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


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
class VocabularyItem:
    id: str
    english_word: str
    translation: str
    topic_id: str
    lesson_id: str | None = None
    image_ref: str | None = None
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
