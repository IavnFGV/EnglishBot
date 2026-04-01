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

- runtime state lives in one local SQLite file instead of a separate service stack
- published content is still imported/exported as JSON packs under `content/demo/` and `content/custom/`
- sense-level dictionary modeling is still intentionally postponed

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

## Storage Model

Runtime storage now uses SQLite with a split between:

- `lexemes`: one global word entry such as `board`
- `learning_items`: the actual teachable unit with translation, hint, image, prompt, and source fragment
- `topic_learning_items`: topic membership for learning items
- `lesson_learning_items`: lesson membership for learning items

Important rule:

- learner sessions, progress, answer history, and image review all use `learning_item.id`

This keeps the learner flow stable while allowing:

- one global word to be reused across multiple teachable items
- the same teachable item to appear in multiple topics or lessons
- different translations or hints for the same headword without introducing full sense modeling yet

## Core Scope

- Topic- and lesson-aware vocabulary practice
- Three training modes:
  - Easy: choose the correct English word from three options
  - Medium: see shuffled letters as a hint and type the English word
  - Hard: type the English word manually without a letter hint
- Per-user progress, goals, and homework tracking in SQLite
- Short session summary after training
- Demo content for `weather`, `school`, and `seasons`
- Structured JSON content packs loaded from `content/demo/` and `content/custom/`

## Architecture summary

The project is a simple modular monolith:

- `englishbot.domain`: entities and repository interfaces
- `englishbot.application`: small use cases plus focused logic components
- `englishbot.infrastructure`: SQLite-backed runtime store, JSON content-pack loading, and persistence adapters
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

More details are in `ARCHITECTURE.md` and `docs/homework-progress.md`.
The admin Telegram Web App MVP is documented in `docs/telegram-webapp-admin.md`.

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
- On import, each pack item becomes a `learning_item`, and the store also creates or reuses a global `lexeme` by normalized headword.
- This format stays intentionally simple even though the runtime database is more normalized.

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

## Learner Goals + Progress (Telegram UI)

Learners now have a dedicated goals flow in `/words`:

1. open `/words`
2. tap `🎯 Goals` to view active goals and create a new one
3. choose period (`homework`)
4. choose `target_count` (preset or manual number)
5. pick `Recent words` as source and save
6. tap `📊 Progress` to see:
   - total correct / incorrect answers
   - current game streak
   - weekly points
   - active goals with completion percent
7. use `Reset goal` from the goals screen to stop an active goal

Supported callback routes:

- `words:goals`
- `words:progress`
- `words:goal_setup`
- `words:goal_period:homework`
- `words:goal_target:<n|custom>`
- `words:goal_source:recent`
- `words:goal_reset:<goal_id>`

## Homework Flow (Telegram UI)

`/assign` is now the dedicated homework area.

What changed in `0.8.x`:

- learners no longer choose between `daily`, `weekly`, and `all assignments`
- the bot shows one homework entry point and one active homework summary
- each homework can have a deadline shown directly in the menu
- homework progress is word-based: assigned words stay active until they reach the required homework level

Current learner flow:

1. open `/assign` or tap `📘 Homework` from `/start`
2. review the homework summary:
   - assigned / not assigned
   - remaining words
   - estimated rounds
   - due date when present
3. choose how many words to take in this round
4. start the homework round
5. answer assigned words
6. after each correct answer, watch:
   - weekly points feedback
   - homework progress text
   - homework progress image / indicator
7. continue with `➡️ Continue` until no assigned words remain

Homework completion rules:

- `new_words` homework counts a word when the learner answers that assigned word correctly
- `word_level_homework` is stricter: the word must reach the target homework level
- current word-level path is:
  - `1 easy`
  - `2 medium`
  - then, with a small random chance, one optional bonus `hard` step
- the bonus `hard` step does not increase homework remaining counters or round size
- when a bonus `hard` step appears, the homework progress circle marks that word with `🔥`
- a homework for 10 words is not the same as 10 rounds
- a deadline helps organize the task, but completion still depends on word progress

Admin homework assignment rules:

- `topic` assigns all words from the chosen topic
- `manual` assigns all words explicitly selected by the admin
- `recent` assigns the full recent-word set available for that learner
- the learner chooses the round batch size when starting homework

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

Important runtime rule:

- AI-assisted parsing is an optional external capability, not a required core dependency
- the bot must continue working even when the external AI node is unavailable
- when smart parsing fails, the admin flow falls back to a simpler local template-based parse and keeps manual review in the loop

Flow:

1. raw text ingestion
2. semantic extraction into a draft structure when the external AI capability is available
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

Fallback behavior:

- if smart parsing is available and returns a valid structured draft, the normal draft-review flow continues
- if smart parsing is unavailable, times out, or returns an invalid response, the app switches to a simpler local fallback parser
- the fallback parser only extracts obvious vocabulary pairs from simple line formats
- partial results stay editable, and the draft explicitly keeps warnings plus unparsed lines for manual completion

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

When `--extractor ollama` is used, Ollama is treated as an external optional dependency:

- if Ollama is healthy, smart parsing is used
- if Ollama is unavailable or fails, the pipeline falls back to the local template parser
- fallback mode is intentionally limited and may produce partial drafts that need manual completion

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

Important runtime rule:

- local AI image generation is an optional external capability
- the bot must continue working even when the external image node is unavailable
- if local AI image generation fails, the app falls back to local placeholder images instead of breaking the editor flow

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

Backfill missing vocabulary images from Pixabay without local image generation:

```bash
python -m englishbot.fill_word_images \
  --assets-dir assets \
  --delay-sec 1
```

Useful options:

- `--topic-id fairy-tales` to fill one topic only
- `--limit 50` to process a smaller batch
- `--force` to redownload even when a local asset already exists
- `--dry-run` to see selections without saving files

The script uses the existing Pixabay API settings from `.env`, fetches the first 20 popular results for each word, and then picks the best candidate using simple semantic heuristics based on tags, source-page text, and image size. This is intentionally a lightweight external-service flow rather than local LLM image generation.

What is still stubbed:

- OCR
- web image search

Current backends:

- `placeholder`: local offline PNG renderer for development and tests
- `comfyui`: local HTTP backend for a running ComfyUI server

Current resilient behavior:

- if `ComfyUI` is available, normal local AI image generation is used
- if `ComfyUI` is unavailable, times out, or fails, the system falls back to local placeholder images
- image review still remains usable because the editor can switch to Pixabay, edit the prompt, or upload a custom image
- auto-image publish still completes, but the final message can indicate that placeholder fallback was used

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
- stronger operational tooling around the existing runtime state

### Optional ComfyUI Devcontainer Pattern

The devcontainer now includes a managed ComfyUI setup similar in spirit to the Ollama setup:

- `.devcontainer/comfyui.env`
- `.devcontainer/prepare-host-dirs.sh`
- `.devcontainer/start-comfyui.sh`
- `.devcontainer/manage-generation-services.sh`
- ComfyUI code installed into the devcontainer image at `/opt/ComfyUI`
- host bind mounts for persistent data:
  - `${HOME}/.comfyui/models -> /opt/ComfyUI/models`
  - `${HOME}/.comfyui/output -> /opt/ComfyUI/output`

This keeps the setup reproducible while still avoiding repeated model downloads across rebuilds.

CPU/GPU behavior:

- CPU profile builds ComfyUI with CPU PyTorch wheels and starts it with `--cpu`
- GPU profile builds ComfyUI with CUDA PyTorch wheels

If you want persistent model storage across rebuilds:

1. Prepare the host directories:

```bash
bash .devcontainer/prepare-host-dirs.sh
```

2. Ensure these directories now exist:
   - `${HOME}/.comfyui/models`
   - `${HOME}/.comfyui/output`
3. Place checkpoints/models into `${HOME}/.comfyui/models`
4. Rebuild/reopen the devcontainer

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

- supports three devcontainer profiles: `cpu`, `gpu`, and `noai`
- installs Ollama only when profile build arg `OLLAMA_INSTALL=1`
- installs ComfyUI only when profile build arg `COMFYUI_INSTALL=1`
- installs Python extras per profile through `PYTHON_EXTRAS` (`dev,llm` for `cpu/gpu`, `dev` for `noai`)
- reuses pip cache through a named Docker volume mounted to `/home/vscode/.cache/pip`
- can keep Ollama/ComfyUI disabled in dev mode via one switch file: `.devcontainer/local-ai.env`

Configuration files:

- `.devcontainer/devcontainer.cpu.json`
- `.devcontainer/devcontainer.gpu.json`
- `.devcontainer/devcontainer.noai.json`
- `.devcontainer/local-ai.env`
- `.devcontainer/local-ai.on.env`
- `.devcontainer/local-ai.off.env`
- `.devcontainer/ollama.env`
- `.devcontainer/comfyui.env`
- `.devcontainer/start-ollama.sh`
- `.devcontainer/start-comfyui.sh`
- `.devcontainer/manage-generation-services.sh`
- `.devcontainer/prepare-host-dirs.sh`
- `.devcontainer/fix-container-perms.sh`
- `.devcontainer/check-host-gpu.sh`
- `scripts/switch-devcontainer-profile.sh`
- `scripts/switch-local-ai-mode.sh`

Switch profiles:

```bash
bash scripts/switch-devcontainer-profile.sh cpu
bash scripts/switch-devcontainer-profile.sh gpu
bash scripts/switch-devcontainer-profile.sh noai
```

Switch local AI services:

```bash
bash scripts/switch-local-ai-mode.sh off
bash scripts/switch-local-ai-mode.sh on
```

The default active profile in `.devcontainer/devcontainer.json` is the `noai` profile for lightweight WSL and non-GPU setups.
The default local AI mode in `.devcontainer/local-ai.env` is `off`, so Ollama/ComfyUI do not autostart and models are not auto-pulled unless you switch it to `on`.

Inside the `cpu` and `gpu` profiles you can also inspect or restart services manually:

```bash
bash .devcontainer/manage-generation-services.sh status
bash .devcontainer/manage-generation-services.sh restart ollama
bash .devcontainer/manage-generation-services.sh restart comfyui
```

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

- SQLite is used as a local runtime store; there is no separate backend service split.
- `Medium` mode is intentionally simplified to typed input with a shuffled-letter hint.
- Local AI services are optional; when image generation is unavailable, the app falls back to placeholder assets instead of failing the flow.
- JSON content packs remain the import/export format even though runtime state is normalized in SQLite.

## Future extensions

- Separate admin bot that reuses the same domain and application services
- OpenAI-backed or other hosted/local semantic extraction clients for lesson import
- Content import from teacher text, spreadsheets, or photo-derived OCR
- Review scheduling and spaced repetition
- Richer moderation and editing flows for imported vocabulary
## Bulk Topic Import

You can bulk-import multiple topic word lists from one text file without images:

```bash
python -m englishbot.bulk_import_topics bulk-topics.txt
```

Supported input format:

```text
Birthday
Birthday boy - именинник
Birthday girl - именинница

School
Board - доска
Chalk - мел
```

You can also use explicit topic headers:

```text
Topic: Food
Bread - хлеб
Milk - молоко
```

By default the command imports directly into the SQLite runtime database.

If you also want JSON files in `content/custom`, pass an output directory:

```bash
python -m englishbot.bulk_import_topics bulk-topics.txt --output-dir content/custom
```
