from __future__ import annotations

import json
import logging
import os
import re
from typing import Protocol

from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)
_SOURCE_SPLIT_RE = re.compile(r"\s*[—–-]\s*")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_PAIR_SPLIT_RE = re.compile(r"\s*/\s*")


class LessonExtractionClient(Protocol):
    def extract(self, raw_text: str) -> LessonExtractionDraft | object:
        ...


class FakeLessonExtractionClient:
    def __init__(self, draft: LessonExtractionDraft | object) -> None:
        self._draft = draft

    @logged_service_call(
        "FakeLessonExtractionClient.extract",
        transforms={"raw_text": lambda value: {"text_length": len(value)}},
    )
    def extract(self, raw_text: str) -> LessonExtractionDraft | object:
        return self._draft


class StubLessonExtractionClient:
    """Placeholder client for local manual use until a real LLM client is wired in."""

    @logged_service_call(
        "StubLessonExtractionClient.extract",
        transforms={"raw_text": lambda value: {"text_length": len(value)}},
        result=lambda value: (
            {
                "topic_title": value.topic_title,
                "item_count": len(value.vocabulary_items),
            }
            if isinstance(value, LessonExtractionDraft)
            else {}
        ),
    )
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


class OllamaLessonExtractionClient:
    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 120,
        include_image_prompts: bool = False,
    ) -> None:
        self._model = model or os.getenv("OLLAMA_PULL_MODEL", "llama3.2:3b")
        self._base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip(
            "/"
        )
        self._timeout = timeout
        self._include_image_prompts = include_image_prompts

    @logged_service_call(
        "OllamaLessonExtractionClient.extract",
        include=(),
        transforms={"raw_text": lambda value: {"text_length": len(value)}},
        result=lambda value: (
            {
                "topic_title": value.topic_title,
                "item_count": len(value.vocabulary_items),
            }
            if isinstance(value, LessonExtractionDraft)
            else {"result_type": type(value).__name__}
        ),
    )
    def extract(self, raw_text: str) -> LessonExtractionDraft | object:
        try:
            import requests
        except ImportError as error:
            logger.error("requests is required for OllamaLessonExtractionClient")
            return {"error": f"Missing dependency: {error}"}

        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": raw_text},
            ],
        }

        try:
            response = requests.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            response_payload = response.json()
            content = response_payload["message"]["content"]
            parsed = self._parse_content(content)
            draft = self._build_draft(parsed, raw_text=raw_text)
            return draft
        except Exception as error:
            logger.exception("OllamaLessonExtractionClient failed: %s", error)
            return {"error": str(error)}

    def _system_prompt(self) -> str:
        return (
            "Extract English lesson vocabulary from messy teacher text. "
            "Return only valid JSON with the keys: "
            "topic_title, lesson_title, vocabulary_items, warnings, "
            "unparsed_lines, confidence_notes. "
            "Each vocabulary item must contain: english_word, translation, "
            "notes, image_prompt, source_fragment. "
            "Use null for missing optional fields. "
            "If one source line contains alternative forms separated by '/' such as "
            "'Princess / Prince — принцесса / принц' or "
            "'Child / Children — ребенок / дети', return separate vocabulary items "
            "for each aligned pair instead of one combined item. "
            "Preserve translations exactly from the source text language; "
            "do not transliterate Russian or Bulgarian words into Latin. "
            "Keep source_fragment close to the original line. "
            "Set image_prompt to null unless explicitly requested by the caller "
            "or clearly present in the source text. "
            "If lesson title is missing, return null. "
            "Do not invent extra words that are not supported by the text."
        )

    def _parse_content(self, content: str) -> dict[str, object]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("Ollama response did not contain a JSON object.")
        parsed = json.loads(stripped[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("Ollama response root must be a JSON object.")
        return parsed

    def _build_draft(self, parsed: dict[str, object], *, raw_text: str) -> LessonExtractionDraft:
        raw_items = parsed.get("vocabulary_items", [])
        if not isinstance(raw_items, list):
            raise ValueError("vocabulary_items must be an array.")
        source_lines = self._candidate_source_lines(raw_text)
        items: list[ExtractedVocabularyItemDraft] = []
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError("Each vocabulary item must be an object.")
            draft_item = ExtractedVocabularyItemDraft(
                english_word=self._string_or_empty(item.get("english_word")),
                translation=self._string_or_empty(item.get("translation")),
                source_fragment=self._string_or_empty(item.get("source_fragment")),
                notes=self._optional_string(item.get("notes")),
                image_prompt=(
                    self._optional_string(item.get("image_prompt"))
                    if self._include_image_prompts
                    else None
                ),
            )
            repaired_item = self._repair_item_from_source(draft_item)
            ensured_item = self._ensure_source_fragment(repaired_item, source_lines)
            items.extend(self._split_paired_item(ensured_item))
        return LessonExtractionDraft(
            topic_title=self._string_or_empty(parsed.get("topic_title")),
            lesson_title=self._optional_string(parsed.get("lesson_title")),
            vocabulary_items=items,
            warnings=self._string_list(parsed.get("warnings")),
            unparsed_lines=self._string_list(parsed.get("unparsed_lines")),
            confidence_notes=self._string_list(parsed.get("confidence_notes")),
        )

    def _string_or_empty(self, value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return None

    def _string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    def _repair_item_from_source(
        self, item: ExtractedVocabularyItemDraft
    ) -> ExtractedVocabularyItemDraft:
        parsed = self._parse_source_fragment(item.source_fragment)
        if parsed is None:
            return item
        parsed_english, parsed_translation = parsed
        english_word = item.english_word
        translation = item.translation
        source_english_parts = self._split_pair_parts(parsed_english)
        source_translation_parts = self._split_pair_parts(parsed_translation)
        item_english_parts = self._split_pair_parts(english_word)
        item_translation_parts = self._split_pair_parts(translation)

        if (
            len(source_english_parts) >= 2
            and len(source_english_parts) == len(source_translation_parts)
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

        if self._looks_like_bad_translation(translation, parsed_translation):
            logger.info(
                "Repairing translation from source_fragment for english_word=%s",
                english_word or parsed_english,
            )
            translation = parsed_translation

        if self._looks_like_bad_english_word(english_word, parsed_english):
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

    def _ensure_source_fragment(
        self,
        item: ExtractedVocabularyItemDraft,
        source_lines: list[str],
    ) -> ExtractedVocabularyItemDraft:
        if item.source_fragment.strip():
            return item

        matched_fragment = self._match_source_fragment(
            english_word=item.english_word,
            translation=item.translation,
            source_lines=source_lines,
        )
        if not matched_fragment:
            return item

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
        return self._repair_item_from_source(repaired)

    def _parse_source_fragment(self, value: str) -> tuple[str, str] | None:
        parts = _SOURCE_SPLIT_RE.split(value, maxsplit=1)
        if len(parts) != 2:
            return None
        left = parts[0].strip()
        right = parts[1].strip()
        if not left or not right:
            return None
        return left, right

    def _looks_like_bad_translation(self, translation: str, parsed_translation: str) -> bool:
        return bool(_LATIN_RE.search(translation)) and bool(_CYRILLIC_RE.search(parsed_translation))

    def _looks_like_bad_english_word(self, english_word: str, parsed_english: str) -> bool:
        return bool(_CYRILLIC_RE.search(english_word)) and bool(_LATIN_RE.search(parsed_english))

    def _candidate_source_lines(self, raw_text: str) -> list[str]:
        candidates: list[str] = []
        for line in raw_text.splitlines():
            stripped = line.strip()
            if stripped and _SOURCE_SPLIT_RE.search(stripped):
                candidates.append(stripped)
        return candidates

    def _match_source_fragment(
        self,
        *,
        english_word: str,
        translation: str,
        source_lines: list[str],
    ) -> str | None:
        normalized_english = self._normalize_text(english_word).lower()
        normalized_translation = self._normalize_text(translation).lower()

        exact_matches: list[str] = []
        english_only_matches: list[str] = []
        translation_only_matches: list[str] = []
        for source_line in source_lines:
            parsed = self._parse_source_fragment(source_line)
            if parsed is None:
                continue
            parsed_english, parsed_translation = parsed
            line_english = self._normalize_text(parsed_english).lower()
            line_translation = self._normalize_text(parsed_translation).lower()
            english_matches = bool(normalized_english) and line_english == normalized_english
            translation_matches = bool(normalized_translation) and (
                line_translation == normalized_translation
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

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())

    def _split_paired_item(
        self,
        item: ExtractedVocabularyItemDraft,
    ) -> list[ExtractedVocabularyItemDraft]:
        english_parts = self._split_pair_parts(item.english_word)
        translation_parts = self._split_pair_parts(item.translation)
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

    def _split_pair_parts(self, value: str) -> list[str]:
        if "/" not in value:
            return [value.strip()] if value.strip() else []
        return [part.strip() for part in _PAIR_SPLIT_RE.split(value) if part.strip()]
