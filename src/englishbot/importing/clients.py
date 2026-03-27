from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

from englishbot.config import resolve_ollama_model
from englishbot.importing.extraction_support import (
    build_draft_items,
    build_line_items,
    build_raw_draft_items,
    candidate_source_lines,
    ensure_source_fragment,
    extract_explicit_topic_and_candidate_lines,
    parse_line_content,
    parse_topic_inference_content,
)
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.prompt_loader import load_prompt_text
from englishbot.logging_utils import logged_service_call
from englishbot.ollama_runtime import resolve_runtime_ollama_model

logger = logging.getLogger(__name__)


def _short_text(value: str, *, limit: int = 180) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _normalize_log_text(value: str) -> str:
    return value.replace("\xa0", " ")


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
        model_file_path: Path | None = None,
        base_url: str | None = None,
        timeout: int = 120,
        include_image_prompts: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        num_predict: int | None = None,
        extraction_mode: str | None = None,
        extract_line_prompt_path: Path | None = None,
        extract_text_prompt_path: Path | None = None,
    ) -> None:
        self._model = model or resolve_ollama_model()
        self._model_file_path = model_file_path or (
            Path(raw_model_file_path)
            if (raw_model_file_path := os.getenv("OLLAMA_MODEL_FILE_PATH", "").strip())
            else None
        )
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
        self._extraction_mode = (
            extraction_mode or os.getenv("OLLAMA_EXTRACTION_MODE", "line_by_line")
        ).strip().lower()
        self._extract_line_prompt_path = extract_line_prompt_path or Path(
            os.getenv("OLLAMA_EXTRACT_LINE_PROMPT_PATH", "prompts/ollama_extract_line_prompt.txt")
        )
        self._extract_text_prompt_path = extract_text_prompt_path or Path(
            os.getenv("OLLAMA_EXTRACT_TEXT_PROMPT_PATH", "prompts/ollama_extract_text_prompt.txt")
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
            if self._extraction_mode == "full_text":
                return self._extract_full_text(raw_text=raw_text, requests_module=requests)
            return self._extract_line_by_line(raw_text=raw_text, requests_module=requests)
        except Exception as error:
            logger.exception("OllamaLessonExtractionClient failed: %s", error)
            return {"error": str(error)}

    def _resolved_model(self) -> str:
        return resolve_runtime_ollama_model(
            default_model=self._model,
            model_file_path=self._model_file_path,
        )

    def _text_system_prompt(self) -> str:
        return load_prompt_text(
            path=self._extract_text_prompt_path,
            fallback=(
                "You extract vocabulary items from teacher-written lesson text.\n\n"
                "Return ONLY valid JSON.\n"
                "Do not return markdown.\n"
                "Do not return explanations.\n"
                "Do not return any text before or after JSON.\n\n"
                "Return JSON in exactly this format:\n"
                "{\n"
                '  "vocabulary_items": [\n'
                "    {\n"
                '      "english_word": "string",\n'
                '      "translation": "string",\n'
                '      "notes": null,\n'
                '      "image_prompt": null,\n'
                '      "source_fragment": "string"\n'
                "    }\n"
                "  ]\n"
                "}\n\n"
                "Task:\n"
                "Extract vocabulary pairs from the INPUT_TEXT.\n\n"
                "Rules:\n"
                "- INPUT_TEXT may contain one or more vocabulary pairs.\n"
                '- A vocabulary pair may appear in formats like:\n'
                '  - "Princess / Prince — принцесса / принц"\n'
                '  - "kind (добрый)"\n'
                '  - "kind (добрый), shy (застенчивый), friendly (дружелюбный)"\n'
                '  - "Eraser / Rubber — ластик"\n'
                "- If both sides contain slash-separated synonyms, map them intelligently.\n"
                "- If one English side maps to one translation, allow multiple vocabulary_items with the same translation when appropriate.\n"
                "- If one fragment contains multiple vocabulary pairs, return multiple items.\n"
                "- Preserve translation text exactly as written.\n"
                "- Set notes to null unless extra clarification is explicitly present.\n"
                "- Set image_prompt to null.\n"
                "- source_fragment should contain the original fragment from which the item was extracted.\n"
                "- Ignore non-vocabulary instructions such as homework directions, grammar explanations, or dialogue practice unless they directly contain vocabulary pairs.\n"
                '- If no vocabulary pairs are found, return: {"vocabulary_items": []}\n\n'
                "Important:\n"
                "- Prefer correctness and strict JSON over completeness.\n"
                "- Do not invent words that are not present in INPUT_TEXT.\n"
                "- Do not merge unrelated fragments.\n"
                "- Do not extract grammar patterns as vocabulary items."
            ),
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

    def _extract_full_text(self, *, raw_text: str, requests_module) -> LessonExtractionDraft:
        resolved_model = self._resolved_model()
        logger.debug(
            "OllamaLessonExtractionClient full-text request model=%s resolved_model=%s model_file_path=%s timeout=%s options=%s "
            "prompt_path=%s text_length=%s",
            self._model,
            resolved_model,
            self._model_file_path,
            self._timeout,
            self._options,
            self._extract_text_prompt_path,
            len(raw_text),
        )
        logger.debug(
            "OllamaLessonExtractionClient full-text payload system_prompt=%r user_content=%r",
            self._text_system_prompt(),
            _normalize_log_text(raw_text),
        )
        payload = {
            "model": resolved_model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": self._text_system_prompt()},
                {"role": "user", "content": raw_text},
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
            "OllamaLessonExtractionClient full-text response raw_content=%r compact=%s",
            content,
            _short_text(content, limit=400),
        )
        raw_items = parse_line_content(content)
        source_lines = candidate_source_lines(raw_text)
        items = []
        for raw_item in build_raw_draft_items(
                raw_items=raw_items,
                default_source_fragment="",
                include_image_prompts=self._include_image_prompts,
            ):
            ensured_item = ensure_source_fragment(raw_item, source_lines=source_lines)
            items.extend(build_draft_items(
                raw_items=[
                    {
                        "english_word": ensured_item.english_word,
                        "translation": ensured_item.translation,
                        "notes": ensured_item.notes,
                        "image_prompt": ensured_item.image_prompt,
                        "source_fragment": ensured_item.source_fragment,
                    }
                ],
                default_source_fragment="",
                include_image_prompts=self._include_image_prompts,
            ))
        topic_title, _ = extract_explicit_topic_and_candidate_lines(raw_text)
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
            warnings=[],
            unparsed_lines=[],
            confidence_notes=[],
        )

    def _extract_line_by_line(self, *, raw_text: str, requests_module) -> LessonExtractionDraft:
        topic_title, candidate_lines = extract_explicit_topic_and_candidate_lines(raw_text)

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

    def _infer_topic_title(
        self,
        *,
        items: list[ExtractedVocabularyItemDraft],
        raw_text: str,
        requests_module,
    ) -> str:
        if not items:
            return "Imported Topic"

        resolved_model = self._resolved_model()
        item_summary = ", ".join(item.english_word for item in items if item.english_word.strip())
        prompt_input = (
            f"Extracted words: {item_summary}\n"
            f"Source text:\n{raw_text.strip()}"
        )
        logger.debug(
            (
                "OllamaLessonExtractionClient infer topic "
                "model=%s resolved_model=%s model_file_path=%s timeout=%s prompt_path=%s item_count=%s"
            ),
            self._model,
            resolved_model,
            self._model_file_path,
            self._timeout,
            self._infer_topic_prompt_path,
            len(items),
        )
        logger.debug(
            "OllamaLessonExtractionClient infer topic payload system_prompt=%r user_content=%r",
            self._infer_topic_system_prompt(),
            _normalize_log_text(prompt_input),
        )
        payload = {
            "model": resolved_model,
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
            "OllamaLessonExtractionClient inferred topic_title=%s raw_content=%r compact=%s",
            topic_title,
            content,
            _short_text(content, limit=240),
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
        return parse_topic_inference_content(content)

    def _extract_line_items(
        self,
        *,
        line_index: int,
        source_line: str,
        requests_module,
    ) -> list[ExtractedVocabularyItemDraft]:
        resolved_model = self._resolved_model()
        logger.debug(
            "OllamaLessonExtractionClient line request line_index=%s model=%s resolved_model=%s model_file_path=%s timeout=%s "
            "options=%s prompt_path=%s source_line=%s",
            line_index,
            self._model,
            resolved_model,
            self._model_file_path,
            self._timeout,
            self._options,
            self._extract_line_prompt_path,
            _short_text(_normalize_log_text(source_line)),
        )
        logger.debug(
            (
                "OllamaLessonExtractionClient line payload "
                "line_index=%s system_prompt=%r user_content=%r"
            ),
            line_index,
            self._line_system_prompt(),
            _normalize_log_text(source_line),
        )
        payload = {
            "model": resolved_model,
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
            "OllamaLessonExtractionClient line response line_index=%s raw_content=%r compact=%s",
            line_index,
            content,
            _short_text(content, limit=400),
        )
        raw_items = parse_line_content(content)
        items = build_line_items(
            raw_items=raw_items,
            source_line=source_line,
            include_image_prompts=self._include_image_prompts,
        )
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
