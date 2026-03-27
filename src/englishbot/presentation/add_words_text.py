from __future__ import annotations

import re

from englishbot.importing.models import (
    ExtractedVocabularyItemDraft,
    ImportLessonResult,
    LessonExtractionDraft,
)


def format_draft_preview(result: ImportLessonResult) -> str:
    draft = result.draft
    if not isinstance(draft, LessonExtractionDraft):
        lines = [
            "Draft preview",
            "Topic: (missing)",
            "Lesson: -",
            "Items: -",
        ]
        if result.validation.errors:
            lines.append(f"Validation errors: {len(result.validation.errors)}")
            for error in result.validation.errors[:5]:
                lines.append(f"- {error.message}")
        return "\n".join(lines)
    lines = [
        "Draft preview",
        f"Topic: {draft.topic_title or '(missing)'}",
        f"Lesson: {draft.lesson_title or '-'}",
        f"Items: {len(draft.vocabulary_items)}",
    ]
    if draft.warnings:
        lines.append(f"Warnings: {len(draft.warnings)}")
        for warning in draft.warnings[:3]:
            lines.append(f"- {warning}")
    if draft.unparsed_lines:
        lines.append(f"Unparsed lines: {len(draft.unparsed_lines)}")
    if result.validation.errors:
        lines.append(f"Validation errors: {len(result.validation.errors)}")
        for error in result.validation.errors[:5]:
            lines.append(f"- {error.message}")
    else:
        for index, item in enumerate(draft.vocabulary_items, start=1):
            candidate = f"{index}. {item.english_word} — {item.translation}"
            projected = "\n".join([*lines, candidate])
            if len(projected) > 3500:
                remaining = len(draft.vocabulary_items) - index + 1
                lines.append(f"... and {remaining} more items")
                break
            lines.append(candidate)
    return "\n".join(lines)


def format_draft_edit_text(draft: LessonExtractionDraft) -> str:
    lines = [
        f"Topic: {draft.topic_title}",
        f"Lesson: {draft.lesson_title or '-'}",
        "",
    ]
    lines.extend(f"{item.english_word}: {item.translation}" for item in draft.vocabulary_items)
    return "\n".join(lines)


def parse_edited_draft_text(
    text: str,
    *,
    previous_draft: LessonExtractionDraft,
) -> LessonExtractionDraft:
    lines = [line.rstrip() for line in text.splitlines()]
    topic_title = previous_draft.topic_title
    lesson_title = previous_draft.lesson_title
    previous_by_word = {
        item.english_word.strip().lower(): item
        for item in previous_draft.vocabulary_items
        if item.english_word.strip()
    }
    items: list[ExtractedVocabularyItemDraft] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if should_ignore_edited_draft_line(line):
            continue
        if line.lower().startswith("topic:"):
            topic_title = line.partition(":")[2].strip() or topic_title
            continue
        if line.lower().startswith("lesson:"):
            lesson_value = line.partition(":")[2].strip()
            lesson_title = None if lesson_value in {"", "-"} else lesson_value
            continue
        parsed_pair = parse_edited_vocabulary_line(line)
        if parsed_pair is None:
            continue
        english_word, translation = parsed_pair
        previous_item = previous_by_word.get(english_word.lower())
        items.append(
            ExtractedVocabularyItemDraft(
                item_id=previous_item.item_id if previous_item is not None else None,
                english_word=english_word,
                translation=translation,
                source_fragment=(
                    previous_item.source_fragment if previous_item is not None else line
                ),
                notes=previous_item.notes if previous_item is not None else None,
                image_prompt=previous_item.image_prompt if previous_item is not None else None,
            )
        )

    return LessonExtractionDraft(
        topic_title=topic_title,
        lesson_title=lesson_title,
        vocabulary_items=items,
        warnings=list(previous_draft.warnings),
        unparsed_lines=[],
        confidence_notes=list(previous_draft.confidence_notes),
    )


def should_ignore_edited_draft_line(line: str) -> bool:
    normalized_line = line.strip().lower()
    if not normalized_line:
        return True
    return (
        normalized_line == "draft preview"
        or normalized_line.startswith("items:")
        or normalized_line.startswith("validation errors:")
        or normalized_line.startswith("- ")
    )


def parse_edited_vocabulary_line(line: str) -> tuple[str, str] | None:
    normalized_line = re.sub(r"^\d+\.\s*", "", line).strip()
    if not normalized_line:
        return None
    for separator in (":", "|", "—", " - ", " – "):
        if separator not in normalized_line:
            continue
        left, _, right = normalized_line.partition(separator)
        english_word = left.strip()
        translation = right.strip()
        if english_word and translation:
            return english_word, translation
    return None
