from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from englishbot.bot import add_words_text_handler
from englishbot.domain.add_words_models import AddWordsFlowState
from englishbot.importing.models import (
    ExtractedVocabularyItemDraft,
    ImportLessonResult,
    LessonExtractionDraft,
    ValidationResult,
)


class _FakeIncomingMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.chat_id = 1
        self.replies: list[SimpleNamespace] = []

    async def reply_text(self, text: str, reply_markup=None):
        sent = SimpleNamespace(
            text=text,
            reply_markup=reply_markup,
            message_id=len(self.replies) + 1,
        )
        self.replies.append(sent)
        return sent


class _FakeApplyEditUseCase:
    def __init__(self, flow: AddWordsFlowState) -> None:
        self._flow = flow

    def execute(self, *, user_id: int, flow_id: str, edited_text: str):  # noqa: ARG002
        assert flow_id == self._flow.flow_id
        return self._flow


class _FakeGetActiveUseCase:
    def __init__(self, flow: AddWordsFlowState) -> None:
        self._flow = flow

    def execute(self, *, user_id: int):  # noqa: ARG002
        return self._flow


class _FakeBot:
    async def edit_message_text(self, **kwargs):  # noqa: ANN003
        raise BadRequest("Message is not modified")


@pytest.mark.anyio
async def test_add_words_text_handler_ignores_message_not_modified_when_updating_preview() -> None:
    draft = LessonExtractionDraft(
        topic_title="Fairy Tales",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="Dragon",
                translation="дракон",
                source_fragment="Dragon — дракон",
                image_prompt="Prompt for Dragon",
            )
        ],
    )
    flow = AddWordsFlowState(
        flow_id="flow123",
        editor_user_id=123,
        raw_text="Topic: Fairy Tales\n\nDragon: дракон",
        draft_result=ImportLessonResult(
            draft=draft,
            validation=ValidationResult(errors=[]),
        ),
    )
    message = _FakeIncomingMessage("Topic: Fairy Tales\n\nDragon: дракон")
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        user_data={"words_flow_mode": "awaiting_edit_text", "edit_flow_id": "flow123"},
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {123},
                "add_words_get_active_use_case": _FakeGetActiveUseCase(flow),
                "add_words_apply_edit_use_case": _FakeApplyEditUseCase(flow),
                "word_import_preview_message_ids": {123: 77},
            }
        ),
        bot=_FakeBot(),
    )

    await add_words_text_handler(update, context)  # type: ignore[arg-type]

    assert context.user_data.get("words_flow_mode") is None
    assert context.user_data.get("edit_flow_id") is None
    assert "Draft updated from edited text." in message.replies[0].text
    assert "Draft preview" in message.replies[0].text
    assert "1. Dragon — дракон" in message.replies[0].text
    assert message.replies[0].reply_markup is not None
