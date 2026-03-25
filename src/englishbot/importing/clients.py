from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Protocol

from englishbot.config import resolve_ollama_model
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.prompt_loader import load_prompt_text
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)
_SOURCE_SPLIT_RE = re.compile(r"\s*[—–-]\s*")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_PAIR_SPLIT_RE = re.compile(r"\s*/\s*")


def _short_text(value: str, *, limit: int = 180) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


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
        temperature: float | None = None,
        top_p: float | None = None,
        num_predict: int | None = None,
        extract_line_prompt_path: Path | None = None,
    ) -> None:
        self._model = model or resolve_ollama_model()
        self._base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip(
            "/"
        )
        self._timeout = timeout
        self._include_image_prompts = include_image_prompts
        self._options = self._build_options(
            temperature=temperature,
            top_p=top_p,
            num_predict=num_predict,
        )
        self._extract_line_prompt_path = extract_line_prompt_path or Path(
            os.getenv("OLLAMA_EXTRACT_LINE_PROMPT_PATH", "prompts/ollama_extract_line_prompt.txt")
        )
        self._infer_topic_prompt_path = Path(
            os.getenv("OLLAMA_INFER_TOPIC_PROMPT_PATH", "prompts/ollama_infer_topic_prompt.txt")
        )

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
        try:
            return self._extract_line_by_line(raw_text=raw_text, requests_module=requests)
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

    def _line_system_prompt(self) -> str:
        return load_prompt_text(
            path=self._extract_line_prompt_path,
            fallback=(
                "Extract vocabulary pairs from one lesson line. "
                "Return only valid JSON with the key vocabulary_items. "
                "vocabulary_items must be an array of objects with keys: "
                "english_word, translation, notes, image_prompt, source_fragment. "
                "One input line may contain multiple aligned pairs separated by '/'. "
                "If the line is 'Princess / Prince — принцесса / принц', return two items. "
                "Preserve the translation text exactly as written in the source language. "
                "Use the original input line as source_fragment unless a cleaner equivalent "
                "is needed. "
                "Set notes and image_prompt to null unless explicitly present. "
                "If the line cannot be parsed into vocabulary pairs, return an empty array."
            ),
        )

    def _extract_line_by_line(self, *, raw_text: str, requests_module) -> LessonExtractionDraft:
        topic_title, candidate_lines = self._extract_explicit_topic_and_candidate_lines(raw_text)

        source_lines = list(candidate_lines)
        unparsed_lines: list[str] = []
        logger.debug(
            "OllamaLessonExtractionClient line-by-line topic=%s source_lines=%s",
            topic_title,
            len(source_lines),
        )

        items: list[ExtractedVocabularyItemDraft] = []
        warnings: list[str] = []
        for index, source_line in enumerate(source_lines, start=1):
            line_items = self._extract_line_items(
                line_index=index,
                source_line=source_line,
                requests_module=requests_module,
            )
            if not line_items:
                logger.warning(
                    "OllamaLessonExtractionClient line parse returned no items line_index=%s "
                    "source_line=%s",
                    index,
                    _short_text(source_line),
                )
                unparsed_lines.append(source_line)
                warnings.append(f"Could not confidently parse line: {source_line}")
                continue
            items.extend(line_items)

        if not topic_title.strip():
            topic_title = self._infer_topic_title(
                items=items,
                raw_text=raw_text,
                requests_module=requests_module,
            )

        return LessonExtractionDraft(
            topic_title=topic_title,
            lesson_title=None,
            vocabulary_items=items,
            warnings=warnings,
            unparsed_lines=unparsed_lines,
            confidence_notes=[],
        )

    def _extract_explicit_topic_and_candidate_lines(self, raw_text: str) -> tuple[str, list[str]]:
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
        if self._is_bracketed_topic_line(first_line):
            topic_title = first_line[1:-1].strip() or "Imported Topic"
            candidate_lines = [
                line.strip() for line in raw_lines[first_content_index + 1 :] if line.strip()
            ]
            return topic_title, candidate_lines

        next_line_index = first_content_index + 1
        if next_line_index < len(raw_lines) and not raw_lines[next_line_index].strip():
            candidate_lines = [
                line.strip()
                for line in raw_lines[next_line_index + 1 :]
                if line.strip()
            ]
            return first_line, candidate_lines

        return "", nonempty_lines

    def _is_bracketed_topic_line(self, line: str) -> bool:
        return line.startswith("[") and line.endswith("]") and len(line) > 2

    def _infer_topic_title(
        self,
        *,
        items: list[ExtractedVocabularyItemDraft],
        raw_text: str,
        requests_module,
    ) -> str:
        if not items:
            return "Imported Topic"

        item_summary = ", ".join(item.english_word for item in items if item.english_word.strip())
        prompt_input = (
            f"Extracted words: {item_summary}\n"
            f"Source text:\n{raw_text.strip()}"
        )
        logger.debug(
            (
                "OllamaLessonExtractionClient infer topic "
                "model=%s timeout=%s prompt_path=%s item_count=%s"
            ),
            self._model,
            self._timeout,
            self._infer_topic_prompt_path,
            len(items),
        )
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": self._infer_topic_system_prompt()},
                {"role": "user", "content": prompt_input},
            ],
        }
        if self._options:
            payload["options"] = dict(self._options)
        response = requests_module.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"].strip()
        topic_title = self._parse_topic_inference_content(content)
        logger.debug(
            "OllamaLessonExtractionClient inferred topic_title=%s raw_content=%s",
            topic_title,
            _short_text(content, limit=120),
        )
        return topic_title or "Imported Topic"

    def _infer_topic_system_prompt(self) -> str:
        return load_prompt_text(
            path=self._infer_topic_prompt_path,
            fallback=(
                "You receive extracted English vocabulary for one lesson. "
                "Return only a short topic title in plain text. "
                "Use 1 to 4 words. "
                "Do not return JSON, explanations, punctuation-only text, or lists."
            ),
        )

    def _parse_topic_inference_content(self, content: str) -> str:
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

    def _extract_line_items(
        self,
        *,
        line_index: int,
        source_line: str,
        requests_module,
    ) -> list[ExtractedVocabularyItemDraft]:
        logger.debug(
            "OllamaLessonExtractionClient line request line_index=%s model=%s timeout=%s "
            "options=%s prompt_path=%s source_line=%s",
            line_index,
            self._model,
            self._timeout,
            self._options,
            self._extract_line_prompt_path,
            _short_text(source_line),
        )
        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": self._line_system_prompt()},
                {"role": "user", "content": source_line},
            ],
        }
        if self._options:
            payload["options"] = dict(self._options)
        response = requests_module.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        logger.debug(
            "OllamaLessonExtractionClient line response line_index=%s raw_content=%s",
            line_index,
            _short_text(content, limit=240),
        )
        raw_items = self._parse_line_content(content)
        items: list[ExtractedVocabularyItemDraft] = []
        for raw_item in raw_items:
            source_fragment = self._string_or_empty(raw_item.get("source_fragment")) or source_line
            draft_item = ExtractedVocabularyItemDraft(
                english_word=self._string_or_empty(raw_item.get("english_word")),
                translation=self._string_or_empty(raw_item.get("translation")),
                source_fragment=source_fragment,
                notes=self._optional_string(raw_item.get("notes")),
                image_prompt=(
                    self._optional_string(raw_item.get("image_prompt"))
                    if self._include_image_prompts
                    else None
                ),
            )
            repaired_item = self._repair_item_from_source(draft_item)
            items.extend(self._split_paired_item(repaired_item))
        logger.debug(
            (
                "OllamaLessonExtractionClient line parsed "
                "line_index=%s raw_item_count=%s final_item_count=%s english_words=%s"
            ),
            line_index,
            len(raw_items),
            len(items),
            [item.english_word for item in items],
        )
        return items

    def _build_options(
        self,
        *,
        temperature: float | None,
        top_p: float | None,
        num_predict: int | None,
    ) -> dict[str, float | int]:
        resolved_temperature = (
            temperature
            if temperature is not None
            else self._optional_float_env("OLLAMA_TEMPERATURE")
        )
        resolved_top_p = (
            top_p if top_p is not None else self._optional_float_env("OLLAMA_TOP_P")
        )
        resolved_num_predict = (
            num_predict
            if num_predict is not None
            else self._optional_int_env("OLLAMA_NUM_PREDICT")
        )
        options: dict[str, float | int] = {}
        if resolved_temperature is not None:
            options["temperature"] = resolved_temperature
        if resolved_top_p is not None:
            options["top_p"] = resolved_top_p
        if resolved_num_predict is not None:
            options["num_predict"] = resolved_num_predict
        return options

    def _optional_float_env(self, name: str) -> float | None:
        value = os.getenv(name, "").strip()
        return float(value) if value else None

    def _optional_int_env(self, name: str) -> int | None:
        value = os.getenv(name, "").strip()
        return int(value) if value else None

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

    def _parse_line_content(self, content: str) -> list[dict[str, object]]:
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
        elif isinstance(parsed, list):
            raw_items = parsed
        else:
            raise ValueError("Line extraction response must be a JSON object or array.")

        if not isinstance(raw_items, list):
            raise ValueError("Line extraction vocabulary_items must be an array.")
        return [item for item in raw_items if isinstance(item, dict)]

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
        item_already_matches_aligned_source_pair = self._matches_aligned_source_pair(
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
            if stripped:
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

    def _matches_aligned_source_pair(
        self,
        *,
        english_word: str,
        translation: str,
        source_english_parts: list[str],
        source_translation_parts: list[str],
    ) -> bool:
        normalized_english = self._normalize_text(english_word).lower()
        normalized_translation = self._normalize_text(translation).lower()
        if not normalized_english or not normalized_translation:
            return False
        for source_english, source_translation in zip(
            source_english_parts,
            source_translation_parts,
            strict=False,
        ):
            normalized_source_english = self._normalize_text(source_english).lower()
            normalized_source_translation = self._normalize_text(source_translation).lower()
            if (
                normalized_source_english == normalized_english
                and normalized_source_translation == normalized_translation
            ):
                return True
            if normalized_source_translation == normalized_translation:
                return True
        return False
