from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from typer.testing import CliRunner
import pytest

from englishbot import media_catalog
from englishbot.application.media_catalog_use_cases import TOPICS_SHEET, WORDS_IN_TOPICS_SHEET
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


class FakeRemoteImageDownloader:
    def download(self, *, url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(url.encode("utf-8"))


def _build_store(tmp_path: Path) -> SQLiteContentStore:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "animals", "title": "Animals"},
            "lessons": [],
            "vocabulary_items": [
                {
                    "id": "animals-cat",
                    "english_word": "Cat",
                    "translation": "кот",
                    "image_ref": "https://cdn.example/images/cat.png",
                }
            ],
        }
    )
    return store


def test_media_catalog_cli_exports_and_imports_simple_workbook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _build_store(tmp_path)
    monkeypatch.setattr(
        "englishbot.application.media_catalog_use_cases.RemoteImageDownloader",
        FakeRemoteImageDownloader,
    )
    runner = CliRunner()
    workbook_path = tmp_path / "exports" / "catalog.xlsx"

    export_result = runner.invoke(
        media_catalog.app,
        ["export-workbook", "--output", str(workbook_path), "--db-path", str(store.db_path)],
    )

    assert export_result.exit_code == 0
    workbook = load_workbook(workbook_path)
    topics_sheet = workbook[TOPICS_SHEET]
    words_sheet = workbook[WORDS_IN_TOPICS_SHEET]
    topics_sheet.append(["Pets"])
    words_sheet["G2"] = "https://img.example/preview/cat-sm.png"
    words_sheet.append(
        [
            "Animals",
            "Dog",
            "собака",
            "",
            "",
            "https://img.example/dog.png",
            "",
            "dog prompt",
            "dog clipart",
            "",
            "TRUE",
        ]
    )
    words_sheet.append(
        [
            "Pets",
            "Hamster",
            "хомяк",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "TRUE",
        ]
    )
    workbook.save(workbook_path)

    import_result = runner.invoke(
        media_catalog.app,
        ["import-workbook", "--input", str(workbook_path), "--db-path", str(store.db_path)],
    )

    assert import_result.exit_code == 0
    assert "updated=3" in import_result.stdout
    assert "backup=" in import_result.stdout
    animals = store.list_vocabulary_by_topic("animals")
    assert {item.english_word for item in animals} == {"Cat", "Dog"}
    dog = next(item for item in animals if item.english_word == "Dog")
    assert dog.image_ref == "assets/animals/animals-dog.png"
    assert dog.image_source == "https://img.example/dog.png"
    assert store.list_vocabulary_by_topic("pets")[0].english_word == "Hamster"
