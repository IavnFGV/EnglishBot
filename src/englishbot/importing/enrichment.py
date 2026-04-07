from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from englishbot.config import RuntimeConfigService
from englishbot.importing.prompt_loader import load_prompt_text
from englishbot.logging_utils import logged_service_call
from englishbot.importing.ollama_runtime import resolve_runtime_ollama_model

logger = logging.getLogger(__name__)
_WHITESPACE_RE = re.compile(r"\s+")


def _compact_text(value: str, *, limit: int = 240) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


@dataclass(slots=True, frozen=True)
class ImagePromptItem:
    item_id: str
    english_word: str
    translation: str
    image_prompt: str


class OllamaImagePromptEnricher:
    def __init__(
        self,
        *,
        config_service: RuntimeConfigService | None = None,
        model: str | None = None,
        model_file_path: Path | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        num_predict: int | None = None,
        prompt_path: Path | None = None,
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
        self._timeout = (
            timeout
            if timeout is not None
            else (
                config_service.get_int("ollama_image_prompt_timeout_sec")
                if config_service is not None
                else 30
            )
        )
        self._options = self._build_options(
            temperature=temperature,
            top_p=top_p,
            num_predict=num_predict,
        )
        self._prompt_path = (
            prompt_path
            or _optional_path_setting(
                name="ollama_image_prompt_path",
                explicit_value=None,
                config_service=config_service,
            )
        )

    def _resolved_model(self) -> str:
        return resolve_runtime_ollama_model(
            default_model=self._model,
            model_file_path=self._model_file_path,
        )

    def _optional_float_setting(self, name: str) -> float | None:
        if self._config_service is None:
            return None
        return self._config_service.get_float(name)

    def _optional_int_setting(self, name: str) -> int | None:
        if self._config_service is None:
            return None
        value = self._config_service.get(name)
        return None if value is None else int(value)

    @logged_service_call(
        "OllamaImagePromptEnricher.enrich",
        include=("topic_title",),
        transforms={"vocabulary_items": lambda value: {"item_count": len(value)}},
        result=lambda items: {
            "item_count": len(items),
            "prompt_count": sum(1 for item in items if item.get("image_prompt")),
        },
    )
    def enrich(
        self,
        *,
        topic_title: str,
        vocabulary_items: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        enriched_items: list[dict[str, object]] = []
        for item in vocabulary_items:
            try:
                prompts = self._generate_item(topic_title=topic_title, item=item)
            except Exception:
                logger.exception(
                    "OllamaImagePromptEnricher failed for english_word=%s",
                    item.get("english_word"),
                )
                prompts = []
            prompts_by_id = {item.item_id: item.image_prompt for item in prompts}
            prompts_by_word = {
                self._normalize_word(item.english_word): item.image_prompt
                for item in prompts
                if self._normalize_word(item.english_word)
            }
            matched = 0
            enriched_item = dict(item)
            item_id = str(item.get("id", ""))
            if item_id in prompts_by_id:
                enriched_item["image_prompt"] = prompts_by_id[item_id]
                matched += 1
            else:
                english_word = self._normalize_word(str(item.get("english_word", "")))
                if english_word in prompts_by_word:
                    enriched_item["image_prompt"] = prompts_by_word[english_word]
                    matched += 1
            enriched_items.append(enriched_item)
            if matched == 0:
                logger.warning(
                    "OllamaImagePromptEnricher matched 0 prompts for english_word=%s",
                    item.get("english_word"),
                )
            else:
                logger.info(
                    "OllamaImagePromptEnricher matched prompts=%s english_word=%s",
                    matched,
                    item.get("english_word"),
                )
        return enriched_items

    def _generate_item(
        self, *, topic_title: str, item: dict[str, object]
    ) -> list[ImagePromptItem]:
        try:
            import requests
        except ImportError as error:
            logger.error("requests is required for OllamaImagePromptEnricher")
            raise RuntimeError(f"Missing dependency: {error}") from error

        payload = {
            "model": self._resolved_model(),
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "topic_title": topic_title,
                            "vocabulary_item": {
                                "id": item.get("id"),
                                "english_word": item.get("english_word"),
                                "translation": item.get("translation"),
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        if self._options:
            payload["options"] = dict(self._options)
        system_prompt = str(payload["messages"][0]["content"])
        user_content = str(payload["messages"][1]["content"])
        logger.debug(
            "OllamaImagePromptEnricher request model=%s timeout=%s options=%s prompt_path=%s "
            "english_word=%s",
            self._resolved_model(),
            self._timeout,
            self._options,
            self._prompt_path,
            item.get("english_word"),
        )
        logger.debug(
            "OllamaImagePromptEnricher request payload system_prompt=%r user_content=%r",
            system_prompt,
            user_content,
        )
        response = requests.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        logger.debug(
            "OllamaImagePromptEnricher response english_word=%s raw_content=%r compact=%s",
            item.get("english_word"),
            content,
            _compact_text(content, limit=400),
        )
        items = self._parse_items(content=content, source_item=item)
        logger.info("OllamaImagePromptEnricher parsed prompts=%s", len(items))
        return items

    def _parse_items(
        self,
        *,
        content: str,
        source_item: dict[str, object],
    ) -> list[ImagePromptItem]:
        try:
            parsed = self._parse_content(content)
        except ValueError:
            direct_prompt = self._normalize_direct_prompt(content)
            if direct_prompt is None:
                return []
            return [
                ImagePromptItem(
                    item_id=str(source_item.get("id", "")).strip(),
                    english_word=str(source_item.get("english_word", "")).strip(),
                    translation=str(source_item.get("translation", "")).strip(),
                    image_prompt=direct_prompt,
                )
            ]

        raw_items = self._extract_items(parsed)
        if raw_items == []:
            direct_json_prompt = self._extract_direct_prompt_from_object(
                parsed=parsed,
                source_item=source_item,
            )
            if direct_json_prompt is not None:
                return [direct_json_prompt]
        if isinstance(raw_items, dict):
            direct_item_prompt = self._extract_direct_prompt_from_object(
                parsed=raw_items,
                source_item=source_item,
            )
            return [direct_item_prompt] if direct_item_prompt is not None else []
        if isinstance(raw_items, str):
            direct_prompt = self._first_non_empty(raw_items)
            if direct_prompt is not None:
                return [
                    ImagePromptItem(
                        item_id=str(source_item.get("id", "")).strip(),
                        english_word=str(source_item.get("english_word", "")).strip(),
                        translation=str(source_item.get("translation", "")).strip(),
                        image_prompt=direct_prompt,
                    )
                ]
            return []
        if not isinstance(raw_items, list):
            logger.warning(
                "OllamaImagePromptEnricher received unsupported payload type=%s",
                type(raw_items).__name__,
            )
            return []
        items: list[ImagePromptItem] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            image_prompt = self._first_non_empty(
                item.get("image_prompt"),
                item.get("prompt"),
                item.get("description"),
            )
            item_id = self._first_non_empty(item.get("id"), item.get("item_id")) or ""
            english_word = self._first_non_empty(item.get("english_word"), item.get("word")) or ""
            translation = self._first_non_empty(item.get("translation")) or ""
            if image_prompt:
                items.append(
                    ImagePromptItem(
                        item_id=item_id,
                        english_word=english_word,
                        translation=translation,
                        image_prompt=image_prompt,
                    )
                )
        return items

    def _system_prompt(self) -> str:
        return load_prompt_text(
            path=self._prompt_path,
            fallback=(
                "You generate image prompts for a children's vocabulary flashcard app. "
                "Return only valid JSON with one key: image_prompts. "
                "Each item must contain: id, english_word, translation, image_prompt. "
                "You will receive exactly one vocabulary_item. Return exactly one prompt item. "
                "Use the following instruction exactly when generating image_prompt. "
                "STRICT RULES: "
                "- Output ONLY one line. "
                "- No explanations. "
                "- One object only. "
                "- No scenes. "
                "- No background descriptions. "
                "- White background only. "
                "- If word somehow about human - say - girl or boy, man or women. "
                "Years - old or young"
                "- Keep it simple and clear. "
                "- Use at most 1-2 short descriptive attributes. "
                "If the vocabulary item names alternatives such as 'Princess / Prince', "
                "choose the exact single object named by the current vocabulary item "
                "and do not combine multiple objects. "
                "FORMAT: "
                "\" illustration of <OBJECT WITH OPTIONAL 1-2 ATTRIBUTES>, "
                "simple cartoon style, centered, white background, colorful, no text\". "
                "EXAMPLES: "
                "Input: king. "
                "Output: illustration of a king - older man with a golden crown, "
                "simple cartoon style, centered, white background, colorful, no text. "
                "Input: dragon. "
                "Output: illustration of a green dragon, "
                "simple cartoon style, centered, white background, colorful, no text. "
                "TASK: Generate the prompt. "
                "INPUT WORD: use the english_word from the provided vocabulary_item."
            ),
        )

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
            else self._optional_float_setting("ollama_temperature")
        )
        resolved_top_p = (
            top_p if top_p is not None else self._optional_float_setting("ollama_top_p")
        )
        resolved_num_predict = (
            num_predict
            if num_predict is not None
            else self._optional_int_setting("ollama_num_predict")
        )
        options: dict[str, float | int] = {}
        if resolved_temperature is not None:
            options["temperature"] = resolved_temperature
        if resolved_top_p is not None:
            options["top_p"] = resolved_top_p
        if resolved_num_predict is not None:
            options["num_predict"] = resolved_num_predict
        return options

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

    def _extract_items(self, parsed: dict[str, object]) -> object:
        for key in ("image_prompts", "vocabulary_items", "items", "prompts"):
            if key in parsed:
                return parsed[key]
        return []

    def _first_non_empty(self, *values: object) -> str | None:
        for value in values:
            if isinstance(value, str):
                normalized = _WHITESPACE_RE.sub(" ", value.strip())
                if normalized:
                    return normalized
        return None

    def _normalize_word(self, value: str) -> str:
        return _WHITESPACE_RE.sub(" ", value.strip()).lower()

    def _normalize_direct_prompt(self, content: str) -> str | None:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`").strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
        normalized = self._first_non_empty(stripped)
        if normalized is None:
            return None
        if normalized.startswith("{") and normalized.endswith("}"):
            return None
        return normalized

    def _extract_direct_prompt_from_object(
        self,
        *,
        parsed: dict[str, object],
        source_item: dict[str, object],
    ) -> ImagePromptItem | None:
        image_prompt = self._first_non_empty(
            parsed.get("image_prompt"),
            parsed.get("result_prompt"),
            parsed.get("prompt"),
            parsed.get("description"),
        )
        if image_prompt is None:
            return None
        return ImagePromptItem(
            item_id=self._first_non_empty(parsed.get("id"), source_item.get("id")) or "",
            english_word=(
                self._first_non_empty(parsed.get("english_word"), source_item.get("english_word"))
                or ""
            ),
            translation=(
                self._first_non_empty(parsed.get("translation"), source_item.get("translation"))
                or ""
            ),
            image_prompt=image_prompt,
        )


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
