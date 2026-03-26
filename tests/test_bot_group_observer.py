from types import SimpleNamespace

import logging

import pytest

from englishbot.bot import (
    chat_member_logger_handler,
    group_text_observer_handler,
    raw_update_logger_handler,
)


@pytest.mark.anyio
async def test_group_text_observer_logs_received_group_message(caplog: pytest.LogCaptureFixture) -> None:
    update = SimpleNamespace(
        effective_message=SimpleNamespace(text="hello family"),
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=-1001, type="group"),
    )
    context = SimpleNamespace(user_data={})

    with caplog.at_level(logging.INFO):
        await group_text_observer_handler(update, context)  # type: ignore[arg-type]

    assert "Received group message chat_id=-1001 chat_type=group user_id=123 text='hello family'" in caplog.text


@pytest.mark.anyio
async def test_raw_update_logger_logs_message_update(caplog: pytest.LogCaptureFixture) -> None:
    update = SimpleNamespace(
        effective_message=SimpleNamespace(text="hello"),
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=-1001, type="group"),
        callback_query=None,
        my_chat_member=None,
        chat_member=None,
    )

    with caplog.at_level(logging.INFO):
        await raw_update_logger_handler(update, SimpleNamespace())  # type: ignore[arg-type]

    assert "Received Telegram update message chat_id=-1001 chat_type=group user_id=123 text='hello'" in caplog.text


@pytest.mark.anyio
async def test_chat_member_logger_logs_membership_update(caplog: pytest.LogCaptureFixture) -> None:
    update = SimpleNamespace(
        my_chat_member=SimpleNamespace(
            chat=SimpleNamespace(id=-1001, type="supergroup"),
            from_user=SimpleNamespace(id=123),
            old_chat_member=SimpleNamespace(status="left"),
            new_chat_member=SimpleNamespace(status="member"),
        ),
        chat_member=None,
    )

    with caplog.at_level(logging.INFO):
        await chat_member_logger_handler(update, SimpleNamespace())  # type: ignore[arg-type]

    assert (
        "Received chat member update chat_id=-1001 chat_type=supergroup user_id=123 "
        "old_status=left new_status=member"
    ) in caplog.text


@pytest.mark.anyio
async def test_group_text_observer_skips_when_user_has_active_flow(caplog: pytest.LogCaptureFixture) -> None:
    update = SimpleNamespace(
        effective_message=SimpleNamespace(text="hello"),
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=-1001, type="supergroup"),
    )
    context = SimpleNamespace(user_data={"words_flow_mode": "awaiting_raw_text"})

    with caplog.at_level(logging.INFO):
        await group_text_observer_handler(update, context)  # type: ignore[arg-type]

    assert "Received group message" not in caplog.text


@pytest.mark.anyio
async def test_group_text_observer_skips_when_waiting_for_training_answer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    update = SimpleNamespace(
        effective_message=SimpleNamespace(text="answer"),
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=-1001, type="group"),
    )
    context = SimpleNamespace(user_data={"awaiting_text_answer": True})

    with caplog.at_level(logging.INFO):
        await group_text_observer_handler(update, context)  # type: ignore[arg-type]

    assert "Received group message" not in caplog.text
