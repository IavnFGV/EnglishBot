# Docker Server Setup

This repo can be run on the Hetzner server with Docker after the host bootstrap step.

## Documentation Rule

Every important deployment or runtime-safety step must be reflected in documentation immediately.

This especially includes:

- deploy workflow changes
- rollback workflow changes
- backup and restore procedures
- retention policy changes
- new required secrets
- new required server directories or files

If the operational process changes, update this document in the same change set.

## Expected server layout

```text
/srv/englishbot/
  app/                  # cloned repository
  shared/
    .env
    data/
    assets/
    nginx/
      acme/
      certs/
    backups/
      db/
      db-versioned/
    logs/
    deploy/
      build-counter.env
      current-release.env
    content/
      custom/
```

## First manual deploy

1. Log in as `deploy`.
2. Clone the repo into `/srv/englishbot/app`.
3. Put production settings into `/srv/englishbot/shared/.env`.
4. Put Web App settings into `/srv/englishbot/shared/.env` if admin access is needed:
   - `WEB_APP_BASE_URL`
   - optional `WEB_APP_PORT`
5. If you do not have a domain yet, you can use a temporary host like `<server-ip>.nip.io`, for example:

```env
WEB_APP_BASE_URL=https://204.168.193.232.nip.io
```

6. Prepare ACME and certificate directories:
   - `/srv/englishbot/shared/nginx/acme/`
   - `/srv/englishbot/shared/nginx/certs/`
7. Put TLS certificate files into `/srv/englishbot/shared/nginx/certs/`:
   - `fullchain.pem`
   - `privkey.pem`
8. Start the runtime:

```bash
cd /srv/englishbot/app
docker compose up -d --build
```

## GitHub Actions auto-deploy

This repo includes [deploy.yml](../.github/workflows/deploy.yml).

It runs on every push to `main` and does:

1. `pytest -q`
2. SSH into the Hetzner server
3. Run [deploy-docker-app.sh](../scripts/deploy-docker-app.sh)
4. Rebuild and restart the Docker services with `docker compose up -d --build`
5. Create a git tag for the successful deploy, for example `deploy-v0.1.0-b3`
6. Keep the latest 5 rolling SQLite backups in `shared/backups/db/`

Backup behavior detail:

- `docker-compose.yml` mounts backup directories explicitly:
  - `shared/backups/db -> /app/backups/db`
  - `shared/backups/db-versioned -> /app/backups/db-versioned`
- `scripts/backup-runtime-db.sh` writes the live SQLite backup directly to `/app/backups/db/...` inside the running container, so the file appears immediately in `shared/backups/db/...` on the host.
- The backup script uses `docker exec -i ... python - <<'PY'` for inline Python snippets; `-i` is required so the heredoc reaches Python via STDIN and the backup file is actually created.
- If the currently running container was started before backup mounts were added, the script falls back to `docker cp` from the container filesystem, so deploy does not fail only because of a stale container mount configuration.
- This keeps rolling SQLite backups on host storage and avoids relying on implicit parent-directory mounts.

### Required GitHub repository secrets

- `DEPLOY_HOST`: Hetzner server IP or hostname
- `DEPLOY_PORT`: optional SSH port, usually `22`
- `DEPLOY_USER`: `deploy`
- `DEPLOY_SSH_KEY`: private SSH key that can log in as `deploy`

### First-time server preparation for auto-deploy

After the bootstrap step, run this once on the server as `deploy`:

```bash
cd /srv/englishbot
git clone YOUR_REPO_URL app
cd /srv/englishbot/app
git checkout main
cp .env.server.bot-only.example /srv/englishbot/shared/.env
docker compose up -d --build
```

After that, GitHub Actions can deploy updates by SSH.

Runtime note:

- `englishbot` runs the Telegram bot process
- `englishbot-webapp` runs the admin Web App process
- `englishbot-nginx` terminates TLS on `443` and proxies to `englishbot-webapp:8080`
- both share the same runtime SQLite database and assets directory
- `englishbot-nginx` also serves `/.well-known/acme-challenge/` from `shared/nginx/acme/`

## Free TLS Certificate

The simplest free option here is Let's Encrypt with an HTTP-01 challenge.

Example for a `nip.io` hostname:

```bash
sudo apt-get update
sudo apt-get install -y certbot
cd /srv/englishbot/app
CERTBOT_EMAIL=you@example.com bash scripts/issue-webapp-cert.sh 204.168.193.232.nip.io
```

The script:

- reads `WEB_APP_BASE_URL` from `shared/.env` when no domain argument is provided
- issues the certificate through `certbot --webroot`
- creates or refreshes:

```text
/srv/englishbot/shared/nginx/certs/fullchain.pem
/srv/englishbot/shared/nginx/certs/privkey.pem
```

and then restarts `englishbot-nginx`.

Manual fallback if needed:

```bash
cd /srv/englishbot/app
docker compose restart englishbot-nginx
```

If the server IP changes:

- the `nip.io` hostname changes too
- `WEB_APP_BASE_URL` must be updated
- you need a new certificate for the new hostname
- Telegram users must open the new Web App URL from the bot

That is why `nip.io` is good for MVP and fast setup, but a stable real domain is better for long-term deployment.

## Rollback

After successful deploys are tagged, you can roll back on the server with one command:

```bash
cd /srv/englishbot/app
bash scripts/rollback-docker-app.sh
```

That rolls back to the previous successful deploy tag.

To roll back to a specific tagged deploy:

```bash
cd /srv/englishbot/app
bash scripts/rollback-docker-app.sh deploy-v0.1.0-b3
```

If the release damaged runtime data, restore the database from a backup copy:

```bash
cd /srv/englishbot/app
bash scripts/restore-runtime-db.sh /srv/englishbot/shared/backups/db/englishbot-db-deploy-v0.1.0-b3-20260327T183000Z.sqlite3
```

## Useful commands

```bash
cd /srv/englishbot/app
docker compose ps
docker compose logs -f englishbot
docker compose logs -f englishbot-webapp
docker compose logs -f englishbot-nginx
docker compose restart englishbot
docker compose restart englishbot-webapp
docker compose restart englishbot-nginx
docker compose up -d --build
bash scripts/backup-runtime-db.sh manual
bash scripts/deploy-docker-app.sh
bash scripts/rollback-docker-app.sh
bash scripts/restore-runtime-db.sh /srv/englishbot/shared/backups/db/<backup-file>.sqlite3
```

## Persistence

- `data/` keeps SQLite runtime state
- `assets/` keeps generated and downloaded images
- `nginx/acme/` keeps ACME HTTP-01 challenge files for Let's Encrypt
- `nginx/certs/` keeps TLS certificate files for the admin Web App reverse proxy
- `backups/db/` keeps the latest 5 rolling SQLite backup copies
- `logs/` keeps rotating log files
- `content/custom/` keeps editor-created content packs
