from __future__ import annotations

import logging

from englishbot.domain.models import SessionSummary, TrainingSession

logger = logging.getLogger(__name__)


class SessionSummaryCalculator:
    def calculate(self, session: TrainingSession) -> SessionSummary:
        summary = SessionSummary(
            total_questions=session.total_items,
            correct_answers=sum(1 for answer in session.answer_history if answer.is_correct),
        )
        logger.info(
            "SessionSummaryCalculator session_id=%s total=%s correct=%s incorrect=%s",
            session.id,
            summary.total_questions,
            summary.correct_answers,
            summary.incorrect_answers,
        )
        return summary
