from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from englishbot.domain.models import Lesson, Topic, VocabularyItem

logger = logging.getLogger(__name__)


class ContentPackError(ValueError):
    """Raised when a content pack is malformed."""


@dataclass(slots=True, frozen=True)
class ContentPack:
    topic: Topic
    lessons: list[Lesson]
    vocabulary_items: list[VocabularyItem]


@dataclass(slots=True, frozen=True)
class LoadedContent:
    topics: list[Topic]
    lessons: list[Lesson]
    vocabulary_items: list[VocabularyItem]


class JsonContentPackLoader:
    def load_directory(self, directory: Path) -> LoadedContent:
        logger.info("Loading content packs from directory %s", directory)
        packs = [self.load_file(path) for path in self._iter_content_pack_files(directory)]
        logger.info("Loaded %s content pack files from %s", len(packs), directory)
        return LoadedContent(
            topics=[pack.topic for pack in packs],
            lessons=[lesson for pack in packs for lesson in pack.lessons],
            vocabulary_items=[item for pack in packs for item in pack.vocabulary_items],
        )

    def _iter_content_pack_files(self, directory: Path) -> list[Path]:
        paths = sorted(directory.glob("*.json"))
        filtered_paths: list[Path] = []
        for path in paths:
            if path.name.endswith(".draft.json") or path.name.endswith(".parsed.json"):
                logger.info("Skipping non-runtime content file %s", path.name)
                continue
            filtered_paths.append(path)
        return filtered_paths

    def load_file(self, path: Path) -> ContentPack:
        logger.debug("Loading content pack file %s", path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            logger.error("Invalid JSON in content pack %s: %s", path, error)
            raise ContentPackError(f"Invalid JSON in {path.name}: {error.msg}") from error
        except OSError as error:
            logger.error("Unable to read content pack %s: %s", path, error)
            raise ContentPackError(f"Unable to read content pack {path.name}.") from error
        pack = self._parse_pack(raw, source_name=path.name)
        logger.info(
            "Loaded content pack %s topic=%s lessons=%s vocabulary_items=%s",
            path.name,
            pack.topic.id,
            len(pack.lessons),
            len(pack.vocabulary_items),
        )
        return pack

    def _parse_pack(self, raw: object, *, source_name: str) -> ContentPack:
        if not isinstance(raw, dict):
            raise ContentPackError(f"{source_name}: root JSON value must be an object.")
        topic_raw = raw.get("topic")
        lessons_raw = raw.get("lessons", [])
        vocabulary_raw = raw.get("vocabulary_items", [])
        if not isinstance(topic_raw, dict):
            raise ContentPackError(f"{source_name}: 'topic' must be an object.")
        if not isinstance(lessons_raw, list) or not isinstance(vocabulary_raw, list):
            raise ContentPackError(
                f"{source_name}: 'lessons' and 'vocabulary_items' must be arrays."
            )

        topic = self._parse_topic(topic_raw, source_name)
        lessons = [
            self._parse_lesson(item, topic_id=topic.id, source_name=source_name)
            for item in lessons_raw
        ]
        lesson_ids = {lesson.id for lesson in lessons}
        vocabulary_items = [
            self._parse_vocabulary_item(
                item,
                topic_id=topic.id,
                lesson_ids=lesson_ids,
                source_name=source_name,
            )
            for item in vocabulary_raw
        ]
        logger.debug(
            "Validated content pack %s topic=%s lessons=%s vocabulary_items=%s",
            source_name,
            topic.id,
            len(lessons),
            len(vocabulary_items),
        )
        return ContentPack(topic=topic, lessons=lessons, vocabulary_items=vocabulary_items)

    def _parse_topic(self, raw: dict[str, object], source_name: str) -> Topic:
        topic_id = self._require_str(raw, "id", source_name, "topic")
        title = self._require_str(raw, "title", source_name, "topic")
        return Topic(id=topic_id, title=title)

    def _parse_lesson(self, raw: object, *, topic_id: str, source_name: str) -> Lesson:
        if not isinstance(raw, dict):
            raise ContentPackError(f"{source_name}: each lesson must be an object.")
        lesson_id = self._require_str(raw, "id", source_name, "lesson")
        title = self._require_str(raw, "title", source_name, "lesson")
        return Lesson(id=lesson_id, title=title, topic_id=topic_id)

    def _parse_vocabulary_item(
        self,
        raw: object,
        *,
        topic_id: str,
        lesson_ids: set[str],
        source_name: str,
    ) -> VocabularyItem:
        if not isinstance(raw, dict):
            raise ContentPackError(f"{source_name}: each vocabulary item must be an object.")
        lesson_id_raw = raw.get("lesson_id")
        lesson_id = None
        if lesson_id_raw is not None:
            if not isinstance(lesson_id_raw, str):
                raise ContentPackError(
                    f"{source_name}: vocabulary item lesson_id must be a string."
                )
            if lesson_id_raw not in lesson_ids:
                raise ContentPackError(
                    f"{source_name}: vocabulary item references unknown lesson '{lesson_id_raw}'."
                )
            lesson_id = lesson_id_raw
        return VocabularyItem(
            id=self._require_str(raw, "id", source_name, "vocabulary item"),
            english_word=self._require_str(raw, "english_word", source_name, "vocabulary item"),
            translation=self._require_str(raw, "translation", source_name, "vocabulary item"),
            topic_id=topic_id,
            lesson_id=lesson_id,
            meaning_hint=self._optional_str(raw, "meaning_hint", source_name, "vocabulary item"),
            image_ref=self._optional_str(raw, "image_ref", source_name, "vocabulary item"),
            image_source=self._optional_str(raw, "image_source", source_name, "vocabulary item"),
            image_prompt=self._optional_str(raw, "image_prompt", source_name, "vocabulary item"),
            source_fragment=self._optional_str(
                raw, "source_fragment", source_name, "vocabulary item"
            ),
            is_active=bool(raw.get("is_active", True)),
        )

    def _require_str(
        self,
        raw: dict[str, object],
        key: str,
        source_name: str,
        section_name: str,
    ) -> str:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ContentPackError(
                f"{source_name}: {section_name} field '{key}' must be a non-empty string."
            )
        return value

    def _optional_str(
        self,
        raw: dict[str, object],
        key: str,
        source_name: str,
        section_name: str,
    ) -> str | None:
        value = raw.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ContentPackError(f"{source_name}: {section_name} field '{key}' must be a string.")
        return value
