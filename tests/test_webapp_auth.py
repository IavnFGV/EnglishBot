from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlencode

from englishbot.webapp_auth import build_dev_session, session_from_init_data, verify_init_data


def test_verify_init_data_accepts_valid_telegram_signature() -> None:
    init_data = _build_signed_init_data(
        bot_token="test-token",
        user={
            "id": 7,
            "username": "alice",
            "first_name": "Alice",
            "last_name": "Admin",
        },
    )

    assert verify_init_data(init_data, bot_token="test-token") is True


def test_session_from_init_data_returns_user_roles_for_verified_user() -> None:
    init_data = _build_signed_init_data(
        bot_token="test-token",
        user={
            "id": 7,
            "username": "alice",
            "first_name": "Alice",
            "last_name": "Admin",
        },
    )

    session = session_from_init_data(
        init_data,
        bot_token="test-token",
        roles_by_user={7: ("admin", "editor")},
    )

    assert session is not None
    assert session.telegram_id == 7
    assert session.roles == ("admin", "editor", "user")
    assert session.is_admin is True
    assert session.is_verified is True


def test_build_dev_session_marks_local_debug_session() -> None:
    session = build_dev_session(
        telegram_id=9,
        roles_by_user={9: ("editor",)},
        profile_by_user={9: {"username": "editor", "first_name": "Edit", "last_name": "User"}},
    )

    assert session.telegram_id == 9
    assert session.roles == ("editor", "user")
    assert session.is_admin is False
    assert session.is_verified is False
    assert session.is_dev_mode is True


def _build_signed_init_data(*, bot_token: str, user: dict[str, object]) -> str:
    payload = {
        "auth_date": "1710000000",
        "query_id": "AAEAAAE",
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    payload["hash"] = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(payload)
