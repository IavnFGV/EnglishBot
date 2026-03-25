from __future__ import annotations

import logging

from englishbot.domain.models import CheckResult, TrainingQuestion
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


class AnswerChecker:
    @logged_service_call(
        "AnswerChecker.check",
        transforms={
            "question": lambda value: {
                "session_id": value.session_id,
                "item_id": value.item_id,
                "mode": value.mode.value,
            },
            "answer": lambda value: {"answer_length": len(value.strip())},
        },
        result=lambda check_result: {"is_correct": check_result.is_correct},
    )
    def check(self, *, question: TrainingQuestion, answer: str) -> CheckResult:
        normalized_answer = answer.strip().lower()
        expected_answer = question.correct_answer.strip().lower()
        is_correct = normalized_answer == expected_answer
        return CheckResult(
            is_correct=is_correct,
            expected_answer=question.correct_answer,
            normalized_answer=normalized_answer,
        )
