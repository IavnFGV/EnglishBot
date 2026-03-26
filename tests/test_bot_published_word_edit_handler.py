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
    words_edit_item_callback_handler,
    words_edit_topic_callback_handler,
    words_edit_words_callback_handler,
)


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
        self.replies: list[tuple[str, object]] = []

    async def reply_text(self, text: str, reply_markup=None):
        self.replies.append((text, reply_markup))
        return SimpleNamespace(message_id=len(self.replies), text=text, edits=[])


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
        '"translation": "математика"},\n'
        '    {"id": "school-subjects-science", "english_word": "Science", '
        '"translation": "естественные науки"}\n'
        "  ]\n"
        "}\n",
        encoding="utf-8",
    )
    rebuilt_services: list[str] = []
    monkeypatch.setattr(
        "englishbot.bot.build_training_service",
        lambda: rebuilt_services.append("rebuilt") or "training-service",
    )
    monkeypatch.chdir(tmp_path)

    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {42},
                "list_editable_topics_use_case": ListEditableTopicsUseCase(content_dir=content_dir),
                "list_editable_words_use_case": ListEditableWordsUseCase(content_dir=content_dir),
                "update_editable_word_use_case": UpdateEditableWordUseCase(content_dir=content_dir),
                "training_service": "before",
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
    assert item_query.message.replies[-1][0] == "Current value:\nMathematics: математика"

    message = _FakeIncomingMessage("Maths: математика / матан")
    text_update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=42),
    )
    await add_words_text_handler(text_update, context)  # type: ignore[arg-type]

    assert context.user_data.get("words_flow_mode") is None
    assert rebuilt_services == ["rebuilt"]
    assert context.application.bot_data["training_service"] == "training-service"
    assert message.replies[0][0] == (
        "Word updated.\n"
        "Maths — математика / матан\n"
        "Changes are now available in training."
    )
    assert message.replies[1][0] == "Quick actions:"
    saved = (content_dir / "school-subjects.json").read_text(encoding="utf-8")
    assert '"english_word": "Maths"' in saved
    assert '"translation": "математика / матан"' in saved
