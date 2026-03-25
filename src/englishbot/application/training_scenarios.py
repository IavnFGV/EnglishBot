from __future__ import annotations

import logging
from dataclasses import dataclass

from englishbot.application.errors import InvalidSessionStateError
from englishbot.application.services import AnswerOutcome, TrainingFacade
from englishbot.domain.models import TrainingMode, TrainingQuestion
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class UserAction:
    action_id: str
    label: str


@dataclass(slots=True, frozen=True)
class UserScreen:
    kind: str
    text: str
    actions: tuple[UserAction, ...] = ()
    expects_text_input: bool = False
    image_ref: str | None = None


class TrainingScenarioController:
    def __init__(self, service: TrainingFacade) -> None:
        self._service = service

    @logged_service_call(
        "TrainingScenarioController.start",
        include=("user_id",),
        result=lambda value: {"kind": value.kind, "action_count": len(value.actions)},
    )
    def start(self, *, user_id: int) -> UserScreen:
        active_session = self._service.get_active_session(user_id=user_id)
        if active_session is not None:
            return UserScreen(
                kind="active_session",
                text=(
                    "You already have an active session.\n"
                    f"Topic: {active_session.topic_id}\n"
                    f"Lesson: {active_session.lesson_id or 'all topic words'}\n"
                    f"Mode: {active_session.mode.value}\n"
                    f"Progress: {active_session.current_position}/{active_session.total_items}"
                ),
                actions=(
                    UserAction(action_id="continue_session", label="Continue"),
                    UserAction(action_id="restart_session", label="Restart"),
                ),
            )
        return self._topic_menu()

    @logged_service_call(
        "TrainingScenarioController.choose_topic",
        include=("topic_id",),
        result=lambda value: {"kind": value.kind, "action_count": len(value.actions)},
    )
    def choose_topic(self, *, topic_id: str) -> UserScreen:
        lesson_selection = self._service.list_lessons_by_topic(topic_id=topic_id)
        if lesson_selection.has_lessons:
            actions = [UserAction(action_id="lesson:all", label="All Topic Words")]
            actions.extend(
                UserAction(action_id=f"lesson:{lesson.id}", label=lesson.title)
                for lesson in lesson_selection.lessons
            )
            return UserScreen(
                kind="lesson_menu",
                text="Choose a lesson or train all words from the topic.",
                actions=tuple(actions),
            )
        return self._mode_menu()

    @logged_service_call(
        "TrainingScenarioController.choose_lesson",
        include=("topic_id", "lesson_id"),
        result=lambda value: {"kind": value.kind, "action_count": len(value.actions)},
    )
    def choose_lesson(self, *, topic_id: str, lesson_id: str | None) -> UserScreen:
        self._service.list_lessons_by_topic(topic_id=topic_id)
        return self._mode_menu()

    @logged_service_call(
        "TrainingScenarioController.choose_mode",
        include=("user_id", "topic_id", "lesson_id", "session_size"),
        transforms={"mode": lambda value: {"mode": value.value}},
        result=lambda value: {"kind": value.kind, "action_count": len(value.actions)},
    )
    def choose_mode(
        self,
        *,
        user_id: int,
        topic_id: str,
        lesson_id: str | None,
        mode: TrainingMode,
        session_size: int = 5,
    ) -> UserScreen:
        question = self._service.start_session(
            user_id=user_id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=mode,
            session_size=session_size,
        )
        return self._question_screen(question)

    @logged_service_call(
        "TrainingScenarioController.continue_session",
        include=("user_id",),
        result=lambda value: {"kind": value.kind, "action_count": len(value.actions)},
    )
    def continue_session(self, *, user_id: int) -> UserScreen:
        question = self._service.get_current_question(user_id=user_id)
        return self._question_screen(question)

    @logged_service_call(
        "TrainingScenarioController.restart_session",
        include=("user_id",),
        result=lambda value: {"kind": value.kind, "action_count": len(value.actions)},
    )
    def restart_session(self, *, user_id: int) -> UserScreen:
        self._service.discard_active_session(user_id=user_id)
        return self._topic_menu()

    @logged_service_call(
        "TrainingScenarioController.answer",
        include=("user_id",),
        transforms={"answer": lambda value: {"answer_length": len(value.strip())}},
        result=lambda value: {"kind": value.kind, "action_count": len(value.actions)},
    )
    def answer(self, *, user_id: int, answer: str) -> UserScreen:
        outcome = self._service.submit_answer(user_id=user_id, answer=answer)
        if outcome.session_completed:
            return self._summary_screen(outcome)
        if outcome.next_question is None:
            raise InvalidSessionStateError("Expected next question for incomplete session.")
        return self._question_screen(outcome.next_question)

    def _topic_menu(self) -> UserScreen:
        topics = self._service.list_topics()
        return UserScreen(
            kind="topic_menu",
            text="Choose a topic to start training.",
            actions=tuple(
                UserAction(action_id=f"topic:{topic.id}", label=topic.title) for topic in topics
            ),
        )

    def _mode_menu(self) -> UserScreen:
        return UserScreen(
            kind="mode_menu",
            text="Choose training mode.",
            actions=tuple(
                UserAction(action_id=f"mode:{mode.value}", label=mode.value.title())
                for mode in TrainingMode
            ),
        )

    def _question_screen(self, question: TrainingQuestion) -> UserScreen:
        actions: tuple[UserAction, ...] = ()
        expects_text_input = question.mode in {TrainingMode.MEDIUM, TrainingMode.HARD}
        if question.options:
            actions = tuple(
                UserAction(action_id=f"answer:{option}", label=option)
                for option in question.options
            )
        return UserScreen(
            kind="question",
            text=question.prompt,
            actions=actions,
            expects_text_input=expects_text_input,
            image_ref=question.image_ref,
        )

    def _summary_screen(self, outcome: AnswerOutcome) -> UserScreen:
        if outcome.summary is None:
            raise InvalidSessionStateError("Expected summary for completed session.")
        return UserScreen(
            kind="summary",
            text=(
                "Session completed.\n"
                f"Correct: {outcome.summary.correct_answers}/{outcome.summary.total_questions}\n"
                f"Incorrect: {outcome.summary.incorrect_answers}"
            ),
            actions=(UserAction(action_id="start_over", label="Start Over"),),
        )
