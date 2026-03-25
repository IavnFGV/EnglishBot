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

## Lesson Text Import Pipeline

The project now includes a separate import pipeline for messy teacher-provided lesson text.

Flow:

1. raw text ingestion
2. semantic extraction into a draft structure
3. strict code-level validation
4. canonicalization into the JSON content-pack format
5. JSON content-pack writing

Why this exists:

- free-form teacher text is usually too inconsistent for rigid parsing rules;
- a semantic extraction client can later use OpenAI or another LLM;
- strict validation still happens in code, so the system does not trust the extractor blindly.

Draft extraction data includes:

- `topic_title`
- optional `lesson_title`
- vocabulary items with `english_word`, `translation`, optional `notes`, optional `image_prompt`, and `source_fragment`
- optional warnings, unparsed lines, and confidence notes

Canonical output remains the same content-pack JSON family already used by the bot, with stable slugs and `image_ref: null` by default.

Human review is still recommended before publishing extracted packs to learner-facing content.

## Local Import CLI

There is a local two-step CLI entrypoint for the import pipeline:

```bash
python -m englishbot.import_lesson_text extract-draft --input lesson.txt --output content/custom/fairy-tales.draft.json
python -m englishbot.import_lesson_text finalize-draft --input content/custom/fairy-tales.draft.json --output content/custom/fairy-tales.json
```

Step 1 extracts an editable draft from raw text. Step 2 takes the reviewed draft JSON and converts it into the final canonical content pack used by the bot.

By default draft extraction uses a real Ollama-backed extractor over HTTP. You can still switch to the offline stub extractor when needed:

```bash
python -m englishbot.import_lesson_text extract-draft \
  --extractor stub \
  --input lesson.txt \
  --output content/custom/fairy-tales.draft.json
```

Useful Ollama options:

```bash
python -m englishbot.import_lesson_text extract-draft \
  --extractor ollama \
  --ollama-model llama3.2:3b \
  --ollama-base-url http://127.0.0.1:11434 \
  --include-image-prompts \
  --input lesson.txt \
  --output content/custom/fairy-tales.draft.json
```

Tests still stay offline because they use fake/mock extraction clients instead of a live Ollama server.

The intended workflow is:

- send raw teacher/parent/student text to `extract-draft`
- let the system propose vocabulary pairs and optional image prompts
- review the draft JSON manually
- add, remove, or edit vocabulary items by hand if needed
- run `finalize-draft` to validate and save the final canonical pack

By default the Ollama draft extraction path is conservative:

- it does not keep model-generated `image_prompt` values unless `--include-image-prompts` is passed
- it tries to repair obvious translation mistakes from `source_fragment`, for example when the model transliterates Russian text into Latin characters

When `--include-image-prompts` is enabled, prompts are generated one vocabulary pair at a time after the initial extraction step. This keeps the mental model simple: first parse the text into pairs, then generate one image prompt for each pair.

Manual review is part of the design, not an edge case. If a reviewer removes items, adds new ones, or edits fields directly in the draft JSON, `finalize-draft` will either:

- accept the reviewed draft and produce a final content pack
- or return structured validation errors for required fields such as missing `translation` or `source_fragment`

## Local Image Generation

Image generation is a separate local-first enrichment step applied to an already finalized content pack.

Current behavior:

- content packs may contain nullable `image_ref`
- content packs may contain nullable `image_prompt`
- if `image_prompt` is missing, the image pipeline generates a fallback child-friendly prompt from `english_word`
- generated images are stored as local assets under a stable deterministic path based on `topic.id` and item `id`

Generate local images for a content pack:

```bash
python -m englishbot.generate_lesson_images \
  --input content/custom/fairy-tales.json \
  --assets-dir assets
```

Force regeneration even when the referenced local file already exists:

```bash
python -m englishbot.generate_lesson_images \
  --input content/custom/fairy-tales.json \
  --assets-dir assets \
  --force
```

Expected assets layout:

```text
assets/
  fairy-tales/
    fairy-tales-dragon.png
    fairy-tales-castle.png
    fairy-tales-elf.png
```

After enrichment the content pack is updated in place, for example:

- `image_ref`: `assets/fairy-tales/fairy-tales-dragon.png`
- `image_prompt`: preserved from the pack if already present, otherwise generated from fallback prompt logic

Learner bot behavior:

- if `image_ref` exists and the local file exists, the bot sends a Telegram photo with the question as caption
- if the file is missing, the bot falls back to the existing text-only question flow

What is still stubbed:

- actual generative image backend
- OCR
- web image search

The current local image backend is a placeholder PNG renderer for offline development. It is intentionally isolated behind a small image generation client interface so it can later be replaced with a real local image model backend.

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

## Ollama Devcontainer Pattern

This repository includes a reusable Ollama devcontainer setup.

What it does:

- installs the Ollama binary into the devcontainer image
- reuses the host model cache by bind-mounting `${HOME}/.ollama` to `/home/vscode/.ollama`
- reuses pip cache through a named Docker volume mounted to `/home/vscode/.cache/pip`
- runs `.devcontainer/start-ollama.sh` on container start to:
  - normalize permissions on mounted directories
  - start `ollama serve` if it is not already running
  - wait for readiness on `http://127.0.0.1:11434/api/tags`
  - pull the configured model only if it is missing

Configuration files:

- `.devcontainer/devcontainer.cpu.json`
- `.devcontainer/devcontainer.gpu.json`
- `.devcontainer/ollama.env`
- `.devcontainer/start-ollama.sh`
- `.devcontainer/fix-container-perms.sh`
- `.devcontainer/check-host-gpu.sh`
- `scripts/switch-devcontainer-profile.sh`

Switch profiles:

```bash
bash scripts/switch-devcontainer-profile.sh cpu
bash scripts/switch-devcontainer-profile.sh gpu
```

The default active profile in `.devcontainer/devcontainer.json` is the CPU profile.

Python-side Ollama integration is intentionally lightweight:

- use HTTP requests to `http://localhost:11434/api/chat`
- install only the minimal `requests` dependency through the optional `llm` extra

Docker build context is reduced through `.dockerignore`, which excludes `.git`, caches, virtual environments, `docs`, `projects`, `output`, and Python bytecode so `load build context` stays fast.

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
- OpenAI-backed or other hosted/local semantic extraction clients for lesson import
- Content import from teacher text, spreadsheets, or photo-derived OCR
- Review scheduling and spaced repetition
- Manual moderation and editing of imported vocabulary
