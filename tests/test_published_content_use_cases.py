from __future__ import annotations

import json
from pathlib import Path

from englishbot.application.published_content_use_cases import (
    ListEditableTopicsUseCase,
    ListEditableWordsUseCase,
    UpdateEditableWordUseCase,
)
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


def test_published_content_use_cases_list_topics_words_and_update_word(tmp_path: Path) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    (content_dir / "school-subjects.json").write_text(
        json.dumps(
            {
                "topic": {"id": "school-subjects", "title": "School Subjects"},
                "lessons": [],
                "vocabulary_items": [
                    {
                        "id": "school-subjects-maths",
                        "english_word": "Mathematics",
                        "translation": "математика",
                        "image_ref": "assets/school-subjects/school-subjects-maths.png",
                    },
                    {
                        "id": "school-subjects-science",
                        "english_word": "Science",
                        "translation": "естественные науки",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "data" / "englishbot.db"
    store = SQLiteContentStore(db_path=db_path)
    store.import_json_directories([content_dir], replace=True)

    topics = ListEditableTopicsUseCase(db_path=db_path).execute()
    assert topics == [
        type(topics[0])(id="school-subjects", title="School Subjects")
    ]

    words = ListEditableWordsUseCase(db_path=db_path).execute(topic_id="school-subjects")
    assert [(item.id, item.english_word, item.translation) for item in words] == [
        ("school-subjects-maths", "Mathematics", "математика"),
        ("school-subjects-science", "Science", "естественные науки"),
    ]

    updated = UpdateEditableWordUseCase(db_path=db_path).execute(
        topic_id="school-subjects",
        item_id="school-subjects-maths",
        english_word="Maths",
        translation="математика / матан",
    )

    assert updated.id == "school-subjects-maths"
    assert updated.english_word == "Maths"
    assert updated.translation == "математика / матан"

    saved = store.get_content_pack("school-subjects")
    assert saved["vocabulary_items"][0]["english_word"] == "Maths"
    assert saved["vocabulary_items"][0]["translation"] == "математика / матан"
