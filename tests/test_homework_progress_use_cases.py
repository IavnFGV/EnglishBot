import random
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from englishbot.domain.models import GoalPeriod, GoalStatus, GoalType, TrainingMode, UserProgress
from englishbot.domain.models import WordStats
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
        awarded_at=datetime.now(UTC),
    )

    created = use_case.create_goal(
        user_id=3,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
    )
    summary = use_case.get_summary(user_id=3)

    assert created.target_count == 2
    assert summary.correct_answers == 1
    assert summary.incorrect_answers == 1
    assert summary.weekly_points > 0
    assert len(summary.active_goals) == 1
    assert summary.active_goals[0].goal.id == created.id


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
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
        source=GoalWordSource.TOPIC,
        topic_id="animals",
    )

    assert len(created) == 2
    assert {goal.user_id for goal in created} == {11, 12}
    assert {goal.target_count for goal in created} == {2}


def test_admin_progress_overview_aggregates_users(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    assign = AssignGoalToUsersUseCase(store=store)
    assign.execute(
        user_ids=[20, 21],
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
        source=GoalWordSource.ALL,
    )

    overview = GetAdminUsersProgressOverviewUseCase(store=store).execute()

    assert len(overview) == 2
    assert overview[0].active_goals_count >= 1


def test_assign_goal_without_manual_selection_uses_random_word_subset(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "animals", "title": "Animals"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "cat", "english_word": "Cat", "translation": "кот"},
                {"id": "dog", "english_word": "Dog", "translation": "собака"},
                {"id": "fox", "english_word": "Fox", "translation": "лиса"},
                {"id": "owl", "english_word": "Owl", "translation": "сова"},
            ],
        }
    )
    use_case = AssignGoalToUsersUseCase(store=store, rng=random.Random(7))

    created = use_case.execute(
        user_ids=[30],
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=2,
        source=GoalWordSource.ALL,
    )

    details = store.list_goal_word_details(goal_id=created[0].id, user_id=30)

    assert {row["word_id"] for row in details} == {"fox", "cat"}
    assert {row["word_id"] for row in details} != {"cat", "dog"}


def test_assign_goal_with_manual_selection_preserves_selected_order(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "animals", "title": "Animals"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "cat", "english_word": "Cat", "translation": "кот"},
                {"id": "dog", "english_word": "Dog", "translation": "собака"},
                {"id": "fox", "english_word": "Fox", "translation": "лиса"},
            ],
        }
    )
    use_case = AssignGoalToUsersUseCase(store=store, rng=random.Random(7))

    created = use_case.execute(
        user_ids=[31],
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=2,
        source=GoalWordSource.MANUAL,
        manual_word_ids=["dog", "cat", "fox"],
    )

    details = store.list_goal_word_details(goal_id=created[0].id, user_id=31)

    assert {row["word_id"] for row in details} == {"dog", "cat", "fox"}
    assert created[0].target_count == 3


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
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
    )
    use_case.reset_goal(user_id=8, goal_id=goal.id)

    goals = GetAdminUserGoalsUseCase(store=store).execute(user_id=8, include_history=True)

    assert len(goals) == 1
    assert goals[0].goal.status.value == "expired"


def test_assignment_launch_summary_returns_homework_only(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = HomeworkProgressUseCase(store=store)
    use_case.create_goal(
        user_id=9,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["dog"],
        deadline_date="2026-04-07",
    )
    summary = GetLearnerAssignmentLaunchSummaryUseCase(store=store, batch_size=1).execute(user_id=9)
    assert len(summary) == 1
    assert summary[0].kind is AssignmentSessionKind.HOMEWORK
    assert summary[0].remaining_word_count == 1
    assert summary[0].completed_word_count == 0
    assert summary[0].total_word_count == 1
    assert summary[0].deadline_date == "2026-04-07"


def test_assignment_launch_summary_counts_completed_homework_words(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = HomeworkProgressUseCase(store=store)
    goal = use_case.create_goal(
        user_id=21,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        target_word_ids=["cat", "dog"],
    )
    store.update_homework_word_progress(
        user_id=21,
        word_id="cat",
        mode=TrainingMode.EASY,
        is_correct=True,
        current_level=0,
        goal_id=goal.id,
    )
    store.update_homework_word_progress(
        user_id=21,
        word_id="cat",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )
    store.update_homework_word_progress(
        user_id=21,
        word_id="cat",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )

    summary = GetLearnerAssignmentLaunchSummaryUseCase(store=store, batch_size=1).execute(user_id=21)
    summary_by_kind = {item.kind: item for item in summary}

    assert goal.required_level == 2
    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].remaining_word_count == 1
    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].completed_word_count == 1
    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].total_word_count == 2


def test_homework_goal_defaults_deadline_when_not_provided(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=30,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["cat"],
    )

    assert goal.deadline_date is not None


def test_start_assignment_round_use_case_creates_assignment_session(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=10,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
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

    question = use_case.execute(user_id=10, kind=AssignmentSessionKind.HOMEWORK)
    session = SQLiteSessionRepository(store).get_active_by_user(10)

    assert session is not None
    assert question.session_id == session.id
    assert session.source_tag == f"assignment:homework:{goal.id}"
    assert len(session.items) == 2


def test_new_words_goal_progress_counts_unique_completed_words(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=15,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=2,
        target_word_ids=["cat", "dog"],
    )
    created_at = datetime(2026, 3, 31, 0, 0, tzinfo=UTC)
    with sqlite3.connect(tmp_path / "data" / "englishbot.db") as connection:
        connection.execute(
            "UPDATE user_goals SET created_at = ? WHERE id = ?",
            (created_at.isoformat(), goal.id),
        )
    store.save_word_stats(
        WordStats(
            user_id=15,
            word_id="cat",
            success_easy=1,
            current_level=1,
            last_correct_at=created_at + timedelta(minutes=1),
        )
    )

    store.update_goals_progress(
        user_id=15,
        word_id="cat",
        topic_id="animals",
        is_correct=True,
        current_level=1,
    )
    store.update_goals_progress(
        user_id=15,
        word_id="cat",
        topic_id="animals",
        is_correct=True,
        current_level=1,
    )

    refreshed_goal = store.list_user_goals(user_id=15)[0]
    summary = GetLearnerAssignmentLaunchSummaryUseCase(store=store, batch_size=5).execute(user_id=15)
    summary_by_kind = {item.kind: item for item in summary}

    assert refreshed_goal.id == goal.id
    assert refreshed_goal.progress_count == 1
    assert refreshed_goal.status.value == "active"
    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].available is True
    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].remaining_word_count == 1


def test_list_user_goals_refreshes_stale_new_words_progress_from_existing_db(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=16,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=2,
        target_word_ids=["cat", "dog"],
    )
    created_at = datetime(2026, 3, 31, 0, 0, tzinfo=UTC)
    with sqlite3.connect(tmp_path / "data" / "englishbot.db") as connection:
        connection.execute(
            "UPDATE user_goals SET created_at = ? WHERE id = ?",
            (created_at.isoformat(), goal.id),
        )
        connection.execute(
            "UPDATE user_goals SET progress_count = ? WHERE id = ?",
            (2, goal.id),
        )
    store.save_word_stats(
        WordStats(
            user_id=16,
            word_id="cat",
            success_easy=1,
            current_level=1,
            last_correct_at=created_at + timedelta(minutes=1),
        )
    )

    refreshed_goal = store.list_user_goals(user_id=16)[0]
    summary = GetLearnerAssignmentLaunchSummaryUseCase(store=store, batch_size=5).execute(user_id=16)
    summary_by_kind = {item.kind: item for item in summary}

    assert refreshed_goal.progress_count == 1
    assert refreshed_goal.status.value == "active"
    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].available is True
    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].remaining_word_count == 1


def test_new_words_goal_does_not_reuse_progress_from_previous_goal_assignments(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = HomeworkProgressUseCase(store=store)

    first_goal = use_case.create_goal(
        user_id=17,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=2,
        target_word_ids=["cat", "dog"],
    )
    first_goal_created_at = "2026-03-30T10:00:00+00:00"
    with sqlite3.connect(tmp_path / "data" / "englishbot.db") as connection:
        connection.execute(
            "UPDATE user_goals SET created_at = ? WHERE id = ?",
            (first_goal_created_at, first_goal.id),
        )
    store.save_word_stats(
        WordStats(
            user_id=17,
            word_id="cat",
            success_easy=2,
            current_level=1,
            last_correct_at=datetime(2026, 3, 30, 10, 5, tzinfo=UTC),
        )
    )
    store.save_word_stats(
        WordStats(
            user_id=17,
            word_id="dog",
            success_easy=2,
            current_level=1,
            last_correct_at=datetime(2026, 3, 30, 10, 6, tzinfo=UTC),
        )
    )

    completed_first_goal = next(goal for goal in store.list_user_goals(user_id=17, statuses=(GoalStatus.ACTIVE, GoalStatus.COMPLETED)) if goal.id == first_goal.id)
    assert completed_first_goal.status is GoalStatus.COMPLETED
    assert completed_first_goal.progress_count == 2

    second_goal = use_case.create_goal(
        user_id=17,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=2,
        target_word_ids=["cat", "dog"],
    )
    second_goal_created_at = "2026-03-30T10:10:00+00:00"
    with sqlite3.connect(tmp_path / "data" / "englishbot.db") as connection:
        connection.execute(
            "UPDATE user_goals SET created_at = ? WHERE id = ?",
            (second_goal_created_at, second_goal.id),
        )

    refreshed_second_goal = next(goal for goal in store.list_user_goals(user_id=17) if goal.id == second_goal.id)
    assert refreshed_second_goal.status is GoalStatus.ACTIVE
    assert refreshed_second_goal.progress_count == 0


def test_multiple_active_homeworks_can_coexist(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = HomeworkProgressUseCase(store=store)

    first_goal = use_case.create_goal(
        user_id=19,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        target_word_ids=["cat", "dog"],
    )
    second_goal = use_case.create_goal(
        user_id=19,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["cat"],
    )

    goals = store.list_user_goals(
        user_id=19,
        statuses=(GoalStatus.ACTIVE, GoalStatus.EXPIRED, GoalStatus.COMPLETED),
    )
    goals_by_id = {goal.id: goal for goal in goals}

    assert goals_by_id[first_goal.id].status is GoalStatus.ACTIVE
    assert goals_by_id[second_goal.id].status is GoalStatus.ACTIVE


def test_assignment_launch_summary_handles_naive_goal_created_at_from_existing_db(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=18,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
        target_word_ids=["cat"],
    )
    with sqlite3.connect(tmp_path / "data" / "englishbot.db") as connection:
        connection.execute(
            "UPDATE user_goals SET created_at = ? WHERE id = ?",
            ("2026-03-31 00:00:00", goal.id),
        )
    store.save_word_stats(
        WordStats(
            user_id=18,
            word_id="cat",
            success_easy=1,
            current_level=1,
            last_correct_at=datetime(2026, 3, 31, 0, 1, tzinfo=UTC),
        )
    )

    summary = GetLearnerAssignmentLaunchSummaryUseCase(store=store, batch_size=5).execute(user_id=18)
    summary_by_kind = {item.kind: item for item in summary}

    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].remaining_word_count == 0
    assert summary_by_kind[AssignmentSessionKind.HOMEWORK].available is False
