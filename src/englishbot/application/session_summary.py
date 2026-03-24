from __future__ import annotations

from englishbot.domain.models import SessionSummary, TrainingSession


class SessionSummaryCalculator:
    def calculate(self, session: TrainingSession) -> SessionSummary:
        return SessionSummary(
            total_questions=session.total_items,
            correct_answers=sum(1 for answer in session.answer_history if answer.is_correct),
        )
