# EnglishBot

EnglishBot is a Telegram bot MVP for lightweight English vocabulary practice for children.

## MVP scope

- Topic-based vocabulary practice
- Three training modes:
  - Easy: choose the correct English word from three options
  - Medium: see shuffled letters as a hint and type the English word
  - Hard: type the English word manually without a letter hint
- Per-user progress tracking in memory
- Short session summary after training
- Demo content for `weather`, `school`, and `seasons`
- Lesson-aware data model and filtering support in the application layer

## Architecture summary

The project is a simple modular monolith:

- `englishbot.domain`: entities and repository interfaces
- `englishbot.application`: small use cases plus focused logic components
- `englishbot.infrastructure`: in-memory repositories and seed data
- `englishbot.bot`: Telegram handlers and UI mapping
- `englishbot.bootstrap`: dependency wiring

The application layer is split into clear responsibilities:

- topic listing
- training session startup
- current question resolution
- answer submission
- word selection strategy
- question generation
- answer checking
- session summary calculation

More details are in `ARCHITECTURE.md`.

## Quick start in VS Code Dev Container

1. Open the project in VS Code.
2. Reopen it in the Dev Container.
3. Create `.env` from the example:

```bash
cp .env.example .env
```

4. Put your bot token into `.env`.
5. Run the bot:

```bash
python -m englishbot
```

## Quick start locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
python -m englishbot
```

## Run tests

```bash
pytest
```

## Future extensions

- Separate admin bot that reuses the same domain and application services
- Content import from teacher text, spreadsheets, or photo-derived OCR
- Review scheduling and spaced repetition
- Manual moderation and editing of imported vocabulary

## Current simplifications

- Storage is in memory for now, so progress is reset on restart.
- `Medium` mode is intentionally simplified to typed input with a shuffled-letter hint.
- Images are represented by placeholder references, not Telegram file uploads.
- Lesson-aware filtering exists in the architecture, but lesson selection is not yet exposed in the Telegram UI.
