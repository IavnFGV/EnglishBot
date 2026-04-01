from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from telegram.error import BadRequest

from englishbot import bot
from englishbot.application.homework_progress_use_cases import (
    AssignmentSessionKind,
    HomeworkProgressUseCase,
)
from englishbot.assignment_progress_image import (
    AssignmentProgressSegment,
    AssignmentProgressSnapshot,
    _segment_color,
    render_assignment_progress_image,
)
from englishbot.domain.models import GoalPeriod, GoalType, TrainingMode
from englishbot.domain.models import SessionItem, TrainingSession
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


def _build_store(tmp_path: Path) -> SQLiteContentStore:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.upsert_content_pack(
        {
            "topic": {"id": "months", "title": "Months"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "april", "english_word": "April", "translation": "апрель"},
                {"id": "august", "english_word": "August", "translation": "август"},
                {"id": "apricot", "english_word": "Apricot", "translation": "абрикос"},
            ],
        }
    )
    return store


def test_render_assignment_progress_image_writes_png(tmp_path: Path) -> None:
    snapshot = AssignmentProgressSnapshot(
        center_label="done",
        legend_labels=("start", "warm-up", "almost", "done"),
        hard_legend_label="hard clear",
        completed_word_count=1,
        total_word_count=3,
        remaining_word_count=2,
        estimated_round_count=1,
        segments=(
            AssignmentProgressSegment("a", "April", 0.0),
            AssignmentProgressSegment("b", "August", 0.66),
            AssignmentProgressSegment("c", "Apricot", 1.0),
        ),
    )

    output_path = render_assignment_progress_image(
        snapshot,
        output_path=tmp_path / "progress" / "homework.png",
    )

    assert output_path.exists()
    assert output_path.read_bytes().startswith(b"\x89PNG")
    with Image.open(output_path) as image:
        assert image.size == (512, 512)


def test_render_assignment_progress_image_draws_combo_streak_dots(tmp_path: Path) -> None:
    snapshot = AssignmentProgressSnapshot(
        center_label="done",
        legend_labels=("start", "warm-up", "almost", "done"),
        hard_legend_label="hard clear",
        completed_word_count=1,
        total_word_count=3,
        remaining_word_count=2,
        estimated_round_count=1,
        segments=(
            AssignmentProgressSegment("a", "April", 0.33),
            AssignmentProgressSegment("b", "August", 0.66),
            AssignmentProgressSegment("c", "Apricot", 1.0),
        ),
        combo_charge_streak=3,
        combo_hard_active=False,
    )

    output_path = render_assignment_progress_image(
        snapshot,
        output_path=tmp_path / "progress" / "combo-dots.png",
    )

    with Image.open(output_path) as image:
        sampled_pixels = [
            image.getpixel((x, y))
            for x in range(425, 475)
            for y in range(330, 470)
        ]

    assert any(green > 200 and red < 170 and blue < 190 for red, green, blue in sampled_pixels)


def test_render_assignment_progress_image_draws_dark_green_combo_dots_when_hard_active(tmp_path: Path) -> None:
    snapshot = AssignmentProgressSnapshot(
        center_label="done",
        legend_labels=("start", "warm-up", "almost", "done"),
        hard_legend_label="hard clear",
        completed_word_count=1,
        total_word_count=3,
        remaining_word_count=2,
        estimated_round_count=1,
        segments=(
            AssignmentProgressSegment("a", "April", 0.33),
            AssignmentProgressSegment("b", "August", 0.66),
            AssignmentProgressSegment("c", "Apricot", 1.0),
        ),
        combo_charge_streak=4,
        combo_hard_active=True,
    )

    output_path = render_assignment_progress_image(
        snapshot,
        output_path=tmp_path / "progress" / "combo-dots-hard.png",
    )

    with Image.open(output_path) as image:
        sampled_pixels = [
            image.getpixel((x, y))
            for x in range(425, 475)
            for y in range(330, 470)
        ]

    assert any(green > 100 and green < 160 and red < 40 and blue < 130 for red, green, blue in sampled_pixels)


def test_segment_color_uses_distinct_teal_for_completed_bonus_hard() -> None:
    assert _segment_color(
        AssignmentProgressSegment(
            "word",
            "Word",
            1.0,
            hard_clear=True,
        )
    ) == "#167a6c"


def test_segment_color_keeps_orange_for_almost_stage() -> None:
    assert _segment_color(
        AssignmentProgressSegment(
            "word",
            "Word",
            0.66,
        )
    ) == "#ffaf5f"


def test_build_assignment_progress_snapshot_uses_homework_word_progress(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=5,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        target_word_ids=["april", "august"],
    )
    assert goal.required_level == 2
    store.update_homework_word_progress(
        user_id=5,
        word_id="april",
        mode=TrainingMode.EASY,
        is_correct=True,
        current_level=1,
    )
    store.update_homework_word_progress(
        user_id=5,
        word_id="august",
        mode=TrainingMode.EASY,
        is_correct=True,
        current_level=0,
        goal_id=goal.id,
    )
    store.update_homework_word_progress(
        user_id=5,
        word_id="august",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )
    store.update_homework_word_progress(
        user_id=5,
        word_id="august",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )

    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "telegram_ui_language": "en",
            }
        )
    )

    snapshot = bot._build_assignment_progress_snapshot(
        context=context,  # type: ignore[arg-type]
        user_id=5,
        kind=AssignmentSessionKind.HOMEWORK,
        user=SimpleNamespace(id=5, language_code="en"),
    )

    assert snapshot is not None
    assert snapshot.total_word_count == 2
    assert snapshot.completed_word_count == 1
    assert snapshot.remaining_word_count == 1
    assert snapshot.estimated_round_count == 0
    assert snapshot.center_label == "done"
    assert snapshot.legend_labels == ("start", "warm-up", "almost", "done")
    assert snapshot.hard_legend_label == "hard clear"
    values = {item.word_id: item.progress_value for item in snapshot.segments}
    assert values["april"] == pytest.approx(0.33)
    assert values["august"] == pytest.approx(1.0)


def test_build_assignment_progress_snapshot_shows_almost_after_first_medium(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=16,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["april"],
    )
    store.update_homework_word_progress(
        user_id=16,
        word_id="april",
        mode=TrainingMode.EASY,
        is_correct=True,
        current_level=0,
        goal_id=goal.id,
    )
    store.update_homework_word_progress(
        user_id=16,
        word_id="april",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "telegram_ui_language": "en",
            }
        )
    )

    snapshot = bot._build_assignment_progress_snapshot(
        context=context,  # type: ignore[arg-type]
        user_id=16,
        kind=AssignmentSessionKind.HOMEWORK,
        user=SimpleNamespace(id=16, language_code="en"),
        goal_id=goal.id,
    )

    assert snapshot is not None
    assert snapshot.segments[0].progress_value == pytest.approx(0.66)


def test_build_assignment_progress_snapshot_marks_hard_clear_when_hard_is_mastered(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=12,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["august"],
    )
    store.update_homework_word_progress(
        user_id=12,
        word_id="august",
        mode=TrainingMode.EASY,
        is_correct=True,
        current_level=0,
        goal_id=goal.id,
    )
    store.update_homework_word_progress(
        user_id=12,
        word_id="august",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )
    store.update_homework_word_progress(
        user_id=12,
        word_id="august",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "telegram_ui_language": "en",
            }
        )
    )

    store.update_homework_word_progress(
        user_id=12,
        word_id="august",
        mode=TrainingMode.HARD,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )

    completed_snapshot = bot._build_assignment_progress_snapshot(
        context=context,  # type: ignore[arg-type]
        user_id=12,
        kind=AssignmentSessionKind.HOMEWORK,
        user=SimpleNamespace(id=12, language_code="en"),
        goal_id=goal.id,
    )

    assert completed_snapshot is not None
    assert completed_snapshot.segments[0].hard_clear is True


def test_build_assignment_progress_snapshot_includes_combo_arrow_state(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=18,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        target_word_ids=["april", "august"],
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "telegram_ui_language": "en",
            }
        )
    )
    active_session = TrainingSession(
        id="session-combo-image",
        user_id=18,
        topic_id="months",
        source_tag=f"assignment:homework:{goal.id}",
        mode=TrainingMode.MEDIUM,
        current_index=1,
        combo_correct_streak=4,
        combo_hard_active=True,
        items=[
            SessionItem(order=0, vocabulary_item_id="april", mode=TrainingMode.MEDIUM),
            SessionItem(order=1, vocabulary_item_id="august", mode=TrainingMode.MEDIUM),
        ],
    )

    snapshot = bot._build_assignment_progress_snapshot(
        context=context,  # type: ignore[arg-type]
        user_id=18,
        kind=AssignmentSessionKind.HOMEWORK,
        user=SimpleNamespace(id=18, language_code="en"),
        goal_id=goal.id,
        active_session=active_session,
    )

    assert snapshot is not None
    assert snapshot.combo_charge_streak == 4
    assert snapshot.combo_hard_active is True
    assert snapshot.combo_target_word_id == "august"


def test_build_assignment_progress_snapshot_uses_current_goal_when_goal_id_is_provided(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    use_case = HomeworkProgressUseCase(store=store)
    first_goal = use_case.create_goal(
        user_id=11,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        target_word_ids=["april", "august"],
    )
    store.update_homework_word_progress(
        user_id=11,
        word_id="april",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=2,
    )
    store.update_homework_word_progress(
        user_id=11,
        word_id="august",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=2,
    )
    second_goal = use_case.create_goal(
        user_id=11,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["apricot"],
    )

    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "telegram_ui_language": "en",
            }
        )
    )

    snapshot = bot._build_assignment_progress_snapshot(
        context=context,  # type: ignore[arg-type]
        user_id=11,
        kind=AssignmentSessionKind.HOMEWORK,
        user=SimpleNamespace(id=11, language_code="en"),
        goal_id=second_goal.id,
    )

    assert snapshot is not None
    assert snapshot.total_word_count == 1
    assert snapshot.completed_word_count == 0
    assert snapshot.remaining_word_count == 1
    assert [item.word_id for item in snapshot.segments] == ["apricot"]
    assert snapshot.segments[0].progress_value == pytest.approx(0.0)


class _FakeFlowRegistry:
    def __init__(self) -> None:
        self.items: list[SimpleNamespace] = []

    def track(self, *, flow_id: str, chat_id: int, message_id: int, tag: str) -> None:
        self.items = [
            item
            for item in self.items
            if not (item.flow_id == flow_id and item.chat_id == chat_id and item.message_id == message_id)
        ]
        self.items.append(SimpleNamespace(flow_id=flow_id, chat_id=chat_id, message_id=message_id, tag=tag))

    def list(self, *, flow_id: str, tag: str | None = None):
        return [
            item
            for item in self.items
            if item.flow_id == flow_id and (tag is None or item.tag == tag)
        ]

    def remove(self, *, flow_id: str, chat_id: int, message_id: int) -> None:
        self.items = [
            item
            for item in self.items
            if not (item.flow_id == flow_id and item.chat_id == chat_id and item.message_id == message_id)
        ]


class _FakePhotoMessage:
    def __init__(self) -> None:
        self.chat_id = 1
        self.message_id = 10
        self.photo_calls: list[tuple[str, str | None, str | None]] = []

    async def reply_photo(self, photo, caption=None, reply_markup=None, parse_mode=None):  # noqa: ARG002
        payload = photo.read()
        self.photo_calls.append((payload[:4].decode("latin1"), caption, parse_mode))
        self.message_id += 1
        return SimpleNamespace(message_id=self.message_id, chat_id=self.chat_id)


class _FakeBot:
    def __init__(self) -> None:
        self.media_edits: list[tuple[int, int, str | None]] = []
        self.deleted_messages: list[tuple[int, int]] = []
        self.sent_photos: list[tuple[int, str | None]] = []

    async def edit_message_media(self, *, chat_id: int, message_id: int, media) -> None:
        self.media_edits.append((chat_id, message_id, getattr(media, "caption", None)))

    async def delete_message(self, *, chat_id: int, message_id: int) -> None:
        self.deleted_messages.append((chat_id, message_id))

    async def send_photo(self, *, chat_id: int, photo, caption=None, parse_mode=None):  # noqa: ARG002
        _ = photo.read()
        self.sent_photos.append((chat_id, caption))
        return SimpleNamespace(message_id=999, chat_id=chat_id)


class _FailingReplyPhotoMessage(_FakePhotoMessage):
    async def reply_photo(self, photo, caption=None, reply_markup=None, parse_mode=None):  # noqa: ARG002
        _ = photo.read()
        raise BadRequest("Message to be replied not found")


@pytest.mark.anyio
async def test_send_or_update_assignment_progress_message_sends_then_updates(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=7,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        target_word_ids=["april", "august"],
    )
    registry = _FakeFlowRegistry()
    message = _FakePhotoMessage()
    fake_bot = _FakeBot()
    context = SimpleNamespace(
        bot=fake_bot,
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "training_service": SimpleNamespace(
                    get_active_session=lambda user_id: SimpleNamespace(  # noqa: ARG005
                        current_position=1,
                        total_items=2,
                        source_tag=f"assignment:homework:{goal.id}",
                    )
                ),
                "telegram_flow_message_repository": registry,
                "telegram_ui_language": "en",
            }
        ),
    )
    user = SimpleNamespace(id=7, language_code="en")

    await bot._send_or_update_assignment_progress_message(
        context,  # type: ignore[arg-type]
        message=message,
        user=user,
        kind=AssignmentSessionKind.HOMEWORK,
    )

    assert len(message.photo_calls) == 1
    assert message.photo_calls[0][0] == "\x89PNG"
    assert (
        message.photo_calls[0][1]
        == "<b>📘 Homework</b>\n✅ Done: 0/2 words • 🎯 Homework left: 2"
    )

    store.update_homework_word_progress(
        user_id=7,
        word_id="april",
        mode=TrainingMode.EASY,
        is_correct=True,
        current_level=0,
        goal_id=goal.id,
    )
    store.update_homework_word_progress(
        user_id=7,
        word_id="april",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )
    store.update_homework_word_progress(
        user_id=7,
        word_id="april",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=1,
        goal_id=goal.id,
    )

    await bot._send_or_update_assignment_progress_message(
        context,  # type: ignore[arg-type]
        message=message,
        user=user,
        kind=AssignmentSessionKind.HOMEWORK,
    )

    assert len(fake_bot.media_edits) == 1
    assert (
        fake_bot.media_edits[0][2]
        == "<b>📘 Homework</b>\n✅ Done: 1/2 words • 🎯 Homework left: 1"
    )


@pytest.mark.anyio
async def test_send_or_update_assignment_progress_message_falls_back_to_send_photo_when_reply_is_gone(
    tmp_path: Path,
) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=8,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        target_word_ids=["april", "august"],
    )
    registry = _FakeFlowRegistry()
    message = _FailingReplyPhotoMessage()
    fake_bot = _FakeBot()
    context = SimpleNamespace(
        bot=fake_bot,
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "training_service": SimpleNamespace(
                    get_active_session=lambda user_id: SimpleNamespace(  # noqa: ARG005
                        current_position=1,
                        total_items=2,
                        source_tag=f"assignment:homework:{goal.id}",
                    )
                ),
                "telegram_flow_message_repository": registry,
                "telegram_ui_language": "en",
            }
        ),
    )
    user = SimpleNamespace(id=8, language_code="en")

    await bot._send_or_update_assignment_progress_message(
        context,  # type: ignore[arg-type]
        message=message,
        user=user,
        kind=AssignmentSessionKind.HOMEWORK,
    )

    assert fake_bot.sent_photos == [
        (
            1,
            "<b>📘 Homework</b>\n✅ Done: 0/2 words • 🎯 Homework left: 2",
        )
    ]
    tracked = registry.list(flow_id=f"assignment-progress:8:homework:{goal.id}", tag="assignment_progress")
    assert len(tracked) == 1
    assert tracked[0].message_id == 999


@pytest.mark.anyio
async def test_send_or_update_assignment_progress_message_uses_current_goal_from_source_tag(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    first_goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=12,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        target_word_ids=["april", "august"],
    )
    second_goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=12,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["apricot"],
    )
    registry = _FakeFlowRegistry()
    message = _FakePhotoMessage()
    fake_bot = _FakeBot()
    context = SimpleNamespace(
        bot=fake_bot,
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "training_service": SimpleNamespace(
                    get_active_session=lambda user_id: SimpleNamespace(  # noqa: ARG005
                        current_position=1,
                        total_items=1,
                        source_tag=f"assignment:homework:{second_goal.id}",
                    )
                ),
                "telegram_flow_message_repository": registry,
                "telegram_ui_language": "en",
            }
        ),
    )
    user = SimpleNamespace(id=12, language_code="en")

    await bot._send_or_update_assignment_progress_message(
        context,  # type: ignore[arg-type]
        message=message,
        user=user,
        kind=AssignmentSessionKind.HOMEWORK,
    )

    assert len(message.photo_calls) == 1
    assert (
        message.photo_calls[0][1]
        == "<b>📘 Homework</b>\n✅ Done: 0/1 words • 🎯 Homework left: 1"
    )


@pytest.mark.anyio
async def test_send_or_update_assignment_progress_message_tracks_different_homeworks_separately(
    tmp_path: Path,
) -> None:
    store = _build_store(tmp_path)
    first_goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=13,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=2,
        target_word_ids=["april", "august"],
    )
    second_goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=13,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["apricot"],
    )
    registry = _FakeFlowRegistry()
    message = _FakePhotoMessage()
    fake_bot = _FakeBot()
    active_session = SimpleNamespace(
        current_position=0,
        total_items=1,
        source_tag=f"assignment:homework:{first_goal.id}",
    )
    context = SimpleNamespace(
        bot=fake_bot,
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "training_service": SimpleNamespace(
                    get_active_session=lambda user_id: active_session,  # noqa: ARG005
                ),
                "telegram_flow_message_repository": registry,
                "telegram_ui_language": "en",
            }
        ),
    )
    user = SimpleNamespace(id=13, language_code="en")

    await bot._send_or_update_assignment_progress_message(
        context,  # type: ignore[arg-type]
        message=message,
        user=user,
        kind=AssignmentSessionKind.HOMEWORK,
    )
    active_session.source_tag = f"assignment:homework:{second_goal.id}"
    await bot._send_or_update_assignment_progress_message(
        context,  # type: ignore[arg-type]
        message=message,
        user=user,
        kind=AssignmentSessionKind.HOMEWORK,
    )

    assert len(message.photo_calls) == 2
    assert registry.list(
        flow_id=f"assignment-progress:13:homework:{first_goal.id}",
        tag="assignment_progress",
    )
    assert registry.list(
        flow_id=f"assignment-progress:13:homework:{second_goal.id}",
        tag="assignment_progress",
    )


@pytest.mark.anyio
async def test_send_or_update_assignment_progress_message_keeps_same_flow_id_after_round_completion(
    tmp_path: Path,
) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=14,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["april"],
    )
    registry = _FakeFlowRegistry()
    message = _FakePhotoMessage()
    fake_bot = _FakeBot()
    active_session = SimpleNamespace(
        current_position=1,
        total_items=1,
        source_tag=f"assignment:homework:{goal.id}",
    )
    context = SimpleNamespace(
        bot=fake_bot,
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "training_service": SimpleNamespace(
                    get_active_session=lambda user_id: None,  # noqa: ARG005
                ),
                "telegram_flow_message_repository": registry,
                "telegram_ui_language": "en",
            }
        ),
    )
    user = SimpleNamespace(id=14, language_code="en")

    await bot._send_or_update_assignment_progress_message(
        context,  # type: ignore[arg-type]
        message=message,
        user=user,
        kind=AssignmentSessionKind.HOMEWORK,
        active_session=active_session,
    )

    assert len(message.photo_calls) == 1
    tracked = registry.list(
        flow_id=f"assignment-progress:14:homework:{goal.id}",
        tag="assignment_progress",
    )
    assert len(tracked) == 1


@pytest.mark.anyio
async def test_send_or_update_assignment_progress_message_updates_latest_tracked_image_and_cleans_older_duplicates(
    tmp_path: Path,
) -> None:
    store = _build_store(tmp_path)
    goal = HomeworkProgressUseCase(store=store).create_goal(
        user_id=15,
        goal_period=GoalPeriod.HOMEWORK,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK,
        target_count=1,
        target_word_ids=["april"],
    )
    registry = _FakeFlowRegistry()
    registry.track(
        flow_id=f"assignment-progress:15:homework:{goal.id}",
        chat_id=1,
        message_id=10,
        tag="assignment_progress",
    )
    registry.track(
        flow_id=f"assignment-progress:15:homework:{goal.id}",
        chat_id=1,
        message_id=11,
        tag="assignment_progress",
    )
    message = _FakePhotoMessage()
    fake_bot = _FakeBot()
    context = SimpleNamespace(
        bot=fake_bot,
        application=SimpleNamespace(
            bot_data={
                "content_store": store,
                "training_service": SimpleNamespace(
                    get_active_session=lambda user_id: SimpleNamespace(  # noqa: ARG005
                        current_position=1,
                        total_items=1,
                        source_tag=f"assignment:homework:{goal.id}",
                    )
                ),
                "telegram_flow_message_repository": registry,
                "telegram_ui_language": "en",
            }
        ),
    )
    user = SimpleNamespace(id=15, language_code="en")

    await bot._send_or_update_assignment_progress_message(
        context,  # type: ignore[arg-type]
        message=message,
        user=user,
        kind=AssignmentSessionKind.HOMEWORK,
    )

    assert fake_bot.media_edits == [
        (
            1,
            11,
            "<b>📘 Homework</b>\n✅ Done: 0/1 words • 🎯 Homework left: 1",
        )
    ]
    assert fake_bot.deleted_messages == [(1, 10)]
    tracked = registry.list(
        flow_id=f"assignment-progress:15:homework:{goal.id}",
        tag="assignment_progress",
    )
    assert [item.message_id for item in tracked] == [11]
