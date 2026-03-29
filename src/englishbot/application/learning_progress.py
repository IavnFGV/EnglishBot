from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import random

from englishbot.domain.models import TrainingMode, WordStats


@dataclass(slots=True, frozen=True)
class RecommendationInput:
    total_attempts: int
    total_success: int
    current_level: int
    days_since_seen: int
    shown_in_last_3_sessions: bool
    in_active_homework: bool
    in_active_goal_targets: bool
    review_due_now: bool


def normalize_mastery_level(stats: WordStats) -> int:
    level = 0
    if stats.success_easy >= 2 or stats.success_medium >= 1 or stats.success_hard >= 1:
        level = 1
    if stats.success_medium >= 2 or (stats.success_hard >= 1 and stats.success_medium >= 1):
        level = 2
    if stats.success_hard >= 2:
        level = 3
    return level


def apply_attempt(*, stats: WordStats, mode: TrainingMode, is_correct: bool, seen_at: datetime) -> tuple[int, int]:
    previous_level = stats.current_level
    if mode is TrainingMode.EASY:
        stats.attempt_easy += 1
        if is_correct:
            stats.success_easy += 1
    elif mode is TrainingMode.MEDIUM:
        stats.attempt_medium += 1
        if is_correct:
            stats.success_medium += 1
    else:
        stats.attempt_hard += 1
        if is_correct:
            stats.success_hard += 1
    stats.last_seen_at = seen_at
    if is_correct:
        stats.last_correct_at = seen_at
        stats.current_streak_success += 1
        stats.current_streak_fail = 0
    else:
        stats.current_streak_fail += 1
        stats.current_streak_success = 0

    promoted_level = normalize_mastery_level(stats)
    effective_level = promoted_level
    if not is_correct and stats.current_streak_fail >= 2 and previous_level > 0:
        effective_level = max(0, previous_level - 1)
    stats.current_level = effective_level
    _apply_spaced_repetition(stats=stats, is_correct=is_correct, seen_at=seen_at, previous_level=previous_level)
    return previous_level, effective_level


def recommendation_score(data: RecommendationInput) -> int:
    fail_count = data.total_attempts - data.total_success
    score = fail_count * 5
    score += min(data.days_since_seen, 14) * 2
    score += max(0, 5 - data.total_attempts) * 2
    score += (3 - data.current_level) * 4
    if data.shown_in_last_3_sessions:
        score -= 8
    if data.in_active_homework:
        score += 1000
    if data.in_active_goal_targets:
        score += 100
    if data.review_due_now:
        score += 20
    return score


def _apply_spaced_repetition(
    *,
    stats: WordStats,
    is_correct: bool,
    seen_at: datetime,
    previous_level: int,
) -> None:
    if stats.current_level < 2:
        return
    if previous_level < 2 and stats.current_level >= 2 and stats.review_interval_days <= 0:
        stats.review_interval_days = 1
        stats.next_review_at = seen_at + timedelta(days=1)
        return
    if stats.next_review_at is None or seen_at < stats.next_review_at:
        return
    if is_correct:
        current = max(1, stats.review_interval_days or 1)
        stats.review_interval_days = min(current * 2, 14)
    else:
        current = max(1, stats.review_interval_days or 1)
        stats.review_interval_days = max(1, current // 2)
    stats.next_review_at = seen_at + timedelta(days=stats.review_interval_days)


def choose_word_mode(
    *,
    current_level: int,
    rng: random.Random,
    min_required_level: int | None = None,
) -> TrainingMode:
    if min_required_level == 3:
        return TrainingMode.HARD

    roll = rng.random()
    if current_level <= 0:
        thresholds = ((0.9, TrainingMode.EASY), (1.0, TrainingMode.MEDIUM))
    elif current_level == 1:
        thresholds = (
            (0.2, TrainingMode.EASY),
            (0.9, TrainingMode.MEDIUM),
            (1.0, TrainingMode.HARD),
        )
    elif current_level == 2:
        thresholds = ((0.4, TrainingMode.MEDIUM), (1.0, TrainingMode.HARD))
    else:
        thresholds = ((0.3, TrainingMode.MEDIUM), (1.0, TrainingMode.HARD))

    mode = TrainingMode.HARD
    for boundary, candidate in thresholds:
        if roll <= boundary:
            mode = candidate
            break

    if min_required_level == 2 and mode is TrainingMode.EASY:
        return TrainingMode.MEDIUM
    return mode


def week_start(value: datetime) -> datetime:
    utc_value = value.astimezone(UTC)
    return datetime(
        utc_value.year,
        utc_value.month,
        utc_value.day,
        tzinfo=UTC,
    ) - timedelta(days=utc_value.weekday())
