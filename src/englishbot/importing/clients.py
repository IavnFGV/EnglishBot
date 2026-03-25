from __future__ import annotations

import logging
from typing import Protocol

from englishbot.importing.models import LessonExtractionDraft

logger = logging.getLogger(__name__)


class LessonExtractionClient(Protocol):
    def extract(self, raw_text: str) -> LessonExtractionDraft | object:
        ...


class FakeLessonExtractionClient:
    def __init__(self, draft: LessonExtractionDraft | object) -> None:
        self._draft = draft

    def extract(self, raw_text: str) -> LessonExtractionDraft | object:
        logger.info("FakeLessonExtractionClient.extract called text_length=%s", len(raw_text))
        return self._draft


class StubLessonExtractionClient:
    """Placeholder client for local manual use until a real LLM client is wired in."""

    def extract(self, raw_text: str) -> LessonExtractionDraft | object:
        logger.warning(
            "StubLessonExtractionClient is producing a placeholder draft. "
            "Use a real semantic extraction client for production."
        )
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        topic_title = lines[0] if lines else "Imported Topic"
        lesson_title = lines[1] if len(lines) > 1 else None
        return LessonExtractionDraft(
            topic_title=topic_title,
            lesson_title=lesson_title,
            vocabulary_items=[],
            warnings=[
                "Stub extraction client was used. Review and enrich the generated content pack."
            ],
            unparsed_lines=lines[2:] if len(lines) > 2 else [],
        )
