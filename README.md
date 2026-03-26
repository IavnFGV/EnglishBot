# EnglishBot

EnglishBot is a Telegram bot POC for lightweight English vocabulary practice for children, with an editor workflow for importing words and curating pictures before learner practice starts.

## Current Status

The current project is already beyond the original narrow training MVP.

What works now:

- learner training by topic, lesson, and difficulty
- short session summary after training
- raw-text word import for editors
- draft preview, draft text editing, and draft approval
- automatic or manual image generation flow for vocabulary items
- per-word image review with prompt editing and custom photo upload
- post-publish editing of words
- post-publish editing of images for a specific word
- application-level scenario tests that cover the core product flows without using the real Telegram API

What is still intentionally simple:

- learner progress and sessions are still in memory
- published content is still stored as JSON packs under `content/demo/` and `content/custom/`
- the content model still duplicates the same word across packs instead of using a normalized vocabulary database

This is acceptable for the current POC. It keeps the workflow understandable while we validate the real product behavior.

## Product Direction

The product direction is now clearer:

- an admin or parent uploads words and curates the content
- the bot then interacts with Teia in a shared Telegram chat
- the learner experience should feel proactive rather than command-driven

The next product milestone is therefore not "more import features", but learner interaction:

- schedule or trigger training prompts for Teia
- send review invitations into the shared chat
- let Teia answer directly in chat and continue the session naturally

## Near-Term Storage Direction

The current JSON-pack storage is enough for the POC, but it is probably not the right long-term shape.

The likely next durable model is:

- one canonical vocabulary table for unique words
- separate topic/lesson grouping tables
- many-to-many links between vocabulary items and topics/lessons
- explicit metadata for image state, review state, and publication state

That direction should reduce duplication and make it easier to reuse the same word in multiple themes or lessons. This has not been implemented yet because the current priority is validating the Telegram-based parent/editor-to-learner workflow.

## Core Scope

- Topic- and lesson-aware vocabulary practice
- Three training modes:
  - Easy: choose the correct English word from three options
  - Medium: see shuffled letters as a hint and type the English word
  - Hard: type the English word manually without a letter hint
- Per-user progress tracking in memory
- Short session summary after training
- Demo content for `weather`, `school`, and `seasons`
- Structured JSON content packs loaded from `content/demo/` and `content/custom/`

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

## Learner Flow

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

## Editor Flow

The editor workflow now exists inside the bot and can also be tested at the application level without Telegram.

Current editor flow:

1. open `/words`
2. choose `Add Words`
3. send raw lesson text
4. review the extracted draft
5. edit the draft text if needed
6. choose one of:
   - `Approve + Auto Images`
   - `Manual Image Review`
   - `Publish Without Images`
7. optionally edit published words and published images later

For published content, the editor can also:

- edit a word after publication
- edit the image for a specific word after publication
- search Pixabay for one word directly in Telegram
- page through Pixabay results 5 at a time
- generate local variants for one word only as a fallback
- edit the image prompt for one word only
- upload a custom replacement image

## Pixabay Image Review

Manual image review now supports two candidate sources:

- Pixabay search for real image candidates
- local AI generation as a fallback

Flow for one vocabulary item:

1. open image review for the word
2. choose `Search Images` to fetch the first 5 Pixabay candidates
3. choose `Use A` to `Use E`, or `Next 5` to continue the same search
4. choose `Generate Image` if you want local AI candidates instead
5. choose `Attach Photo` to upload your own image
6. when a candidate is approved, the bot stores a local copy and updates the vocabulary item

Notes:

- approved Pixabay images are downloaded to the local `assets/<topic>/<item>.png` path
- review previews are stored under `assets/<topic>/review/`
- learner mode never hotlinks remote Pixabay URLs
- Pixabay state such as query, page, and current candidates is persisted in the same runtime store as the rest of the review flow

Required environment variables:

- `PIXABAY_API_KEY`
- optional `PIXABAY_BASE_URL` with default `https://pixabay.com/api/`

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

Human review is still part of the design before publishing extracted packs to learner-facing content.

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
  --ollama-model qwen2.5:7b \
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

Use a running local ComfyUI backend instead of the placeholder renderer:

```bash
python -m englishbot.generate_lesson_images \
  --input content/custom/fairy-tales.json \
  --assets-dir assets \
  --backend comfyui \
  --comfyui-base-url http://127.0.0.1:8188 \
  --comfyui-checkpoint v1-5-pruned-emaonly.safetensors
```

If a checkpoint requires a separate VAE, pass it explicitly:

```bash
python -m englishbot.generate_lesson_images \
  --input content/custom/fairy-tales.json \
  --assets-dir assets \
  --backend comfyui \
  --comfyui-checkpoint revAnimated_v121.safetensors \
  --comfyui-vae vae-ft-mse-840000-ema-pruned.safetensors
```

`ComfyUI` startup can auto-download both the checkpoint and an optional VAE from `.devcontainer/comfyui.env`:

- `COMFYUI_CHECKPOINT_NAME`
- `COMFYUI_CHECKPOINT_URL`
- `COMFYUI_VAE_NAME`
- `COMFYUI_VAE_URL`

The same env file includes commented presets for:

- Stable Diffusion 1.5
- DreamShaper 8
- ReVAnimated 1.2.1

So after checkout you can switch the active model set in one place and restart the container services.

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

- OCR
- web image search

Current backends:

- `placeholder`: local offline PNG renderer for development and tests
- `comfyui`: local HTTP backend for a running ComfyUI server

The image generation layer is intentionally isolated behind a small client interface so additional backends can be added later without changing learner-bot handlers or content-pack structure.

## Testing Approach

The project uses readable application-level scenario tests instead of relying on Telegram API tests.

Current testing strategy:

- use `pytest`
- test learner flows through app-level harnesses
- test editor/import flows through app-level harnesses
- keep Telegram as a thin adapter and only test the adapter behavior where wiring matters
- use optional live integration tests for Ollama and ComfyUI only when needed

This makes it easier to reproduce beta incidents from concrete inputs without depending on Telegram itself.

## Next Product Step

The next step is to make the learner interaction proactive for Teia:

- parent/admin prepares the content
- bot sends Teia messages into the shared chat from time to time
- Teia answers directly there
- the bot keeps the conversation going as a natural training session

That means the next major implementation slice should focus on:

- shared-chat interaction rules
- learner-trigger and review-trigger scheduling
- safe chat routing when both editor and learner are present
- durable persistence for learner progress and content state

### Optional ComfyUI Devcontainer Pattern

The devcontainer now includes a managed ComfyUI setup similar in spirit to the Ollama setup:

- `.devcontainer/comfyui.env`
- `.devcontainer/start-comfyui.sh`
- ComfyUI code installed into the devcontainer image at `/opt/ComfyUI`
- host bind mounts for persistent data:
  - `${HOME}/.comfyui/models -> /opt/ComfyUI/models`
  - `${HOME}/.comfyui/output -> /opt/ComfyUI/output`

This keeps the setup reproducible while still avoiding repeated model downloads across rebuilds.

CPU/GPU behavior:

- CPU profile builds ComfyUI with CPU PyTorch wheels and starts it with `--cpu`
- GPU profile builds ComfyUI with CUDA PyTorch wheels

If you want persistent model storage across rebuilds:

1. Ensure host directories exist:
   - `${HOME}/.comfyui/models`
   - `${HOME}/.comfyui/output`
2. Place checkpoints/models into `${HOME}/.comfyui/models`
3. Rebuild/reopen the devcontainer

If the configured checkpoint file is missing, `.devcontainer/start-comfyui.sh` now behaves similarly to the Ollama startup flow:

- checks whether `COMFYUI_CHECKPOINT_NAME` already exists under `/opt/ComfyUI/models/checkpoints`
- if the file is missing and `COMFYUI_CHECKPOINT_URL` is configured, downloads it automatically
- if the file already exists, skips the download

The startup script will:

- start managed ComfyUI from `/opt/ComfyUI`
- prefer `/opt/ComfyUI/venv/bin/python`
- use `COMFYUI_EXTRA_ARGS` from env/profile
- keep model/output data outside the image through bind mounts
- auto-download the configured checkpoint on first use when missing

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
