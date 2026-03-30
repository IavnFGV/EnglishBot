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
from englishbot.domain.image_review_models import (
    ImageCandidate,
    ImageCandidateBatch,
    ImageReviewFlowState,
    ImageReviewItem,
)
from englishbot.bootstrap import build_training_service
from englishbot.domain.models import GoalPeriod, GoalType, TrainingMode
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
    SQLitePendingTelegramNotificationRepository,
    SQLiteTelegramFlowMessageRepository,
    SQLiteTelegramUserLoginRepository,
    SQLiteTelegramUserRoleRepository,
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
    ) -> ImageCandidateBatch:
        return ImageCandidateBatch(
            candidates=[
                ImageCandidate(
                    model_name=model_names[0],
                    image_ref=f"assets/{topic_id}/{item_id}.png",
                    output_path=assets_dir / topic_id / f"{item_id}.png",
                    prompt=prompt,
                )
            ]
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


def test_sqlite_telegram_user_logins_store_last_seen_username(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    repository = SQLiteTelegramUserLoginRepository(store)

    repository.record(user_id=7, username="first_name", first_name="Alice", last_name="Admin")
    first_snapshot = repository.list()
    repository.record(user_id=7, username="renamed_user", first_name="Alice", last_name="Owner")
    second_snapshot = repository.list()

    assert len(second_snapshot) == 1
    assert second_snapshot[0].user_id == 7
    assert second_snapshot[0].username == "renamed_user"
    assert second_snapshot[0].first_name == "Alice"
    assert second_snapshot[0].last_name == "Owner"
    assert second_snapshot[0].first_seen_at == first_snapshot[0].first_seen_at
    assert second_snapshot[0].last_seen_at >= first_snapshot[0].last_seen_at


def test_sqlite_telegram_user_roles_are_persisted_and_grouped(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    repository = SQLiteTelegramUserRoleRepository(store)

    repository.grant(user_id=7, role="admin")
    repository.grant(user_id=8, role="editor")
    repository.grant(user_id=7, role="admin")

    assignments = repository.list_assignments()
    memberships = repository.list_memberships()

    assert [(item.user_id, item.role) for item in assignments] == [(7, "admin"), (8, "editor")]
    assert memberships == {
        "user": frozenset(),
        "admin": frozenset({7}),
        "editor": frozenset({8}),
    }


def test_sqlite_telegram_user_roles_can_be_replaced_and_listed_for_admin_webapp(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    login_repository = SQLiteTelegramUserLoginRepository(store)
    role_repository = SQLiteTelegramUserRoleRepository(store)

    login_repository.record(
        user_id=7,
        username="alice",
        first_name="Alice",
        last_name="Admin",
    )
    role_repository.grant(user_id=7, role="admin")
    role_repository.replace(user_id=7, roles=("editor", "user"))

    users = role_repository.list_users()

    assert role_repository.list_roles_for_user(user_id=7) == ("editor",)
    assert len(users) == 1
    assert users[0].telegram_id == 7
    assert users[0].first_name == "Alice"
    assert users[0].last_name == "Admin"
    assert users[0].roles == ("editor", "user")


def test_sqlite_pending_telegram_notification_repository_persists_notifications(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    repository = SQLitePendingTelegramNotificationRepository(store)

    repository.save(
        notification_key="n1",
        recipient_user_id=77,
        text="Hello",
        not_before_at=__import__("datetime").datetime(2026, 3, 30, tzinfo=__import__("datetime").UTC),
    )

    stored = repository.get(notification_key="n1")
    items = repository.list(recipient_user_id=77)

    assert stored is not None
    assert stored.key == "n1"
    assert stored.recipient_user_id == 77
    assert stored.text == "Hello"
    assert len(items) == 1
    repository.remove(notification_key="n1")
    assert repository.get(notification_key="n1") is None


def test_sqlite_content_store_reuses_lexeme_across_multiple_learning_items(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")

    store.upsert_content_pack(
        {
            "topic": {"id": "classroom", "title": "Classroom"},
            "lessons": [{"id": "classroom-1", "title": "Lesson 1"}],
            "vocabulary_items": [
                {
                    "id": "board-surface",
                    "english_word": "Board",
                    "translation": "доска",
                    "meaning_hint": "classroom surface",
                    "lesson_id": "classroom-1",
                },
                {
                    "id": "board-members",
                    "english_word": "Board",
                    "translation": "совет",
                    "meaning_hint": "group of directors",
                    "lesson_id": "classroom-1",
                },
            ],
        }
    )

    lexemes = store.list_lexemes()
    items = store.list_all_vocabulary()

    assert len(lexemes) == 1
    assert lexemes[0].normalized_headword == "board"
    assert {item.id for item in items} == {"board-surface", "board-members"}
    assert {item.lexeme_id for item in items} == {lexemes[0].id}
    assert {item.translation for item in items} == {"доска", "совет"}
    assert {item.meaning_hint for item in items} == {"classroom surface", "group of directors"}


def test_sqlite_content_store_splits_slash_synonyms_into_separate_learning_items(
    tmp_path: Path,
) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")

    store.upsert_content_pack(
        {
            "topic": {"id": "school-things", "title": "School Things"},
            "lessons": [],
            "vocabulary_items": [
                {
                    "id": "eraser-rubber",
                    "english_word": "Eraser / Rubber",
                    "translation": "ластик",
                }
            ],
        }
    )

    items = store.list_all_vocabulary()
    lexemes = store.list_lexemes()
    content_pack = store.get_content_pack("school-things")

    assert [(item.id, item.english_word, item.translation) for item in items] == [
        ("eraser-rubber-eraser", "Eraser", "ластик"),
        ("eraser-rubber-rubber", "Rubber", "ластик"),
    ]
    assert {lexeme.normalized_headword for lexeme in lexemes} == {"eraser", "rubber"}
    assert [item["english_word"] for item in content_pack["vocabulary_items"]] == [
        "Eraser",
        "Rubber",
    ]


def test_same_learning_item_can_belong_to_multiple_topics_and_lessons(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")

    shared_item = {
        "id": "board-surface",
        "english_word": "Board",
        "translation": "доска",
        "meaning_hint": "classroom surface",
        "image_ref": "assets/shared/board.png",
    }
    store.upsert_content_pack(
        {
            "topic": {"id": "classroom", "title": "Classroom"},
            "lessons": [{"id": "classroom-1", "title": "Lesson 1"}],
            "vocabulary_items": [{**shared_item, "lesson_id": "classroom-1"}],
        }
    )
    store.upsert_content_pack(
        {
            "topic": {"id": "geometry", "title": "Geometry"},
            "lessons": [{"id": "geometry-1", "title": "Lesson 1"}],
            "vocabulary_items": [{**shared_item, "lesson_id": "geometry-1"}],
        }
    )

    assert [item.id for item in store.list_vocabulary_by_topic("classroom")] == ["board-surface"]
    assert [item.id for item in store.list_vocabulary_by_topic("geometry")] == ["board-surface"]
    assert store.list_topic_ids_for_item("board-surface") == ["classroom", "geometry"]
    assert store.list_lesson_ids_for_item("board-surface") == ["classroom-1", "geometry-1"]


def test_sqlite_content_store_tracks_game_stars_and_daily_streak(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")

    first_streak = store.update_game_streak(user_id=7, played_at=datetime(2026, 3, 20, tzinfo=UTC))
    second_streak = store.update_game_streak(user_id=7, played_at=datetime(2026, 3, 21, tzinfo=UTC))
    same_day_streak = store.update_game_streak(user_id=7, played_at=datetime(2026, 3, 21, 12, tzinfo=UTC))
    reset_streak = store.update_game_streak(user_id=7, played_at=datetime(2026, 3, 24, tzinfo=UTC))

    total = store.add_game_stars(user_id=7, stars=10)
    total = store.add_game_stars(user_id=7, stars=40)

    assert first_streak == 1
    assert second_streak == 2
    assert same_day_streak == 2
    assert reset_streak == 1
    assert total == 50


def test_sqlite_content_store_lists_users_goal_overview(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "animals", "title": "Animals"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "cat", "english_word": "Cat", "translation": "кот"},
            ],
        }
    )
    store.assign_goal(
        user_id=101,
        goal_period=GoalPeriod.WEEKLY,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
        target_word_ids=["cat"],
    )

    overview = store.list_users_goal_overview()

    assert len(overview) == 1
    assert overview[0]["user_id"] == 101
    assert overview[0]["active_goals_count"] == 1


def test_initialize_drops_legacy_vocabulary_items_table_after_learning_items_exists(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "data" / "englishbot.db"
    store = SQLiteContentStore(db_path=db_path)
    store.initialize()

    import sqlite3

    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE vocabulary_items (id TEXT PRIMARY KEY)")

    store.initialize()

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "learning_items" in tables
    assert "vocabulary_items" not in tables


def test_sqlite_store_configures_wal_and_busy_timeout_for_multi_process_access(
    tmp_path: Path,
) -> None:
    import sqlite3

    db_path = tmp_path / "data" / "englishbot.db"
    store = SQLiteContentStore(db_path=db_path)

    store.initialize()

    with sqlite3.connect(db_path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]

    assert str(journal_mode).lower() == "wal"
    assert int(busy_timeout) == 5000


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


def test_content_pack_round_trip_preserves_item_level_pixabay_search_query(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")

    topic_id = store.upsert_content_pack(
        {
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "lessons": [],
            "vocabulary_items": [
                {
                    "id": "dragon",
                    "english_word": "Dragon",
                    "translation": "дракон",
                    "image_prompt": "dragon toy, cartoon style, simple, centered, white background",
                    "pixabay_search_query": "dragon scissors clipart",
                }
            ],
        }
    )

    restored = store.get_content_pack(topic_id)

    assert restored["vocabulary_items"][0]["image_prompt"] == (
        "dragon toy, cartoon style, simple, centered, white background"
    )
    assert restored["vocabulary_items"][0]["pixabay_search_query"] == "dragon scissors clipart"


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


def test_sqlite_content_store_word_stats_weekly_points_and_homework_goals(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from englishbot.domain.models import GoalPeriod, GoalType, TrainingMode, WordStats

    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "animals", "title": "Animals"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "cat", "english_word": "Cat", "translation": "кот"},
                {"id": "dog", "english_word": "Dog", "translation": "собака"},
            ],
        }
    )

    stats = WordStats(user_id=1, word_id="cat", success_easy=2, current_level=1)
    store.save_word_stats(stats)
    loaded = store.get_word_stats(1, "cat")
    assert loaded is not None
    assert loaded.current_level == 1
    assert loaded.review_interval_days == 0

    score_after_first = store.award_weekly_points(
        user_id=1,
        word_id="cat",
        mode=TrainingMode.MEDIUM,
        level_up_delta=1,
        awarded_at=datetime(2026, 3, 24, tzinfo=UTC),
    )
    score_after_repeat = store.award_weekly_points(
        user_id=1,
        word_id="cat",
        mode=TrainingMode.HARD,
        level_up_delta=0,
        awarded_at=datetime(2026, 3, 25, tzinfo=UTC),
    )
    assert score_after_first == 16
    assert score_after_repeat == 18

    store.assign_goal(
        user_id=1,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        required_level=2,
        target_word_ids=["cat"],
    )
    assert store.required_homework_level(user_id=1, item_id="cat") == 2
    assert store.list_active_homework_words(user_id=1) == {"cat": 2}


def test_sqlite_store_homework_stage_progression_and_autoskip(tmp_path: Path) -> None:
    from englishbot.domain.models import GoalPeriod, GoalType

    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "animals", "title": "Animals"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "cat", "english_word": "Cat", "translation": "кот"},
                {"id": "dog", "english_word": "Dog", "translation": "собака"},
            ],
        }
    )
    store.assign_goal(
        user_id=5,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        required_level=2,
        target_word_ids=["cat", "dog"],
    )
    assert store.get_homework_stage_mode(user_id=5, item_id="cat") is TrainingMode.EASY
    store.update_homework_word_progress(
        user_id=5,
        word_id="cat",
        mode=TrainingMode.EASY,
        is_correct=True,
        current_level=0,
    )
    store.update_homework_word_progress(
        user_id=5,
        word_id="cat",
        mode=TrainingMode.EASY,
        is_correct=True,
        current_level=0,
    )
    assert store.get_homework_stage_mode(user_id=5, item_id="cat") is TrainingMode.MEDIUM
    store.update_homework_word_progress(
        user_id=5,
        word_id="cat",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=2,
    )
    assert store.get_homework_stage_mode(user_id=5, item_id="cat") is TrainingMode.HARD
    store.update_homework_word_progress(
        user_id=5,
        word_id="cat",
        mode=TrainingMode.HARD,
        is_correct=False,
        current_level=2,
    )
    store.update_homework_word_progress(
        user_id=5,
        word_id="cat",
        mode=TrainingMode.HARD,
        is_correct=False,
        current_level=2,
    )
    assert store.get_homework_stage_mode(user_id=5, item_id="cat") is TrainingMode.MEDIUM


def test_sqlite_store_tracks_recent_session_words(tmp_path: Path) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "animals", "title": "Animals"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "cat", "english_word": "Cat", "translation": "кот"},
                {"id": "dog", "english_word": "Dog", "translation": "собака"},
                {"id": "sun", "english_word": "Sun", "translation": "солнце"},
            ],
        }
    )

    from englishbot.domain.models import SessionItem, TrainingMode, TrainingSession

    store.save_session(
        TrainingSession(
            id="s1",
            user_id=1,
            topic_id="animals",
            mode=TrainingMode.EASY,
            items=[SessionItem(order=0, vocabulary_item_id="cat")],
        )
    )
    store.save_session(
        TrainingSession(
            id="s2",
            user_id=1,
            topic_id="animals",
            mode=TrainingMode.EASY,
            items=[SessionItem(order=0, vocabulary_item_id="dog")],
        )
    )
    store.save_session(
        TrainingSession(
            id="s3",
            user_id=1,
            topic_id="animals",
            mode=TrainingMode.EASY,
            items=[SessionItem(order=0, vocabulary_item_id="sun")],
        )
    )

    assert store.list_recent_session_words(user_id=1, limit_sessions=2) == {"dog", "sun"}


def test_sqlite_store_lists_goals_and_user_metrics(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from englishbot.domain.models import GoalPeriod, GoalStatus, GoalType, TrainingMode

    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "animals", "title": "Animals"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "cat", "english_word": "Cat", "translation": "кот"},
            ],
        }
    )
    goal = store.assign_goal(
        user_id=1,
        goal_period=GoalPeriod.DAILY,
        goal_type=GoalType.NEW_WORDS,
        target_count=1,
        target_word_ids=["cat"],
    )
    store.award_weekly_points(
        user_id=1,
        word_id="cat",
        mode=TrainingMode.EASY,
        level_up_delta=0,
        awarded_at=datetime(2026, 3, 24, tzinfo=UTC),
    )
    store.update_game_streak(user_id=1, played_at=datetime(2026, 3, 24, tzinfo=UTC))

    goals = store.list_user_goals(user_id=1, statuses=(GoalStatus.ACTIVE,))
    profile = store.get_game_profile(user_id=1)
    weekly_points = store.get_weekly_points(user_id=1, now=datetime(2026, 3, 24, tzinfo=UTC))

    assert goals[0].id == goal.id
    assert profile.current_streak_days == 1
    assert weekly_points == 10
