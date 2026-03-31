from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlencode
from wsgiref.simple_server import make_server

from dotenv import load_dotenv

from englishbot.__main__ import configure_logging
from englishbot.config import Settings, create_runtime_config_service
from englishbot.infrastructure.sqlite_store import (
    SQLiteContentStore,
    SQLiteTelegramUserLoginRepository,
    SQLiteTelegramUserRoleRepository,
)
from englishbot.webapp_auth import (
    TelegramWebAppSession,
    build_dev_session,
    build_link_session,
    session_from_init_data,
)

logger = logging.getLogger(__name__)

_ROLE_CHOICES = ("admin", "user", "editor")
_REPO_ROOT = Path(__file__).resolve().parents[2]


def create_web_app(settings: Settings) -> Callable:
    store = SQLiteContentStore(db_path=settings.content_db_path)
    store.initialize()
    login_repository = SQLiteTelegramUserLoginRepository(store)
    role_repository = SQLiteTelegramUserRoleRepository(store)
    _seed_configured_roles(role_repository=role_repository, settings=settings)

    def application(environ, start_response):  # noqa: ANN001
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        is_read_request = method in {"GET", "HEAD"}
        try:
            if is_read_request and path == "/webapp":
                return _html_response(start_response, _render_webapp_html())
            if is_read_request and path == "/webapp/help":
                session = _authenticate_request(
                    environ,
                    settings=settings,
                    login_repository=login_repository,
                    role_repository=role_repository,
                )
                return _html_response(start_response, _render_help_html(session, environ=environ))
            if is_read_request and path == "/api/session":
                session = _authenticate_request(
                    environ,
                    settings=settings,
                    login_repository=login_repository,
                    role_repository=role_repository,
                )
                if session is None:
                    return _json_response(
                        start_response,
                        401,
                        {
                            "message": (
                                "Open this page from Telegram or use the configured local dev mode."
                            )
                        },
                    )
                return _json_response(start_response, 200, {"session": _session_payload(session)})
            if is_read_request and path == "/api/users":
                session, error_response = _require_admin(
                    environ,
                    start_response,
                    settings=settings,
                    login_repository=login_repository,
                    role_repository=role_repository,
                )
                if error_response is not None:
                    return error_response
                return _json_response(
                    start_response,
                    200,
                    {"users": [_user_payload(item) for item in role_repository.list_users()]},
                )
            if method == "POST" and path.startswith("/api/users/") and path.endswith("/roles"):
                session, error_response = _require_admin(
                    environ,
                    start_response,
                    settings=settings,
                    login_repository=login_repository,
                    role_repository=role_repository,
                )
                if error_response is not None:
                    return error_response
                user_id = _user_id_from_path(path)
                if user_id is None:
                    return _json_response(start_response, 404, {"message": "User was not found."})
                payload = _read_json_body(environ)
                roles = payload.get("roles", [])
                if not isinstance(roles, list):
                    return _json_response(
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
                    return _json_response(
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
                    return _json_response(start_response, 404, {"message": "User was not found."})
                return _json_response(start_response, 200, {"user": _user_payload(updated_user)})
            return _json_response(start_response, 404, {"message": "Not found."})
        except json.JSONDecodeError:
            logger.warning("Invalid JSON body in web app request", exc_info=True)
            return _json_response(start_response, 400, {"message": "Invalid JSON body."})
        except Exception:
            logger.exception("Unhandled web app error path=%s method=%s", path, method)
            return _json_response(start_response, 500, {"message": "Internal server error."})

    return application


def main() -> None:
    env_file_path = _REPO_ROOT / ".env"
    load_dotenv(env_file_path, override=True)
    config_service = create_runtime_config_service(env_file_path=env_file_path)
    settings = Settings.from_config_service(config_service)
    configure_logging(settings.log_level, log_file_path=settings.log_file_path)
    application = create_web_app(settings)
    logger.info(
        "Starting Telegram Web App server host=%s port=%s db_path=%s",
        settings.web_app_host,
        settings.web_app_port,
        settings.content_db_path,
    )
    with make_server(settings.web_app_host, settings.web_app_port, application) as server:
        server.serve_forever()


def _authenticate_request(
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
    init_data = _header(environ, "HTTP_X_TELEGRAM_INIT_DATA") or _query_param(environ, "initData")
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

    public_user_id_raw = _header(environ, "HTTP_X_TELEGRAM_USER_ID") or _query_param(environ, "user_id")
    if public_user_id_raw:
        language_code = _header(environ, "HTTP_X_TELEGRAM_LANG") or _query_param(environ, "lang")
        # This is an MVP shortcut for Telegram menu links that open normal HTTPS pages.
        # Replace it with verified initData when the bot switches back to proper Web App launches.
        return build_link_session(
            telegram_id=int(public_user_id_raw),
            roles_by_user=roles_by_user,
            language_code=language_code,
            profile_by_user=profile_by_user,
        )

    dev_user_id_raw = _header(environ, "HTTP_X_DEV_USER_ID") or _query_param(environ, "dev_user_id")
    if dev_user_id_raw and _is_loopback_request(environ):
        dev_user_id = int(dev_user_id_raw)
        if dev_user_id in settings.web_app_dev_user_ids:
            # This fallback exists only to keep the MVP testable on localhost before the
            # Telegram launch flow is available in every local environment.
            return build_dev_session(
                telegram_id=dev_user_id,
                roles_by_user=roles_by_user,
                profile_by_user=profile_by_user,
            )
    return None


def _require_admin(
    environ,
    start_response,
    *,
    settings: Settings,
    login_repository: SQLiteTelegramUserLoginRepository,
    role_repository: SQLiteTelegramUserRoleRepository,
) -> tuple[TelegramWebAppSession | None, list[bytes] | None]:
    session = _authenticate_request(
        environ,
        settings=settings,
        login_repository=login_repository,
        role_repository=role_repository,
    )
    if session is None:
        return None, _json_response(
            start_response,
            401,
            {"message": "Open this page from Telegram or use the configured local dev mode."},
        )
    if not session.is_admin:
        return None, _json_response(
            start_response,
            403,
            {
                "message": "Access denied. Admin role is required.",
                "session": _session_payload(session),
            },
        )
    return session, None


def _header(environ, name: str) -> str | None:  # noqa: ANN001
    value = environ.get(name)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _query_param(environ, name: str) -> str | None:  # noqa: ANN001
    query_string = environ.get("QUERY_STRING", "")
    query = parse_qs(query_string, keep_blank_values=True)
    values = query.get(name, [])
    if not values:
        return None
    normalized = values[0].strip()
    return normalized or None


def _read_json_body(environ) -> dict[str, object]:  # noqa: ANN001
    content_length = environ.get("CONTENT_LENGTH", "0").strip() or "0"
    body_length = int(content_length)
    body = environ["wsgi.input"].read(body_length).decode("utf-8") if body_length > 0 else "{}"
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Expected object", body, 0)
    return parsed


def _user_id_from_path(path: str) -> int | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) != 4 or parts[0] != "api" or parts[1] != "users" or parts[3] != "roles":
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


def _session_payload(session: TelegramWebAppSession) -> dict[str, object]:
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


def _user_payload(user) -> dict[str, object]:  # noqa: ANN001
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "roles": list(user.roles),
    }


def _json_response(start_response, status_code: int, payload: dict[str, object]) -> list[bytes]:  # noqa: ANN001
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        f"{status_code} {_status_text(status_code)}",
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def _html_response(start_response, html: str) -> list[bytes]:  # noqa: ANN001
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


def _status_text(status_code: int) -> str:
    return {
        200: "OK",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        500: "Internal Server Error",
    }.get(status_code, "OK")


def _seed_configured_roles(
    *,
    role_repository: SQLiteTelegramUserRoleRepository,
    settings: Settings,
) -> None:
    for user_id in settings.admin_user_ids:
        role_repository.grant(user_id=user_id, role="admin")
    for user_id in settings.editor_user_ids:
        role_repository.grant(user_id=user_id, role="editor")


def _is_loopback_request(environ) -> bool:  # noqa: ANN001
    remote_addr = str(environ.get("REMOTE_ADDR", "")).strip()
    return remote_addr in {"127.0.0.1", "::1", "localhost"}


def _render_webapp_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TeiaLearns Admin</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      --bg: #f5f1e8;
      --panel: rgba(255, 252, 246, 0.95);
      --line: #d7ccb8;
      --text: #1e1c18;
      --muted: #6d665b;
      --accent: #0f766e;
      --accent-soft: #dff2ef;
      --danger: #b91c1c;
      --shadow: 0 18px 48px rgba(66, 43, 13, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Trebuchet MS", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(194, 120, 3, 0.16), transparent 24%),
        linear-gradient(180deg, #f7f2e8 0%, #efe6d7 100%);
      min-height: 100vh;
      padding: 24px;
    }
    .shell {
      max-width: 1180px;
      margin: 0 auto;
      background: var(--panel);
      border: 1px solid rgba(215, 204, 184, 0.8);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .hero {
      padding: 28px 28px 18px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(135deg, rgba(15, 118, 110, 0.12), rgba(255, 255, 255, 0.55));
    }
    h1 {
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0.02em;
    }
    .subtitle, .meta {
      margin: 0;
      color: var(--muted);
    }
    .content {
      padding: 24px 28px 28px;
    }
    .status {
      margin-bottom: 18px;
      padding: 14px 16px;
      border-radius: 16px;
      background: var(--accent-soft);
      color: var(--text);
    }
    .status.error {
      background: rgba(185, 28, 28, 0.1);
      color: var(--danger);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: white;
      border: 1px solid var(--line);
      border-radius: 16px;
      overflow: hidden;
    }
    th, td {
      padding: 12px 10px;
      border-bottom: 1px solid rgba(215, 204, 184, 0.7);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }
    th {
      background: #f6efe3;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    tr:last-child td {
      border-bottom: none;
    }
    .roles {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      min-width: 230px;
    }
    label {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    button {
      border: none;
      border-radius: 999px;
      background: var(--accent);
      color: white;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
    }
    button[disabled] {
      opacity: 0.55;
      cursor: progress;
    }
    .muted {
      color: var(--muted);
    }
    .hidden {
      display: none;
    }
    @media (max-width: 860px) {
      body { padding: 12px; }
      .hero, .content { padding-left: 16px; padding-right: 16px; }
      .table-wrap { overflow-x: auto; }
      table { min-width: 920px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>TeiaLearns Admin</h1>
      <p class="subtitle">Manage Telegram user roles with a minimal Telegram Web App.</p>
      <p class="meta" id="session-meta">Checking Telegram session...</p>
    </section>
    <section class="content">
      <div id="status" class="status">Loading session…</div>
      <p class="muted"><a href="/webapp/help" id="help-link">Open assignment guide</a></p>
      <div id="table-wrap" class="table-wrap hidden">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Telegram ID</th>
              <th>Username</th>
              <th>First Name</th>
              <th>Last Name</th>
              <th>Roles</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="users-body"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const telegramApp = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
    if (telegramApp) {
      telegramApp.ready();
      telegramApp.expand();
    }

    const statusBox = document.getElementById("status");
    const sessionMeta = document.getElementById("session-meta");
    const tableWrap = document.getElementById("table-wrap");
    const usersBody = document.getElementById("users-body");
    const helpLink = document.getElementById("help-link");
    const roleChoices = ["admin", "user", "editor"];

    function setStatus(message, isError = false) {
      statusBox.textContent = message;
      statusBox.classList.toggle("error", isError);
    }

    function authHeaders() {
      const headers = { "Content-Type": "application/json" };
      const initData = telegramApp ? telegramApp.initData : "";
      if (initData) {
        headers["X-Telegram-Init-Data"] = initData;
      }
      const query = new URLSearchParams(window.location.search);
      const userId = query.get("user_id");
      const language = query.get("lang");
      if (userId) {
        headers["X-Telegram-User-Id"] = userId;
      }
      if (language) {
        headers["X-Telegram-Lang"] = language;
      }
      const devUserId = query.get("dev_user_id");
      if (!initData && devUserId) {
        headers["X-Dev-User-Id"] = devUserId;
      }
      return headers;
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, {
        ...options,
        headers: {
          ...authHeaders(),
          ...(options.headers || {}),
        },
      });
      const data = await response.json();
      return { response, data };
    }

    function checkboxLabel(role) {
      return role.charAt(0).toUpperCase() + role.slice(1);
    }

    function checkedRoles(row) {
      return roleChoices.filter((role) => {
        const input = row.querySelector(`input[data-role="${role}"]`);
        return input && input.checked;
      });
    }

    async function saveRoles(userId, button) {
      const row = button.closest("tr");
      const roles = checkedRoles(row);
      button.disabled = true;
      button.textContent = "Saving...";
      const { response, data } = await fetchJson(`/api/users/${userId}/roles`, {
        method: "POST",
        body: JSON.stringify({ roles }),
      });
      button.disabled = false;
      button.textContent = "Save";
      if (!response.ok) {
        setStatus(data.message || "Failed to save roles.", true);
        return;
      }
      const savedRoles = Array.isArray(data.user && data.user.roles)
        ? data.user.roles.join(", ")
        : "user";
      setStatus(`Roles updated for Telegram user ${userId}: ${savedRoles}.`);
    }

    function renderUsers(users) {
      usersBody.innerHTML = "";
      for (const user of users) {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${user.id}</td>
          <td>${user.telegram_id}</td>
          <td class="muted">${user.username || ""}</td>
          <td>${user.first_name || ""}</td>
          <td>${user.last_name || ""}</td>
          <td>
            <div class="roles">
              ${roleChoices.map((role) => `
                <label>
                  <input
                    type="checkbox"
                    data-role="${role}"
                    ${Array.isArray(user.roles) && user.roles.includes(role) ? "checked" : ""}
                  >
                  <span>${checkboxLabel(role)}</span>
                </label>
              `).join("")}
            </div>
          </td>
          <td><button type="button">Save</button></td>
        `;
        row.querySelector("button").addEventListener(
          "click",
          () => saveRoles(user.telegram_id, row.querySelector("button"))
        );
        usersBody.appendChild(row);
      }
    }

    async function load() {
      const sessionResult = await fetchJson("/api/session");
      if (!sessionResult.response.ok) {
        sessionMeta.textContent = "Session unavailable";
        setStatus(sessionResult.data.message || "Open this page from Telegram.", true);
        return;
      }

      const session = sessionResult.data.session;
      const sessionBits = [
        `Telegram ID: ${session.telegram_id}`,
        `Roles: ${session.roles.join(", ")}`,
      ];
      if (helpLink) {
        helpLink.href = `/webapp/help${window.location.search || ""}`;
      }
      if (session.is_dev_mode) {
        sessionBits.push("Local dev mode");
      } else if (session.is_verified) {
        sessionBits.push("Verified by Telegram initData");
      }
      sessionMeta.textContent = sessionBits.join(" | ");

      if (!session.is_admin) {
        setStatus("Access denied. Admin role is required.", true);
        return;
      }

      setStatus("Loading users...");
      const usersResult = await fetchJson("/api/users");
      if (!usersResult.response.ok) {
        setStatus(usersResult.data.message || "Failed to load users.", true);
        return;
      }
      renderUsers(usersResult.data.users || []);
      tableWrap.classList.remove("hidden");
      setStatus(`Loaded ${usersResult.data.users.length} users.`);
    }

    load().catch((error) => {
      console.error(error);
      setStatus("Unexpected error while loading the admin panel.", true);
    });
  </script>
</body>
</html>
"""


def _render_help_html(session: TelegramWebAppSession | None, *, environ) -> str:  # noqa: ANN001
    language = _web_language(
        (session.language_code if session is not None else None) or _query_param(environ, "lang")
    )
    text = _help_content(language)
    back_query: dict[str, str | int] = {"lang": language}
    if session is not None:
        back_query["user_id"] = session.telegram_id
    back_href = f"/webapp?{urlencode(back_query)}"
    return f"""<!doctype html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{text["title"]}</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {{
      --bg: #f5f1e8;
      --panel: rgba(255, 252, 246, 0.96);
      --line: #d7ccb8;
      --text: #1e1c18;
      --muted: #6d665b;
      --accent: #0f766e;
      --shadow: 0 18px 48px rgba(66, 43, 13, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Trebuchet MS", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(194, 120, 3, 0.16), transparent 24%),
        linear-gradient(180deg, #f7f2e8 0%, #efe6d7 100%);
      min-height: 100vh;
      padding: 24px;
    }}
    .shell {{
      max-width: 980px;
      margin: 0 auto;
      background: var(--panel);
      border: 1px solid rgba(215, 204, 184, 0.8);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .hero {{
      padding: 28px 28px 18px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(135deg, rgba(15, 118, 110, 0.12), rgba(255, 255, 255, 0.55));
    }}
    .content {{
      padding: 24px 28px 28px;
    }}
    h1, h2 {{
      margin-top: 0;
    }}
    h2 {{
      margin-bottom: 10px;
      font-size: 20px;
    }}
    p, li {{
      line-height: 1.55;
    }}
    .card {{
      background: white;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px 18px 16px;
      margin-bottom: 16px;
    }}
    .muted {{
      color: var(--muted);
    }}
    code {{
      background: #f6efe3;
      padding: 2px 6px;
      border-radius: 6px;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 700;
    }}
    @media (max-width: 860px) {{
      body {{ padding: 12px; }}
      .hero, .content {{ padding-left: 16px; padding-right: 16px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>{text["title"]}</h1>
      <p class="muted">{text["subtitle"]}</p>
    </section>
    <section class="content">
      <div class="card">
        <h2>{text["mechanics_title"]}</h2>
        <ul>
          <li>{text["mechanics_item_1"]}</li>
          <li>{text["mechanics_item_2"]}</li>
          <li>{text["mechanics_item_3"]}</li>
        </ul>
      </div>
      <div class="card">
        <h2>{text["points_title"]}</h2>
        <ul>
          <li>{text["points_item_1"]}</li>
          <li>{text["points_item_2"]}</li>
          <li>{text["points_item_3"]}</li>
        </ul>
      </div>
      <div class="card">
        <h2>{text["examples_title"]}</h2>
        <p>{text["example_words"]}</p>
        <p>{text["example_homework"]}</p>
      </div>
      <div class="card">
        <h2>{text["visibility_title"]}</h2>
        <ul>
          <li>{text["visibility_item_1"]}</li>
          <li>{text["visibility_item_2"]}</li>
          <li>{text["visibility_item_3"]}</li>
        </ul>
      </div>
      <p><a href="{back_href}">{text["back_link"]}</a></p>
    </section>
  </main>
</body>
</html>
"""


def _web_language(language_code: str | None) -> str:
    if not language_code:
        return "en"
    primary = language_code.split("-", 1)[0].split("_", 1)[0].lower()
    if primary in {"ru", "uk", "en"}:
        return primary
    return "en"


def _help_content(language: str) -> dict[str, str]:
    content: dict[str, dict[str, str]] = {
        "en": {
            "title": "How homework works",
            "subtitle": "A short guide to homework progress, deadlines, weekly points, and completion rules.",
            "mechanics_title": "Homework mechanics",
            "mechanics_item_1": "Homework is now one dedicated flow: the learner opens Homework and continues the remaining assigned words instead of choosing between daily or weekly sections.",
            "mechanics_item_2": "Each assigned word has to reach its homework target level. Easy answers warm the word up, Medium moves it further, and Hard can finish it sooner.",
            "mechanics_item_3": "A deadline shows when the homework should be finished. It helps organize the task, while progress still depends on the assigned words reaching their target level.",
            "points_title": "How weekly points are added",
            "points_item_1": "You get base points for the first correct answer on a word during the current week.",
            "points_item_2": "Medium and Hard answers add an extra difficulty bonus.",
            "points_item_3": "If an answer increases the word level, you also get a level-up bonus.",
            "examples_title": "Examples",
            "example_words": "Example: homework for 10 words means the task tracks those 10 assigned words. It is not the same as 10 rounds.",
            "example_homework": "Example: homework for 5 words may stay active after one successful round, because some words may still need another Medium answer or a Hard finish to reach the target level.",
            "visibility_title": "What you see in the bot",
            "visibility_item_1": "Homework shows the current task, remaining words, due date, and a progress indicator that moves forward after correct answers.",
            "visibility_item_2": "After a correct answer, the bot shows whether weekly points were added and how homework progress changed.",
            "visibility_item_3": "If homework is completed, the bot shows it explicitly instead of letting it disappear silently.",
            "back_link": "Back to admin panel",
        },
        "ru": {
            "title": "Как работает домашка",
            "subtitle": "Короткое объяснение прогресса по домашке, дедлайнов, недельных очков и правил завершения.",
            "mechanics_title": "Механика домашки",
            "mechanics_item_1": "Теперь домашка идёт одним отдельным потоком: ученик открывает домашку и продолжает оставшиеся назначенные слова без деления на daily или weekly разделы.",
            "mechanics_item_2": "Каждое назначенное слово должно дойти до целевого уровня домашки. Easy разогревает слово, Medium двигает его дальше, а Hard может закрыть его быстрее.",
            "mechanics_item_3": "Дедлайн показывает, к какому сроку желательно закончить домашку. Сам прогресс считается по тому, достигли ли назначенные слова целевого уровня.",
            "points_title": "Как начисляются недельные очки",
            "points_item_1": "Базовые очки даются за первый правильный ответ по слову в текущей неделе.",
            "points_item_2": "За Medium и Hard добавляется бонус сложности.",
            "points_item_3": "Если ответ повысил уровень слова, добавляется бонус за level-up.",
            "examples_title": "Примеры",
            "example_words": "Пример: домашка на 10 слов означает, что задача следит за этими 10 назначенными словами. Это не то же самое, что 10 раундов.",
            "example_homework": "Пример: домашка на 5 слов может остаться активной после одного удачного раунда, потому что части слов всё ещё может не хватать ещё одного Medium-ответа или завершения на Hard.",
            "visibility_title": "Что видно в боте",
            "visibility_item_1": "В домашке видно текущее задание, сколько слов осталось, дедлайн и индикатор прогресса, который двигается после правильных ответов.",
            "visibility_item_2": "После правильного ответа бот показывает, добавились ли недельные очки и как изменился прогресс домашки.",
            "visibility_item_3": "Если домашка закрылась этим ответом, бот показывает это явно, а не прячет молча.",
            "back_link": "Назад в админку",
        },
        "uk": {
            "title": "Як працює домашка",
            "subtitle": "Короткий опис прогресу домашки, дедлайнів, тижневих очок і правил завершення.",
            "mechanics_title": "Механіка домашки",
            "mechanics_item_1": "Тепер домашка йде одним окремим потоком: учень відкриває домашку і продовжує решту призначених слів без поділу на daily чи weekly розділи.",
            "mechanics_item_2": "Кожне призначене слово має дійти до цільового рівня домашки. Easy розігріває слово, Medium рухає його далі, а Hard може закрити його швидше.",
            "mechanics_item_3": "Дедлайн показує, до якого терміну бажано завершити домашку. Сам прогрес рахується за тим, чи досягли призначені слова цільового рівня.",
            "points_title": "Як нараховуються тижневі очки",
            "points_item_1": "Базові очки даються за першу правильну відповідь по слову в поточному тижні.",
            "points_item_2": "За Medium і Hard додається бонус складності.",
            "points_item_3": "Якщо відповідь підвищила рівень слова, додається бонус за level-up.",
            "examples_title": "Приклади",
            "example_words": "Приклад: домашка на 10 слів означає, що задача стежить саме за цими 10 призначеними словами. Це не те саме, що 10 раундів.",
            "example_homework": "Приклад: домашка на 5 слів може залишитися активною після одного вдалого раунду, бо частині слів ще може бракувати ще однієї Medium-відповіді або завершення на Hard.",
            "visibility_title": "Що видно в боті",
            "visibility_item_1": "У домашці видно поточне завдання, скільки слів залишилося, дедлайн і індикатор прогресу, який рухається після правильних відповідей.",
            "visibility_item_2": "Після правильної відповіді бот показує, чи додалися тижневі очки і як змінився прогрес домашки.",
            "visibility_item_3": "Якщо домашка закрилася саме цією відповіддю, бот покаже це явно, а не сховає мовчки.",
            "back_link": "Назад в адмінку",
        },
    }
    return content.get(language, content["en"])


if __name__ == "__main__":
    main()
