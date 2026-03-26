from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from englishbot.logging_utils import logged_service_call


@dataclass(slots=True, frozen=True)
class EditableTopic:
    id: str
    title: str


@dataclass(slots=True, frozen=True)
class EditableWord:
    id: str
    english_word: str
    translation: str


class ListEditableTopicsUseCase:
    def __init__(self, *, content_dir: Path) -> None:
        self._content_dir = content_dir

    @logged_service_call(
        "ListEditableTopicsUseCase.execute",
        result=lambda value: {"topic_count": len(value)},
    )
    def execute(self) -> list[EditableTopic]:
        topics: list[EditableTopic] = []
        for path in sorted(self._content_dir.glob("*.json")):
            if path.name.endswith(".draft.json") or path.name.endswith(".parsed.json"):
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            topic = raw.get("topic", {})
            if not isinstance(topic, dict):
                continue
            topic_id = str(topic.get("id", "")).strip()
            title = str(topic.get("title", "")).strip()
            if not topic_id or not title:
                continue
            topics.append(EditableTopic(id=topic_id, title=title))
        return topics


class ListEditableWordsUseCase:
    def __init__(self, *, content_dir: Path) -> None:
        self._content_dir = content_dir

    @logged_service_call(
        "ListEditableWordsUseCase.execute",
        include=("topic_id",),
        result=lambda value: {"item_count": len(value)},
    )
    def execute(self, *, topic_id: str) -> list[EditableWord]:
        path = self._content_dir / f"{topic_id}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw_items = raw.get("vocabulary_items", [])
        if not isinstance(raw_items, list):
            return []
        items: list[EditableWord] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            item_id = str(raw_item.get("id", "")).strip()
            english_word = str(raw_item.get("english_word", "")).strip()
            translation = str(raw_item.get("translation", "")).strip()
            if not item_id or not english_word:
                continue
            items.append(
                EditableWord(
                    id=item_id,
                    english_word=english_word,
                    translation=translation,
                )
            )
        return items


class UpdateEditableWordUseCase:
    def __init__(self, *, content_dir: Path) -> None:
        self._content_dir = content_dir

    @logged_service_call(
        "UpdateEditableWordUseCase.execute",
        include=("topic_id", "item_id"),
        transforms={
            "english_word": lambda value: {"english_word": value},
            "translation": lambda value: {"translation": value},
        },
    )
    def execute(
        self,
        *,
        topic_id: str,
        item_id: str,
        english_word: str,
        translation: str,
    ) -> EditableWord:
        normalized_english = " ".join(english_word.split()).strip()
        normalized_translation = " ".join(translation.split()).strip()
        if not normalized_english:
            raise ValueError("English word is required.")
        if not normalized_translation:
            raise ValueError("Translation is required.")

        path = self._content_dir / f"{topic_id}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw_items = raw.get("vocabulary_items", [])
        if not isinstance(raw_items, list):
            raise ValueError("Content pack vocabulary_items must be a list.")

        updated = False
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            if str(raw_item.get("id", "")).strip() != item_id:
                continue
            raw_item["english_word"] = normalized_english
            raw_item["translation"] = normalized_translation
            updated = True
            break
        if not updated:
            raise ValueError("Vocabulary item was not found.")

        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return EditableWord(
            id=item_id,
            english_word=normalized_english,
            translation=normalized_translation,
        )
