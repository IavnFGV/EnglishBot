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
    render_assignment_progress_image,
)
from englishbot.domain.models import GoalPeriod, GoalType, TrainingMode
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
        word_id="april",
        mode=TrainingMode.EASY,
        is_correct=True,
        current_level=1,
    )
    store.update_homework_word_progress(
        user_id=5,
        word_id="august",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=2,
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
    values = {item.word_id: item.progress_value for item in snapshot.segments}
    assert values["april"] == pytest.approx(0.33)
    assert values["august"] == pytest.approx(1.0)


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
    HomeworkProgressUseCase(store=store).create_goal(
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
    assert message.photo_calls[0][1] == "<b>📘 Homework</b>\n✅ Done: 0/2 words • 🎯 Left: 2 • 🔁 About 0 rounds"

    store.update_homework_word_progress(
        user_id=7,
        word_id="april",
        mode=TrainingMode.MEDIUM,
        is_correct=True,
        current_level=2,
    )

    await bot._send_or_update_assignment_progress_message(
        context,  # type: ignore[arg-type]
        message=message,
        user=user,
        kind=AssignmentSessionKind.HOMEWORK,
    )

    assert len(fake_bot.media_edits) == 1
    assert fake_bot.media_edits[0][2] == "<b>📘 Homework</b>\n✅ Done: 1/2 words • 🎯 Left: 1 • 🔁 About 0 rounds"


@pytest.mark.anyio
async def test_send_or_update_assignment_progress_message_falls_back_to_send_photo_when_reply_is_gone(
    tmp_path: Path,
) -> None:
    store = _build_store(tmp_path)
    HomeworkProgressUseCase(store=store).create_goal(
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
        (1, "<b>📘 Homework</b>\n✅ Done: 0/2 words • 🎯 Left: 2 • 🔁 About 0 rounds")
    ]
    tracked = registry.list(flow_id="assignment-progress:8:homework", tag="assignment_progress")
    assert len(tracked) == 1
    assert tracked[0].message_id == 999
