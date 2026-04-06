from __future__ import annotations

import logging
import sys

import pytest

from englishbot.image_generation.ollama_reranker import (
    OllamaPixabayVisionRerankerClient,
    _parse_rerank_decision,
)


class _FakeResponse:
    def __init__(self, *, content: bytes | None = None, payload: dict | None = None) -> None:
        self.content = content or b""
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeRequestsModule:
    def __init__(self) -> None:
        self.post_calls: list[dict[str, object]] = []

    def get(self, url: str, timeout: int) -> _FakeResponse:
        return _FakeResponse(content=b"fake-image")

    def post(self, url: str, json: dict[str, object], timeout: int) -> _FakeResponse:
        self.post_calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResponse(
            payload={
                "message": {
                    "content": '{"selected_index": 0, "confidence": 0.4, "rationale": "bad "quote""}'
                }
            }
        )


def test_parse_rerank_decision_accepts_valid_payload() -> None:
    decision = _parse_rerank_decision(
        content='{"selected_index": 1, "confidence": 0.8, "rationale": "clear"}',
        candidate_count=3,
    )

    assert decision.selected_index == 1
    assert decision.confidence == 0.8
    assert decision.rationale == "clear"


def test_parse_rerank_decision_accepts_string_index_inside_json_block() -> None:
    decision = _parse_rerank_decision(
        content='```json\n{"selected_index": "2"}\n```',
        candidate_count=3,
    )

    assert decision.selected_index == 2
    assert decision.confidence is None
    assert decision.rationale == ""


def test_parse_rerank_decision_extracts_json_from_wrapped_text() -> None:
    decision = _parse_rerank_decision(
        content='Best match found.\n{"selected_index": 0, "confidence": 0.6}\nDone.',
        candidate_count=2,
    )

    assert decision.selected_index == 0
    assert decision.confidence == 0.6


def test_rerank_logs_raw_content_when_model_returns_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_requests = _FakeRequestsModule()
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    client = OllamaPixabayVisionRerankerClient(
        base_url="http://127.0.0.1:11434",
        model="qwen2.5vl:3b",
        timeout=5,
    )

    with caplog.at_level(logging.ERROR, logger="englishbot.image_generation.ollama_reranker"):
        with pytest.raises(Exception):
            client.rerank(
                english_word="Action figure",
                translation="фигурка",
                topic_title="Toys",
                candidates=[
                    {
                        "preview_url": "https://cdn.example/1.jpg",
                        "tags": ["toy"],
                        "source_page_url": "https://pixabay.example/1",
                        "width": 100,
                        "height": 100,
                    }
                ],
            )

    assert "Ollama reranker returned invalid content" in caplog.text
    assert 'raw_content=\'{"selected_index": 0, "confidence": 0.4, "rationale": "bad "quote""}\'' in caplog.text
