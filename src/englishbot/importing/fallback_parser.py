from __future__ import annotations

import logging
import re
from typing import Protocol

from englishbot.importing.extraction_support import (
    extract_explicit_topic_and_candidate_lines,
    repair_item_from_source,
    split_paired_item,
)
from englishbot.importing.models import ExtractedVocabularyItemDraft, FallbackParseResult, LessonExtractionDraft
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)

_LATIN_RE = re.compile(r"[A-Za-z]")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


class FallbackLessonParser(Protocol):
    def parse(self, *, raw_text: str) -> FallbackParseResult:
        ...


class TemplateLessonFallbackParser:
    @logged_service_call(
        "TemplateLessonFallbackParser.parse",
        transforms={"raw_text": lambda value: {"text_length": len(value)}},
        result=lambda value: {
            "item_count": len(value.draft.vocabulary_items),
            "is_partial": value.is_partial,
            "warning_count": len(value.draft.warnings),
            "unparsed_line_count": len(value.draft.unparsed_lines),
        },
    )
    def parse(self, *, raw_text: str) -> FallbackParseResult:
        topic_title, candidate_lines = extract_explicit_topic_and_candidate_lines(raw_text)
        lesson_title: str | None = None
        items: list[ExtractedVocabularyItemDraft] = []
        unparsed_lines: list[str] = []

        for line in candidate_lines:
            lowered = line.strip().lower()
            if lowered.startswith("topic:"):
                candidate_topic = line.partition(":")[2].strip()
                if candidate_topic:
                    topic_title = candidate_topic
                continue
            if lowered.startswith("lesson:"):
                candidate_lesson = line.partition(":")[2].strip()
                lesson_title = candidate_lesson or None
                continue

            parsed_items = _parse_simple_line(line)
            if parsed_items:
                items.extend(parsed_items)
                continue
            unparsed_lines.append(line)

        warnings = ["Smart parsing is unavailable, so a simpler template-based parse was used."]
        if unparsed_lines:
            warnings.append("Some lines could not be parsed automatically and need manual review.")
        if not items:
            warnings.append("No obvious vocabulary pairs were found. Please complete the draft manually.")

        draft = LessonExtractionDraft(
            topic_title=topic_title or "Imported Topic",
            lesson_title=lesson_title,
            vocabulary_items=items,
            warnings=warnings,
            unparsed_lines=unparsed_lines,
            confidence_notes=[],
        )
        return FallbackParseResult(
            draft=draft,
            is_partial=bool(unparsed_lines) or not items,
        )


def _parse_simple_line(line: str) -> list[ExtractedVocabularyItemDraft]:
    stripped = line.strip()
    if not stripped:
        return []
    for separator in ("—", " – ", " - ", ":", "|"):
        if separator not in stripped:
            continue
        left, _, right = stripped.partition(separator)
        english_word = left.strip()
        translation = right.strip()
        if not english_word or not translation:
            return []
        if not _looks_like_supported_pair(english_word=english_word, translation=translation):
            return []
        repaired = repair_item_from_source(
            ExtractedVocabularyItemDraft(
                english_word=english_word,
                translation=translation,
                source_fragment=stripped,
            )
        )
        return split_paired_item(repaired)
    return []


def _looks_like_supported_pair(*, english_word: str, translation: str) -> bool:
    return bool(_LATIN_RE.search(english_word)) and bool(_CYRILLIC_RE.search(translation))
