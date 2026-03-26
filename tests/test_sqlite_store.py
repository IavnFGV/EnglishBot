from __future__ import annotations

import json
from pathlib import Path

from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.application.add_words_use_cases import ApproveAddWordsDraftUseCase, StartAddWordsFlowUseCase
from englishbot.bootstrap import build_training_service
from englishbot.domain.models import TrainingMode
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import InMemoryAddWordsFlowRepository
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


class _StubExtractionClient:
    def extract(self, raw_text: str) -> LessonExtractionDraft:  # noqa: ARG002
        return LessonExtractionDraft(
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


def test_sqlite_content_store_imports_json_and_reconstructs_content_pack(tmp_path: Path) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    (content_dir / "fairy-tales.json").write_text(
        json.dumps(
            {
                "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
                "lessons": [{"id": "lesson-1", "title": "Lesson 1"}],
                "vocabulary_items": [
                    {
                        "id": "dragon",
                        "english_word": "Dragon",
                        "translation": "дракон",
                        "lesson_id": "lesson-1",
                        "image_ref": "assets/fairy-tales/dragon.png",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")

    store.import_json_directories([content_dir], replace=True)

    topics = store.list_topics()
    assert topics == [type(topics[0])(id="fairy-tales", title="Fairy Tales")]
    content_pack = store.get_content_pack("fairy-tales")
    assert content_pack["topic"] == {"id": "fairy-tales", "title": "Fairy Tales"}
    assert content_pack["lessons"] == [{"id": "lesson-1", "title": "Lesson 1"}]
    assert content_pack["vocabulary_items"][0]["image_ref"] == "assets/fairy-tales/dragon.png"


def test_build_training_service_uses_sqlite_runtime_storage(tmp_path: Path) -> None:
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
                    },
                    {
                        "id": "rain",
                        "english_word": "Rain",
                        "translation": "дождь",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    service = build_training_service(
        db_path=tmp_path / "data" / "englishbot.db",
        content_directories=[content_dir],
    )

    topics = service.list_topics()
    assert topics == [type(topics[0])(id="weather", title="Weather")]
    question = service.start_session(
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.HARD,
        session_size=1,
    )
    assert question.item_id in {"sun", "rain"}


def test_add_words_approve_publishes_into_sqlite_without_export_file_by_default(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    pipeline = LessonImportPipeline(
        extraction_client=_StubExtractionClient(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )
    harness = AddWordsFlowHarness(
        pipeline=pipeline,
        content_store=store,
    )
    repository = InMemoryAddWordsFlowRepository()
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    approve = ApproveAddWordsDraftUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(user_id=1, raw_text="Dragon — дракон")
    approved = approve.execute(user_id=1, flow_id=flow.flow_id)

    assert approved.published_topic_id == "fairy-tales"
    assert approved.output_path is None
    saved = store.get_content_pack("fairy-tales")
    assert saved["vocabulary_items"][0]["english_word"] == "Dragon"
