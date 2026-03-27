# Docker Server Setup

This repo can be run on the Hetzner server with Docker after the host bootstrap step.

## Expected server layout

```text
/srv/englishbot/
  app/                  # cloned repository
  shared/
    .env
    data/
    assets/
    logs/
    content/
      custom/
```

## First manual deploy

1. Log in as `deploy`.
2. Clone the repo into `/srv/englishbot/app`.
3. Put production settings into `/srv/englishbot/shared/.env`.
4. Start the bot:

```bash
cd /srv/englishbot/app
docker compose up -d --build
```

## GitHub Actions auto-deploy

This repo includes [deploy.yml](/workspaces/EnglishBot/.github/workflows/deploy.yml).

It runs on every push to `master` and does:

1. `pytest -q`
2. SSH into the Hetzner server
3. Run [deploy-docker-app.sh](/workspaces/EnglishBot/scripts/deploy-docker-app.sh)
4. Rebuild and restart the Docker container with `docker compose up -d --build`

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
git checkout master
cp .env.server.bot-only.example /srv/englishbot/shared/.env
docker compose up -d --build
```

After that, GitHub Actions can deploy updates by SSH.

## Useful commands

```bash
cd /srv/englishbot/app
docker compose ps
docker compose logs -f englishbot
docker compose restart englishbot
docker compose up -d --build
bash scripts/deploy-docker-app.sh
```

## Persistence

- `data/` keeps SQLite runtime state
- `assets/` keeps generated and downloaded images
- `logs/` keeps rotating log files
- `content/custom/` keeps editor-created content packs
