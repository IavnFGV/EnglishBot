from __future__ import annotations

from urllib.parse import urlencode


def render_webapp_html() -> str:
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


def render_help_html(session, *, environ, query_param) -> str:
    language = web_language(
        (session.language_code if session is not None else None) or query_param(environ, "lang")
    )
    text = help_content(language)
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


def web_language(language_code: str | None) -> str:
    if not language_code:
        return "en"
    primary = language_code.split("-", 1)[0].split("_", 1)[0].lower()
    if primary in {"ru", "uk", "en"}:
        return primary
    return "en"


def help_content(language: str) -> dict[str, str]:
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
            "example_words": "Example: homework for 10 words means the task tracks those 10 assigned words until they reach the homework target.",
            "example_homework": "Example: homework for 5 words may stay active after one successful pass, because some words may still need another Medium answer or a Hard finish to reach the target level.",
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
            "example_words": "Пример: домашка на 10 слов означает, что задача следит за этими 10 назначенными словами, пока они не дойдут до домашней цели.",
            "example_homework": "Пример: домашка на 5 слов может остаться активной после одного удачного прохода, потому что части слов всё ещё может не хватать ещё одного Medium-ответа или завершения на Hard.",
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
            "example_words": "Приклад: домашка на 10 слів означає, що задача стежить саме за цими 10 призначеними словами, доки вони не дійдуть до домашньої цілі.",
            "example_homework": "Приклад: домашка на 5 слів може залишитися активною після одного вдалого проходу, бо частині слів ще може бракувати ще однієї Medium-відповіді або завершення на Hard.",
            "visibility_title": "Що видно в боті",
            "visibility_item_1": "У домашці видно поточне завдання, скільки слів залишилося, дедлайн і індикатор прогресу, який рухається після правильних відповідей.",
            "visibility_item_2": "Після правильної відповіді бот показує, чи додалися тижневі очки і як змінився прогрес домашки.",
            "visibility_item_3": "Якщо домашка закрилася саме цією відповіддю, бот покаже це явно, а не сховає мовчки.",
            "back_link": "Назад в адмінку",
        },
    }
    return content.get(language, content["en"])
