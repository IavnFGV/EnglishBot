from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import FakeLessonExtractionClient
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.sqlite_store import SQLiteContentStore
from englishbot.simulate_add_words_flow import app
import englishbot.simulate_add_words_flow as simulate_add_words_flow


def _build_pipeline() -> LessonImportPipeline:
    return LessonImportPipeline(
        extraction_client=FakeLessonExtractionClient(
            LessonExtractionDraft(
                topic_title="Fairy Tales",
                vocabulary_items=[
                    ExtractedVocabularyItemDraft(
                        item_id="dragon",
                        english_word="Dragon",
                        translation="дракон",
                        source_fragment="Dragon — дракон",
                    )
                ],
            )
        ),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )


def test_simulate_add_words_flow_cli_persists_active_flow_in_sqlite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw_input_path = tmp_path / "lesson.txt"
    raw_input_path.write_text("Dragon — дракон\n", encoding="utf-8")
    db_path = tmp_path / "data" / "englishbot.db"
    monkeypatch.setattr(
        "englishbot.simulate_add_words_flow.build_lesson_import_pipeline",
        lambda **kwargs: _build_pipeline(),  # noqa: ARG005
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "--input",
            str(raw_input_path),
            "--db-path",
            str(db_path),
            "--user-id",
            "17",
        ],
    )

    assert result.exit_code == 0
    store = SQLiteContentStore(db_path=db_path)
    flow = store.get_active_add_words_flow_by_user(17)
    assert flow is not None
    assert flow.stage == "draft_review"
    assert flow.draft_result.draft.vocabulary_items[0].english_word == "Dragon"


def test_simulate_add_words_flow_cli_approves_into_sqlite_and_exports_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw_input_path = tmp_path / "lesson.txt"
    raw_input_path.write_text("Dragon — дракон\n", encoding="utf-8")
    edited_input_path = tmp_path / "edited.txt"
    edited_input_path.write_text(
        "Topic: Fairy Tales\n\nDragon: дракон\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "data" / "englishbot.db"
    output_path = tmp_path / "exports" / "fairy-tales.json"
    monkeypatch.setattr(
        "englishbot.simulate_add_words_flow.build_lesson_import_pipeline",
        lambda **kwargs: _build_pipeline(),  # noqa: ARG005
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "--input",
            str(raw_input_path),
            "--edited-input",
            str(edited_input_path),
            "--output",
            str(output_path),
            "--db-path",
            str(db_path),
            "--user-id",
            "18",
        ],
    )

    assert result.exit_code == 0
    assert "Topic: fairy-tales" in result.stdout
    assert str(output_path) in result.stdout
    store = SQLiteContentStore(db_path=db_path)
    content_pack = store.get_content_pack("fairy-tales")
    assert content_pack["vocabulary_items"][0]["english_word"] == "Dragon"
    assert output_path.exists()
    assert store.get_active_add_words_flow_by_user(18) is None


def test_simulate_add_words_flow_cli_resolves_runtime_config_at_command_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_input_path = tmp_path / "lesson.txt"
    raw_input_path.write_text("Dragon — дракон\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def _fake_build_lesson_import_pipeline(**kwargs):
        captured.update(kwargs)
        return _build_pipeline()

    monkeypatch.setattr(
        simulate_add_words_flow,
        "build_lesson_import_pipeline",
        _fake_build_lesson_import_pipeline,
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://late-cli.example:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "late-cli-model")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "--input",
            str(raw_input_path),
            "--user-id",
            "25",
        ],
    )

    assert result.exit_code == 0
    assert captured["ollama_base_url"] == "http://late-cli.example:11434"
    assert captured["ollama_model"] == "late-cli-model"
