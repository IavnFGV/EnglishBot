from pathlib import Path
from types import SimpleNamespace

import pytest

from englishbot.application.published_content_use_cases import (
    ListEditableTopicsUseCase,
    ListEditableWordsUseCase,
    UpdateEditableWordUseCase,
)
from englishbot.bot import (
    add_words_text_handler,
    words_edit_cancel_callback_handler,
    words_edit_item_callback_handler,
    words_edit_topic_callback_handler,
    words_edit_words_callback_handler,
)
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


class _RecordingQuery:
    def __init__(self, data: str | None = None) -> None:
        self.data = data or ""
        self.answered = False
        self.edits: list[tuple[str, object]] = []
        self.message = _FakeIncomingMessage("")

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup=None) -> None:
        self.edits.append((text, reply_markup))


class _FakeIncomingMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.chat_id = 1
        self.message_id = 999
        self.replies: list[tuple[str, object]] = []

    async def reply_text(self, text: str, reply_markup=None):
        self.replies.append((text, reply_markup))
        return SimpleNamespace(message_id=len(self.replies), text=text, edits=[], chat_id=self.chat_id)


class _FakeTelegramFlowMessageRepository:
    def __init__(self) -> None:
        self.messages: list[SimpleNamespace] = []

    def track(self, *, flow_id: str, chat_id: int, message_id: int, tag: str) -> None:
        self.messages = [
            item
            for item in self.messages
            if not (
                item.flow_id == flow_id
                and item.chat_id == chat_id
                and item.message_id == message_id
            )
        ]
        self.messages.append(
            SimpleNamespace(flow_id=flow_id, chat_id=chat_id, message_id=message_id, tag=tag)
        )

    def list(self, *, flow_id: str, tag: str | None = None):
        return [
            item
            for item in self.messages
            if item.flow_id == flow_id and (tag is None or item.tag == tag)
        ]

    def remove(self, *, flow_id: str, chat_id: int, message_id: int) -> None:
        self.messages = [
            item
            for item in self.messages
            if not (
                item.flow_id == flow_id
                and item.chat_id == chat_id
                and item.message_id == message_id
            )
        ]

    def clear(self, *, flow_id: str, tag: str | None = None) -> None:
        self.messages = [
            item
            for item in self.messages
            if not (item.flow_id == flow_id and (tag is None or item.tag == tag))
        ]


class _FakeBot:
    def __init__(self) -> None:
        self.deleted_messages: list[tuple[int, int]] = []

    async def delete_message(self, *, chat_id: int, message_id: int) -> None:
        self.deleted_messages.append((chat_id, message_id))


@pytest.mark.anyio
async def test_editor_can_edit_published_word_from_words_menu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    (content_dir / "school-subjects.json").write_text(
        '{\n'
        '  "topic": {"id": "school-subjects", "title": "School Subjects"},\n'
        '  "lessons": [],\n'
        '  "vocabulary_items": [\n'
        '    {"id": "school-subjects-maths", "english_word": "Mathematics", '
        '"translation": "математика", '
        '"image_ref": "assets/school-subjects/school-subjects-maths.png"},\n'
        '    {"id": "school-subjects-science", "english_word": "Science", '
        '"translation": "естественные науки"}\n'
        "  ]\n"
        "}\n",
        encoding="utf-8",
    )
    rebuilt_services: list[str] = []
    monkeypatch.setattr(
        "englishbot.bot.build_training_service",
        lambda db_path=None: rebuilt_services.append(str(db_path)) or "training-service",
    )
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "data" / "englishbot.db"
    store = SQLiteContentStore(db_path=db_path)
    store.import_json_directories([content_dir], replace=True)

    context = SimpleNamespace(
        user_data={},
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {42},
                "content_store": store,
                "list_editable_topics_use_case": ListEditableTopicsUseCase(db_path=db_path),
                "list_editable_words_use_case": ListEditableWordsUseCase(db_path=db_path),
                "update_editable_word_use_case": UpdateEditableWordUseCase(db_path=db_path),
                "training_service": "before",
                "telegram_flow_message_repository": _FakeTelegramFlowMessageRepository(),
            }
        ),
    )

    menu_query = _RecordingQuery("words:edit_words")
    menu_update = SimpleNamespace(callback_query=menu_query, effective_user=SimpleNamespace(id=42))
    await words_edit_words_callback_handler(menu_update, context)  # type: ignore[arg-type]

    assert menu_query.answered is True
    assert menu_query.edits[-1][0] == "Choose a topic to edit words."

    topic_query = _RecordingQuery("words:edit_topic:school-subjects")
    topic_update = SimpleNamespace(
        callback_query=topic_query,
        effective_user=SimpleNamespace(id=42),
    )
    await words_edit_topic_callback_handler(topic_update, context)  # type: ignore[arg-type]

    assert topic_query.edits[-1][0] == "Choose a word to edit."
    assert topic_query.edits[-1][1].inline_keyboard[0][0].text == "* Mathematics — математика"
    assert topic_query.edits[-1][1].inline_keyboard[1][0].text == "Science — естественные науки"

    item_query = _RecordingQuery("words:edit_item:school-subjects:0")
    item_update = SimpleNamespace(
        callback_query=item_query,
        effective_user=SimpleNamespace(id=42),
    )
    await words_edit_item_callback_handler(item_update, context)  # type: ignore[arg-type]

    assert context.user_data["words_flow_mode"] == "awaiting_published_word_edit_text"
    assert context.user_data["published_edit_topic_id"] == "school-subjects"
    assert context.user_data["published_edit_item_id"] == "school-subjects-maths"
    assert item_query.edits[-1][0] == (
        "Send the updated word as one line.\nFormat: English: Translation"
    )
    assert item_query.edits[-1][1] is not None
    assert item_query.message.replies[-1][0] == "Current value:\nMathematics: математика"

    message = _FakeIncomingMessage("Maths: математика / матан")
    message.message_id = 555
    text_update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=42),
    )
    await add_words_text_handler(text_update, context)  # type: ignore[arg-type]

    assert context.user_data.get("words_flow_mode") is None
    assert rebuilt_services == [str(db_path)]
    assert context.application.bot_data["training_service"] == "training-service"
    assert message.replies[0][0] == (
        "Word updated.\n"
        "Maths — математика / матан\n"
        "Changes are now available in training."
    )
    assert message.replies[1][0] == "Choose another word to edit."
    assert message.replies[1][1] is not None
    assert context.bot.deleted_messages == [(1, 999), (1, 1), (1, 555)]
    saved = store.get_content_pack("school-subjects")
    assert saved["vocabulary_items"][0]["english_word"] == "Maths"
    assert saved["vocabulary_items"][0]["translation"] == "математика / матан"


@pytest.mark.anyio
async def test_editor_can_cancel_published_word_edit_and_return_to_word_list(
    tmp_path: Path,
) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    (content_dir / "school-subjects.json").write_text(
        '{\n'
        '  "topic": {"id": "school-subjects", "title": "School Subjects"},\n'
        '  "lessons": [],\n'
        '  "vocabulary_items": [\n'
        '    {"id": "school-subjects-maths", "english_word": "Mathematics", '
        '"translation": "математика"}\n'
        "  ]\n"
        "}\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "data" / "englishbot.db"
    store = SQLiteContentStore(db_path=db_path)
    store.import_json_directories([content_dir], replace=True)
    context = SimpleNamespace(
        user_data={
            "words_flow_mode": "awaiting_published_word_edit_text",
            "published_edit_topic_id": "school-subjects",
            "published_edit_item_id": "school-subjects-maths",
        },
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {42},
                "content_store": store,
                "list_editable_words_use_case": ListEditableWordsUseCase(db_path=db_path),
                "telegram_flow_message_repository": _FakeTelegramFlowMessageRepository(),
            }
        ),
    )
    context.application.bot_data["telegram_flow_message_repository"].track(
        flow_id="published-word-edit:42",
        chat_id=1,
        message_id=999,
        tag="published_word_edit",
    )
    context.application.bot_data["telegram_flow_message_repository"].track(
        flow_id="published-word-edit:42",
        chat_id=1,
        message_id=1,
        tag="published_word_edit",
    )
    cancel_query = _RecordingQuery("words:edit_item_cancel:school-subjects")
    cancel_update = SimpleNamespace(
        callback_query=cancel_query,
        effective_user=SimpleNamespace(id=42),
    )

    await words_edit_cancel_callback_handler(cancel_update, context)  # type: ignore[arg-type]

    assert cancel_query.answered is True
    assert cancel_query.edits[-1][0] == "Edit cancelled. Choose a word to edit."
    assert cancel_query.edits[-1][1] is not None
    assert context.bot.deleted_messages == [(1, 1)]
    assert context.user_data.get("words_flow_mode") is None
    assert context.user_data.get("published_edit_topic_id") is None
    assert context.user_data.get("published_edit_item_id") is None
