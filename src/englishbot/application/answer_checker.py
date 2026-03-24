from __future__ import annotations

from englishbot.domain.models import CheckResult, TrainingQuestion


class AnswerChecker:
    def check(self, *, question: TrainingQuestion, answer: str) -> CheckResult:
        normalized_answer = answer.strip().lower()
        expected_answer = question.correct_answer.strip().lower()
        return CheckResult(
            is_correct=normalized_answer == expected_answer,
            expected_answer=question.correct_answer,
            normalized_answer=answer.strip(),
        )
