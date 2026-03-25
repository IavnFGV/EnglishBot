from __future__ import annotations

import json
from pathlib import Path

from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.logging_utils import logged_service_call


def _string_or_empty(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def draft_to_data(draft: LessonExtractionDraft) -> dict[str, object]:
    return {
        "topic_title": draft.topic_title,
        "lesson_title": draft.lesson_title,
        "vocabulary_items": [
            {
                "item_id": item.item_id,
                "english_word": item.english_word,
                "translation": item.translation,
                "source_fragment": item.source_fragment,
                "notes": item.notes,
                "image_prompt": item.image_prompt,
            }
            for item in draft.vocabulary_items
        ],
        "warnings": list(draft.warnings),
        "unparsed_lines": list(draft.unparsed_lines),
        "confidence_notes": list(draft.confidence_notes),
    }


class JsonDraftWriter:
    @logged_service_call(
        "JsonDraftWriter.write",
        transforms={
            "draft": lambda value: {"item_count": len(value.vocabulary_items)},
            "output_path": lambda value: {"output_path": value},
        },
    )
    def write(self, *, draft: LessonExtractionDraft, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(draft_to_data(draft), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


class JsonDraftReader:
    @logged_service_call(
        "JsonDraftReader.read",
        transforms={"input_path": lambda value: {"input_path": value}},
        result=lambda value: {"item_count": len(value.vocabulary_items)},
    )
    def read(self, *, input_path: Path) -> LessonExtractionDraft:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        return self.read_data(data)

    def read_data(self, data: object) -> LessonExtractionDraft:
        if not isinstance(data, dict):
            return LessonExtractionDraft(topic_title="", vocabulary_items=[])

        raw_items = data.get("vocabulary_items", [])
        parsed_items: list[ExtractedVocabularyItemDraft] = []
        if isinstance(raw_items, list):
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    raw_item = {}
                parsed_items.append(
                    ExtractedVocabularyItemDraft(
                        item_id=_optional_string(raw_item.get("item_id")),
                        english_word=_string_or_empty(raw_item.get("english_word")),
                        translation=_string_or_empty(raw_item.get("translation")),
                        source_fragment=_string_or_empty(raw_item.get("source_fragment")),
                        notes=_optional_string(raw_item.get("notes")),
                        image_prompt=_optional_string(raw_item.get("image_prompt")),
                    )
                )

        return LessonExtractionDraft(
            topic_title=_string_or_empty(data.get("topic_title")),
            lesson_title=_optional_string(data.get("lesson_title")),
            vocabulary_items=parsed_items,
            warnings=_string_list(data.get("warnings")),
            unparsed_lines=_string_list(data.get("unparsed_lines")),
            confidence_notes=_string_list(data.get("confidence_notes")),
        )
