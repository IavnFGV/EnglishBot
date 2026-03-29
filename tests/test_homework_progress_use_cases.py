from pathlib import Path
import random

from englishbot.application.homework_progress_use_cases import (
    AssignmentSessionKind,
    AssignGoalToUsersUseCase,
    GetAdminGoalDetailUseCase,
    GetAdminUserGoalsUseCase,
    GetAdminUsersProgressOverviewUseCase,
    GetLearnerAssignmentLaunchSummaryUseCase,
    GoalWordSource,
    HomeworkProgressUseCase,
    StartAssignmentRoundUseCase,
)
from englishbot.domain.models import GoalPeriod, GoalType, TrainingMode, UserProgress
from englishbot.application.question_factory import QuestionFactory
from englishbot.infrastructure.sqlite_store import (
    SQLiteContentStore,
    SQLiteSessionRepository,
    SQLiteUserProgressRepository,
    SQLiteVocabularyRepository,
)


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


def test_assign_goal_to_multiple_users_with_topic_source(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = AssignGoalToUsersUseCase(store=store)

    created = use_case.execute(
        user_ids=[11, 12],
        goal_period=GoalPeriod.WEEKLY,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
        source=GoalWordSource.TOPIC,
        topic_id="animals",
    )

    assert len(created) == 2
    assert {goal.user_id for goal in created} == {11, 12}


def test_admin_progress_overview_aggregates_users(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    assign = AssignGoalToUsersUseCase(store=store)
    assign.execute(
        user_ids=[20, 21],
        goal_period=GoalPeriod.DAILY,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
        source=GoalWordSource.ALL,
    )

    overview = GetAdminUsersProgressOverviewUseCase(store=store).execute()

    assert len(overview) == 2
    assert overview[0].active_goals_count >= 1


def test_admin_goal_detail_returns_words_and_homework_stage(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=8,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["cat"],
    )

    detail = GetAdminGoalDetailUseCase(store=store).execute(user_id=8, goal_id=goal.id)

    assert detail is not None
    assert detail.goal.id == goal.id
    assert detail.words[0].word_id == "cat"
    assert detail.words[0].homework_mode is TrainingMode.EASY


def test_admin_user_goals_returns_history(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = HomeworkProgressUseCase(store=store)
    goal = use_case.create_goal(
        user_id=8,
        goal_period=GoalPeriod.DAILY,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
    )
    use_case.reset_goal(user_id=8, goal_id=goal.id)

    goals = GetAdminUserGoalsUseCase(store=store).execute(user_id=8, include_history=True)

    assert len(goals) == 1
    assert goals[0].goal.status.value == "expired"


def test_assignment_launch_summary_aggregates_daily_homework_and_all(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = HomeworkProgressUseCase(store=store)
    use_case.create_goal(
        user_id=9,
        goal_period=GoalPeriod.DAILY,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
        target_word_ids=["cat"],
    )
    use_case.create_goal(
        user_id=9,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["dog"],
    )
    store.save_progress(UserProgress(user_id=9, item_id="cat", times_seen=1, correct_answers=1))

    summary = GetLearnerAssignmentLaunchSummaryUseCase(store=store, batch_size=1).execute(user_id=9)
    summary_by_kind = {item.kind: item for item in summary}

    assert summary_by_kind[AssignmentSessionKind.DAILY].available is False
    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].remaining_word_count == 1
    assert summary_by_kind[AssignmentSessionKind.ALL].remaining_word_count == 1


def test_start_assignment_round_use_case_creates_assignment_session(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    HomeworkProgressUseCase(store=store).create_goal(
        user_id=10,
        goal_period=GoalPeriod.WEEKLY,
        goal_type=GoalType.NEW_WORDS,
        target_count=2,
        target_word_ids=["cat", "dog"],
    )
    use_case = StartAssignmentRoundUseCase(
        store=store,
        vocabulary_repository=SQLiteVocabularyRepository(store),
        progress_repository=SQLiteUserProgressRepository(store),
        session_repository=SQLiteSessionRepository(store),
        question_factory=QuestionFactory(random.Random(7)),
        batch_size=2,
    )

    question = use_case.execute(user_id=10, kind=AssignmentSessionKind.WEEKLY)
    session = SQLiteSessionRepository(store).get_active_by_user(10)

    assert session is not None
    assert question.session_id == session.id
    assert session.source_tag == "assignment:weekly"
    assert len(session.items) == 2
