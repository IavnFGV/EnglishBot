from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from englishbot.telegram.interaction import (
    TelegramExpectedInputPrompt,
    chat_menu_interaction_id,
    clear_expected_user_input,
    edit_expected_user_input_prompt,
    finish_interaction,
    get_expected_user_input_prompt,
    lesson_interaction_id,
    published_word_edit_interaction_id,
    remember_expected_user_input,
    replace_flow_message,
    tts_voice_interaction_id,
)


def test_remember_and_get_expected_user_input_prompt() -> None:
    context = SimpleNamespace(user_data={})

    remember_expected_user_input(context, chat_id=101, message_id=202)

    assert get_expected_user_input_prompt(context) == TelegramExpectedInputPrompt(
        chat_id=101,
        message_id=202,
    )


def test_named_interaction_ids_are_stable() -> None:
    assert lesson_interaction_id(session_id="lesson-1") == "lesson-1"
    assert chat_menu_interaction_id(user_id=7) == "chat-menu:7"
    assert published_word_edit_interaction_id(user_id=7) == "published-word-edit:7"
    assert tts_voice_interaction_id(user_id=7) == "tts-voice:7"


def test_clear_expected_user_input_prompt() -> None:
    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 1, "message_id": 2}}
    )

    clear_expected_user_input(context)

    assert get_expected_user_input_prompt(context) is None


def test_edit_expected_user_input_prompt_returns_false_without_prompt() -> None:
    context = SimpleNamespace(user_data={}, bot=SimpleNamespace())

    edited = asyncio.run(
        edit_expected_user_input_prompt(
            context,
            text="hello",
            reply_markup=None,
        )
    )

    assert edited is False


def test_edit_expected_user_input_prompt_edits_stored_prompt() -> None:
    calls: list[dict[str, object]] = []

    async def fake_edit_message_text(**kwargs):
        calls.append(kwargs)

    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 11, "message_id": 22}},
        bot=SimpleNamespace(edit_message_text=fake_edit_message_text),
    )

    edited = asyncio.run(
        edit_expected_user_input_prompt(
            context,
            text="updated",
            reply_markup="markup",
        )
    )

    assert edited is True
    assert calls == [
        {
            "chat_id": 11,
            "message_id": 22,
            "text": "updated",
            "reply_markup": "markup",
        }
    ]


def test_edit_expected_user_input_prompt_treats_not_modified_as_success() -> None:
    async def fake_edit_message_text(**kwargs):  # noqa: ARG001
        raise BadRequest("Message is not modified")

    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 11, "message_id": 22}},
        bot=SimpleNamespace(edit_message_text=fake_edit_message_text),
    )

    edited = asyncio.run(
        edit_expected_user_input_prompt(
            context,
            text="updated",
            reply_markup=None,
        )
    )

    assert edited is True


class _FakeTracked:
    def __init__(self, *, flow_id: str, chat_id: int, message_id: int, tag: str) -> None:
        self.flow_id = flow_id
        self.chat_id = chat_id
        self.message_id = message_id
        self.tag = tag


class _FakeRegistry:
    def __init__(self) -> None:
        self.items: list[_FakeTracked] = []

    def list(self, *, flow_id: str, tag: str):
        return [item for item in self.items if item.flow_id == flow_id and item.tag == tag]

    def track(self, *, flow_id: str, chat_id: int, message_id: int, tag: str) -> None:
        self.items.append(
            _FakeTracked(flow_id=flow_id, chat_id=chat_id, message_id=message_id, tag=tag)
        )

    def remove(self, *, flow_id: str, chat_id: int, message_id: int) -> None:
        self.items = [
            item
            for item in self.items
            if not (
                item.flow_id == flow_id
                and item.chat_id == chat_id
                and item.message_id == message_id
            )
        ]


@pytest.mark.anyio
async def test_replace_flow_message_replaces_previous_tracked_message() -> None:
    registry = _FakeRegistry()
    registry.track(flow_id="lesson-1", chat_id=10, message_id=20, tag="question")
    deleted: list[tuple[int, int]] = []

    async def fake_delete_message(*, chat_id: int, message_id: int) -> None:
        deleted.append((chat_id, message_id))

    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=SimpleNamespace(delete_message=fake_delete_message),
    )
    message = SimpleNamespace(chat_id=10, message_id=30)

    await replace_flow_message(
        context,
        flow_id="lesson-1",
        tag="question",
        message=message,
        fallback_chat_id=10,
    )

    assert deleted == [(10, 20)]
    tracked = registry.list(flow_id="lesson-1", tag="question")
    assert [(item.chat_id, item.message_id) for item in tracked] == [(10, 30)]


@pytest.mark.anyio
async def test_finish_interaction_clears_tags_and_prompt_state() -> None:
    registry = _FakeRegistry()
    registry.track(flow_id="lesson-1", chat_id=10, message_id=20, tag="question")
    registry.track(flow_id="lesson-1", chat_id=10, message_id=21, tag="feedback")
    deleted: list[tuple[int, int]] = []

    async def fake_delete_message(*, chat_id: int, message_id: int) -> None:
        deleted.append((chat_id, message_id))

    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 10, "message_id": 99}},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=SimpleNamespace(delete_message=fake_delete_message),
    )

    await finish_interaction(
        context,
        flow_id="lesson-1",
        tags=("question", "feedback"),
        clear_expected_input_prompt=True,
    )

    assert deleted == [(10, 20), (10, 21)]
    assert registry.list(flow_id="lesson-1", tag="question") == []
    assert registry.list(flow_id="lesson-1", tag="feedback") == []
    assert get_expected_user_input_prompt(context) is None
