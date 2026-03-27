from __future__ import annotations

import json
import logging
import re

from englishbot.importing.models import ExtractedVocabularyItemDraft

logger = logging.getLogger(__name__)

_SOURCE_SPLIT_RE = re.compile(r"\s*[—–-]\s*")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_PAIR_SPLIT_RE = re.compile(r"\s*/\s*")
_EDGE_PUNCTUATION_RE = re.compile(r'^[\s"\'.!,:;?()]+|[\s"\'.!,:;?()]+$')
_LEADING_LIST_MARKER_RE = re.compile(r"^\s*\d+[.)]\s*")


def extract_explicit_topic_and_candidate_lines(raw_text: str) -> tuple[str, list[str]]:
    raw_lines = raw_text.splitlines()
    nonempty_lines = [line.strip() for line in raw_lines if line.strip()]
    if not nonempty_lines:
        return "Imported Topic", []

    first_content_index = next(
        (index for index, line in enumerate(raw_lines) if line.strip()),
        None,
    )
    if first_content_index is None:
        return "Imported Topic", []

    first_line = raw_lines[first_content_index].strip()
    if _is_bracketed_topic_line(first_line):
        topic_title = first_line[1:-1].strip() or "Imported Topic"
        candidate_lines = [line.strip() for line in raw_lines[first_content_index + 1 :] if line.strip()]
        return topic_title, candidate_lines

    next_line_index = first_content_index + 1
    if next_line_index < len(raw_lines) and not raw_lines[next_line_index].strip():
        candidate_lines = [line.strip() for line in raw_lines[next_line_index + 1 :] if line.strip()]
        return first_line, candidate_lines

    return "", nonempty_lines


def parse_topic_inference_content(content: str) -> str:
    stripped = content.strip().strip('"').strip("'")
    if not stripped:
        return ""
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        if isinstance(parsed, dict):
            value = parsed.get("topic_title")
            if isinstance(value, str):
                return value.strip()
    return stripped


def parse_line_content(content: str) -> list[dict[str, object]]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1:
        parsed = json.loads(stripped[start : end + 1])
    else:
        parsed = json.loads(stripped)

    if isinstance(parsed, dict):
        raw_items = parsed.get("vocabulary_items")
        if raw_items is None and any(
            key in parsed for key in ("english_word", "translation", "source_fragment")
        ):
            raw_items = [parsed]
        if raw_items is None:
            return []
    elif isinstance(parsed, list):
        raw_items = parsed
    else:
        raise ValueError("Line extraction response must be a JSON object or array.")

    if not isinstance(raw_items, list):
        raise ValueError("Line extraction vocabulary_items must be an array.")
    return [item for item in raw_items if isinstance(item, dict)]


def build_line_items(
    *,
    raw_items: list[dict[str, object]],
    source_line: str,
    include_image_prompts: bool,
) -> list[ExtractedVocabularyItemDraft]:
    return build_draft_items(
        raw_items=raw_items,
        default_source_fragment=source_line,
        include_image_prompts=include_image_prompts,
    )


def build_raw_draft_items(
    *,
    raw_items: list[dict[str, object]],
    default_source_fragment: str,
    include_image_prompts: bool,
) -> list[ExtractedVocabularyItemDraft]:
    items: list[ExtractedVocabularyItemDraft] = []
    for raw_item in raw_items:
        source_fragment = _string_or_empty(raw_item.get("source_fragment")) or default_source_fragment
        items.append(
            ExtractedVocabularyItemDraft(
                english_word=_string_or_empty(raw_item.get("english_word")),
                translation=_string_or_empty(raw_item.get("translation")),
                source_fragment=source_fragment,
                notes=_optional_string(raw_item.get("notes")),
                image_prompt=(
                    _optional_string(raw_item.get("image_prompt")) if include_image_prompts else None
                ),
            )
        )
    return items


def build_draft_items(
    *,
    raw_items: list[dict[str, object]],
    default_source_fragment: str,
    include_image_prompts: bool,
) -> list[ExtractedVocabularyItemDraft]:
    items: list[ExtractedVocabularyItemDraft] = []
    for draft_item in build_raw_draft_items(
        raw_items=raw_items,
        default_source_fragment=default_source_fragment,
        include_image_prompts=include_image_prompts,
    ):
        repaired_item = repair_item_from_source(draft_item)
        items.extend(split_paired_item(repaired_item))
    return items


def ensure_source_fragment(
    item: ExtractedVocabularyItemDraft,
    *,
    source_lines: list[str],
) -> ExtractedVocabularyItemDraft:
    current_source_fragment = item.source_fragment.strip()
    if current_source_fragment and any(
        _normalize_text(source_line) == _normalize_text(current_source_fragment)
        for source_line in source_lines
    ):
        return item

    matched_fragment = _match_source_fragment(
        english_word=item.english_word,
        translation=item.translation,
        source_lines=source_lines,
    )
    if not matched_fragment:
        return item

    if current_source_fragment:
        logger.info(
            "Replaced malformed source_fragment from raw text for english_word=%s old_source_fragment=%s new_source_fragment=%s",
            item.english_word,
            item.source_fragment,
            matched_fragment,
        )
    else:
        logger.info(
            "Recovered source_fragment from raw text for english_word=%s",
            item.english_word,
        )
    repaired = ExtractedVocabularyItemDraft(
        english_word=item.english_word,
        translation=item.translation,
        source_fragment=matched_fragment,
        item_id=item.item_id,
        notes=item.notes,
        image_prompt=item.image_prompt,
    )
    return repair_item_from_source(repaired)


def candidate_source_lines(raw_text: str) -> list[str]:
    candidates: list[str] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped:
            candidates.append(stripped)
    return candidates


def repair_item_from_source(item: ExtractedVocabularyItemDraft) -> ExtractedVocabularyItemDraft:
    parsed = _parse_source_fragment(item.source_fragment)
    if parsed is None:
        return ExtractedVocabularyItemDraft(
            english_word=_strip_leading_list_marker(item.english_word),
            translation=item.translation,
            source_fragment=item.source_fragment,
            item_id=item.item_id,
            notes=item.notes,
            image_prompt=item.image_prompt,
        )
    parsed_english, parsed_translation = parsed
    parsed_english = _strip_leading_list_marker(parsed_english)
    english_word = _strip_leading_list_marker(item.english_word)
    translation = item.translation
    source_english_parts = _split_pair_parts(parsed_english)
    source_translation_parts = _split_pair_parts(parsed_translation)
    item_english_parts = _split_pair_parts(english_word)
    item_translation_parts = _split_pair_parts(translation)
    item_already_matches_aligned_source_pair = _matches_aligned_source_pair(
        english_word=english_word,
        translation=translation,
        source_english_parts=source_english_parts,
        source_translation_parts=source_translation_parts,
    )

    if (
        len(source_english_parts) >= 2
        and len(source_english_parts) == len(source_translation_parts)
        and not item_already_matches_aligned_source_pair
        and (
            len(item_english_parts) != len(source_english_parts)
            or len(item_translation_parts) != len(source_translation_parts)
        )
    ):
        logger.info(
            "Repairing paired item from source_fragment english_word=%s source_fragment=%s",
            english_word or parsed_english,
            item.source_fragment,
        )
        english_word = parsed_english
        translation = parsed_translation

    if _looks_like_bad_translation(translation, parsed_translation):
        logger.info(
            "Repairing translation from source_fragment for english_word=%s",
            english_word or parsed_english,
        )
        translation = parsed_translation

    if _looks_like_bad_english_word(english_word, parsed_english):
        logger.info("Repairing english_word from source_fragment value=%s", parsed_english)
        english_word = parsed_english

    return ExtractedVocabularyItemDraft(
        english_word=english_word,
        translation=translation,
        source_fragment=item.source_fragment,
        item_id=item.item_id,
        notes=item.notes,
        image_prompt=item.image_prompt,
    )


def split_paired_item(item: ExtractedVocabularyItemDraft) -> list[ExtractedVocabularyItemDraft]:
    english_parts = _split_pair_parts(item.english_word)
    translation_parts = _split_pair_parts(item.translation)
    if len(english_parts) < 2 or len(english_parts) != len(translation_parts):
        return [item]

    logger.info(
        "Splitting paired vocabulary item english_word=%s parts=%s",
        item.english_word,
        len(english_parts),
    )
    return [
        ExtractedVocabularyItemDraft(
            english_word=english_part,
            translation=translation_part,
            source_fragment=f"{english_part} — {translation_part}",
            item_id=item.item_id,
            notes=item.notes,
            image_prompt=None,
        )
        for english_part, translation_part in zip(english_parts, translation_parts, strict=True)
    ]


def _is_bracketed_topic_line(line: str) -> bool:
    return line.startswith("[") and line.endswith("]") and len(line) > 2


def _string_or_empty(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _parse_source_fragment(value: str) -> tuple[str, str] | None:
    parts = _SOURCE_SPLIT_RE.split(value, maxsplit=1)
    if len(parts) != 2:
        return None
    left = _strip_leading_list_marker(parts[0].strip())
    right = parts[1].strip()
    if not left or not right:
        return None
    return left, right


def _strip_leading_list_marker(value: str) -> str:
    return _LEADING_LIST_MARKER_RE.sub("", value).strip()


def _looks_like_bad_translation(translation: str, parsed_translation: str) -> bool:
    return bool(_LATIN_RE.search(translation)) and bool(_CYRILLIC_RE.search(parsed_translation))


def _looks_like_bad_english_word(english_word: str, parsed_english: str) -> bool:
    return bool(_CYRILLIC_RE.search(english_word)) and bool(_LATIN_RE.search(parsed_english))


def _match_source_fragment(
    *,
    english_word: str,
    translation: str,
    source_lines: list[str],
) -> str | None:
    normalized_english = _normalize_text(english_word).lower()
    normalized_translation = _normalize_text(translation).lower()

    exact_matches: list[str] = []
    english_only_matches: list[str] = []
    translation_only_matches: list[str] = []
    for source_line in source_lines:
        parsed = _parse_source_fragment(source_line)
        if parsed is None:
            continue
        parsed_english, parsed_translation = parsed
        line_english = _normalize_text(parsed_english).lower()
        line_translation = _normalize_text(parsed_translation).lower()
        source_english_parts = [_normalize_text(part).lower() for part in _split_pair_parts(parsed_english)]
        source_translation_parts = [
            _normalize_text(part).lower() for part in _split_pair_parts(parsed_translation)
        ]
        english_matches = bool(normalized_english) and (
            line_english == normalized_english or normalized_english in source_english_parts
        )
        translation_matches = bool(normalized_translation) and (
            line_translation == normalized_translation or normalized_translation in source_translation_parts
        )

        if english_matches and translation_matches:
            exact_matches.append(source_line)
        elif english_matches:
            english_only_matches.append(source_line)
        elif translation_matches:
            translation_only_matches.append(source_line)

    if exact_matches:
        return exact_matches[0]
    if english_only_matches:
        return english_only_matches[0]
    if translation_only_matches:
        return translation_only_matches[0]
    return None


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _normalize_pair_token(value: str) -> str:
    normalized = _normalize_text(value)
    normalized = _EDGE_PUNCTUATION_RE.sub("", normalized)
    return normalized.lower()


def _split_pair_parts(value: str) -> list[str]:
    if "/" not in value:
        return [value.strip()] if value.strip() else []
    return [part.strip() for part in _PAIR_SPLIT_RE.split(value) if part.strip()]


def _matches_aligned_source_pair(
    *,
    english_word: str,
    translation: str,
    source_english_parts: list[str],
    source_translation_parts: list[str],
) -> bool:
    normalized_english = _normalize_pair_token(english_word)
    normalized_translation = _normalize_pair_token(translation)
    if not normalized_english or not normalized_translation:
        return False
    for source_english, source_translation in zip(
        source_english_parts,
        source_translation_parts,
        strict=False,
    ):
        normalized_source_english = _normalize_pair_token(source_english)
        normalized_source_translation = _normalize_pair_token(source_translation)
        if (
            normalized_source_english == normalized_english
            and normalized_source_translation == normalized_translation
        ):
            return True
        if normalized_source_translation == normalized_translation:
            return True
    return False
