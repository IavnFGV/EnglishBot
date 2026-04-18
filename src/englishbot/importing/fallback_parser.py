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
from englishbot.text_variants import expand_aligned_slash_variants

logger = logging.getLogger(__name__)

_LATIN_RE = re.compile(r"[A-Za-z]")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_TRAILING_PUNCTUATION_RE = re.compile(r"[.!?]+$")
_LEADING_LIST_MARKER_RE = re.compile(r"^\s*\d+[\.\)]\s*")
_GENERIC_LEADING_LIST_MARKER_RE = re.compile(
    r"^\s*(?:[-*•▪◦●○]\s+|\[[ xX]\]\s+|\d+[\.)]\s+|[A-Za-z][\.)]\s+)+"
)
_PARENTHESES_PAIR_RE = re.compile(
    r"(?P<english>[A-Za-z][A-Za-z0-9'’/\\ -]*[A-Za-z0-9'’/\\-]|[A-Za-z])\s*"
    r"\((?P<translation>[^()]+)\)"
)
_PARENTHESES_LINE_REMAINDER_RE = re.compile(r"^[\s,;:.!?-]*$")


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
    stripped = _strip_leading_list_markers(line)
    if not stripped:
        return []
    parsed_parentheses_items = _parse_parentheses_pair_line(stripped)
    if parsed_parentheses_items:
        return parsed_parentheses_items
    for separator in ("—", " – ", " - ", ":", "|"):
        if separator not in stripped:
            continue
        left, _, right = stripped.partition(separator)
        english_word = _normalize_fallback_token(left)
        translation = _normalize_fallback_token(right)
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
        return _expand_fallback_item_variants(repaired)
    return []


def _parse_parentheses_pair_line(line: str) -> list[ExtractedVocabularyItemDraft]:
    matches = list(_PARENTHESES_PAIR_RE.finditer(line))
    if not matches:
        return []

    remainder_parts: list[str] = []
    previous_end = 0
    for match in matches:
        remainder_parts.append(line[previous_end : match.start()])
        previous_end = match.end()
    remainder_parts.append(line[previous_end:])
    remainder = "".join(remainder_parts)
    if not _PARENTHESES_LINE_REMAINDER_RE.fullmatch(remainder):
        return []

    parsed_items: list[ExtractedVocabularyItemDraft] = []
    for match in matches:
        english_word = _normalize_fallback_token(
            _LEADING_LIST_MARKER_RE.sub("", match.group("english")).strip()
        )
        translation = _normalize_fallback_token(match.group("translation"))
        if not english_word or not translation:
            return []
        if not _looks_like_supported_pair(english_word=english_word, translation=translation):
            return []
        repaired = repair_item_from_source(
            ExtractedVocabularyItemDraft(
                english_word=english_word,
                translation=translation,
                source_fragment=f"{english_word} — {translation}",
            )
        )
        parsed_items.extend(_expand_fallback_item_variants(repaired))
    return parsed_items


def _expand_fallback_item_variants(item: ExtractedVocabularyItemDraft) -> list[ExtractedVocabularyItemDraft]:
    split_items = split_paired_item(item)
    expanded_items: list[ExtractedVocabularyItemDraft] = []
    for split_item in split_items:
        english_variants, translation_variants = expand_aligned_slash_variants(
            english_word=split_item.english_word,
            translation=split_item.translation,
        )
        for variant, resolved_translation in zip(
            english_variants,
            translation_variants,
            strict=False,
        ):
            expanded_items.append(
                ExtractedVocabularyItemDraft(
                    english_word=variant,
                    translation=resolved_translation,
                    source_fragment=f"{variant} — {resolved_translation}",
                )
            )
    return expanded_items


def _looks_like_supported_pair(*, english_word: str, translation: str) -> bool:
    return bool(_LATIN_RE.search(english_word)) and bool(_CYRILLIC_RE.search(translation))


def _normalize_fallback_token(value: str) -> str:
    normalized = " ".join(value.split()).strip()
    return _TRAILING_PUNCTUATION_RE.sub("", normalized).strip()


def _strip_leading_list_markers(value: str) -> str:
    return _GENERIC_LEADING_LIST_MARKER_RE.sub("", value).strip()
