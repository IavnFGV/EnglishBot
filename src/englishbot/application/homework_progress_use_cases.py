from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from englishbot.domain.models import Goal, GoalPeriod, GoalStatus, GoalType, TrainingMode
from englishbot.infrastructure.sqlite_store import SQLiteContentStore
from englishbot.logging_utils import logged_service_call


@dataclass(slots=True, frozen=True)
class GoalProgressView:
    goal: Goal
    progress_percent: int


@dataclass(slots=True, frozen=True)
class LearnerProgressSummary:
    correct_answers: int
    incorrect_answers: int
    game_streak_days: int
    weekly_points: int
    active_goals: list[GoalProgressView]


@dataclass(slots=True, frozen=True)
class AdminUserProgressOverviewItem:
    user_id: int
    active_goals_count: int
    completed_goals_count: int
    aggregate_percent: int
    last_activity_at: datetime | None


@dataclass(slots=True, frozen=True)
class GoalWordDetailView:
    word_id: str
    english_word: str
    translation: str
    homework_mode: TrainingMode | None
    easy_mastered: bool = False
    medium_mastered: bool = False
    hard_mastered: bool = False
    hard_skipped: bool = False


@dataclass(slots=True, frozen=True)
class AdminGoalDetailView:
    goal: Goal
    progress_percent: int
    words: list[GoalWordDetailView]


class GoalWordSource(StrEnum):
    RECENT = "recent"
    TOPIC = "topic"
    ALL = "all"
    MANUAL = "manual"


class GetGoalWordCandidatesUseCase:
    def __init__(self, *, store: SQLiteContentStore) -> None:
        self._store = store

    @logged_service_call(
        "GetGoalWordCandidatesUseCase.execute",
        include=("user_id", "source", "topic_id"),
        transforms={
            "manual_word_ids": lambda value: {"manual_count": len(value or [])},
        },
        result=lambda value: {"item_count": len(value)},
    )
    def execute(
        self,
        *,
        user_id: int,
        source: GoalWordSource,
        topic_id: str | None = None,
        manual_word_ids: list[str] | None = None,
    ) -> list[str]:
        if source is GoalWordSource.RECENT:
            recent = sorted(self._store.list_recent_session_words(user_id=user_id))
            if recent:
                return recent
            return [item.id for item in self._store.list_all_vocabulary()]
        if source is GoalWordSource.TOPIC:
            if not topic_id:
                raise ValueError("topic_id is required for topic source")
            return [item.id for item in self._store.list_vocabulary_by_topic(topic_id)]
        if source is GoalWordSource.ALL:
            return [item.id for item in self._store.list_all_vocabulary()]

        manual = list(dict.fromkeys(manual_word_ids or []))
        if not manual:
            raise ValueError("manual word selection cannot be empty")
        available = {item.id for item in self._store.list_all_vocabulary()}
        return [word_id for word_id in manual if word_id in available]


class ListUserGoalsUseCase:
    def __init__(self, *, store: SQLiteContentStore) -> None:
        self._store = store

    @logged_service_call(
        "ListUserGoalsUseCase.execute",
        include=("user_id",),
        result=lambda value: {"goal_count": len(value)},
    )
    def execute(self, *, user_id: int, include_history: bool = False) -> list[GoalProgressView]:
        statuses = (
            (GoalStatus.ACTIVE, GoalStatus.COMPLETED, GoalStatus.EXPIRED)
            if include_history
            else (GoalStatus.ACTIVE,)
        )
        goals = self._store.list_user_goals(user_id=user_id, statuses=statuses)
        return [
            GoalProgressView(
                goal=goal,
                progress_percent=(
                    min(100, int((goal.progress_count / goal.target_count) * 100))
                    if goal.target_count > 0
                    else 0
                ),
            )
            for goal in goals
        ]


class GetUserProgressSummaryUseCase:
    def __init__(self, *, store: SQLiteContentStore) -> None:
        self._store = store
        self._goals_use_case = ListUserGoalsUseCase(store=store)

    @logged_service_call(
        "GetUserProgressSummaryUseCase.execute",
        include=("user_id",),
        result=lambda value: {
            "goal_count": len(value.active_goals),
            "correct_answers": value.correct_answers,
            "incorrect_answers": value.incorrect_answers,
        },
    )
    def execute(self, *, user_id: int) -> LearnerProgressSummary:
        progress_items = self._store.list_progress_by_user(user_id)
        game_profile = self._store.get_game_profile(user_id=user_id)
        return LearnerProgressSummary(
            correct_answers=sum(item.correct_answers for item in progress_items),
            incorrect_answers=sum(item.incorrect_answers for item in progress_items),
            game_streak_days=game_profile.current_streak_days,
            weekly_points=self._store.get_weekly_points(user_id=user_id),
            active_goals=self._goals_use_case.execute(user_id=user_id, include_history=False),
        )


class AssignGoalToUsersUseCase:
    def __init__(self, *, store: SQLiteContentStore) -> None:
        self._store = store
        self._word_candidates = GetGoalWordCandidatesUseCase(store=store)

    @logged_service_call(
        "AssignGoalToUsersUseCase.execute",
        include=("goal_period", "goal_type", "target_count", "source", "topic_id"),
        transforms={
            "user_ids": lambda value: {"user_count": len(value)},
            "manual_word_ids": lambda value: {"manual_count": len(value or [])},
        },
        result=lambda value: {"goal_count": len(value)},
    )
    def execute(  # noqa: PLR0913
        self,
        *,
        user_ids: list[int],
        goal_period: GoalPeriod,
        goal_type: GoalType,
        target_count: int,
        source: GoalWordSource,
        topic_id: str | None = None,
        manual_word_ids: list[str] | None = None,
    ) -> list[Goal]:
        deduplicated_user_ids = list(dict.fromkeys(user_ids))
        if not deduplicated_user_ids:
            raise ValueError("At least one user id is required")
        if target_count <= 0:
            raise ValueError("target_count must be positive")

        required_level = 2 if goal_type is GoalType.WORD_LEVEL_HOMEWORK else None
        created: list[Goal] = []
        for user_id in deduplicated_user_ids:
            candidate_word_ids = self._word_candidates.execute(
                user_id=user_id,
                source=source,
                topic_id=topic_id,
                manual_word_ids=manual_word_ids,
            )
            target_word_ids = candidate_word_ids[:target_count]
            if goal_type in {GoalType.NEW_WORDS, GoalType.WORD_LEVEL_HOMEWORK} and not target_word_ids:
                raise ValueError(f"No words available for user_id={user_id}")
            created.append(
                self._store.assign_goal(
                    user_id=user_id,
                    goal_period=goal_period,
                    goal_type=goal_type,
                    target_count=target_count,
                    required_level=required_level,
                    target_topic_id=topic_id,
                    target_word_ids=target_word_ids or None,
                )
            )
        return created


class GetAdminUsersProgressOverviewUseCase:
    def __init__(self, *, store: SQLiteContentStore) -> None:
        self._store = store

    @logged_service_call(
        "GetAdminUsersProgressOverviewUseCase.execute",
        result=lambda value: {"user_count": len(value)},
    )
    def execute(self) -> list[AdminUserProgressOverviewItem]:
        rows = self._store.list_users_goal_overview()
        return [
            AdminUserProgressOverviewItem(
                user_id=row["user_id"],
                active_goals_count=row["active_goals_count"],
                completed_goals_count=row["completed_goals_count"],
                aggregate_percent=row["aggregate_percent"],
                last_activity_at=row["last_activity_at"],
            )
            for row in rows
        ]


class GetAdminUserGoalsUseCase:
    def __init__(self, *, store: SQLiteContentStore) -> None:
        self._goals = ListUserGoalsUseCase(store=store)

    @logged_service_call(
        "GetAdminUserGoalsUseCase.execute",
        include=("user_id", "include_history"),
        result=lambda value: {"goal_count": len(value)},
    )
    def execute(self, *, user_id: int, include_history: bool = True) -> list[GoalProgressView]:
        return self._goals.execute(user_id=user_id, include_history=include_history)


class GetAdminGoalDetailUseCase:
    def __init__(self, *, store: SQLiteContentStore) -> None:
        self._store = store

    @logged_service_call(
        "GetAdminGoalDetailUseCase.execute",
        include=("user_id", "goal_id"),
        result=lambda value: {"found": value is not None, "word_count": (len(value.words) if value is not None else 0)},
    )
    def execute(self, *, user_id: int, goal_id: str) -> AdminGoalDetailView | None:
        goals = self._store.list_user_goals(
            user_id=user_id,
            statuses=(GoalStatus.ACTIVE, GoalStatus.COMPLETED, GoalStatus.EXPIRED),
        )
        goal = next((item for item in goals if item.id == goal_id), None)
        if goal is None:
            return None
        words = [
            GoalWordDetailView(
                word_id=row["word_id"],
                english_word=row["english_word"],
                translation=row["translation"],
                homework_mode=(
                    TrainingMode(row["homework_mode"])
                    if row.get("homework_mode")
                    else None
                ),
                easy_mastered=bool(row.get("easy_mastered")),
                medium_mastered=bool(row.get("medium_mastered")),
                hard_mastered=bool(row.get("hard_mastered")),
                hard_skipped=bool(row.get("hard_skipped")),
            )
            for row in self._store.list_goal_word_details(goal_id=goal_id, user_id=user_id)
        ]
        return AdminGoalDetailView(
            goal=goal,
            progress_percent=(
                min(100, int((goal.progress_count / goal.target_count) * 100))
                if goal.target_count > 0
                else 0
            ),
            words=words,
        )


class HomeworkProgressUseCase:
    """Backward-compatible facade used by existing handlers/tests."""

    def __init__(self, *, store: SQLiteContentStore) -> None:
        self._store = store
        self._summary = GetUserProgressSummaryUseCase(store=store)
        self._assign = AssignGoalToUsersUseCase(store=store)

    def get_summary(self, *, user_id: int) -> LearnerProgressSummary:
        return self._summary.execute(user_id=user_id)

    def create_goal(
        self,
        *,
        user_id: int,
        goal_period: GoalPeriod,
        goal_type: GoalType,
        target_count: int,
        target_word_ids: list[str] | None = None,
    ) -> Goal:
        source = GoalWordSource.MANUAL if target_word_ids else GoalWordSource.RECENT
        return self._assign.execute(
            user_ids=[user_id],
            goal_period=goal_period,
            goal_type=goal_type,
            target_count=target_count,
            source=source,
            manual_word_ids=target_word_ids,
        )[0]

    @logged_service_call(
        "HomeworkProgressUseCase.reset_goal",
        include=("user_id", "goal_id"),
        result=lambda value: {"reset": value},
    )
    def reset_goal(self, *, user_id: int, goal_id: str) -> bool:
        return self._store.update_goal_status(
            user_id=user_id,
            goal_id=goal_id,
            status=GoalStatus.EXPIRED,
        )
