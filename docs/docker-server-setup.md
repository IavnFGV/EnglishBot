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

## Useful commands

```bash
cd /srv/englishbot/app
docker compose ps
docker compose logs -f englishbot
docker compose restart englishbot
docker compose up -d --build
```

## Persistence

- `data/` keeps SQLite runtime state
- `assets/` keeps generated and downloaded images
- `logs/` keeps rotating log files
- `content/custom/` keeps editor-created content packs
