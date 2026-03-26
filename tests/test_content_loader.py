from __future__ import annotations

from pathlib import Path

import pytest

from englishbot.infrastructure.content_loader import ContentPackError, JsonContentPackLoader


def test_content_pack_loading_from_demo_directory() -> None:
    loader = JsonContentPackLoader()
    loaded = loader.load_directory(Path("content/demo"))
    assert {topic.id for topic in loaded.topics} == {"school", "seasons", "weather"}
    assert any(item.lesson_id == "weather-1" for item in loaded.vocabulary_items)
    assert any(item.lesson_id is None for item in loaded.vocabulary_items)


def test_content_pack_loader_reads_image_source(tmp_path: Path) -> None:
    path = tmp_path / "pixabay.json"
    path.write_text(
        """
        {
          "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
          "lessons": [],
          "vocabulary_items": [
            {
              "id": "dragon",
              "english_word": "Dragon",
              "translation": "дракон",
              "image_ref": "assets/fairy-tales/dragon.png",
              "image_source": "pixabay"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    loader = JsonContentPackLoader()

    pack = loader.load_file(path)

    assert pack.vocabulary_items[0].image_source == "pixabay"


def test_malformed_json_content_validation(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"topic": {"id": "weather", "title": "Weather"},', encoding="utf-8")
    loader = JsonContentPackLoader()
    with pytest.raises(ContentPackError):
        loader.load_file(path)


def test_invalid_lesson_reference_in_content_pack(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        """
        {
          "topic": {"id": "weather", "title": "Weather"},
          "lessons": [{"id": "lesson-1", "title": "Lesson 1"}],
          "vocabulary_items": [
            {
              "id": "weather-sun",
              "english_word": "sun",
              "translation": "солнце",
              "lesson_id": "missing-lesson"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    loader = JsonContentPackLoader()
    with pytest.raises(ContentPackError):
        loader.load_file(path)
