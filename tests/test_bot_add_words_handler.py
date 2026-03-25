from types import SimpleNamespace

import pytest

from englishbot.bot import add_words_text_handler


class _FakeSentMessage:
    def __init__(self, text: str, *, message_id: int = 1) -> None:
        self.text = text
        self.message_id = message_id
        self.edits: list[str] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:  # noqa: ARG002
        self.edits.append(text)
        self.text = text


class _FakeIncomingMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.chat_id = 1
        self.replies: list[_FakeSentMessage] = []

    async def reply_text(self, text: str, reply_markup=None) -> _FakeSentMessage:  # noqa: ARG002
        sent = _FakeSentMessage(text=text, message_id=len(self.replies) + 1)
        self.replies.append(sent)
        return sent


class _FakeStartUseCase:
    def execute(self, *, user_id: int, raw_text: str):  # noqa: ARG002
        raise RuntimeError("broken extraction")


@pytest.mark.anyio
async def test_add_words_text_handler_reports_failure_to_user() -> None:
    message = _FakeIncomingMessage("Fairy Tales\n\nDragon — дракон")
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        user_data={"words_flow_mode": "awaiting_raw_text"},
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {123},
                "add_words_start_use_case": _FakeStartUseCase(),
                "word_import_preview_message_ids": {},
            }
        ),
        bot=SimpleNamespace(),
    )

    await add_words_text_handler(update, context)  # type: ignore[arg-type]

    assert context.user_data.get("words_flow_mode") is None
    assert len(message.replies) == 1
    assert message.replies[0].edits[-1] == (
        "Parsing draft... failed\n"
        "Could not parse this text. Please try again or simplify the input."
    )
