from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)
_WHITESPACE_RE = re.compile(r"\s+")


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
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 120,
    ) -> None:
        self._model = model or os.getenv("OLLAMA_PULL_MODEL", "llama3.2:3b")
        self._base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip(
            "/"
        )
        self._timeout = timeout

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
            prompts = self._generate_item(topic_title=topic_title, item=item)
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
            "model": self._model,
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
        response = requests.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        logger.debug("OllamaImagePromptEnricher raw content=%s", content)
        parsed = self._parse_content(content)
        raw_items = self._extract_items(parsed)
        if not isinstance(raw_items, list):
            raise ValueError("image prompt payload must be an array.")
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
        logger.info("OllamaImagePromptEnricher parsed prompts=%s", len(items))
        return items

    def _system_prompt(self) -> str:
        return (
            "You generate short, concrete image prompts for children's English flashcards. "
            "Return only valid JSON with one key: image_prompts. "
            "Each item must contain: id, english_word, translation, image_prompt. "
            "You will receive exactly one vocabulary_item. Return exactly one prompt item. "
            "Keep prompts visually clear, age-appropriate, and specific to the vocabulary item. "
            "Do not add background stories, violence, horror, or extra characters "
            "unless necessary. "
            "Each image_prompt should be one short sentence."
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
