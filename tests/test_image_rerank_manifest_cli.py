from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from englishbot.apply_image_rerank_decisions import app as apply_app
from englishbot.export_image_rerank_manifest import app as export_app
from englishbot.infrastructure.sqlite_store import SQLiteContentStore
from englishbot.rerank_image_manifest import app as rerank_app


class FakePixabaySearchClient:
    def __init__(self, **_: object) -> None:
        pass

    def search(
        self,
        *,
        english_word: str,
        query: str | None = None,
        page: int = 1,
        per_page: int = 6,
    ):
        from englishbot.image_generation.pixabay import PixabayImageResult

        return (query or english_word), [
            PixabayImageResult(
                source_id="7",
                preview_url="https://cdn.example/7.jpg",
                full_image_url="https://cdn.example/full-7.jpg",
                source_page_url="https://pixabay.example/photos/windy-tree",
                width=900,
                height=900,
                tags=("wind", "tree"),
            )
        ]


class FakeReranker:
    def __init__(self, **_: object) -> None:
        pass

    def rerank(self, *, english_word: str, translation: str, topic_title: str, candidates: list[dict[str, object]]):
        class Decision:
            selected_index = 0
            confidence = 0.8
            rationale = "Clear match."

        return Decision()


class FakeDownloader:
    def __init__(self, **_: object) -> None:
        pass

    def download(self, *, url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(url.encode("utf-8"))


def _build_store(tmp_path: Path) -> SQLiteContentStore:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.initialize()
    store.upsert_content_pack(
        {
            "topic": {"id": "weather", "title": "Weather"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "wind", "english_word": "wind", "translation": "ветер"},
            ],
        }
    )
    return store


def test_export_rerank_apply_cli_flow(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                f"CONTENT_DB_PATH={(tmp_path / 'data' / 'englishbot.db').as_posix()}",
                "PIXABAY_API_KEY=dummy-pixabay-key",
                "OLLAMA_BASE_URL=http://127.0.0.1:11434",
                "OLLAMA_MODEL=qwen2.5vl:3b",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    store = _build_store(tmp_path)
    manifest_path = tmp_path / "output" / "manifest.json"
    decisions_path = tmp_path / "output" / "decisions.json"

    monkeypatch.setattr("englishbot.export_image_rerank_manifest._REPO_ROOT", tmp_path)
    monkeypatch.setattr("englishbot.rerank_image_manifest._REPO_ROOT", tmp_path)
    monkeypatch.setattr("englishbot.apply_image_rerank_decisions._REPO_ROOT", tmp_path)
    monkeypatch.setattr("englishbot.rerank_image_manifest.PixabayImageSearchClient", FakePixabaySearchClient)
    monkeypatch.setattr("englishbot.rerank_image_manifest.OllamaPixabayVisionRerankerClient", FakeReranker)
    monkeypatch.setattr("englishbot.apply_image_rerank_decisions.RemoteImageDownloader", FakeDownloader)

    export_result = CliRunner().invoke(export_app, ["--output", str(manifest_path)])
    assert export_result.exit_code == 0
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["item_count"] == 1

    rerank_result = CliRunner().invoke(
        rerank_app,
        [
            "--input",
            str(manifest_path),
            "--output",
            str(decisions_path),
        ],
    )
    assert rerank_result.exit_code == 0
    decisions_payload = json.loads(decisions_path.read_text(encoding="utf-8"))
    assert decisions_payload["item_count"] == 1

    apply_result = CliRunner().invoke(
        apply_app,
        [
            "--input",
            str(decisions_path),
            "--assets-dir",
            str(tmp_path / "assets"),
        ],
    )
    assert apply_result.exit_code == 0
    saved = store.get_vocabulary_item("wind")
    assert saved is not None
    assert saved.image_ref == (tmp_path / "assets" / "weather" / "wind.jpg").as_posix()
