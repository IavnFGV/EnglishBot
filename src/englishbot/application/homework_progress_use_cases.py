from __future__ import annotations

import hashlib
import random
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import ceil

from englishbot.application.learning_progress import choose_word_mode
from englishbot.application.question_factory import QuestionFactory
from englishbot.domain.models import Goal, GoalPeriod, GoalStatus, GoalType, SessionItem, TrainingMode
from englishbot.domain.models import TrainingQuestion, TrainingSession, VocabularyItem
from englishbot.infrastructure.sqlite_store import (
    SQLiteContentStore,
    SQLiteSessionRepository,
    SQLiteUserProgressRepository,
    SQLiteVocabularyRepository,
)
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


class AssignmentSessionKind(StrEnum):
    HOMEWORK = "homework"


@dataclass(slots=True, frozen=True)
class AssignmentLaunchView:
    kind: AssignmentSessionKind
    available: bool
    remaining_word_count: int
    estimated_round_count: int
    completed_word_count: int = 0
    total_word_count: int = 0
    progress_variant_key: str = ""
    deadline_date: str | None = None


@dataclass(slots=True, frozen=True)
class AssignmentWordView:
    word_id: str
    english_word: str
    translation: str
    required_level: int | None = None


class GoalWordSource(StrEnum):
    RECENT = "recent"
    TOPIC = "topic"
    ALL = "all"
    MANUAL = "manual"


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
    def __init__(self, *, store: SQLiteContentStore, rng: random.Random | None = None) -> None:
        self._store = store
        self._word_candidates = GetGoalWordCandidatesUseCase(store=store)
        self._rng = rng or random.Random()

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
        target_count: int | None,
        source: GoalWordSource,
        topic_id: str | None = None,
        manual_word_ids: list[str] | None = None,
        deadline_date: str | None = None,
    ) -> list[Goal]:
        deduplicated_user_ids = list(dict.fromkeys(user_ids))
        if not deduplicated_user_ids:
            raise ValueError("At least one user id is required")
        if source is GoalWordSource.ALL and (target_count is None or target_count <= 0):
            raise ValueError("target_count must be positive")

        required_level = 2 if goal_type is GoalType.WORD_LEVEL_HOMEWORK else None
        effective_deadline_date = deadline_date
        if effective_deadline_date is None and goal_period is GoalPeriod.HOMEWORK:
            effective_deadline_date = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()
        created: list[Goal] = []
        for user_id in deduplicated_user_ids:
            candidate_word_ids = self._word_candidates.execute(
                user_id=user_id,
                source=source,
                topic_id=topic_id,
                manual_word_ids=manual_word_ids,
            )
            if source in {
                GoalWordSource.RECENT,
                GoalWordSource.TOPIC,
                GoalWordSource.MANUAL,
            }:
                target_word_ids = list(candidate_word_ids)
            else:
                target_word_ids = self._rng.sample(
                    candidate_word_ids,
                    k=min(int(target_count or 0), len(candidate_word_ids)),
                )
            if goal_type in {GoalType.NEW_WORDS, GoalType.WORD_LEVEL_HOMEWORK} and not target_word_ids:
                raise ValueError(f"No words available for user_id={user_id}")
            effective_target_count = len(target_word_ids) if target_word_ids else int(target_count or 0)
            created.append(
                self._store.assign_goal(
                    user_id=user_id,
                    goal_period=goal_period,
                    goal_type=goal_type,
                    target_count=effective_target_count,
                    deadline_date=effective_deadline_date,
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
        deadline_date: str | None = None,
    ) -> Goal:
        source = GoalWordSource.MANUAL if target_word_ids else GoalWordSource.RECENT
        return self._assign.execute(
            user_ids=[user_id],
            goal_period=goal_period,
            goal_type=goal_type,
            target_count=target_count,
            source=source,
            manual_word_ids=target_word_ids,
            deadline_date=deadline_date,
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


class GetLearnerAssignmentLaunchSummaryUseCase:
    def __init__(self, *, store: SQLiteContentStore, batch_size: int = 5) -> None:
        self._store = store
        self._batch_size = batch_size

    @logged_service_call(
        "GetLearnerAssignmentLaunchSummaryUseCase.execute",
        include=("user_id",),
        result=lambda value: {"option_count": len(value)},
    )
    def execute(self, *, user_id: int) -> list[AssignmentLaunchView]:
        return [self._build_launch_view(user_id=user_id, kind=AssignmentSessionKind.HOMEWORK)]

    def _build_launch_view(self, *, user_id: int, kind: AssignmentSessionKind) -> AssignmentLaunchView:
        remaining_words = _remaining_assignment_words(store=self._store, user_id=user_id, kind=kind)
        remaining_count = len(remaining_words)
        total_count = _total_assignment_word_count(store=self._store, user_id=user_id, kind=kind)
        return AssignmentLaunchView(
            kind=kind,
            available=remaining_count > 0,
            remaining_word_count=remaining_count,
            estimated_round_count=(ceil(remaining_count / self._batch_size) if remaining_count > 0 else 0),
            completed_word_count=max(0, total_count - remaining_count),
            total_word_count=total_count,
            progress_variant_key=_assignment_progress_variant_key(
                store=self._store,
                user_id=user_id,
                kind=kind,
            ),
            deadline_date=_assignment_deadline_date(store=self._store, user_id=user_id, kind=kind),
        )


class StartAssignmentRoundUseCase:
    def __init__(
        self,
        *,
        store: SQLiteContentStore,
        vocabulary_repository: SQLiteVocabularyRepository,
        progress_repository: SQLiteUserProgressRepository,
        session_repository: SQLiteSessionRepository,
        question_factory: QuestionFactory,
        batch_size: int = 5,
    ) -> None:
        self._store = store
        self._vocabulary_repository = vocabulary_repository
        self._progress_repository = progress_repository
        self._session_repository = session_repository
        self._question_factory = question_factory
        self._batch_size = batch_size

    @logged_service_call(
        "StartAssignmentRoundUseCase.execute",
        include=("user_id",),
        transforms={"kind": lambda value: {"kind": value.value}},
        result=lambda value: {"session_id": value.session_id, "item_id": value.item_id},
    )
    def execute(self, *, user_id: int, kind: AssignmentSessionKind) -> TrainingQuestion:
        return self.execute_with_batch_size(user_id=user_id, kind=kind, batch_size=None)

    @logged_service_call(
        "StartAssignmentRoundUseCase.execute_with_batch_size",
        include=("user_id",),
        transforms={
            "kind": lambda value: {"kind": value.value},
            "batch_size": lambda value: {"batch_size": value},
        },
        result=lambda value: {"session_id": value.session_id, "item_id": value.item_id},
    )
    def execute_with_batch_size(
        self,
        *,
        user_id: int,
        kind: AssignmentSessionKind,
        batch_size: int | None,
    ) -> TrainingQuestion:
        effective_kind = AssignmentSessionKind.HOMEWORK
        effective_batch_size = batch_size if batch_size is not None and batch_size > 0 else self._batch_size
        selected_goal = _select_assignment_goal(
            store=self._store,
            user_id=user_id,
            kind=effective_kind,
        )
        if selected_goal is None:
            raise ValueError("No active assignments available for this section.")
        remaining_words = _remaining_assignment_words(
            store=self._store,
            user_id=user_id,
            kind=effective_kind,
            goal_id=selected_goal.id,
        )
        selected_words = remaining_words[:effective_batch_size]
        if not selected_words:
            raise ValueError("No active assignments available for this section.")
        items = self._resolve_items(selected_words)
        item_modes = self._build_item_modes(
            user_id=user_id,
            goal_id=selected_goal.id,
            selected_words=selected_words,
            items=items,
            batch_size=effective_batch_size,
        )
        session = TrainingSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            topic_id=self._resolve_session_topic_id(items),
            mode=TrainingMode.MEDIUM,
            source_tag=f"assignment:{effective_kind.value}:{selected_goal.id}",
            items=[
                SessionItem(order=index, vocabulary_item_id=item.id, mode=item_modes[item.id])
                for index, item in enumerate(items)
            ],
        )
        self._session_repository.save(session)
        return self._question_factory.create_question(
            session=session,
            item=items[0],
            all_topic_items=items,
        )

    def _resolve_items(self, selected_words: list[AssignmentWordView]) -> list[VocabularyItem]:
        items: list[VocabularyItem] = []
        for word in selected_words:
            item = self._vocabulary_repository.get_by_id(word.word_id)
            if item is not None:
                items.append(item)
        if not items:
            raise ValueError("No assignment words are currently available.")
        return items

    def _resolve_session_topic_id(self, items: list[VocabularyItem]) -> str:
        for item in items:
            if item.topic_id:
                return item.topic_id
            topic_ids = self._store.list_topic_ids_for_item(item.id)
            if topic_ids:
                return topic_ids[0]
        raise ValueError("Assignment words are missing topic bindings.")

    def _build_item_modes(
        self,
        *,
        user_id: int,
        goal_id: str,
        selected_words: list[AssignmentWordView],
        items: list[VocabularyItem],
        batch_size: int,
    ) -> dict[str, TrainingMode]:
        selected_word_map = {item.word_id: item for item in selected_words}
        hard_limit = max(1, len(items) // 4) if items else 0
        hard_selected = 0
        item_modes: dict[str, TrainingMode] = {}
        for item in items:
            selected_word = selected_word_map[item.id]
            mode = self._progress_repository.get_homework_stage_mode(
                user_id=user_id,
                item_id=item.id,
                goal_id=goal_id,
            )
            if mode is None:
                word_stats = self._progress_repository.get_word_stats(user_id, item.id)
                current_level = word_stats.current_level if word_stats is not None else 0
                mode = choose_word_mode(
                    current_level=current_level,
                    rng=random.Random(f"assignment:{user_id}:{item.id}:{batch_size}"),
                    min_required_level=selected_word.required_level,
                )
            if len(items) < 3 and mode is TrainingMode.EASY:
                mode = TrainingMode.MEDIUM
            if mode is TrainingMode.HARD and hard_selected >= hard_limit:
                mode = TrainingMode.MEDIUM
            if mode is TrainingMode.HARD:
                hard_selected += 1
            item_modes[item.id] = mode
        return item_modes


def _remaining_assignment_words(
    *,
    store: SQLiteContentStore,
    user_id: int,
    kind: AssignmentSessionKind,
    goal_id: str | None = None,
) -> list[AssignmentWordView]:
    goals = store.list_user_goals(user_id=user_id, statuses=(GoalStatus.ACTIVE,))
    periods = _periods_for_kind(kind)
    remaining: OrderedDict[str, AssignmentWordView] = OrderedDict()
    for goal in goals:
        if goal_id is not None and goal.id != goal_id:
            continue
        if goal.goal_period not in periods:
            continue
        if goal.goal_type not in {GoalType.NEW_WORDS, GoalType.WORD_LEVEL_HOMEWORK}:
            continue
        for row in store.list_goal_word_details(goal_id=goal.id, user_id=user_id):
            word_id = str(row["word_id"])
            if word_id in remaining:
                continue
            if goal.goal_type is GoalType.WORD_LEVEL_HOMEWORK:
                is_complete = bool(row.get("medium_mastered"))
                required_level = int(goal.required_level or 2)
            else:
                word_stats = store.get_word_stats(user_id, word_id)
                last_correct_at = _as_utc_datetime(
                    word_stats.last_correct_at if word_stats is not None else None
                )
                goal_created_at = _as_utc_datetime(goal.created_at)
                is_complete = bool(
                    word_stats is not None
                    and last_correct_at is not None
                    and goal_created_at is not None
                    and last_correct_at >= goal_created_at
                )
                required_level = None
            if is_complete:
                continue
            remaining[word_id] = AssignmentWordView(
                word_id=word_id,
                english_word=str(row["english_word"]),
                translation=str(row["translation"]),
                required_level=required_level,
            )
    return list(remaining.values())


def _select_assignment_goal(
    *,
    store: SQLiteContentStore,
    user_id: int,
    kind: AssignmentSessionKind,
) -> Goal | None:
    goals = store.list_user_goals(user_id=user_id, statuses=(GoalStatus.ACTIVE,))
    periods = _periods_for_kind(kind)
    relevant_goals = [
        goal
        for goal in goals
        if goal.goal_period in periods
        and goal.goal_type in {GoalType.NEW_WORDS, GoalType.WORD_LEVEL_HOMEWORK}
    ]
    if not relevant_goals:
        return None
    return min(
        relevant_goals,
        key=lambda goal: (
            goal.deadline_date or "9999-12-31",
            -(goal.created_at.timestamp() if goal.created_at is not None else 0.0),
        ),
    )


def _total_assignment_word_count(
    *,
    store: SQLiteContentStore,
    user_id: int,
    kind: AssignmentSessionKind,
) -> int:
    goals = store.list_user_goals(
        user_id=user_id,
        statuses=(GoalStatus.ACTIVE, GoalStatus.COMPLETED),
    )
    periods = _periods_for_kind(kind)
    word_ids: OrderedDict[str, None] = OrderedDict()
    for goal in goals:
        if goal.goal_period not in periods:
            continue
        if goal.goal_type not in {GoalType.NEW_WORDS, GoalType.WORD_LEVEL_HOMEWORK}:
            continue
        for row in store.list_goal_word_details(goal_id=goal.id, user_id=user_id):
            word_ids[str(row["word_id"])] = None
    return len(word_ids)


def _assignment_progress_variant_key(
    *,
    store: SQLiteContentStore,
    user_id: int,
    kind: AssignmentSessionKind,
) -> str:
    goals = store.list_user_goals(
        user_id=user_id,
        statuses=(GoalStatus.ACTIVE, GoalStatus.COMPLETED),
    )
    periods = _periods_for_kind(kind)
    relevant_goal_ids = [
        goal.id
        for goal in goals
        if goal.goal_period in periods
        and goal.goal_type in {GoalType.NEW_WORDS, GoalType.WORD_LEVEL_HOMEWORK}
    ]
    if not relevant_goal_ids:
        return f"{kind.value}:empty"
    joined_ids = "|".join(sorted(relevant_goal_ids))
    digest = hashlib.sha256(joined_ids.encode("utf-8")).hexdigest()[:12]
    return f"{kind.value}:{digest}"


def _periods_for_kind(kind: AssignmentSessionKind) -> tuple[GoalPeriod, ...]:
    return (GoalPeriod.HOMEWORK,)


def _assignment_deadline_date(
    *,
    store: SQLiteContentStore,
    user_id: int,
    kind: AssignmentSessionKind,
) -> str | None:
    goals = store.list_user_goals(
        user_id=user_id,
        statuses=(GoalStatus.ACTIVE,),
    )
    deadlines = [
        goal.deadline_date
        for goal in goals
        if goal.goal_period in _periods_for_kind(kind)
        and goal.goal_type in {GoalType.NEW_WORDS, GoalType.WORD_LEVEL_HOMEWORK}
        and goal.deadline_date
    ]
    if not deadlines:
        return None
    return min(deadlines)
