from __future__ import annotations

from pathlib import Path

from englishbot.application.fill_word_images_use_cases import (
    FillWordImagesUseCase,
    select_best_pixabay_candidate,
)
from englishbot.image_generation.pixabay import PixabayImageResult
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


class FakePixabaySearchClient:
    def __init__(self, results_by_word: dict[str, list[PixabayImageResult]]) -> None:
        self.results_by_word = results_by_word
        self.calls: list[tuple[str, str | None, int]] = []

    def search(
        self,
        *,
        english_word: str,
        query: str | None = None,
        page: int = 1,
        per_page: int = 6,
    ) -> tuple[str, list[PixabayImageResult]]:
        self.calls.append((english_word, query, per_page))
        return (query or english_word), list(self.results_by_word.get(english_word, ()))


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
            "topic": {"id": "basics", "title": "Basics"},
            "lessons": [],
            "vocabulary_items": [
                {
                    "id": "good",
                    "english_word": "good",
                    "translation": "хороший",
                },
                {
                    "id": "bad",
                    "english_word": "bad",
                    "translation": "плохой",
                    "pixabay_search_query": "bad emotion",
                },
            ],
        }
    )
    return store


def test_select_best_pixabay_candidate_prefers_semantic_tag_match() -> None:
    candidates = [
        PixabayImageResult(
            source_id="1",
            preview_url="https://cdn.example/1.jpg",
            full_image_url="https://cdn.example/full-1.jpg",
            source_page_url="https://pixabay.example/photos/random-forest",
            width=1200,
            height=800,
            tags=("forest", "nature"),
        ),
        PixabayImageResult(
            source_id="2",
            preview_url="https://cdn.example/2.jpg",
            full_image_url="https://cdn.example/full-2.jpg",
            source_page_url="https://pixabay.example/photos/good-smile-happy",
            width=900,
            height=900,
            tags=("good", "smile", "happy"),
        ),
    ]

    selected = select_best_pixabay_candidate(
        english_word="good",
        normalized_query="good",
        candidates=candidates,
    )

    assert selected is not None
    assert selected.source_id == "2"


def test_fill_word_images_use_case_downloads_best_candidate_and_updates_store(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    downloader = FakeRemoteImageDownloader()
    client = FakePixabaySearchClient(
        {
            "good": [
                PixabayImageResult(
                    source_id="1",
                    preview_url="https://cdn.example/1.jpg",
                    full_image_url="https://cdn.example/full-1.jpg",
                    source_page_url="https://pixabay.example/photos/random-forest",
                    width=1200,
                    height=800,
                    tags=("forest", "nature"),
                ),
                PixabayImageResult(
                    source_id="2",
                    preview_url="https://cdn.example/2.jpg",
                    full_image_url="https://cdn.example/full-2.jpg",
                    source_page_url="https://pixabay.example/photos/good-smile-happy",
                    width=900,
                    height=900,
                    tags=("good", "smile", "happy"),
                ),
            ],
            "bad": [
                PixabayImageResult(
                    source_id="3",
                    preview_url="https://cdn.example/3.jpg",
                    full_image_url="https://cdn.example/full-3.png",
                    source_page_url="https://pixabay.example/photos/bad-emotion-sad",
                    width=1024,
                    height=768,
                    tags=("bad", "emotion", "sad"),
                )
            ],
        }
    )
    use_case = FillWordImagesUseCase(
        store=store,
        image_search_client=client,
        remote_image_downloader=downloader,
        assets_dir=tmp_path / "assets",
    )

    summary = use_case.execute()

    assert summary.scanned_count == 2
    assert summary.updated_count == 2
    assert summary.skipped_count == 0
    assert summary.failed_count == 0
    assert len(downloader.downloads) == 2

    good = store.get_vocabulary_item("good")
    assert good is not None
    assert good.image_source == "pixabay"
    assert good.image_ref == (tmp_path / "assets" / "basics" / "good.jpg").as_posix()
    assert good.pixabay_search_query == "good"
    assert good.source_fragment == "https://pixabay.example/photos/good-smile-happy"

    bad = store.get_vocabulary_item("bad")
    assert bad is not None
    assert bad.image_ref == (tmp_path / "assets" / "basics" / "bad.png").as_posix()
    assert bad.pixabay_search_query == "bad emotion"


def test_fill_word_images_use_case_skips_existing_local_image_without_force(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    existing_path = tmp_path / "assets" / "basics" / "good.jpg"
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_bytes(b"already-there")
    store.update_word_image(
        item_id="good",
        image_ref=existing_path.as_posix(),
        image_source="pixabay",
        pixabay_search_query="good",
        source_fragment="https://pixabay.example/photos/good-smile-happy",
    )
    downloader = FakeRemoteImageDownloader()
    client = FakePixabaySearchClient(
        {
            "bad": [
                PixabayImageResult(
                    source_id="3",
                    preview_url="https://cdn.example/3.jpg",
                    full_image_url="https://cdn.example/full-3.png",
                    source_page_url="https://pixabay.example/photos/bad-emotion-sad",
                    width=1024,
                    height=768,
                    tags=("bad", "emotion", "sad"),
                )
            ]
        }
    )
    use_case = FillWordImagesUseCase(
        store=store,
        image_search_client=client,
        remote_image_downloader=downloader,
        assets_dir=tmp_path / "assets",
    )

    summary = use_case.execute()

    assert summary.scanned_count == 2
    assert summary.updated_count == 1
    assert summary.skipped_count == 1
    assert len(downloader.downloads) == 1
