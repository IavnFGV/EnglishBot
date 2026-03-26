from __future__ import annotations

import logging
from types import SimpleNamespace

from englishbot.image_generation.pixabay import PixabayImageSearchClient


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def test_pixabay_client_builds_query_from_word() -> None:
    client = PixabayImageSearchClient(api_key="test-key")

    query = client.build_query(english_word="Red Dragon")

    assert query == "Red Dragon"


def test_pixabay_client_prefers_illustration_and_falls_back_to_all(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, *, params: dict[str, object], timeout: int):  # noqa: ARG001
        calls.append(params)
        if params["image_type"] == "illustration":
            return _FakeResponse({"hits": []})
        return _FakeResponse(
            {
                "hits": [
                    {
                        "id": 101,
                        "webformatURL": "https://cdn.example/101.jpg",
                        "largeImageURL": "https://cdn.example/101-large.jpg",
                        "pageURL": "https://pixabay.example/101",
                        "imageWidth": 640,
                        "imageHeight": 480,
                    }
                ]
            }
        )

    monkeypatch.setitem(__import__("sys").modules, "requests", SimpleNamespace(get=fake_get))
    client = PixabayImageSearchClient(api_key="test-key")

    query, results = client.search(english_word="Dragon", page=2, per_page=5)

    assert query == "Dragon"
    assert len(results) == 1
    assert results[0].source_id == "101"
    assert results[0].preview_url == "https://cdn.example/101.jpg"
    assert calls == [
        {
            "key": "test-key",
            "q": "Dragon",
            "page": 2,
            "per_page": 5,
            "image_type": "illustration",
            "safesearch": "true",
            "order": "popular",
        },
        {
            "key": "test-key",
            "q": "Dragon",
            "page": 2,
            "per_page": 5,
            "image_type": "all",
            "safesearch": "true",
            "order": "popular",
        },
    ]


def test_pixabay_client_logs_query_and_response_without_api_key(monkeypatch, caplog) -> None:
    def fake_get(url: str, *, params: dict[str, object], timeout: int):  # noqa: ARG001
        return _FakeResponse(
            {
                "total": 1,
                "totalHits": 1,
                "hits": [
                    {
                        "id": 101,
                        "webformatURL": "https://cdn.example/101.jpg",
                        "largeImageURL": "https://cdn.example/101-large.jpg",
                        "pageURL": "https://pixabay.example/101",
                        "imageWidth": 640,
                        "imageHeight": 480,
                    }
                ],
            }
        )

    monkeypatch.setitem(__import__("sys").modules, "requests", SimpleNamespace(get=fake_get))
    caplog.set_level(logging.DEBUG, logger="englishbot.image_generation.pixabay")
    client = PixabayImageSearchClient(api_key="super-secret-key")

    client.search(english_word="Dragon", page=1, per_page=5)

    assert "Pixabay request" in caplog.text
    assert "Pixabay response" in caplog.text
    assert "Dragon" in caplog.text
    assert "super-secret-key" not in caplog.text
    assert "'key':" not in caplog.text
