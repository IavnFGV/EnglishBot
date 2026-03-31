from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from englishbot.fill_word_images import app
from englishbot.image_generation.pixabay import PixabayImageResult
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


class FakePixabaySearchClient:
    def __init__(self, **_: object) -> None:
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
        return (query or english_word), [
            PixabayImageResult(
                source_id="7",
                preview_url="https://cdn.example/7.jpg",
                full_image_url="https://cdn.example/full-7.jpg",
                source_page_url="https://pixabay.example/photos/good-smile-happy",
                width=900,
                height=900,
                tags=("good", "smile", "happy"),
            )
        ]


class FakeRemoteImageDownloader:
    def __init__(self, **_: object) -> None:
        self.downloads: list[tuple[str, Path]] = []

    def download(self, *, url: str, output_path: Path) -> None:
        self.downloads.append((url, output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(url.encode("utf-8"))


def test_fill_word_images_cli_updates_missing_images(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                f"CONTENT_DB_PATH={(tmp_path / 'data' / 'englishbot.db').as_posix()}",
                "PIXABAY_API_KEY=dummy-pixabay-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
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
                }
            ],
        }
    )
    monkeypatch.setattr("englishbot.fill_word_images._REPO_ROOT", tmp_path)
    monkeypatch.setattr("englishbot.fill_word_images.PixabayImageSearchClient", FakePixabaySearchClient)
    monkeypatch.setattr("englishbot.fill_word_images.RemoteImageDownloader", FakeRemoteImageDownloader)

    result = CliRunner().invoke(
        app,
        [
            "--assets-dir",
            str(tmp_path / "assets"),
            "--log-level",
            "DEBUG",
        ],
    )

    assert result.exit_code == 0
    saved = store.get_vocabulary_item("good")
    assert saved is not None
    assert saved.image_ref == (tmp_path / "assets" / "basics" / "good.jpg").as_posix()
    assert saved.image_source == "pixabay"
