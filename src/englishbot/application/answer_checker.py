from __future__ import annotations

import logging

from englishbot.domain.models import CheckResult, TrainingQuestion

logger = logging.getLogger(__name__)


class AnswerChecker:
    def check(self, *, question: TrainingQuestion, answer: str) -> CheckResult:
        normalized_answer = answer.strip().lower()
        expected_answer = question.correct_answer.strip().lower()
        is_correct = normalized_answer == expected_answer
        logger.info(
            "AnswerChecker.check session_id=%s item_id=%s mode=%s is_correct=%s",
            question.session_id,
            question.item_id,
            question.mode.value,
            is_correct,
        )
        return CheckResult(
            is_correct=is_correct,
            expected_answer=question.correct_answer,
            normalized_answer=normalized_answer,
        )
