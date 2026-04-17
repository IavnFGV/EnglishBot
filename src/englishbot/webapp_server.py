from __future__ import annotations

import json
import logging
import mimetypes
from collections.abc import Callable
from email.utils import formatdate
from pathlib import Path

from englishbot.config import Settings
from englishbot.infrastructure.sqlite_store import (
    SQLiteContentStore,
    SQLiteTelegramUserLoginRepository,
    SQLiteTelegramUserRoleRepository,
)
from englishbot.public_assets import (
    resolve_public_asset_preview_path,
    verify_public_asset_signature,
)
from englishbot.webapp_auth import (
    TelegramWebAppSession,
    build_dev_session,
    build_link_session,
    session_from_init_data,
)
from englishbot.webapp_pages import render_help_html, render_webapp_html

logger = logging.getLogger(__name__)

_ROLE_CHOICES = ("admin", "user", "editor")


def create_web_app(settings: Settings) -> Callable:
    store = SQLiteContentStore(db_path=settings.content_db_path)
    store.initialize()
    login_repository = SQLiteTelegramUserLoginRepository(store)
    role_repository = SQLiteTelegramUserRoleRepository(store)
    seed_configured_roles(role_repository=role_repository, settings=settings)

    def application(environ, start_response):  # noqa: ANN001
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        is_read_request = method in {"GET", "HEAD"}
        try:
            if is_read_request and path == "/webapp":
                return html_response(start_response, render_webapp_html())
            if is_read_request and path == "/webapp/help":
                session = authenticate_request(
                    environ,
                    settings=settings,
                    login_repository=login_repository,
                    role_repository=role_repository,
                )
                return html_response(
                    start_response,
                    render_help_html(session, environ=environ, query_param=query_param),
                )
            if is_read_request and path == "/api/session":
                session = authenticate_request(
                    environ,
                    settings=settings,
                    login_repository=login_repository,
                    role_repository=role_repository,
                )
                if session is None:
                    return json_response(
                        start_response,
                        401,
                        {
                            "message": (
                                "Open this page from Telegram or use the configured local dev mode."
                            )
                        },
                    )
                return json_response(start_response, 200, {"session": session_payload(session)})
            if is_read_request and path == "/public-assets/preview":
                return public_asset_preview_response(
                    environ,
                    start_response,
                    settings=settings,
                    method=method,
                )
            if is_read_request and path == "/api/users":
                _session, error_response = require_admin(
                    environ,
                    start_response,
                    settings=settings,
                    login_repository=login_repository,
                    role_repository=role_repository,
                )
                if error_response is not None:
                    return error_response
                return json_response(
                    start_response,
                    200,
                    {"users": [user_payload(item) for item in role_repository.list_users()]},
                )
            if method == "POST" and path.startswith("/api/users/") and path.endswith("/roles"):
                _session, error_response = require_admin(
                    environ,
                    start_response,
                    settings=settings,
                    login_repository=login_repository,
                    role_repository=role_repository,
                )
                if error_response is not None:
                    return error_response
                user_id = user_id_from_path(path)
                if user_id is None:
                    return json_response(start_response, 404, {"message": "User was not found."})
                payload = read_json_body(environ)
                roles = payload.get("roles", [])
                if not isinstance(roles, list):
                    return json_response(
                        start_response,
                        400,
                        {"message": "roles must be a JSON array."},
                    )
                normalized_roles = tuple(
                    sorted(
                        {
                            str(role).strip().lower()
                            for role in roles
                            if str(role).strip()
                        }
                    )
                )
                invalid_roles = [role for role in normalized_roles if role not in _ROLE_CHOICES]
                if invalid_roles:
                    return json_response(
                        start_response,
                        400,
                        {"message": f"Unsupported roles: {', '.join(invalid_roles)}."},
                    )
                role_repository.replace(user_id=user_id, roles=normalized_roles)
                updated_user = next(
                    (item for item in role_repository.list_users() if item.telegram_id == user_id),
                    None,
                )
                if updated_user is None:
                    return json_response(start_response, 404, {"message": "User was not found."})
                return json_response(start_response, 200, {"user": user_payload(updated_user)})
            return json_response(start_response, 404, {"message": "Not found."})
        except json.JSONDecodeError:
            logger.warning("Invalid JSON body in web app request", exc_info=True)
            return json_response(start_response, 400, {"message": "Invalid JSON body."})
        except FileNotFoundError:
            return json_response(start_response, 404, {"message": "Not found."})
        except Exception:
            logger.exception("Unhandled web app error path=%s method=%s", path, method)
            return json_response(start_response, 500, {"message": "Internal server error."})

    return application


def authenticate_request(
    environ,
    *,
    settings: Settings,
    login_repository: SQLiteTelegramUserLoginRepository,
    role_repository: SQLiteTelegramUserRoleRepository,
) -> TelegramWebAppSession | None:
    users = role_repository.list_users()
    roles_by_user = {item.telegram_id: item.roles for item in users}
    profile_by_user = {
        item.telegram_id: {
            "username": item.username,
            "first_name": item.first_name,
            "last_name": item.last_name,
        }
        for item in users
    }
    init_data = header(environ, "HTTP_X_TELEGRAM_INIT_DATA") or query_param(environ, "initData")
    if init_data:
        session = session_from_init_data(
            init_data,
            bot_token=settings.telegram_token,
            roles_by_user=roles_by_user,
        )
        if session is None:
            return None
        login_repository.record(
            user_id=session.telegram_id,
            username=session.username,
            first_name=session.first_name,
            last_name=session.last_name,
        )
        return session

    public_user_id_raw = header(environ, "HTTP_X_TELEGRAM_USER_ID") or query_param(environ, "user_id")
    if public_user_id_raw:
        language_code = header(environ, "HTTP_X_TELEGRAM_LANG") or query_param(environ, "lang")
        return build_link_session(
            telegram_id=int(public_user_id_raw),
            roles_by_user=roles_by_user,
            language_code=language_code,
            profile_by_user=profile_by_user,
        )

    dev_user_id_raw = header(environ, "HTTP_X_DEV_USER_ID") or query_param(environ, "dev_user_id")
    if dev_user_id_raw and is_loopback_request(environ):
        dev_user_id = int(dev_user_id_raw)
        if dev_user_id in settings.web_app_dev_user_ids:
            return build_dev_session(
                telegram_id=dev_user_id,
                roles_by_user=roles_by_user,
                profile_by_user=profile_by_user,
            )
    return None


def require_admin(
    environ,
    start_response,
    *,
    settings: Settings,
    login_repository: SQLiteTelegramUserLoginRepository,
    role_repository: SQLiteTelegramUserRoleRepository,
) -> tuple[TelegramWebAppSession | None, list[bytes] | None]:
    session = authenticate_request(
        environ,
        settings=settings,
        login_repository=login_repository,
        role_repository=role_repository,
    )
    if session is None:
        return None, json_response(
            start_response,
            401,
            {"message": "Open this page from Telegram or use the configured local dev mode."},
        )
    if not session.is_admin:
        return None, json_response(
            start_response,
            403,
            {
                "message": "Access denied. Admin role is required.",
                "session": session_payload(session),
            },
        )
    return session, None


def header(environ, name: str) -> str | None:  # noqa: ANN001
    value = environ.get(name)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def query_param(environ, name: str) -> str | None:  # noqa: ANN001
    from urllib.parse import parse_qs

    query_string = environ.get("QUERY_STRING", "")
    query = parse_qs(query_string, keep_blank_values=True)
    values = query.get(name, [])
    if not values:
        return None
    normalized = values[0].strip()
    return normalized or None


def read_json_body(environ) -> dict[str, object]:  # noqa: ANN001
    content_length = environ.get("CONTENT_LENGTH", "0").strip() or "0"
    body_length = int(content_length)
    body = environ["wsgi.input"].read(body_length).decode("utf-8") if body_length > 0 else "{}"
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Expected object", body, 0)
    return parsed


def user_id_from_path(path: str) -> int | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) != 4 or parts[0] != "api" or parts[1] != "users" or parts[3] != "roles":
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


def session_payload(session: TelegramWebAppSession) -> dict[str, object]:
    return {
        "telegram_id": session.telegram_id,
        "username": session.username,
        "first_name": session.first_name,
        "last_name": session.last_name,
        "language_code": session.language_code,
        "roles": list(session.roles),
        "is_admin": session.is_admin,
        "is_verified": session.is_verified,
        "is_dev_mode": session.is_dev_mode,
    }


def user_payload(user) -> dict[str, object]:  # noqa: ANN001
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "roles": list(user.roles),
    }


def json_response(start_response, status_code: int, payload: dict[str, object]) -> list[bytes]:  # noqa: ANN001
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        f"{status_code} {status_text(status_code)}",
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def html_response(start_response, html: str) -> list[bytes]:  # noqa: ANN001
    body = html.encode("utf-8")
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def public_asset_preview_response(
    environ,
    start_response,
    *,
    settings: Settings,
    method: str,
) -> list[bytes]:  # noqa: ANN001
    relative_path = query_param(environ, "path")
    signature = query_param(environ, "sig")
    signing_secret = settings.public_asset_signing_secret.strip()
    if relative_path is None or signature is None or not signing_secret:
        return json_response(start_response, 404, {"message": "Not found."})
    if not verify_public_asset_signature(
        relative_path=relative_path,
        variant="preview",
        signature=signature,
        signing_secret=signing_secret,
    ):
        return json_response(start_response, 403, {"message": "Access denied."})
    preview_path = resolve_public_asset_preview_path(
        relative_path=relative_path,
        assets_dir=settings.assets_dir,
    )
    return file_response(start_response, preview_path, method=method)


def file_response(start_response, file_path: Path, *, method: str) -> list[bytes]:  # noqa: ANN001
    body = b"" if method == "HEAD" else file_path.read_bytes()
    content_type, _encoding = mimetypes.guess_type(file_path.name)
    stat = file_path.stat()
    start_response(
        "200 OK",
        [
            ("Content-Type", content_type or "application/octet-stream"),
            ("Content-Length", str(stat.st_size)),
            ("Cache-Control", "public, max-age=86400"),
            ("Last-Modified", formatdate(stat.st_mtime, usegmt=True)),
            ("X-Content-Type-Options", "nosniff"),
        ],
    )
    return [body]


def status_text(status_code: int) -> str:
    return {
        200: "OK",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        500: "Internal Server Error",
    }.get(status_code, "OK")


def seed_configured_roles(
    *,
    role_repository: SQLiteTelegramUserRoleRepository,
    settings: Settings,
) -> None:
    for user_id in settings.admin_user_ids:
        role_repository.grant(user_id=user_id, role="admin")
    for user_id in settings.editor_user_ids:
        role_repository.grant(user_id=user_id, role="editor")


def is_loopback_request(environ) -> bool:  # noqa: ANN001
    remote_addr = str(environ.get("REMOTE_ADDR", "")).strip()
    return remote_addr in {"127.0.0.1", "::1", "localhost"}
