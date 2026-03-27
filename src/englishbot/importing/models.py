from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True, frozen=True)
class ExtractedVocabularyItemDraft:
    english_word: str
    translation: str
    source_fragment: str
    item_id: str | None = None
    notes: str | None = None
    image_prompt: str | None = None


@dataclass(slots=True, frozen=True)
class LessonExtractionDraft:
    topic_title: str
    vocabulary_items: list[ExtractedVocabularyItemDraft]
    lesson_title: str | None = None
    warnings: list[str] = field(default_factory=list)
    unparsed_lines: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class ValidationError:
    code: str
    message: str
    field_name: str | None = None
    item_index: int | None = None


@dataclass(slots=True, frozen=True)
class ValidationResult:
    errors: list[ValidationError]

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(slots=True, frozen=True)
class CanonicalContentPack:
    data: dict[str, object]


@dataclass(slots=True, frozen=True)
class CanonicalizationResult:
    content_pack: CanonicalContentPack
    warnings: list[str]


@dataclass(slots=True, frozen=True)
class AICapabilityAvailability:
    is_available: bool
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class SmartParseSuccess:
    draft: LessonExtractionDraft


@dataclass(slots=True, frozen=True)
class SmartParseUnavailable:
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class SmartParseTimeout:
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class SmartParseInvalidResponse:
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class SmartParseRemoteError:
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class FallbackParseResult:
    draft: LessonExtractionDraft
    is_partial: bool = False


@dataclass(slots=True, frozen=True)
class DraftExtractionMetadata:
    parse_path: Literal["smart", "fallback"]
    smart_parse_status: Literal[
        "success",
        "unavailable",
        "timeout",
        "invalid_response",
        "remote_error",
    ] | None = None
    status_messages: list[str] = field(default_factory=list)
    fallback_is_partial: bool = False


@dataclass(slots=True, frozen=True)
class ImportLessonResult:
    draft: LessonExtractionDraft
    validation: ValidationResult
    canonicalization: CanonicalizationResult | None = None
    extraction_metadata: DraftExtractionMetadata | None = None
