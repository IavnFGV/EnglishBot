from __future__ import annotations

from types import SimpleNamespace

from englishbot.telegram.callback_tokens import (
    CALLBACK_TOKEN_TTL_SECONDS,
    EDITABLE_WORD_CALLBACK_ACTION,
    HARD_SKIP_CALLBACK_ACTION,
    PUBLISHED_IMAGE_ITEM_CALLBACK_ACTION,
    consume_callback_token,
    create_callback_token,
    editable_word_callback_data,
    hard_skip_callback_data,
    published_image_item_callback_data,
)


def test_create_callback_token_uses_fallback_when_store_has_no_creator() -> None:
    assert (
        create_callback_token(
            store=SimpleNamespace(),
            user_id=7,
            action="some-action",
            payload={"id": "x"},
            fallback_value="fallback",
        )
        == "fallback"
    )


def test_create_callback_token_uses_store_creator_with_default_ttl() -> None:
    calls: list[dict[str, object]] = []

    def create_telegram_callback_token(**kwargs):
        calls.append(kwargs)
        return "token-123"

    token = create_callback_token(
        store=SimpleNamespace(create_telegram_callback_token=create_telegram_callback_token),
        user_id=7,
        action="some-action",
        payload={"id": "x"},
        fallback_value="fallback",
    )

    assert token == "token-123"
    assert calls == [
        {
            "user_id": 7,
            "action": "some-action",
            "payload": {"id": "x"},
            "ttl_seconds": CALLBACK_TOKEN_TTL_SECONDS,
        }
    ]


def test_consume_callback_token_uses_plain_fallback_without_store_consumer() -> None:
    assert consume_callback_token(
        store=SimpleNamespace(),
        user_id=7,
        action="some-action",
        token="plain-token",
        fallback_key="value",
    ) == {"value": "plain-token"}


def test_consume_callback_token_rejects_colon_fallback_by_default() -> None:
    assert (
        consume_callback_token(
            store=SimpleNamespace(consume_telegram_callback_token=lambda **kwargs: None),
            user_id=7,
            action="some-action",
            token="topic:3",
            fallback_key="value",
        )
        is None
    )


def test_consume_callback_token_allows_colon_fallback_when_requested() -> None:
    assert consume_callback_token(
        store=SimpleNamespace(consume_telegram_callback_token=lambda **kwargs: None),
        user_id=7,
        action="some-action",
        token="topic:3",
        fallback_key="value",
        allow_colon_fallback=True,
    ) == {"value": "topic:3"}


def test_consume_callback_token_returns_resolved_payload() -> None:
    assert consume_callback_token(
        store=SimpleNamespace(
            consume_telegram_callback_token=lambda **kwargs: {"topic_id": "weather", "item_index": 2}
        ),
        user_id=7,
        action="some-action",
        token="abc",
        fallback_key="value",
    ) == {"topic_id": "weather", "item_index": 2}


def test_hard_skip_callback_data_uses_named_action() -> None:
    calls: list[dict[str, object]] = []

    def create_telegram_callback_token(**kwargs):
        calls.append(kwargs)
        return "token-1"

    data = hard_skip_callback_data(
        store=SimpleNamespace(create_telegram_callback_token=create_telegram_callback_token),
        user_id=7,
        session_id="session-1",
    )

    assert data == "hard:skip:token-1"
    assert calls[0]["action"] == HARD_SKIP_CALLBACK_ACTION
    assert calls[0]["payload"] == {"session_id": "session-1"}


def test_editable_word_callback_data_uses_named_action() -> None:
    calls: list[dict[str, object]] = []

    def create_telegram_callback_token(**kwargs):
        calls.append(kwargs)
        return "token-2"

    data = editable_word_callback_data(
        store=SimpleNamespace(create_telegram_callback_token=create_telegram_callback_token),
        user_id=7,
        topic_id="weather",
        item_index=3,
    )

    assert data == "words:edit_item:token-2"
    assert calls[0]["action"] == EDITABLE_WORD_CALLBACK_ACTION
    assert calls[0]["payload"] == {"topic_id": "weather", "item_index": 3}


def test_published_image_item_callback_data_uses_named_action() -> None:
    calls: list[dict[str, object]] = []

    def create_telegram_callback_token(**kwargs):
        calls.append(kwargs)
        return "token-3"

    data = published_image_item_callback_data(
        store=SimpleNamespace(create_telegram_callback_token=create_telegram_callback_token),
        user_id=7,
        topic_id="weather",
        item_index=4,
    )

    assert data == "words:edit_published_image:token-3"
    assert calls[0]["action"] == PUBLISHED_IMAGE_ITEM_CALLBACK_ACTION
    assert calls[0]["payload"] == {"topic_id": "weather", "item_index": 4}
