# EnglishBot

EnglishBot is a Telegram bot MVP for lightweight English vocabulary practice for children.

## MVP scope

- Topic- and lesson-aware vocabulary practice
- Three training modes:
  - Easy: choose the correct English word from three options
  - Medium: see shuffled letters as a hint and type the English word
  - Hard: type the English word manually without a letter hint
- Per-user progress tracking in memory
- Short session summary after training
- Demo content for `weather`, `school`, and `seasons`
- Structured JSON content packs loaded from `content/demo/`

## Architecture summary

The project is a simple modular monolith:

- `englishbot.domain`: entities and repository interfaces
- `englishbot.application`: small use cases plus focused logic components
- `englishbot.infrastructure`: in-memory repositories and seed data
- `englishbot.bot`: Telegram handlers and UI mapping
- `englishbot.bootstrap`: dependency wiring

The application layer is split into clear responsibilities:

- topic listing
- lesson listing and topic/lesson validation
- training session startup
- current question resolution
- answer submission
- word selection strategy
- question generation
- answer checking
- session summary calculation

More details are in `ARCHITECTURE.md`.

## Learner flow

1. Choose a topic
2. Choose `All Topic Words` or a specific lesson when lessons exist
3. Choose a training mode
4. Answer the session questions
5. Receive a short session summary

If a topic has no lessons, the bot skips the lesson step and goes directly to mode selection.

## Content pack JSON format

Demo content is loaded from JSON packs in `content/demo/`.

```json
{
  "topic": {"id": "weather", "title": "Weather"},
  "lessons": [{"id": "weather-1", "title": "Weather Lesson 1"}],
  "vocabulary_items": [
    {
      "id": "weather-sun",
      "english_word": "sun",
      "translation": "солнце",
      "lesson_id": "weather-1",
      "image_ref": "bright yellow sun"
    }
  ]
}
```

Notes:

- `lesson_id` is optional, which allows topic-only packs.
- Packs are validated on load, including lesson references.
- This format is suitable for manual teacher-prepared content before a future admin bot exists.

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

## Current simplifications

- Storage is in memory for now, so progress is reset on restart.
- `Medium` mode is intentionally simplified to typed input with a shuffled-letter hint.
- Images are represented by placeholder references, not Telegram file uploads.
- Demo content is loaded from local JSON files rather than a database or admin-managed import pipeline.

## Future extensions

- Separate admin bot that reuses the same domain and application services
- Teacher/admin workflow for preparing and validating JSON packs before full in-app content management
- Content import from teacher text, spreadsheets, or photo-derived OCR
- Review scheduling and spaced repetition
- Manual moderation and editing of imported vocabulary
