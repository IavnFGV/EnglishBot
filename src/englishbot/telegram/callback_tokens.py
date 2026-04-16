from __future__ import annotations

CALLBACK_TOKEN_TTL_SECONDS = 48 * 60 * 60
HARD_SKIP_CALLBACK_ACTION = "hard_skip"
EDITABLE_WORD_CALLBACK_ACTION = "editable_word"
PUBLISHED_IMAGE_ITEM_CALLBACK_ACTION = "published_image_item"


def create_callback_token(
    *,
    store,
    user_id: int,
    action: str,
    payload: dict[str, object],
    ttl_seconds: int = CALLBACK_TOKEN_TTL_SECONDS,
) -> str:
    creator = getattr(store, "create_telegram_callback_token", None)
    if creator is None:
        raise RuntimeError("Telegram callback token creation is not available.")
    return str(
        creator(
            user_id=user_id,
            action=action,
            payload=payload,
            ttl_seconds=ttl_seconds,
        )
    )


def consume_callback_token(
    *,
    store,
    user_id: int,
    action: str,
    token: str,
) -> dict[str, object] | None:
    consumer = getattr(store, "consume_telegram_callback_token", None)
    if consumer is None:
        return None
    return consumer(user_id=user_id, action=action, token=token)


def hard_skip_callback_data(
    *,
    store,
    user_id: int,
    session_id: str,
) -> str:
    token = create_callback_token(
        store=store,
        user_id=user_id,
        action=HARD_SKIP_CALLBACK_ACTION,
        payload={"session_id": session_id},
    )
    return f"hard:skip:{token}"


def editable_word_callback_data(
    *,
    store,
    user_id: int,
    topic_id: str,
    item_index: int,
) -> str:
    token = create_callback_token(
        store=store,
        user_id=user_id,
        action=EDITABLE_WORD_CALLBACK_ACTION,
        payload={"topic_id": topic_id, "item_index": item_index},
    )
    return f"words:edit_item:{token}"


def published_image_item_callback_data(
    *,
    store,
    user_id: int,
    topic_id: str,
    item_index: int,
) -> str:
    token = create_callback_token(
        store=store,
        user_id=user_id,
        action=PUBLISHED_IMAGE_ITEM_CALLBACK_ACTION,
        payload={"topic_id": topic_id, "item_index": item_index},
    )
    return f"words:edit_published_image:{token}"
