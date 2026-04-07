# Changelog

## 1.0.0 - 2026-04-07

First stable release of the simplified EnglishBot architecture.

Highlights:

- the default runtime is the Telegram bot via `python -m englishbot`
- the repository is split into clearer layers: `application`, `presentation`, `telegram`, `capabilities`, and focused tooling packages
- the Telegram interaction layer is now a reusable thin lifecycle module for prompts, tracked messages, and feature-specific flow state
- editor and image-review flows no longer depend directly on bot-private helper calls
- tracked-message plumbing now goes through `telegram/runtime.py`
- notification policy constants are localized in `telegram/notifications.py`
- Docker runtime is split into:
  - `docker-compose.yml` for the core bot
  - `docker-compose.optional.yml` for optional Web App, TTS, and nginx services
- the default devcontainer is explicitly lightweight, with optional `cpu` and `gpu` AI profiles

Known release boundary:

- `src/englishbot/bot.py` remains a transitional facade for `1.0.0`
- optional AI, TTS, and Web App features remain supported, but they are not part of the core startup story
