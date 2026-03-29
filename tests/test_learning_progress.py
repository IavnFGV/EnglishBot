from datetime import UTC, datetime

from englishbot.application.learning_progress import (
    RecommendationInput,
    apply_attempt,
    choose_word_mode,
    recommendation_score,
    week_start,
)
from englishbot.domain.models import TrainingMode, WordStats


def test_apply_attempt_promotes_and_demotion() -> None:
    stats = WordStats(user_id=1, word_id="w1")
    now = datetime(2026, 3, 29, tzinfo=UTC)

    _, level = apply_attempt(stats=stats, mode=TrainingMode.EASY, is_correct=True, seen_at=now)
    assert level == 0
    _, level = apply_attempt(stats=stats, mode=TrainingMode.EASY, is_correct=True, seen_at=now)
    assert level == 1

    _, level = apply_attempt(stats=stats, mode=TrainingMode.MEDIUM, is_correct=False, seen_at=now)
    assert level == 1
    _, level = apply_attempt(stats=stats, mode=TrainingMode.MEDIUM, is_correct=False, seen_at=now)
    assert level == 0


def test_recommendation_score_with_boosts() -> None:
    score = recommendation_score(
        RecommendationInput(
            total_attempts=2,
            total_success=1,
            current_level=1,
            days_since_seen=20,
            shown_in_last_3_sessions=True,
            in_active_homework=True,
            in_active_goal_targets=True,
            review_due_now=True,
        )
    )
    assert score == 1159


def test_choose_word_mode_respects_homework_min_level() -> None:
    mode = choose_word_mode(current_level=0, rng=__import__("random").Random(0), min_required_level=3)
    assert mode is TrainingMode.HARD


def test_week_start_uses_monday() -> None:
    sunday = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    assert week_start(sunday).date().isoformat() == "2026-03-23"


def test_spaced_repetition_starts_at_medium_and_updates() -> None:
    stats = WordStats(user_id=1, word_id="w2", success_medium=1, current_level=1)
    now = datetime(2026, 3, 29, tzinfo=UTC)
    apply_attempt(stats=stats, mode=TrainingMode.MEDIUM, is_correct=True, seen_at=now)
    assert stats.current_level >= 2
    assert stats.review_interval_days == 1
    assert stats.next_review_at == datetime(2026, 3, 30, tzinfo=UTC)

    apply_attempt(
        stats=stats,
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        seen_at=datetime(2026, 3, 31, tzinfo=UTC),
    )
    assert stats.review_interval_days == 2

    apply_attempt(
        stats=stats,
        mode=TrainingMode.MEDIUM,
        is_correct=False,
        seen_at=datetime(2026, 4, 3, tzinfo=UTC),
    )
    assert stats.review_interval_days == 1
