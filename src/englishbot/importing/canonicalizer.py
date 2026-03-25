from __future__ import annotations

import logging
import re
import unicodedata

from englishbot.importing.models import (
    CanonicalContentPack,
    CanonicalizationResult,
    LessonExtractionDraft,
)
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _WHITESPACE_RE.sub(" ", value.strip())
    return normalized or None


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", normalized.lower()).strip("-")
    return slug or "item"


class DraftToContentPackCanonicalizer:
    @logged_service_call(
        "DraftToContentPackCanonicalizer.convert",
        transforms={
            "draft": lambda value: {
                "topic_title": value.topic_title,
                "item_count": len(value.vocabulary_items),
                "has_lesson": value.lesson_title is not None,
            }
        },
        result=lambda result: {
            "item_count": len(result.content_pack.data.get("vocabulary_items", [])),
            "warning_count": len(result.warnings),
        },
    )
    def convert(self, draft: LessonExtractionDraft) -> CanonicalizationResult:
        topic_title = _normalize_text(draft.topic_title) or "Imported Topic"
        lesson_title = _normalize_text(draft.lesson_title)
        topic_id = _slugify(topic_title)
        lesson_id = f"{topic_id}-{_slugify(lesson_title)}" if lesson_title else None

        vocabulary_items: list[dict[str, object]] = []
        used_ids: set[str] = set()
        for item in draft.vocabulary_items:
            english_word = _normalize_text(item.english_word) or ""
            translation = _normalize_text(item.translation) or ""
            proposed_id = _normalize_text(item.item_id)
            base_id = proposed_id or f"{topic_id}-{_slugify(english_word)}"
            stable_id = self._make_unique(base_id, used_ids)
            used_ids.add(stable_id)
            entry: dict[str, object] = {
                "id": stable_id,
                "english_word": english_word,
                "translation": translation,
                "image_ref": None,
            }
            if lesson_id is not None:
                entry["lesson_id"] = lesson_id
            notes = _normalize_text(item.notes)
            image_prompt = _normalize_text(item.image_prompt)
            source_fragment = _normalize_text(item.source_fragment)
            if notes is not None:
                entry["notes"] = notes
            if image_prompt is not None:
                entry["image_prompt"] = image_prompt
            if source_fragment is not None:
                entry["source_fragment"] = source_fragment
            vocabulary_items.append(entry)

        pack: dict[str, object] = {
            "topic": {"id": topic_id, "title": topic_title},
            "lessons": [],
            "vocabulary_items": vocabulary_items,
        }
        if lesson_title is not None:
            pack["lessons"] = [{"id": lesson_id, "title": lesson_title}]
        metadata = {
            "draft_warnings": list(draft.warnings),
            "unparsed_lines": list(draft.unparsed_lines),
            "confidence_notes": list(draft.confidence_notes),
            "review_recommended": True,
        }
        pack["metadata"] = metadata
        return CanonicalizationResult(
            content_pack=CanonicalContentPack(data=pack),
            warnings=list(draft.warnings),
        )

    def _make_unique(self, base_id: str, used_ids: set[str]) -> str:
        if base_id not in used_ids:
            return base_id
        suffix = 2
        while f"{base_id}-{suffix}" in used_ids:
            suffix += 1
        return f"{base_id}-{suffix}"
