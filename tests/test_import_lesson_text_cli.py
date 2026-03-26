from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from englishbot import import_lesson_text


def test_import_json_to_db_cli_imports_topics_and_show_topics_reads_them(tmp_path: Path) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    (content_dir / "weather.json").write_text(
        json.dumps(
            {
                "topic": {"id": "weather", "title": "Weather"},
                "lessons": [],
                "vocabulary_items": [
                    {"id": "sun", "english_word": "Sun", "translation": "солнце"}
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    db_path = tmp_path / "data" / "englishbot.db"

    import_result = runner.invoke(
        import_lesson_text.app,
        [
            "import-json-to-db",
            "--input-dir",
            str(content_dir),
            "--db-path",
            str(db_path),
        ],
    )

    assert import_result.exit_code == 0
    assert f"db={db_path}" in import_result.stdout
    assert "topics=1" in import_result.stdout

    show_result = runner.invoke(
        import_lesson_text.app,
        [
            "show-topics",
            "--db-path",
            str(db_path),
        ],
    )

    assert show_result.exit_code == 0
    assert '"id": "weather"' in show_result.stdout
    assert '"title": "Weather"' in show_result.stdout


def test_reset_db_cli_clears_existing_topics(tmp_path: Path) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    (content_dir / "weather.json").write_text(
        json.dumps(
            {
                "topic": {"id": "weather", "title": "Weather"},
                "lessons": [],
                "vocabulary_items": [
                    {"id": "sun", "english_word": "Sun", "translation": "солнце"}
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    db_path = tmp_path / "data" / "englishbot.db"
    runner.invoke(
        import_lesson_text.app,
        [
            "import-json-to-db",
            "--input-dir",
            str(content_dir),
            "--db-path",
            str(db_path),
        ],
        catch_exceptions=False,
    )

    reset_result = runner.invoke(
        import_lesson_text.app,
        [
            "reset-db",
            "--db-path",
            str(db_path),
        ],
    )

    assert reset_result.exit_code == 0

    show_result = runner.invoke(
        import_lesson_text.app,
        [
            "show-topics",
            "--db-path",
            str(db_path),
        ],
    )

    assert show_result.exit_code == 0
    assert show_result.stdout.strip() == "[]"


def test_export_topic_from_db_cli_writes_json_export(tmp_path: Path) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    (content_dir / "weather.json").write_text(
        json.dumps(
            {
                "topic": {"id": "weather", "title": "Weather"},
                "lessons": [],
                "vocabulary_items": [
                    {
                        "id": "sun",
                        "english_word": "Sun",
                        "translation": "солнце",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    db_path = tmp_path / "data" / "englishbot.db"
    export_path = tmp_path / "exports" / "weather.json"

    import_result = runner.invoke(
        import_lesson_text.app,
        [
            "import-json-to-db",
            "--input-dir",
            str(content_dir),
            "--db-path",
            str(db_path),
        ],
    )

    assert import_result.exit_code == 0

    export_result = runner.invoke(
        import_lesson_text.app,
        [
            "export-topic-from-db",
            "--topic-id",
            "weather",
            "--output",
            str(export_path),
            "--db-path",
            str(db_path),
        ],
    )

    assert export_result.exit_code == 0
    assert export_result.stdout.strip() == str(export_path)
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["topic"] == {"id": "weather", "title": "Weather"}
    assert exported["vocabulary_items"][0]["english_word"] == "Sun"
