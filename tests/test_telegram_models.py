from __future__ import annotations

from datetime import UTC, datetime

from englishbot import bot
from englishbot.telegram.models import AssignmentRoundProgressView, PendingNotification


def test_bot_assignment_progress_view_alias_points_to_telegram_model() -> None:
    progress = bot._AssignmentRoundProgressView(
        completed_word_count=2,
        total_word_count=5,
        remaining_word_count=3,
        variant_key="goal-1",
    )

    assert isinstance(progress, AssignmentRoundProgressView)


def test_bot_pending_notification_alias_supports_optional_timestamps() -> None:
    now = datetime.now(UTC)

    notification = bot._PendingNotification(
        key="n1",
        recipient_user_id=7,
        text="hello",
        not_before_at=now,
        created_at=now,
    )

    assert isinstance(notification, PendingNotification)
    assert notification.not_before_at == now
    assert notification.created_at == now
