from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from englishbot.bot import (
    words_catalog_callback_handler,
    words_catalog_document_handler,
    words_catalog_export_callback_handler,
    words_catalog_image_saver_callback_handler,
    words_catalog_import_callback_handler,
    words_catalog_photo_handler,
)
from englishbot.telegram.interaction import (
    is_catalog_image_saver_interaction,
    is_catalog_workbook_import_interaction,
)


class _RecordingQuery:
    def __init__(self) -> None:
        self.answered = False
        self.edits: list[tuple[str, object]] = []
        self.message = _RecordingMessage()

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup=None) -> None:
        self.edits.append((text, reply_markup))


class _RecordingMessage:
    def __init__(self) -> None:
        self.chat_id = 77
        self.message_id = 88
        self.documents: list[dict[str, object]] = []
        self.replies: list[str] = []
        self.status_messages: list[_EditableStatusMessage] = []
        self.document = None
        self.photo = None

    async def reply_document(self, *, document, filename: str, caption: str):
        payload = document.read()
        self.documents.append(
            {
                "filename": filename,
                "caption": caption,
                "size": len(payload),
            }
        )
        return SimpleNamespace(message_id=501)

    async def reply_text(self, text: str):
        self.replies.append(text)
        status = _EditableStatusMessage(text=text)
        self.status_messages.append(status)
        return status


class _EditableStatusMessage:
    def __init__(self, *, text: str) -> None:
        self.text = text
        self.edits: list[str] = []

    async def edit_text(self, text: str) -> None:
        self.text = text
        self.edits.append(text)


class _FakeTelegramFile:
    def __init__(self) -> None:
        self.downloaded_to: str | None = None

    async def download_to_drive(self, *, custom_path: str) -> None:
        self.downloaded_to = custom_path
        Path(custom_path).write_bytes(b"workbook")


class _FakeDocument:
    def __init__(self, *, file_name: str = "catalog.xlsx", mime_type: str = "") -> None:
        self.file_name = file_name
        self.mime_type = mime_type
        self._file = _FakeTelegramFile()

    async def get_file(self):
        return self._file


class _FakePhoto:
    def __init__(self) -> None:
        self._file = _FakeTelegramFile()

    async def get_file(self):
        return self._file


class _RecordingBot:
    def __init__(self) -> None:
        self.edits: list[dict[str, object]] = []

    async def edit_message_text(self, *, chat_id: int, message_id: int, text: str, reply_markup):
        self.edits.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )


@pytest.mark.anyio
async def test_words_catalog_callback_handler_opens_admin_menu() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=7))
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"admin_user_ids": {7}}),
        user_data={},
    )

    await words_catalog_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True
    assert query.edits[-1][0] == "Workbook import/export"
    keyboard = query.edits[-1][1]
    assert keyboard.inline_keyboard[0][0].callback_data == "words:catalog:export"


@pytest.mark.anyio
async def test_words_catalog_export_callback_handler_sends_workbook_document(tmp_path: Path) -> None:
    query = _RecordingQuery()
    export_calls: list[Path] = []
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=7))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "admin_user_ids": {7},
                "export_media_catalog_use_case": SimpleNamespace(
                    execute=lambda *, output_path: (export_calls.append(output_path), output_path.write_bytes(b"xlsx"))
                ),
            }
        ),
        user_data={},
    )

    await words_catalog_export_callback_handler(update, context)  # type: ignore[arg-type]

    assert export_calls
    assert query.message.documents[0]["filename"] == "englishbot-catalog.xlsx"
    assert query.edits[-1][0] == "Workbook import/export"


@pytest.mark.anyio
async def test_words_catalog_import_callback_handler_starts_document_wait_state() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=7))
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"admin_user_ids": {7}}),
        user_data={},
    )

    await words_catalog_import_callback_handler(update, context)  # type: ignore[arg-type]

    assert is_catalog_workbook_import_interaction(context) is True
    assert query.edits[-1][0].startswith("Send the edited .xlsx workbook")


@pytest.mark.anyio
async def test_words_catalog_image_saver_callback_handler_starts_media_wait_state() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=7))
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"admin_user_ids": {7}}),
        user_data={},
    )

    await words_catalog_image_saver_callback_handler(update, context)  # type: ignore[arg-type]

    assert is_catalog_image_saver_interaction(context) is True
    assert query.edits[-1][0].startswith("Send a photo or an image file")


@pytest.mark.anyio
async def test_words_catalog_document_handler_imports_uploaded_workbook() -> None:
    message = _RecordingMessage()
    message.document = _FakeDocument()
    update = SimpleNamespace(effective_message=message, effective_user=SimpleNamespace(id=7))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "admin_user_ids": {7},
                "import_media_catalog_use_case": SimpleNamespace(
                    execute=lambda *, input_path: SimpleNamespace(updated_count=5, topic_count=2)
                ),
            }
        ),
        user_data={
            "words_flow_mode": "awaiting_catalog_workbook_document",
            "expected_user_input_state": {"chat_id": 77, "message_id": 88},
        },
        bot=_RecordingBot(),
    )

    await words_catalog_document_handler(update, context)  # type: ignore[arg-type]

    assert is_catalog_workbook_import_interaction(context) is False
    assert message.replies[0] == "Importing workbook..."
    assert context.bot.edits[-1]["text"] == "Workbook import/export"


@pytest.mark.anyio
async def test_words_catalog_photo_handler_saves_uploaded_image_and_returns_link() -> None:
    message = _RecordingMessage()
    message.photo = [_FakePhoto()]
    update = SimpleNamespace(effective_message=message, effective_user=SimpleNamespace(id=7))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "admin_user_ids": {7},
                "save_catalog_uploaded_image_use_case": SimpleNamespace(
                    execute=lambda **kwargs: SimpleNamespace(
                        public_url="https://admin.example.com/public-assets/file?path=uploads/test.png&sig=123"
                    )
                ),
            }
        ),
        user_data={
            "words_flow_mode": "awaiting_catalog_image_saver_media",
            "expected_user_input_state": {"chat_id": 77, "message_id": 88},
        },
        bot=_RecordingBot(),
    )

    await words_catalog_photo_handler(update, context)  # type: ignore[arg-type]

    assert is_catalog_image_saver_interaction(context) is True
    assert message.replies[0] == "Saving image..."
    assert "https://admin.example.com/public-assets/file" in message.status_messages[0].text
    assert context.bot.edits[-1]["text"].startswith("Send a photo or an image file")


@pytest.mark.anyio
async def test_words_catalog_document_handler_saves_uploaded_image_document_and_returns_link() -> None:
    message = _RecordingMessage()
    message.document = _FakeDocument(file_name="dragon.png", mime_type="image/png")
    update = SimpleNamespace(effective_message=message, effective_user=SimpleNamespace(id=7))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "admin_user_ids": {7},
                "save_catalog_uploaded_image_use_case": SimpleNamespace(
                    execute=lambda **kwargs: SimpleNamespace(
                        public_url="https://admin.example.com/public-assets/file?path=uploads/dragon.png&sig=abc"
                    )
                ),
            }
        ),
        user_data={
            "words_flow_mode": "awaiting_catalog_image_saver_media",
            "expected_user_input_state": {"chat_id": 77, "message_id": 88},
        },
        bot=_RecordingBot(),
    )

    await words_catalog_document_handler(update, context)  # type: ignore[arg-type]

    assert "https://admin.example.com/public-assets/file" in message.status_messages[0].text
