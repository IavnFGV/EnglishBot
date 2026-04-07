from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AssignmentRoundProgressView:
    completed_word_count: int
    total_word_count: int
    remaining_word_count: int
    variant_key: str


@dataclass(frozen=True, slots=True)
class PendingNotification:
    key: str
    recipient_user_id: int
    text: str
    not_before_at: datetime | None = None
    created_at: datetime | None = None
