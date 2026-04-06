from __future__ import annotations

from pathlib import Path

from englishbot.application.image_rerank_manifest_use_cases import (
    ApplyImageRerankDecisionsUseCase,
    ExportImageRerankManifestUseCase,
    ImageRerankManifest,
    ImageRerankManifestItem,
    RerankImageManifestUseCase,
)
from englishbot.image_generation.pixabay import PixabayImageResult
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


class FakePixabaySearchClient:
    def __init__(self, results_by_word: dict[str, list[PixabayImageResult]]) -> None:
        self._results_by_word = results_by_word

    def search(
        self,
        *,
        english_word: str,
        query: str | None = None,
        page: int = 1,
        per_page: int = 6,
    ) -> tuple[str, list[PixabayImageResult]]:
        return (query or english_word), list(self._results_by_word.get(english_word, ())[:per_page])


class FakeRerankerClient:
    def __init__(self, *, selected_index: int = 0, fail: bool = False) -> None:
        self._selected_index = selected_index
        self._fail = fail

    def rerank(
        self,
        *,
        english_word: str,
        translation: str,
        topic_title: str,
        candidates: list[dict[str, object]],
    ):
        if self._fail:
            raise RuntimeError("vision unavailable")

        class Decision:
            def __init__(self, selected_index: int) -> None:
                self.selected_index = selected_index
                self.confidence = 0.9
                self.rationale = "Looks like the clearest match."

        return Decision(self._selected_index)


class FakeRemoteImageDownloader:
    def __init__(self) -> None:
        self.downloads: list[tuple[str, Path]] = []

    def download(self, *, url: str, output_path: Path) -> None:
        self.downloads.append((url, output_path))
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
                {
                    "id": "wind",
                    "english_word": "wind",
                    "translation": "ветер",
                }
            ],
        }
    )
    return store


def test_export_image_rerank_manifest_use_case_builds_manifest(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    manifest = ExportImageRerankManifestUseCase(store=store).execute()

    assert manifest.item_count == 1
    assert manifest.items[0].item_id == "wind"
    assert manifest.items[0].topic_title == "Weather"
    assert manifest.items[0].query == "wind"


def test_rerank_image_manifest_use_case_uses_llm_choice(tmp_path: Path) -> None:
    manifest = ImageRerankManifest(
        exported_at="2026-04-06T00:00:00+00:00",
        item_count=1,
        items=[
            ImageRerankManifestItem(
                item_id="wind",
                english_word="wind",
                translation="ветер",
                topic_id="weather",
                topic_title="Weather",
                query="wind",
            )
        ],
    )
    client = FakePixabaySearchClient(
        {
            "wind": [
                PixabayImageResult(
                    source_id="1",
                    preview_url="https://cdn.example/1.jpg",
                    full_image_url="https://cdn.example/full-1.jpg",
                    source_page_url="https://pixabay.example/photos/flag",
                    width=900,
                    height=600,
                    tags=("flag",),
                ),
                PixabayImageResult(
                    source_id="2",
                    preview_url="https://cdn.example/2.jpg",
                    full_image_url="https://cdn.example/full-2.jpg",
                    source_page_url="https://pixabay.example/photos/windy-tree",
                    width=900,
                    height=600,
                    tags=("wind", "tree"),
                ),
            ]
        }
    )

    decisions = RerankImageManifestUseCase(
        image_search_client=client,
        reranker_client=FakeRerankerClient(selected_index=1),
        candidate_count=3,
    ).execute(manifest=manifest, model_name="qwen2.5vl:3b")

    assert decisions.item_count == 1
    assert decisions.items[0].decision_source == "ollama"
    assert decisions.items[0].selected_candidate["source_id"] == "2"


def test_rerank_image_manifest_use_case_falls_back_to_heuristic(tmp_path: Path) -> None:
    manifest = ImageRerankManifest(
        exported_at="2026-04-06T00:00:00+00:00",
        item_count=1,
        items=[
            ImageRerankManifestItem(
                item_id="wind",
                english_word="wind",
                translation="ветер",
                topic_id="weather",
                topic_title="Weather",
                query="wind",
            )
        ],
    )
    client = FakePixabaySearchClient(
        {
            "wind": [
                PixabayImageResult(
                    source_id="1",
                    preview_url="https://cdn.example/1.jpg",
                    full_image_url="https://cdn.example/full-1.jpg",
                    source_page_url="https://pixabay.example/photos/flag",
                    width=900,
                    height=600,
                    tags=("flag",),
                ),
                PixabayImageResult(
                    source_id="2",
                    preview_url="https://cdn.example/2.jpg",
                    full_image_url="https://cdn.example/full-2.jpg",
                    source_page_url="https://pixabay.example/photos/windy-tree",
                    width=900,
                    height=600,
                    tags=("wind", "tree"),
                ),
            ]
        }
    )

    decisions = RerankImageManifestUseCase(
        image_search_client=client,
        reranker_client=FakeRerankerClient(fail=True),
        candidate_count=3,
    ).execute(manifest=manifest, model_name="qwen2.5vl:3b")

    assert decisions.items[0].decision_source == "heuristic_fallback"
    assert decisions.items[0].selected_candidate["source_id"] == "2"


def test_rerank_image_manifest_use_case_reports_partial_progress(tmp_path: Path) -> None:
    manifest = ImageRerankManifest(
        exported_at="2026-04-06T00:00:00+00:00",
        item_count=2,
        items=[
            ImageRerankManifestItem(
                item_id="wind",
                english_word="wind",
                translation="ветер",
                topic_id="weather",
                topic_title="Weather",
                query="wind",
            ),
            ImageRerankManifestItem(
                item_id="rain",
                english_word="rain",
                translation="дождь",
                topic_id="weather",
                topic_title="Weather",
                query="rain",
            ),
        ],
    )
    client = FakePixabaySearchClient(
        {
            "wind": [
                PixabayImageResult(
                    source_id="1",
                    preview_url="https://cdn.example/1.jpg",
                    full_image_url="https://cdn.example/full-1.jpg",
                    source_page_url="https://pixabay.example/photos/wind",
                    width=900,
                    height=600,
                    tags=("wind",),
                ),
            ],
            "rain": [
                PixabayImageResult(
                    source_id="2",
                    preview_url="https://cdn.example/2.jpg",
                    full_image_url="https://cdn.example/full-2.jpg",
                    source_page_url="https://pixabay.example/photos/rain",
                    width=900,
                    height=600,
                    tags=("rain",),
                ),
            ],
        }
    )
    snapshots: list[tuple[int, list[str]]] = []

    decisions = RerankImageManifestUseCase(
        image_search_client=client,
        reranker_client=FakeRerankerClient(selected_index=0),
        candidate_count=1,
    ).execute(
        manifest=manifest,
        model_name="qwen2.5vl:3b",
        progress_callback=lambda partial: snapshots.append(
            (partial.item_count, [item.item_id for item in partial.items])
        ),
    )

    assert snapshots == [(1, ["wind"]), (2, ["wind", "rain"])]
    assert decisions.item_count == 2


def test_apply_image_rerank_decisions_use_case_downloads_and_updates_store(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    downloader = FakeRemoteImageDownloader()
    manifest = ImageRerankManifest(
        exported_at="2026-04-06T00:00:00+00:00",
        item_count=1,
        items=[],
    )
    decisions = RerankImageManifestUseCase(
        image_search_client=FakePixabaySearchClient(
            {
                "wind": [
                    PixabayImageResult(
                        source_id="2",
                        preview_url="https://cdn.example/2.jpg",
                        full_image_url="https://cdn.example/full-2.png",
                        source_page_url="https://pixabay.example/photos/windy-tree",
                        width=900,
                        height=600,
                        tags=("wind", "tree"),
                    ),
                ]
            }
        ),
        reranker_client=FakeRerankerClient(selected_index=0),
        candidate_count=1,
    ).execute(
        manifest=ImageRerankManifest(
            exported_at=manifest.exported_at,
            item_count=1,
            items=[
                ImageRerankManifestItem(
                    item_id="wind",
                    english_word="wind",
                    translation="ветер",
                    topic_id="weather",
                    topic_title="Weather",
                    query="wind",
                )
            ],
        ),
        model_name="qwen2.5vl:3b",
    )

    summary = ApplyImageRerankDecisionsUseCase(
        store=store,
        remote_image_downloader=downloader,
        assets_dir=tmp_path / "assets",
    ).execute(decisions=decisions)

    assert summary == {"updated_count": 1, "failed_count": 0}
    saved = store.get_vocabulary_item("wind")
    assert saved is not None
    assert saved.image_ref == (tmp_path / "assets" / "weather" / "wind.png").as_posix()
    assert saved.image_source == "pixabay:ollama"
