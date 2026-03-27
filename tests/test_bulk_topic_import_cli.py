from pathlib import Path

from typer.testing import CliRunner

from englishbot import bulk_import_topics
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


def test_bulk_import_topics_cli_imports_topics_to_db_by_default(tmp_path: Path) -> None:
    input_path = tmp_path / "bulk.txt"
    input_path.write_text(
        """
Birthday
Birthday cake - торт ко дню рождения
Candles - свечи

School
Board - доска
Chalk - мел
""",
        encoding="utf-8",
    )
    db_path = tmp_path / "data" / "englishbot.db"

    result = CliRunner().invoke(
        bulk_import_topics.app,
        [
            str(input_path),
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert '"topic_id": "birthday"' in result.stdout
    assert '"topic_id": "school"' in result.stdout
    assert '"output_path"' not in result.stdout

    store = SQLiteContentStore(db_path=db_path)
    assert [topic.id for topic in store.list_topics()] == ["birthday", "school"]


def test_bulk_import_topics_cli_can_skip_db_import(tmp_path: Path) -> None:
    input_path = tmp_path / "bulk.txt"
    input_path.write_text(
        """
Topic: Animals
Cat - кот
Dog - собака
""",
        encoding="utf-8",
    )
    output_dir = tmp_path / "content" / "custom"
    db_path = tmp_path / "data" / "englishbot.db"

    result = CliRunner().invoke(
        bulk_import_topics.app,
        [
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--db-path",
            str(db_path),
            "--no-db-import",
        ],
    )

    assert result.exit_code == 0
    assert (output_dir / "animals.json").exists()
    store = SQLiteContentStore(db_path=db_path)
    assert store.list_topics() == []


def test_bulk_import_topics_cli_requires_output_dir_when_db_import_is_disabled(tmp_path: Path) -> None:
    input_path = tmp_path / "bulk.txt"
    input_path.write_text(
        """
Topic: Animals
Cat - кот
Dog - собака
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        bulk_import_topics.app,
        [
            str(input_path),
            "--no-db-import",
        ],
    )

    assert result.exit_code != 0
    assert "Use --output-dir when --no-db-import is set." in result.output
