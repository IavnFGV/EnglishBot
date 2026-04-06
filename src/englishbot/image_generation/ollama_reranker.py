from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass

from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ImageRerankDecision:
    selected_index: int
    rationale: str = ""
    confidence: float | None = None


class OllamaPixabayVisionRerankerClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: int = 60,
        temperature: float | None = None,
        top_p: float | None = None,
        num_predict: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._options = self._build_options(
            temperature=temperature,
            top_p=top_p,
            num_predict=num_predict,
        )

    @logged_service_call(
        "OllamaPixabayVisionRerankerClient.rerank",
        include=("english_word", "translation", "topic_title"),
        transforms={"candidates": lambda value: {"candidate_count": len(value)}},
        result=lambda value: {
            "selected_index": value.selected_index,
            "confidence": value.confidence,
        },
    )
    def rerank(
        self,
        *,
        english_word: str,
        translation: str,
        topic_title: str,
        candidates: list[dict[str, object]],
    ) -> ImageRerankDecision:
        try:
            import requests
        except ImportError as error:
            raise RuntimeError("requests is required for Ollama vision reranking.") from error

        if not candidates:
            raise ValueError("At least one candidate is required.")

        candidate_payload: list[dict[str, object]] = []
        images: list[str] = []
        for index, candidate in enumerate(candidates):
            preview_url = str(candidate.get("preview_url", "")).strip()
            if not preview_url:
                raise ValueError("Each candidate must include preview_url.")
            preview_bytes = requests.get(preview_url, timeout=self._timeout).content
            images.append(base64.b64encode(preview_bytes).decode("ascii"))
            candidate_payload.append(
                {
                    "index": index,
                    "tags": list(candidate.get("tags", ())),
                    "source_page_url": candidate.get("source_page_url"),
                    "width": candidate.get("width"),
                    "height": candidate.get("height"),
                }
            )

        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "english_word": english_word,
                            "translation": translation,
                            "topic_title": topic_title,
                            "candidates": candidate_payload,
                        },
                        ensure_ascii=False,
                    ),
                    "images": images,
                },
            ],
        }
        if self._options:
            payload["options"] = dict(self._options)
        response = requests.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        try:
            return _parse_rerank_decision(content=content, candidate_count=len(candidates))
        except (json.JSONDecodeError, ValueError):
            logger.exception(
                "Ollama reranker returned invalid content model=%s candidate_count=%s raw_content=%r",
                self._model,
                len(candidates),
                content,
            )
            raise

    @staticmethod
    def _build_options(
        *,
        temperature: float | None,
        top_p: float | None,
        num_predict: int | None,
    ) -> dict[str, float | int]:
        options: dict[str, float | int] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if top_p is not None:
            options["top_p"] = top_p
        if num_predict is not None:
            options["num_predict"] = num_predict
        return options


_SYSTEM_PROMPT = (
    "Choose the best vocabulary image for children.\n"
    "You will receive one English word, its translation, the topic title, and candidate images.\n"
    "Pick the most literal, clear, child-friendly match.\n"
    "Avoid abstract art, text-heavy images, collages, and loosely related concepts.\n"
    'Return only a JSON object: {"selected_index": 0}\n'
    "Do not include markdown. Do not include explanation. selected_index must be one of the provided candidate indices."
)


def _parse_rerank_decision(*, content: str, candidate_count: int) -> ImageRerankDecision:
    parsed = _load_json_object(content)
    if not isinstance(parsed, dict):
        raise ValueError("Ollama reranker returned a non-object response.")
    raw_index = parsed.get("selected_index")
    if isinstance(raw_index, str) and raw_index.strip().isdigit():
        raw_index = int(raw_index.strip())
    if not isinstance(raw_index, int) or not (0 <= raw_index < candidate_count):
        raise ValueError("Ollama reranker returned an invalid selected_index.")
    raw_rationale = parsed.get("rationale")
    rationale = raw_rationale.strip() if isinstance(raw_rationale, str) else ""
    raw_confidence = parsed.get("confidence")
    confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float)) else None
    return ImageRerankDecision(
        selected_index=raw_index,
        rationale=rationale,
        confidence=confidence,
    )


def _load_json_object(content: str) -> object:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and start < end:
            return json.loads(stripped[start : end + 1])
        raise
