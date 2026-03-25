from __future__ import annotations

import logging
import re

from englishbot.importing.models import (
    ExtractedVocabularyItemDraft,
    LessonExtractionDraft,
    ValidationError,
    ValidationResult,
)
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip())


def _normalize_word(value: str) -> str:
    return _normalize_text(value).lower()


class LessonExtractionValidator:
    @logged_service_call(
        "LessonExtractionValidator.validate",
        transforms={
            "draft": lambda value: (
                {
                    "topic_title": value.topic_title,
                    "item_count": len(value.vocabulary_items),
                }
                if isinstance(value, LessonExtractionDraft)
                else {"draft_type": type(value).__name__}
            )
        },
        result=lambda result: {"error_count": len(result.errors), "is_valid": result.is_valid},
    )
    def validate(self, draft: LessonExtractionDraft | object) -> ValidationResult:
        errors: list[ValidationError] = []
        if not isinstance(draft, LessonExtractionDraft):
            logger.warning("LessonExtractionValidator received malformed extraction result")
            return ValidationResult(
                errors=[
                    ValidationError(
                        code="malformed_result",
                        message="Extraction client returned an invalid draft structure.",
                    )
                ]
            )

        if not _normalize_text(draft.topic_title):
            errors.append(
                ValidationError(
                    code="empty_topic_title",
                    message="Topic title is required.",
                    field_name="topic_title",
                )
            )

        proposed_ids: set[str] = set()
        normalized_words: set[str] = set()
        for index, item in enumerate(draft.vocabulary_items):
            errors.extend(self._validate_item(item, index=index))

            if item.item_id is not None:
                normalized_id = _normalize_word(item.item_id)
                if normalized_id in proposed_ids:
                    errors.append(
                        ValidationError(
                            code="duplicate_item_id",
                            message="Duplicate item id inside the same draft.",
                            field_name="item_id",
                            item_index=index,
                        )
                    )
                proposed_ids.add(normalized_id)

            normalized_word = _normalize_word(item.english_word)
            if normalized_word:
                if normalized_word in normalized_words:
                    errors.append(
                        ValidationError(
                            code="duplicate_english_word",
                            message="Duplicate English word inside the same lesson draft.",
                            field_name="english_word",
                            item_index=index,
                        )
                    )
                normalized_words.add(normalized_word)
        return ValidationResult(errors=errors)

    def _validate_item(
        self, item: ExtractedVocabularyItemDraft, *, index: int
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []
        if not _normalize_text(item.english_word):
            errors.append(
                ValidationError(
                    code="empty_english_word",
                    message="English word is required.",
                    field_name="english_word",
                    item_index=index,
                )
            )
        if not _normalize_text(item.translation):
            errors.append(
                ValidationError(
                    code="empty_translation",
                    message="Translation is required.",
                    field_name="translation",
                    item_index=index,
                )
            )
        if not _normalize_text(item.source_fragment):
            errors.append(
                ValidationError(
                    code="empty_source_fragment",
                    message="Source fragment is required for traceability.",
                    field_name="source_fragment",
                    item_index=index,
                )
            )
        return errors
