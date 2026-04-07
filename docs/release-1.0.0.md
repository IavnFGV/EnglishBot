# Release 1.0.0

`1.0.0` is the first stable release of the simplified EnglishBot shape.

## What this release means

- the default product is the Telegram learner bot
- the default runtime is `python -m englishbot`
- the default devcontainer is the lightweight no-AI profile
- Docker startup is split into:
  - core bot runtime in [docker-compose.yml](/workspaces/EnglishBot/docker-compose.yml)
  - optional Web App, TTS, and nginx overlay in [docker-compose.optional.yml](/workspaces/EnglishBot/docker-compose.optional.yml)

## Core story

The `1.0.0` core product is:

- words and lessons
- learner training flows
- homework
- learner progress
- simple teacher or parent administration in Telegram

## Optional extensions

These remain supported, but they are not required for the core startup story:

- raw-text import tooling
- image generation and image review tooling
- TTS runtime
- Telegram Web App administration
- local Ollama and ComfyUI development services

## Architecture checkpoint

The repository now reads as:

- `application/` for use cases
- `presentation/` for Telegram-facing screens and keyboards
- `telegram/` for Telegram runtime, handlers, interaction state, and feature policies
- `capabilities/` for optional AI and TTS wiring
- `bot.py` as a transitional facade rather than the real Telegram application center

## Release notes

Highlights:

- Telegram interaction lifecycle is now centralized through [interaction.py](/workspaces/EnglishBot/src/englishbot/telegram/interaction.py)
- large editor and image-review flows no longer depend directly on bot-private helpers
- tracked-message and shared Telegram runtime access now go through focused helper layers
- devcontainer profiles and Docker runtime surface are explicitly documented for normal bot work vs optional AI work

## Verification

Current release checkpoint verification:

```bash
python -m pytest -q
```

The repository test suite is green at the `1.0.0` candidate checkpoint.
