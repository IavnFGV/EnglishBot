from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from englishbot.bot import (
    words_add_words_callback_handler,
    words_menu_callback_handler,
    words_topics_callback_handler,
)


class _FakeQuery:
    def __init__(self) -> None:
        self.answered = False
        self.edits: list[tuple[str, object]] = []

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup=None) -> None:  # noqa: ARG002
        self.edits.append((text, reply_markup))
        raise BadRequest("Message is not modified")


@pytest.mark.anyio
async def test_words_menu_callback_handler_ignores_message_not_modified() -> None:
    query = _FakeQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {123},
            }
        )
    )

    await words_menu_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True


class _RecordingQuery:
    def __init__(self) -> None:
        self.answered = False
        self.edits: list[tuple[str, object]] = []

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup=None) -> None:  # noqa: ARG002
        self.edits.append((text, reply_markup))


@pytest.mark.anyio
async def test_words_topics_callback_handler_opens_topic_list() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={}),
    )
    context.application.bot_data["training_service"] = SimpleNamespace(
        list_topics=lambda: [
            SimpleNamespace(id="weather", title="Weather"),
            SimpleNamespace(id="school", title="School"),
        ]
    )

    await words_topics_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True
    assert query.edits[-1][0] == "Choose a topic to start training."
    assert query.edits[-1][1] is not None


@pytest.mark.anyio
async def test_words_add_words_callback_handler_enters_editor_flow() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={"editor_user_ids": {123}}),
    )

    await words_add_words_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True
    assert context.user_data["words_flow_mode"] == "awaiting_raw_text"
    assert query.edits[-1][0].startswith("Send the raw lesson text in one message.")
