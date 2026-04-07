from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NOTIFICATIONS_MODULE = REPO_ROOT / "src" / "englishbot" / "telegram" / "notifications.py"


def test_notifications_module_does_not_pull_policy_constants_from_bot() -> None:
    text = NOTIFICATIONS_MODULE.read_text(encoding="utf-8")

    forbidden_snippets = (
        "bot_module._NOTIFICATION_DISMISS_CALLBACK",
        "bot_module._NOTIFICATION_ACTIVE_SESSION_ACTIVITY_WINDOW",
        "bot_module._NOTIFICATION_RECENT_ANSWER_GRACE_PERIOD",
        "bot_module._NOTIFICATION_DELAY_AFTER_RECENT_ANSWER",
        "bot_module._assignment_assigned_notification_emoji",
        "bot_module._deliver_pending_notification_job",
    )

    assert not any(snippet in text for snippet in forbidden_snippets)
