# Telegram Admin Web App MVP

## What Was Added

- a minimal Telegram Web App entry point at `/webapp`
- a lightweight Python web server entrypoint: `python -m englishbot.webapp`
- temporary link-based auth for menu links with `user_id` and `lang` query parameters
- optional server-side Telegram `initData` verification remains supported for future Web App launches
- an admin-only users table with role editing for:
  - `admin`
  - `user`
  - `editor`
- backend API endpoints:
  - `GET /api/session`
  - `GET /api/users`
  - `POST /api/users/<telegram_id>/roles`
- an admin-only Telegram button that opens the Web App from the bot UI when `WEB_APP_BASE_URL` is configured

## Current Project Placement

- bot entrypoint: `src/englishbot/__main__.py`
- bot wiring and handlers: `src/englishbot/bot.py`
- runtime SQLite store: `src/englishbot/infrastructure/sqlite_store.py`
- new Web App server: `src/englishbot/webapp.py`
- Telegram Web App auth helpers: `src/englishbot/webapp_auth.py`

## Storage Notes

This project still does not have a separate first-class application `users` table.

For this MVP:

- `telegram_user_logins` stores Telegram profile snapshots
- `telegram_user_roles` stores explicit elevated roles
- the Web App returns both `id` and `telegram_id`
- today `id == telegram_id` because there is no separate internal user entity yet

This keeps the implementation small and compatible with the current project state.

## Local Run

1. Configure `.env`:
   - `TELEGRAM_BOT_TOKEN`
   - `CONTENT_DB_PATH`
   - `ADMIN_USER_IDS`
   - `WEB_APP_BASE_URL`
   - optional `ADMIN_BOOTSTRAP_SECRET` for emergency admin recovery
2. Start the bot:

```bash
python -m englishbot
```

3. Start the Web App server:

```bash
python -m englishbot.webapp
```

In Docker deployment, `docker compose up -d --build --force-recreate` now starts both:

- `englishbot`
- `englishbot-webapp`
- `englishbot-nginx`

The nginx container terminates HTTPS on `443` and proxies requests to the Web App container.
Before certificates are issued, it can still run in plain HTTP mode on `80` for the ACME challenge.

Default local bind:

- host: `127.0.0.1`
- port: `8080`

## Opening From Telegram

Set `WEB_APP_BASE_URL` to the public HTTPS base URL that points to the web server, for example:

```env
WEB_APP_BASE_URL=https://204.168.193.232.nip.io
```

When the current Telegram user has the `admin` role, the bot shows an `Admin Panel` button in the start menu and assignments menu. The button opens a direct HTTPS link like:

```text
<WEB_APP_BASE_URL>/webapp?user_id=<telegram_id>&lang=<ui_language>
```

The guide button opens a public help page like:

```text
<WEB_APP_BASE_URL>/webapp/help?lang=<ui_language>
```

## Current MVP Security Note

This iteration intentionally uses simple menu links with `user_id` and `lang` query parameters so the bot UI stays predictable.

That means:

- the help page is public and localized by `lang`
- the admin page currently trusts the `user_id` passed in the link and still checks backend roles
- this is acceptable only as a temporary MVP shortcut
- the code still keeps the `initData` path so verified Telegram launches can be restored later without redesign

## Free HTTPS

For a quick MVP deploy without buying a domain, you can use a hostname like:

```text
204.168.193.232.nip.io
```

and issue a free Let's Encrypt certificate for it through the nginx ACME webroot documented in [docs/docker-server-setup.md](/workspaces/EnglishBot/docs/docker-server-setup.md).

Recommended host-side command:

```bash
CERTBOT_EMAIL=you@example.com bash scripts/issue-webapp-cert.sh 204.168.193.232.nip.io
```

If the server IP changes, the `nip.io` hostname changes too, so you must:

- update `WEB_APP_BASE_URL`
- issue a new certificate
- redeploy or restart the nginx service

## Manual Verification

1. Put your Telegram ID into `ADMIN_USER_IDS`.
2. Start the bot and send `/start`.
3. Confirm the `Admin Panel` button is visible.
4. Open the Web App from Telegram.
5. Confirm the users table loads.
6. Toggle roles for a user and press `Save`.
7. Reopen the page and confirm the roles persisted.
8. Open the page as a non-admin user and confirm it shows `Access denied. Admin role is required.`

## Emergency Recovery

There is a hidden recovery command for restoring admin access:

```text
/makeadmin <telegram_id> [bootstrap_secret]
```

Rules:

- current admins can run it without a secret
- non-admin users must provide the configured `ADMIN_BOOTSTRAP_SECRET`
- the command is intentionally hidden from the public command list

## MVP Follow-ups

- the page is intentionally one-screen and uses inline HTML/CSS/JS instead of a dedicated frontend stack
- `initData` signature verification is implemented, but no separate freshness/TTL policy is enforced yet
- there is still no standalone application-level user entity separate from Telegram identities
- the local dev fallback is intentionally limited and should stay disabled in environments that do not need it
