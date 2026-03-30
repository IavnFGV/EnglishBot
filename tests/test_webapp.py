from __future__ import annotations

import hashlib
import hmac
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

from englishbot.config import Settings
from englishbot.infrastructure.sqlite_store import (
    SQLiteContentStore,
    SQLiteTelegramUserLoginRepository,
    SQLiteTelegramUserRoleRepository,
)
from englishbot.webapp import create_web_app


def test_webapp_session_endpoint_allows_local_dev_admin(tmp_path: Path) -> None:
    _seed_user_store(
        tmp_path=tmp_path,
        logins=[
            SimpleNamespace(user_id=7, username="alice", first_name="Alice", last_name="Admin")
        ],
        roles=[(7, "admin")],
    )
    app = create_web_app(
        Settings(
            telegram_token="test-token",
            log_level="INFO",
            content_db_path=tmp_path / "data" / "englishbot.db",
            web_app_dev_user_ids=(7,),
        )
    )

    response = _request(app, "GET", "/api/session", headers={"X-Dev-User-Id": "7"})

    assert response.status_code == 200
    assert response.json["session"]["telegram_id"] == 7
    assert response.json["session"]["is_admin"] is True
    assert response.json["session"]["is_dev_mode"] is True


def test_webapp_users_endpoint_rejects_non_admin_user(tmp_path: Path) -> None:
    _seed_user_store(
        tmp_path=tmp_path,
        logins=[SimpleNamespace(user_id=8, username="bob", first_name="Bob", last_name="User")],
        roles=[(8, "editor")],
    )
    app = create_web_app(
        Settings(
            telegram_token="test-token",
            log_level="INFO",
            content_db_path=tmp_path / "data" / "englishbot.db",
        )
    )
    init_data = _signed_init_data(
        bot_token="test-token",
        user={"id": 8, "username": "bob", "first_name": "Bob", "last_name": "User"},
    )

    response = _request(app, "GET", "/api/users", headers={"X-Telegram-Init-Data": init_data})

    assert response.status_code == 403
    assert response.json["message"] == "Access denied. Admin role is required."


def test_webapp_users_endpoint_returns_users_for_admin_and_updates_roles(tmp_path: Path) -> None:
    _seed_user_store(
        tmp_path=tmp_path,
        logins=[
            SimpleNamespace(user_id=7, username="alice", first_name="Alice", last_name="Admin"),
            SimpleNamespace(user_id=8, username="bob", first_name="Bob", last_name="User"),
        ],
        roles=[(7, "admin"), (8, "editor")],
    )
    app = create_web_app(
        Settings(
            telegram_token="test-token",
            log_level="INFO",
            content_db_path=tmp_path / "data" / "englishbot.db",
        )
    )
    admin_init_data = _signed_init_data(
        bot_token="test-token",
        user={"id": 7, "username": "alice", "first_name": "Alice", "last_name": "Admin"},
    )

    list_response = _request(
        app,
        "GET",
        "/api/users",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    update_response = _request(
        app,
        "POST",
        "/api/users/8/roles",
        headers={"X-Telegram-Init-Data": admin_init_data},
        body={"roles": ["admin", "user"]},
    )

    assert list_response.status_code == 200
    assert [user["telegram_id"] for user in list_response.json["users"]] == [7, 8]
    assert update_response.status_code == 200
    assert update_response.json["user"]["roles"] == ["admin", "user"]

    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    role_repository = SQLiteTelegramUserRoleRepository(store)
    assert role_repository.list_roles_for_user(user_id=8) == ("admin",)


def _seed_user_store(
    *,
    tmp_path: Path,
    logins: list[SimpleNamespace],
    roles: list[tuple[int, str]],
) -> None:
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    login_repository = SQLiteTelegramUserLoginRepository(store)
    role_repository = SQLiteTelegramUserRoleRepository(store)
    for login in logins:
        login_repository.record(
            user_id=login.user_id,
            username=login.username,
            first_name=login.first_name,
            last_name=login.last_name,
        )
    for user_id, role in roles:
        role_repository.grant(user_id=user_id, role=role)


def _signed_init_data(*, bot_token: str, user: dict[str, object]) -> str:
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


def _request(
    app,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, object] | None = None,
) -> SimpleNamespace:
    encoded_body = b""
    if body is not None:
        encoded_body = json.dumps(body).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(encoded_body)),
        "wsgi.input": io.BytesIO(encoded_body),
        "REMOTE_ADDR": "127.0.0.1",
    }
    for key, value in (headers or {}).items():
        normalized = f"HTTP_{key.upper().replace('-', '_')}"
        environ[normalized] = value
    captured: dict[str, object] = {}

    def start_response(status, response_headers):  # noqa: ANN001
        captured["status"] = status
        captured["headers"] = response_headers

    chunks = app(environ, start_response)
    payload = b"".join(chunks).decode("utf-8")
    status_code = int(str(captured["status"]).split(" ", maxsplit=1)[0])
    return SimpleNamespace(
        status_code=status_code,
        body=payload,
        json=json.loads(payload),
    )
