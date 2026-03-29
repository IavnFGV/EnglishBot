from pathlib import Path

from englishbot.application.homework_progress_use_cases import HomeworkProgressUseCase
from englishbot.domain.models import GoalPeriod, GoalType, TrainingMode, UserProgress
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


def _build_store(tmp_path: Path) -> SQLiteContentStore:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "animals", "title": "Animals"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "cat", "english_word": "Cat", "translation": "кот"},
                {"id": "dog", "english_word": "Dog", "translation": "собака"},
            ],
        }
    )
    return store


def test_homework_progress_use_case_creates_and_summarizes_goal(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = HomeworkProgressUseCase(store=store)

    progress = UserProgress(user_id=3, item_id="cat", times_seen=2, correct_answers=1, incorrect_answers=1)
    store.save_progress(progress)
    store.award_weekly_points(
        user_id=3,
        word_id="cat",
        mode=TrainingMode.MEDIUM,
        level_up_delta=1,
        awarded_at=__import__("datetime").datetime(2026, 3, 24, tzinfo=__import__("datetime").UTC),
    )

    created = use_case.create_goal(
        user_id=3,
        goal_period=GoalPeriod.DAILY,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
    )
    summary = use_case.get_summary(user_id=3)

    assert created.target_count == 1
    assert summary.correct_answers == 1
    assert summary.incorrect_answers == 1
    assert summary.weekly_points > 0
    assert len(summary.active_goals) == 1


def test_homework_progress_use_case_resets_goal(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = HomeworkProgressUseCase(store=store)
    goal = use_case.create_goal(
        user_id=8,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["cat"],
    )

    reset = use_case.reset_goal(user_id=8, goal_id=goal.id)
    summary = use_case.get_summary(user_id=8)

    assert reset is True
    assert summary.active_goals == []
