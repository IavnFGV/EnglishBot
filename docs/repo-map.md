# Repo Map

This document is the shortest way to understand the repository layout.

## Read This First

If you are new to the project, read files in this order:

1. [README.md](/workspaces/EnglishBot/README.md)
2. [docs/1.0.0-plan.md](/workspaces/EnglishBot/docs/1.0.0-plan.md)
3. [docs/telegram-runtime-map.md](/workspaces/EnglishBot/docs/telegram-runtime-map.md)
4. [docs/telegram-interaction-contract.md](/workspaces/EnglishBot/docs/telegram-interaction-contract.md)
5. [docs/bot-py-map.md](/workspaces/EnglishBot/docs/bot-py-map.md)

## Main Runtime

- [src/englishbot/__main__.py](/workspaces/EnglishBot/src/englishbot/__main__.py)
  The main bot entrypoint. Loads `.env`, builds `Settings`, configures logging, builds the Telegram application, and starts polling.
- [src/englishbot/telegram/bootstrap.py](/workspaces/EnglishBot/src/englishbot/telegram/bootstrap.py)
  The Telegram composition root. Registers handlers and puts runtime services or repositories into `app.bot_data`.
- [src/englishbot/bot.py](/workspaces/EnglishBot/src/englishbot/bot.py)
  Transitional Telegram facade. Still large, but now mostly shared helpers, public handler wrappers, and runtime glue.

## Core Product Layers

- [src/englishbot/domain/](/workspaces/EnglishBot/src/englishbot/domain)
  Entities and repository contracts.
- [src/englishbot/application/](/workspaces/EnglishBot/src/englishbot/application)
  Use cases and focused services for lessons, training, homework, editor flows, and image review flows.
- [src/englishbot/infrastructure/](/workspaces/EnglishBot/src/englishbot/infrastructure)
  SQLite-backed runtime storage and content loading.

## Telegram Layer

- [src/englishbot/telegram/](/workspaces/EnglishBot/src/englishbot/telegram)
  Telegram-specific handlers and helpers, split by responsibility.
- [src/englishbot/telegram/runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/runtime.py)
  Thin shared runtime-access layer for Telegram modules.
- [src/englishbot/presentation/](/workspaces/EnglishBot/src/englishbot/presentation)
  Telegram-facing text, views, keyboards, and progress rendering.

## Optional Capabilities

- [src/englishbot/capabilities/ai_text.py](/workspaces/EnglishBot/src/englishbot/capabilities/ai_text.py)
  Optional AI text parsing and import pipeline wiring.
- [src/englishbot/capabilities/ai_images.py](/workspaces/EnglishBot/src/englishbot/capabilities/ai_images.py)
  Optional image-generation and image-review wiring.
- [src/englishbot/capabilities/tts.py](/workspaces/EnglishBot/src/englishbot/capabilities/tts.py)
  Optional TTS capability wiring for the bot runtime.

## Optional Tools

- [src/englishbot/importing/](/workspaces/EnglishBot/src/englishbot/importing)
  Raw-text import pipeline and related helpers.
- [src/englishbot/image_generation/](/workspaces/EnglishBot/src/englishbot/image_generation)
  Image generation, review, prompt shaping, rerank, and Pixabay integration.
- [src/englishbot/image_tooling/](/workspaces/EnglishBot/src/englishbot/image_tooling)
  Shared image CLI orchestration.
- [src/englishbot/audio_tooling/](/workspaces/EnglishBot/src/englishbot/audio_tooling)
  Shared audio CLI orchestration.
- [src/englishbot/webapp.py](/workspaces/EnglishBot/src/englishbot/webapp.py)
  Telegram Web App entrypoint.
- [src/englishbot/tts_service.py](/workspaces/EnglishBot/src/englishbot/tts_service.py)
  Separate HTTP TTS service entrypoint.

## Public CLI Entrypoints

These top-level modules are intentionally still public entrypoints, not refactor leftovers:

- [src/englishbot/import_lesson_text.py](/workspaces/EnglishBot/src/englishbot/import_lesson_text.py)
- [src/englishbot/bulk_import_topics.py](/workspaces/EnglishBot/src/englishbot/bulk_import_topics.py)
- [src/englishbot/fill_word_images.py](/workspaces/EnglishBot/src/englishbot/fill_word_images.py)
- [src/englishbot/fill_word_audio.py](/workspaces/EnglishBot/src/englishbot/fill_word_audio.py)
- [src/englishbot/generate_image.py](/workspaces/EnglishBot/src/englishbot/generate_image.py)
- [src/englishbot/generate_lesson_images.py](/workspaces/EnglishBot/src/englishbot/generate_lesson_images.py)
- [src/englishbot/export_image_rerank_manifest.py](/workspaces/EnglishBot/src/englishbot/export_image_rerank_manifest.py)
- [src/englishbot/rerank_image_manifest.py](/workspaces/EnglishBot/src/englishbot/rerank_image_manifest.py)
- [src/englishbot/apply_image_rerank_decisions.py](/workspaces/EnglishBot/src/englishbot/apply_image_rerank_decisions.py)

## Quick Mental Model

Use this sentence as the project summary:

`__main__` starts the bot, `telegram/bootstrap.py` wires it, `application/` contains the use cases, `presentation/` formats Telegram screens, `telegram/` handles Telegram-specific flow logic, and `bot.py` is the remaining facade we are gradually shrinking.
