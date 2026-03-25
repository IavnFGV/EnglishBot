from __future__ import annotations

from dataclasses import dataclass, field


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
class ImportLessonResult:
    draft: LessonExtractionDraft
    validation: ValidationResult
    canonicalization: CanonicalizationResult | None = None
