# EnglishBot

EnglishBot is a Telegram bot MVP for lightweight English vocabulary practice for children.

## MVP scope

- Topic-based vocabulary practice
- Three training modes:
  - Easy: choose the correct English word from three options
  - Medium: see scrambled letters and choose the correct ordered word
  - Hard: type the English word manually
- Per-user progress tracking in memory
- Short session summary after training
- Demo content for `weather`, `school`, and `seasons`

## Architecture summary

The project is a simple modular monolith:

- `englishbot.domain`: entities and repository interfaces
- `englishbot.application`: session orchestration and training logic
- `englishbot.infrastructure`: in-memory repositories and seed data
- `englishbot.bot`: Telegram handlers and UI mapping
- `englishbot.bootstrap`: dependency wiring

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
