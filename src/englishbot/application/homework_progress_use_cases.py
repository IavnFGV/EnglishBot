from __future__ import annotations

from dataclasses import dataclass

from englishbot.domain.models import Goal, GoalPeriod, GoalStatus, GoalType
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


class HomeworkProgressUseCase:
    def __init__(self, *, store: SQLiteContentStore) -> None:
        self._store = store

    @logged_service_call(
        "HomeworkProgressUseCase.get_summary",
        include=("user_id",),
        result=lambda value: {
            "goal_count": len(value.active_goals),
            "correct_answers": value.correct_answers,
            "incorrect_answers": value.incorrect_answers,
        },
    )
    def get_summary(self, *, user_id: int) -> LearnerProgressSummary:
        progress_items = self._store.list_progress_by_user(user_id)
        active_goals = self._store.list_user_goals(user_id=user_id, statuses=(GoalStatus.ACTIVE,))
        game_profile = self._store.get_game_profile(user_id=user_id)
        return LearnerProgressSummary(
            correct_answers=sum(item.correct_answers for item in progress_items),
            incorrect_answers=sum(item.incorrect_answers for item in progress_items),
            game_streak_days=game_profile.current_streak_days,
            weekly_points=self._store.get_weekly_points(user_id=user_id),
            active_goals=[
                GoalProgressView(
                    goal=goal,
                    progress_percent=(
                        min(100, int((goal.progress_count / goal.target_count) * 100))
                        if goal.target_count > 0
                        else 0
                    ),
                )
                for goal in active_goals
            ],
        )

    @logged_service_call(
        "HomeworkProgressUseCase.create_goal",
        include=("user_id", "goal_period", "goal_type", "target_count"),
        result=lambda value: {"goal_id": value.id},
    )
    def create_goal(
        self,
        *,
        user_id: int,
        goal_period: GoalPeriod,
        goal_type: GoalType,
        target_count: int,
        target_word_ids: list[str] | None = None,
    ) -> Goal:
        if target_count <= 0:
            raise ValueError("target_count must be positive")

        word_ids = list(dict.fromkeys(target_word_ids or []))
        required_level = 2 if goal_type is GoalType.WORD_LEVEL_HOMEWORK else None
        if goal_type in {GoalType.NEW_WORDS, GoalType.WORD_LEVEL_HOMEWORK} and not word_ids:
            recent_word_ids = sorted(self._store.list_recent_session_words(user_id=user_id))
            if recent_word_ids:
                word_ids = recent_word_ids[:target_count]
            else:
                word_ids = [item.id for item in self._store.list_all_vocabulary()[:target_count]]
        if goal_type in {GoalType.NEW_WORDS, GoalType.WORD_LEVEL_HOMEWORK} and not word_ids:
            raise ValueError("No words available for this goal")

        return self._store.assign_goal(
            user_id=user_id,
            goal_period=goal_period,
            goal_type=goal_type,
            target_count=target_count,
            required_level=required_level,
            target_word_ids=word_ids or None,
        )

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
