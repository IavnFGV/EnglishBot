from __future__ import annotations

import logging

from englishbot.domain.models import SessionSummary, TrainingSession
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


class SessionSummaryCalculator:
    @logged_service_call(
        "SessionSummaryCalculator.calculate",
        transforms={
            "session": lambda value: {
                "session_id": value.id,
                "total_items": value.total_items,
            }
        },
        result=lambda summary: {
            "correct_answers": summary.correct_answers,
            "incorrect_answers": summary.incorrect_answers,
        },
    )
    def calculate(self, session: TrainingSession) -> SessionSummary:
        summary = SessionSummary(
            total_questions=session.total_items,
            correct_answers=sum(1 for answer in session.answer_history if answer.is_correct),
        )
        return summary
