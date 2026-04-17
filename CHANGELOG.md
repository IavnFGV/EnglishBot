# Changelog

## 1.1.0 - 2026-04-16

Bulk media-catalog import/export release for centralized image management.

Highlights:

- added `python -m englishbot.media_catalog export-workbook` to export DB-backed image metadata into an `.xlsx` workbook
- added `python -m englishbot.media_catalog import-workbook` to import edited workbook data back into the SQLite DB
- workbook format is intentionally text-only so large catalogs stay lightweight
- export now uses a simplified two-sheet format: `topics` and `words_in_topics`
- image-related fields can now be mass-edited through links and metadata instead of Telegram-only UI
- export now includes Google-Sheets-friendly `preview` and `preview_url` columns for image browsing
- signed preview URLs are served through the Web App instead of exposing the raw assets directory
- preview requests use cached `256px` thumbnails and the Web App server now runs in threaded mode
- admins can open workbook import/export directly from the `/words` menu in Telegram
- workbook import now applies all topic updates atomically and creates a pre-import SQLite backup snapshot
- added workbook-flow documentation in `docs/media-catalog-workbook.md`

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
