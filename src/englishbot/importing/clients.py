from __future__ import annotations

import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Protocol
from datetime import datetime, timezone

from englishbot.config import RuntimeConfigService
from englishbot.importing.extraction_support import (
    build_draft_items,
    build_line_items,
    build_raw_draft_items,
    ensure_source_fragment,
    extract_explicit_topic_and_candidate_lines,
    parse_line_content,
    parse_topic_inference_content,
)
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.prompt_loader import load_prompt_text
from englishbot.importing.trace import append_jsonl_trace
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


def _metric_bool(value: bool) -> str:
    return "true" if value else "false"


def _metric_optional_int(value: int | None) -> str:
    return "none" if value is None else str(value)


def _draft_item_to_trace(item: ExtractedVocabularyItemDraft) -> dict[str, object]:
    return {
        "english_word": item.english_word,
        "translation": item.translation,
        "source_fragment": item.source_fragment,
        "item_id": item.item_id,
        "notes": item.notes,
        "image_prompt": item.image_prompt,
    }


def _raw_item_to_trace(item: dict[str, object]) -> dict[str, object]:
    return {
        "english_word": item.get("english_word"),
        "translation": item.get("translation"),
        "source_fragment": item.get("source_fragment"),
        "item_id": item.get("item_id"),
        "notes": item.get("notes"),
        "image_prompt": item.get("image_prompt"),
    }


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
        config_service: RuntimeConfigService | None = None,
        model: str | None = None,
        model_file_path: Path | None = None,
        base_url: str | None = None,
        timeout: int = 120,
        trace_file_path: Path | None = None,
        include_image_prompts: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        num_predict: int | None = None,
        extraction_mode: str | None = None,
        extract_line_prompt_path: Path | None = None,
        extract_text_prompt_path: Path | None = None,
    ) -> None:
        self._config_service = config_service
        self._model = _required_str_setting(
            name="ollama_model",
            explicit_value=model,
            config_service=config_service,
        )
        self._model_file_path = _optional_path_setting(
            name="ollama_model_file_path",
            explicit_value=model_file_path,
            config_service=config_service,
        )
        self._base_url = _required_str_setting(
            name="ollama_base_url",
            explicit_value=base_url,
            config_service=config_service,
        ).rstrip("/")
        self._timeout = timeout
        self._trace_file_path = _optional_path_setting(
            name="ollama_trace_file_path",
            explicit_value=trace_file_path,
            config_service=config_service,
        )
        self._include_image_prompts = include_image_prompts
        self._options = self._build_options(
            temperature=temperature,
            top_p=top_p,
            num_predict=num_predict,
        )
        self._extraction_mode = (
            extraction_mode
            if extraction_mode is not None
            else (
                config_service.get_str("ollama_extraction_mode")
                if config_service is not None
                else "line_by_line"
            )
        ).strip().lower()
        self._extract_line_prompt_path = (
            extract_line_prompt_path
            or _optional_path_setting(
                name="ollama_extract_line_prompt_path",
                explicit_value=None,
                config_service=config_service,
            )
        )
        self._extract_text_prompt_path = (
            extract_text_prompt_path
            or _optional_path_setting(
                name="ollama_extract_text_prompt_path",
                explicit_value=None,
                config_service=config_service,
            )
        )
        self._infer_topic_prompt_path = (
            _optional_path_setting(
                name="ollama_infer_topic_prompt_path",
                explicit_value=None,
                config_service=config_service,
            )
        )

    @property
    def base_url(self) -> str:
        return self._base_url

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
        started = perf_counter()
        trace_context = self._build_trace_context(raw_text)
        try:
            import requests
        except ImportError as error:
            logger.error("requests is required for OllamaLessonExtractionClient")
            return {"error": f"Missing dependency: {error}"}
        try:
            if self._extraction_mode == "full_text":
                draft, metrics = self._extract_full_text(raw_text=raw_text, requests_module=requests)
            else:
                draft, metrics = self._extract_line_by_line(raw_text=raw_text, requests_module=requests)
            self._write_trace_event(
                raw_text=raw_text,
                elapsed_ms=int((perf_counter() - started) * 1000),
                success=True,
                trace_context={**trace_context, **metrics},
                topic_title=draft.topic_title,
            )
            return draft
        except Exception as error:
            self._write_trace_event(
                raw_text=raw_text,
                elapsed_ms=int((perf_counter() - started) * 1000),
                success=False,
                trace_context=trace_context,
                error=error,
            )
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

    def _extract_full_text(self, *, raw_text: str, requests_module) -> tuple[LessonExtractionDraft, dict[str, object]]:
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
        topic_title, source_lines = extract_explicit_topic_and_candidate_lines(raw_text)
        infer_topic_requested = not bool(topic_title.strip())
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
        if infer_topic_requested:
            topic_title = self._infer_topic_title(
                items=items,
                raw_text=raw_text,
                requests_module=requests_module,
            )
        draft = LessonExtractionDraft(
            topic_title=topic_title,
            lesson_title=None,
            vocabulary_items=items,
            warnings=[],
            unparsed_lines=[],
            confidence_notes=[],
        )
        metrics = {
            "mode": "full_text",
            "request_count": 1,
            "source_line_count": len(source_lines),
            "parsed_line_count": len(source_lines),
            "unparsed_line_count": 0,
            "raw_item_count": len(raw_items),
            "final_item_count": len(draft.vocabulary_items),
            "infer_topic_requested": infer_topic_requested,
            "model_output_items": [_raw_item_to_trace(item) for item in raw_items],
            "normalized_items": [_draft_item_to_trace(item) for item in draft.vocabulary_items],
        }
        self._log_metrics(metrics)
        return draft, metrics

    def _extract_line_by_line(self, *, raw_text: str, requests_module) -> tuple[LessonExtractionDraft, dict[str, object]]:
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

        infer_topic_requested = not topic_title.strip()
        if infer_topic_requested:
            topic_title = self._infer_topic_title(
                items=items,
                raw_text=raw_text,
                requests_module=requests_module,
            )

        draft = LessonExtractionDraft(
            topic_title=topic_title,
            lesson_title=None,
            vocabulary_items=items,
            warnings=warnings,
            unparsed_lines=unparsed_lines,
            confidence_notes=[],
        )
        metrics = {
            "mode": "line_by_line",
            "request_count": len(candidate_lines) + (1 if infer_topic_requested else 0),
            "source_line_count": len(candidate_lines),
            "parsed_line_count": len(candidate_lines) - len(unparsed_lines),
            "unparsed_line_count": len(unparsed_lines),
            "raw_item_count": None,
            "final_item_count": len(draft.vocabulary_items),
            "infer_topic_requested": infer_topic_requested,
            "model_output_items": None,
            "normalized_items": [_draft_item_to_trace(item) for item in draft.vocabulary_items],
        }
        self._log_metrics(metrics)
        return draft, metrics

    def _build_trace_context(self, raw_text: str) -> dict[str, object]:
        topic_title, candidate_lines = extract_explicit_topic_and_candidate_lines(raw_text)
        infer_topic_requested = not bool(topic_title.strip())
        return {
            "mode": self._extraction_mode,
            "prompt_path": str(
                self._extract_text_prompt_path
                if self._extraction_mode == "full_text"
                else self._extract_line_prompt_path
            ),
            "request_count": (
                1
                if self._extraction_mode == "full_text"
                else len(candidate_lines) + (1 if infer_topic_requested else 0)
            ),
            "source_line_count": len(candidate_lines),
            "parsed_line_count": None,
            "unparsed_line_count": None,
            "raw_item_count": None,
            "final_item_count": None,
            "infer_topic_requested": infer_topic_requested,
            "model_output_items": None,
            "normalized_items": None,
        }

    def _log_metrics(self, metrics: dict[str, object]) -> None:
        logger.info(
            "OllamaLessonExtractionClient metrics mode=%s request_count=%s source_line_count=%s parsed_line_count=%s "
            "unparsed_line_count=%s raw_item_count=%s final_item_count=%s infer_topic_requested=%s",
            metrics["mode"],
            metrics["request_count"],
            metrics["source_line_count"],
            metrics["parsed_line_count"],
            metrics["unparsed_line_count"],
            _metric_optional_int(metrics["raw_item_count"] if isinstance(metrics["raw_item_count"], int) else None),
            metrics["final_item_count"],
            _metric_bool(bool(metrics["infer_topic_requested"])),
        )

    def _write_trace_event(
        self,
        *,
        raw_text: str,
        elapsed_ms: int,
        success: bool,
        trace_context: dict[str, object],
        topic_title: str | None = None,
        error: Exception | None = None,
    ) -> None:
        if self._trace_file_path is None:
            return
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": "ollama_extraction",
            "success": success,
            "default_model": self._model,
            "resolved_model": self._resolved_model(),
            "model_file_path": str(self._model_file_path) if self._model_file_path is not None else None,
            "base_url": self._base_url,
            "timeout_sec": self._timeout,
            "text_length": len(raw_text),
            "input_preview": _short_text(_normalize_log_text(raw_text), limit=400),
            "elapsed_ms": elapsed_ms,
            "topic_title": topic_title,
            "error_type": type(error).__name__ if error is not None else None,
            "error": str(error) if error is not None else None,
            **trace_context,
        }
        try:
            append_jsonl_trace(self._trace_file_path, event)
        except Exception as trace_error:  # pragma: no cover
            logger.exception("Failed to append Ollama extraction trace: %s", trace_error)

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
        if self._config_service is None:
            return None
        if name == "OLLAMA_TEMPERATURE":
            return self._config_service.get_float("ollama_temperature")
        if name == "OLLAMA_TOP_P":
            return self._config_service.get_float("ollama_top_p")
        return None

    def _optional_int_env(self, name: str) -> int | None:
        if self._config_service is None:
            return None
        if name == "OLLAMA_NUM_PREDICT":
            value = self._config_service.get("ollama_num_predict")
            return None if value is None else int(value)
        return None

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


def _required_str_setting(
    *,
    name: str,
    explicit_value: str | None,
    config_service: RuntimeConfigService | None,
) -> str:
    if explicit_value is not None:
        return explicit_value
    if config_service is not None:
        return config_service.get_str(name)
    raise ValueError(f"{name} must be provided explicitly or via config_service.")


def _optional_path_setting(
    *,
    name: str,
    explicit_value: Path | None,
    config_service: RuntimeConfigService | None,
) -> Path | None:
    if explicit_value is not None:
        return explicit_value
    if config_service is not None:
        return config_service.get_path(name)
    return None
