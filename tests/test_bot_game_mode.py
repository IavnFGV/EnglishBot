from types import SimpleNamespace

import pytest

from englishbot.application.training_use_cases import AnswerOutcome
from englishbot.bot import _mode_keyboard, _process_answer, game_mode_selected_handler
from englishbot.domain.models import CheckResult, SessionSummary, TrainingMode, TrainingQuestion


class _FakeStore:
    def __init__(self) -> None:
        self.total_stars = 0
        self.streak_days = 2

    def update_game_streak(self, *, user_id: int, played_at):  # noqa: ARG002
        self.streak_days += 1
        return self.streak_days

    def add_game_stars(self, *, user_id: int, stars: int):  # noqa: ARG002
        self.total_stars += stars
        return self.total_stars


class _FakeService:
    def __init__(self, outcomes: list[AnswerOutcome] | None = None) -> None:
        self.outcomes = outcomes or []

    def start_session(self, *, user_id: int, topic_id: str, lesson_id: str | None, mode: TrainingMode):
        return TrainingQuestion(
            session_id="s1",
            item_id="i1",
            mode=mode,
            prompt=f"{topic_id}:{lesson_id}",
            image_ref=None,
            correct_answer="cat",
            options=["cat", "dog", "sun"] if mode is TrainingMode.EASY else None,
        )

    def submit_answer(self, *, user_id: int, answer: str):  # noqa: ARG002
        return self.outcomes.pop(0)

    def get_active_session(self, *, user_id: int):  # noqa: ARG002
        return SimpleNamespace(current_position=2)


class _FakeMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=42, language_code="en")
        self.replies: list[tuple[str, object | None]] = []

    async def reply_text(self, text: str, reply_markup=None, parse_mode=None):  # noqa: ARG002
        self.replies.append((text, reply_markup))


class _FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.edits: list[tuple[str, object | None]] = []

    async def answer(self) -> None:
        return None

    async def edit_message_text(self, text: str, reply_markup=None) -> None:
        self.edits.append((text, reply_markup))


@pytest.mark.anyio
async def test_game_mode_selected_handler_starts_game_state() -> None:
    query = _FakeQuery("gamemode:animals:all:easy")
    user = SimpleNamespace(id=42, language_code="en")
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "training_service": _FakeService(),
                "content_store": _FakeStore(),
                "telegram_ui_language": "en",
            }
        ),
    )
    update = SimpleNamespace(callback_query=query, effective_user=user, effective_message=_FakeMessage())

    await game_mode_selected_handler(update, context)  # type: ignore[arg-type]

    assert context.user_data["game_mode_state"]["active"] is True
    assert context.user_data["game_mode_state"]["topic_id"] == "animals"
    assert context.user_data["awaiting_text_answer"] is False
    assert query.edits
    assert "Game on" in query.edits[0][0]


@pytest.mark.anyio
async def test_process_answer_in_game_mode_sends_feedback_and_completion() -> None:
    message = _FakeMessage()
    outcomes = [
        AnswerOutcome(
            result=CheckResult(is_correct=True, expected_answer="cat", normalized_answer="cat"),
            summary=None,
            next_question=TrainingQuestion(
                session_id="s1",
                item_id="i2",
                mode=TrainingMode.EASY,
                prompt="q2",
                image_ref=None,
                correct_answer="sun",
                options=["sun", "moon", "book"],
            ),
        ),
        AnswerOutcome(
            result=CheckResult(is_correct=False, expected_answer="sun", normalized_answer="son"),
            summary=SessionSummary(total_questions=5, correct_answers=1),
            next_question=None,
        ),
    ]
    context = SimpleNamespace(
        user_data={
            "game_mode_state": {
                "active": True,
                "topic_id": "animals",
                "lesson_id": None,
                "mode_value": "easy",
                "session_stars": 0,
                "correct_answers": 0,
            }
        },
        application=SimpleNamespace(
            bot_data={
                "training_service": _FakeService(outcomes),
                "content_store": _FakeStore(),
                "telegram_ui_language": "en",
            }
        ),
    )
    update = SimpleNamespace(effective_user=message.from_user, effective_message=message)

    await _process_answer(update, context, "cat")  # type: ignore[arg-type]
    await _process_answer(update, context, "son")  # type: ignore[arg-type]

    assert any("Progress: 1/5" in text for text, _ in message.replies)
    assert any("Level complete" in text for text, _ in message.replies)


def test_mode_keyboard_contains_game_mode_entry() -> None:
    keyboard = _mode_keyboard("animals", None, language="en")
    rows = keyboard.inline_keyboard

    assert rows[1][0].callback_data == "gameentry:animals:all"
    assert rows[1][0].text == "🎮 Game Mode"
