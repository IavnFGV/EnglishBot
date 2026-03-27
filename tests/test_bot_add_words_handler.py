from types import SimpleNamespace

import pytest

from englishbot.bot import add_words_regenerate_draft_handler, add_words_text_handler
from englishbot.domain.add_words_models import AddWordsFlowState
from englishbot.importing.models import (
    DraftExtractionMetadata,
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


class _FakeCallbackMessage:
    async def reply_text(self, text: str, reply_markup=None):  # noqa: ARG002
        return SimpleNamespace(text=text, message_id=1)


class _FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = _FakeCallbackMessage()
        self.edits: list[str] = []
        self.answered = False

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup=None) -> None:  # noqa: ARG002
        self.edits.append(text)


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
        draft = LessonExtractionDraft(
            topic_title="Fairy Tales",
            lesson_title=None,
            vocabulary_items=[
                ExtractedVocabularyItemDraft(
                    item_id="fairy-tales-dragon",
                    english_word="Dragon",
                    translation="дракон",
                    source_fragment="Dragon — дракон",
                )
            ],
            warnings=[
                "Smart parsing timed out. I will try a simpler template-based parse.",
                "Here is the partial result. Please review and complete the missing parts manually.",
            ],
            unparsed_lines=["непонятная строка"],
        )
        return AddWordsFlowState(
            flow_id="flow-timeout",
            editor_user_id=user_id,
            raw_text=raw_text,
            draft_result=ImportLessonResult(
                draft=draft,
                validation=ValidationResult(errors=[]),
                extraction_metadata=DraftExtractionMetadata(
                    parse_path="fallback",
                    smart_parse_status="timeout",
                    status_messages=[
                        "Smart parsing timed out. I will try a simpler template-based parse.",
                        "Here is the partial result. Please review and complete the missing parts manually.",
                    ],
                    fallback_is_partial=True,
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
async def test_add_words_text_handler_reports_ollama_timeout_and_shows_fallback_preview() -> None:
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
    assert len(message.replies) == 2
    assert message.replies[0].edits[-1] == (
        "Parsing draft... done\n"
        "Smart parsing timed out. I will try a simpler template-based parse.\n"
        "Here is the partial result. Please review and complete the missing parts manually.\n"
        "Items found: 1\n"
        "Validation errors: 0"
    )
    assert "Warnings: 2" in message.replies[1].text
    assert "Unparsed lines: 1" in message.replies[1].text


@pytest.mark.anyio
async def test_add_words_regenerate_draft_handler_reports_unavailable_when_button_is_stale() -> None:
    query = _FakeQuery("words:regenerate_draft:flow-1")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    flow = _FakeSuccessfulStartUseCase().execute(user_id=123, raw_text="Fairy Tales")
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {123},
                "add_words_get_active_use_case": SimpleNamespace(execute=lambda *, user_id: flow),
                "smart_parsing_available": False,
            }
        ),
    )

    await add_words_regenerate_draft_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True
    assert query.edits == ["Smart parsing is currently unavailable right now."]
