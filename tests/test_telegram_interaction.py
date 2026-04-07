from __future__ import annotations

import asyncio
from types import SimpleNamespace

from telegram.error import BadRequest

from englishbot.telegram.interaction import (
    TelegramExpectedInputPrompt,
    clear_expected_user_input,
    edit_expected_user_input_prompt,
    get_expected_user_input_prompt,
    remember_expected_user_input,
)


def test_remember_and_get_expected_user_input_prompt() -> None:
    context = SimpleNamespace(user_data={})

    remember_expected_user_input(context, chat_id=101, message_id=202)

    assert get_expected_user_input_prompt(context) == TelegramExpectedInputPrompt(
        chat_id=101,
        message_id=202,
    )


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
