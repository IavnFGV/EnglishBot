from types import SimpleNamespace

import pytest

from englishbot.bot import add_words_text_handler
from englishbot.domain.add_words_models import AddWordsFlowState
from englishbot.importing.models import (
    ExtractedVocabularyItemDraft,
    ImportLessonResult,
    LessonExtractionDraft,
    ValidationError,
    ValidationResult,
)


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


class _FakeSuccessfulStartUseCase:
    def execute(self, *, user_id: int, raw_text: str):  # noqa: ARG002
        draft = LessonExtractionDraft(
            topic_title="Fairy Tales",
            lesson_title=None,
            vocabulary_items=[
                ExtractedVocabularyItemDraft(
                    item_id="fairy-tales-dragon",
                    english_word="Dragon",
                    translation="дракон",
                    source_fragment="Dragon — дракон",
                    image_prompt="Prompt for Dragon",
                )
            ],
        )
        return AddWordsFlowState(
            flow_id="flow-1",
            editor_user_id=user_id,
            raw_text=raw_text,
            draft_result=ImportLessonResult(
                draft=draft,
                validation=ValidationResult(errors=[]),
            ),
        )


class _FakeTimeoutStartUseCase:
    def execute(self, *, user_id: int, raw_text: str):  # noqa: ARG002
        return AddWordsFlowState(
            flow_id="flow-timeout",
            editor_user_id=user_id,
            raw_text=raw_text,
            draft_result=ImportLessonResult(
                draft={"error": "HTTPConnectionPool(host='127.0.0.1', port=11434): Read timed out. (read timeout=180)"},  # type: ignore[arg-type]
                validation=ValidationResult(
                    errors=[
                        ValidationError(
                            code="malformed_result",
                            message="Extraction client returned an invalid draft structure.",
                        )
                    ]
                ),
            ),
        )


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


@pytest.mark.anyio
async def test_add_words_text_handler_sends_only_one_draft_preview_after_success() -> None:
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
                "add_words_start_use_case": _FakeSuccessfulStartUseCase(),
                "word_import_preview_message_ids": {},
            }
        ),
        bot=SimpleNamespace(),
    )

    await add_words_text_handler(update, context)  # type: ignore[arg-type]

    assert context.user_data.get("words_flow_mode") is None
    assert len(message.replies) == 2
    assert message.replies[0].edits[-1].startswith("Parsing draft... done")
    assert message.replies[1].text.startswith("Draft preview\nTopic: Fairy Tales")


@pytest.mark.anyio
async def test_add_words_text_handler_reports_ollama_timeout_without_preview() -> None:
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
                "add_words_start_use_case": _FakeTimeoutStartUseCase(),
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
        "Ollama timed out while parsing this text. "
        "Try a shorter text, a faster model, or increase OLLAMA_TIMEOUT_SEC."
    )
