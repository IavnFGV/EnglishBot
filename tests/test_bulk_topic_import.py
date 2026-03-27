from pathlib import Path

from englishbot.importing.bulk_topics import parse_bulk_topic_text, write_bulk_topic_content_packs
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


def test_parse_bulk_topic_text_parses_multiple_plain_topic_blocks() -> None:
    text = """
Birthday
Birthday boy - именинник
Birthday girl - именинница

School
Eraser / Rubber - ластик
"""

    drafts = parse_bulk_topic_text(text)

    assert [draft.topic_title for draft in drafts] == ["Birthday", "School"]
    assert [item.english_word for item in drafts[0].vocabulary_items] == [
        "Birthday boy",
        "Birthday girl",
    ]
    assert [item.translation for item in drafts[1].vocabulary_items] == [
        "ластик",
        "ластик",
    ]
    assert [item.english_word for item in drafts[1].vocabulary_items] == [
        "Eraser",
        "Rubber",
    ]


def test_parse_bulk_topic_text_supports_explicit_topic_headers() -> None:
    text = """
Topic: Food
Bread - хлеб
Milk - молоко
"""

    drafts = parse_bulk_topic_text(text)

    assert len(drafts) == 1
    assert drafts[0].topic_title == "Food"
    assert [item.english_word for item in drafts[0].vocabulary_items] == ["Bread", "Milk"]


def test_write_bulk_topic_content_packs_writes_json_and_imports_to_db(tmp_path: Path) -> None:
    drafts = parse_bulk_topic_text(
        """
Birthday
Birthday boy / Birthday girl - именинник / именинница
"""
    )
    output_dir = tmp_path / "content" / "custom"
    db_path = tmp_path / "data" / "englishbot.db"

    results = write_bulk_topic_content_packs(
        drafts=drafts,
        output_dir=output_dir,
        db_path=db_path,
    )

    assert len(results) == 1
    assert results[0].topic_id == "birthday"
    assert results[0].output_path == output_dir / "birthday.json"
    assert results[0].output_path.exists()

    store = SQLiteContentStore(db_path=db_path)
    topics = store.list_topics()
    assert [topic.id for topic in topics] == ["birthday"]
    words = store.list_editable_words("birthday")
    assert [(english_word, translation) for _, english_word, translation in words] == [
        ("Birthday boy", "именинник"),
        ("Birthday girl", "именинница"),
    ]


def test_write_bulk_topic_content_packs_can_import_only_to_db(tmp_path: Path) -> None:
    drafts = parse_bulk_topic_text(
        """
School
Board - доска
Chalk - мел
"""
    )
    db_path = tmp_path / "data" / "englishbot.db"

    results = write_bulk_topic_content_packs(
        drafts=drafts,
        db_path=db_path,
    )

    assert len(results) == 1
    assert results[0].output_path is None
    store = SQLiteContentStore(db_path=db_path)
    assert [topic.id for topic in store.list_topics()] == ["school"]
