from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def test_extract_draft_cli_resolves_runtime_config_at_command_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "lesson.txt"
    input_path.write_text("Dragon — дракон\n", encoding="utf-8")
    output_path = tmp_path / "draft.json"
    captured: dict[str, object] = {}

    def _fake_build_pipeline(**kwargs):
        captured.update(kwargs)

        class _Pipeline:
            def extract_draft(
                self,
                *,
                raw_text: str,
                output_path: Path,
                intermediate_output_path=None,
                enrich_image_prompts: bool = False,
            ):
                output_path.write_text("{}", encoding="utf-8")

                class _Validation:
                    is_valid = True
                    errors = []

                class _Draft:
                    vocabulary_items = []

                class _Result:
                    validation = _Validation()
                    draft = _Draft()

                return _Result()

        return _Pipeline()

    monkeypatch.setattr(import_lesson_text, "_build_pipeline", _fake_build_pipeline)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://late-bound.example:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "late-model")
    runner = CliRunner()

    result = runner.invoke(
        import_lesson_text.app,
        [
            "extract-draft",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--extractor",
            "ollama",
        ],
    )

    assert result.exit_code == 0
    assert captured["ollama_base_url"] == "http://late-bound.example:11434"
    assert captured["ollama_model"] == "late-model"
