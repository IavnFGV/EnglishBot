from __future__ import annotations

import json
from pathlib import Path

from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.application.add_words_use_cases import (
    ApproveAddWordsDraftUseCase,
    SaveApprovedAddWordsDraftUseCase,
    StartAddWordsFlowUseCase,
)
from englishbot.application.image_review_flow import ImageReviewFlowHarness
from englishbot.application.image_review_use_cases import (
    GenerateImageReviewCandidatesUseCase,
    StartImageReviewUseCase,
)
from englishbot.domain.image_review_models import ImageCandidate, ImageReviewFlowState, ImageReviewItem
from englishbot.bootstrap import build_training_service
from englishbot.domain.models import TrainingMode
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import InMemoryAddWordsFlowRepository
from englishbot.infrastructure.sqlite_store import (
    SQLiteAddWordsFlowRepository,
    SQLiteContentStore,
    SQLiteImageReviewFlowRepository,
    SQLiteTelegramFlowMessageRepository,
)


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


class _StubImagePromptEnricher:
    def enrich(
        self,
        *,
        topic_title: str,  # noqa: ARG002
        vocabulary_items: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        return [
            {
                "id": item["id"],
                "english_word": item["english_word"],
                "image_prompt": f"Prompt for {item['english_word']}",
            }
            for item in vocabulary_items
        ]


class _StubImageCandidateGenerator:
    def generate_candidates(  # noqa: PLR0913
        self,
        *,
        topic_id: str,
        item_id: str,
        english_word: str,
        prompt: str,
        assets_dir: Path,
        model_names: tuple[str, ...],
    ) -> list:
        return [
            ImageCandidate(
                model_name=model_names[0],
                image_ref=f"assets/{topic_id}/{item_id}.png",
                output_path=assets_dir / topic_id / f"{item_id}.png",
                prompt=prompt,
            )
        ]


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


def test_save_approved_draft_can_use_database_checkpoint_without_writing_file(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    pipeline = LessonImportPipeline(
        extraction_client=_StubExtractionClient(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        image_prompt_enricher=_StubImagePromptEnricher(),  # type: ignore[arg-type]
    )
    harness = AddWordsFlowHarness(
        pipeline=pipeline,
        content_store=store,
    )
    repository = SQLiteAddWordsFlowRepository(store)
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    save_approved_draft = SaveApprovedAddWordsDraftUseCase(
        harness=harness,
        flow_repository=repository,
    )

    flow = start.execute(user_id=1, raw_text="Dragon — дракон")
    saved_flow = save_approved_draft.execute(user_id=1, flow_id=flow.flow_id)

    assert saved_flow.stage == "draft_saved"
    assert saved_flow.draft_output_path is None
    restored_store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    restored_repository = SQLiteAddWordsFlowRepository(restored_store)
    restored_flow = restored_repository.get_active_by_user(1)
    assert restored_flow is not None
    assert restored_flow.stage == "draft_saved"
    assert restored_flow.draft_output_path is None
    assert restored_flow.draft_result.draft.vocabulary_items[0].english_word == "Dragon"


def test_image_review_flow_is_restored_from_sqlite_after_restart(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    repository = SQLiteImageReviewFlowRepository(store)
    harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=_StubImageCandidateGenerator(),
        assets_dir=tmp_path / "assets",
        content_store=store,
        default_model_names=("dreamshaper",),
    )
    start = StartImageReviewUseCase(harness=harness, repository=repository)
    generate = GenerateImageReviewCandidatesUseCase(harness=harness, repository=repository)
    draft = LessonExtractionDraft(
        topic_title="Fairy Tales",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                item_id="dragon",
                english_word="Dragon",
                translation="дракон",
                source_fragment="Dragon — дракон",
                image_prompt="Prompt for Dragon",
            )
        ],
    )

    flow = start.execute(user_id=7, draft=draft, model_names=("dreamshaper",))
    updated = generate.execute(user_id=7, flow_id=flow.flow_id)

    restored_store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    restored_repository = SQLiteImageReviewFlowRepository(restored_store)
    restored_flow = restored_repository.get_active_by_user(7)

    assert restored_flow is not None
    assert restored_flow.flow_id == updated.flow_id
    assert restored_flow.current_item is not None
    assert len(restored_flow.current_item.candidates) == 1


def test_image_review_flow_persists_pixabay_search_state(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    repository = SQLiteImageReviewFlowRepository(store)
    flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=7,
        content_pack={"topic": {"id": "fairy-tales", "title": "Fairy Tales"}},
        items=[
            ImageReviewItem(
                item_id="dragon",
                english_word="Dragon",
                translation="дракон",
                prompt="Prompt for Dragon",
                search_query="Dragon",
                search_page=2,
                candidate_source_type="pixabay",
                approved_source_type=None,
                needs_review=True,
                skipped=False,
                candidates=[
                    ImageCandidate(
                        model_name="pixabay",
                        image_ref="assets/fairy-tales/review/dragon--pixabay-1.jpg",
                        output_path=tmp_path / "assets" / "fairy-tales" / "review" / "dragon--pixabay-1.jpg",
                        prompt="Prompt for Dragon",
                        source_type="pixabay",
                        source_id="1",
                        preview_url="https://cdn.example/1.jpg",
                        full_image_url="https://cdn.example/full-1.jpg",
                        source_page_url="https://pixabay.example/1",
                        width=640,
                        height=480,
                    )
                ],
            )
        ],
    )

    repository.save(flow)
    restored_flow = repository.get_active_by_user(7)

    assert restored_flow is not None
    assert restored_flow.current_item is not None
    assert restored_flow.current_item.search_query == "Dragon"
    assert restored_flow.current_item.search_page == 2
    assert restored_flow.current_item.candidate_source_type == "pixabay"
    assert restored_flow.current_item.candidates[0].source_id == "1"
    assert restored_flow.current_item.candidates[0].preview_url == "https://cdn.example/1.jpg"
    assert (
        restored_flow.current_item.candidates[0].image_ref
        == "assets/fairy-tales/review/dragon--pixabay-1.jpg"
    )


def test_image_review_flow_restores_null_search_query_as_none(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    repository = SQLiteImageReviewFlowRepository(store)
    flow = ImageReviewFlowState(
        flow_id="review-null",
        editor_user_id=7,
        content_pack={"topic": {"id": "fairy-tales", "title": "Fairy Tales"}},
        items=[
            ImageReviewItem(
                item_id="scissors",
                english_word="Scissors",
                translation="ножницы",
                prompt="Prompt for Scissors",
                search_query=None,
                search_page=1,
                candidate_source_type=None,
                approved_source_type=None,
                needs_review=True,
                skipped=False,
                candidates=[],
            )
        ],
    )

    repository.save(flow)
    restored_flow = repository.get_active_by_user(7)

    assert restored_flow is not None
    assert restored_flow.current_item is not None
    assert restored_flow.current_item.search_query is None
    assert restored_flow.current_item.candidate_source_type is None
    assert restored_flow.current_item.approved_source_type is None


def test_sqlite_telegram_flow_message_repository_tracks_and_clears_by_tag(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    repository = SQLiteTelegramFlowMessageRepository(store)

    repository.track(flow_id="flow123", chat_id=1, message_id=10, tag="image_review_step")
    repository.track(flow_id="flow123", chat_id=1, message_id=11, tag="image_review_step")
    repository.track(flow_id="flow123", chat_id=1, message_id=12, tag="other")

    tracked_step = repository.list(flow_id="flow123", tag="image_review_step")
    assert [(item.chat_id, item.message_id) for item in tracked_step] == [(1, 10), (1, 11)]

    repository.remove(flow_id="flow123", chat_id=1, message_id=10)
    tracked_after_remove = repository.list(flow_id="flow123", tag="image_review_step")
    assert [(item.chat_id, item.message_id) for item in tracked_after_remove] == [(1, 11)]

    repository.clear(flow_id="flow123", tag="image_review_step")
    assert repository.list(flow_id="flow123", tag="image_review_step") == []
    assert [(item.chat_id, item.message_id) for item in repository.list(flow_id="flow123")] == [(1, 12)]
