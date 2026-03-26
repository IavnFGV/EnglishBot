from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from englishbot.logging_utils import logged_service_call
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


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
    def __init__(self, *, db_path: Path) -> None:
        self._store = SQLiteContentStore(db_path=db_path)
        self._store.initialize()

    @logged_service_call(
        "ListEditableTopicsUseCase.execute",
        result=lambda value: {"topic_count": len(value)},
    )
    def execute(self) -> list[EditableTopic]:
        return [
            EditableTopic(id=topic.id, title=topic.title)
            for topic in self._store.list_topics()
        ]


class ListEditableWordsUseCase:
    def __init__(self, *, db_path: Path) -> None:
        self._store = SQLiteContentStore(db_path=db_path)
        self._store.initialize()

    @logged_service_call(
        "ListEditableWordsUseCase.execute",
        include=("topic_id",),
        result=lambda value: {"item_count": len(value)},
    )
    def execute(self, *, topic_id: str) -> list[EditableWord]:
        return [
            EditableWord(id=item_id, english_word=english_word, translation=translation)
            for item_id, english_word, translation in self._store.list_editable_words(topic_id)
        ]


class UpdateEditableWordUseCase:
    def __init__(self, *, db_path: Path) -> None:
        self._store = SQLiteContentStore(db_path=db_path)
        self._store.initialize()

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

        self._store.update_word(
            topic_id=topic_id,
            item_id=item_id,
            english_word=normalized_english,
            translation=normalized_translation,
        )
        return EditableWord(
            id=item_id,
            english_word=normalized_english,
            translation=normalized_translation,
        )
