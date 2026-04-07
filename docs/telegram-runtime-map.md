# Telegram Runtime Map

This document explains how the Telegram runtime is assembled today.

## Runtime Flow

1. [src/englishbot/__main__.py](/workspaces/EnglishBot/src/englishbot/__main__.py)
   Loads environment, builds settings, configures logging, and starts polling.
2. [src/englishbot/telegram/bootstrap.py](/workspaces/EnglishBot/src/englishbot/telegram/bootstrap.py)
   Creates the `Application`, initializes repositories and use cases, registers optional capabilities, and adds Telegram handlers.
3. [src/englishbot/bot.py](/workspaces/EnglishBot/src/englishbot/bot.py)
   Exposes the callback functions that bootstrap registers.

## What Lives In `app.bot_data`

The Telegram bootstrap stores:

- shared repositories such as content, Telegram roles, and tracked flow messages
- training service and homework use cases
- editor and image review use cases
- optional capability outputs such as smart parsing, image generation, and TTS flags
- runtime settings and version metadata

This is the main runtime dependency container for Telegram handlers.

## Telegram Module Responsibilities

- [src/englishbot/telegram/entry_handlers.py](/workspaces/EnglishBot/src/englishbot/telegram/entry_handlers.py)
  `/start`, `/help`, `/version`
- [src/englishbot/telegram/navigation_handlers.py](/workspaces/EnglishBot/src/englishbot/telegram/navigation_handlers.py)
  top-level menus such as `/words`, `/assign`, and start menu callbacks
- [src/englishbot/telegram/learner_entry_handlers.py](/workspaces/EnglishBot/src/englishbot/telegram/learner_entry_handlers.py)
  lesson selection, mode selection, continue or restart session
- [src/englishbot/telegram/answer_handlers.py](/workspaces/EnglishBot/src/englishbot/telegram/answer_handlers.py)
  answer-entry callbacks and text answers
- [src/englishbot/telegram/question_delivery.py](/workspaces/EnglishBot/src/englishbot/telegram/question_delivery.py)
  sending or editing the current question
- [src/englishbot/telegram/answer_processing.py](/workspaces/EnglishBot/src/englishbot/telegram/answer_processing.py)
  post-answer orchestration and feedback
- [src/englishbot/telegram/homework_admin.py](/workspaces/EnglishBot/src/englishbot/telegram/homework_admin.py)
  homework setup and admin drill-down
- [src/englishbot/telegram/editor_add_words.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_add_words.py)
  draft extraction and text editing flow
- [src/englishbot/telegram/editor_images.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_images.py)
  image review and published image editing flow
- [src/englishbot/telegram/assignment_progress.py](/workspaces/EnglishBot/src/englishbot/telegram/assignment_progress.py)
  assignment progress rendering and update helpers
- [src/englishbot/telegram/notifications.py](/workspaces/EnglishBot/src/englishbot/telegram/notifications.py)
  Telegram notification delivery helpers
- [src/englishbot/telegram/flow_tracking.py](/workspaces/EnglishBot/src/englishbot/telegram/flow_tracking.py)
  tracked Telegram messages and cleanup
- [src/englishbot/telegram/interaction.py](/workspaces/EnglishBot/src/englishbot/telegram/interaction.py)
  Telegram interaction lifecycle helpers such as expected-input prompt state, named interaction ids and tags, lesson, chat-menu, TTS, image-review, and assignment-progress interaction policies, plus editor prompt/draft/image-review subflow state
- [src/englishbot/telegram/runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/runtime.py)
  thin access layer for shared Telegram runtime dependencies such as `tg`, `service`, `content_store`, UI language, and small `bot_data` or `user_data` helpers
- [src/englishbot/telegram/editor_runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_runtime.py)
  thin editor-specific orchestration layer for active draft flows, image-review use cases, preview or checkpoint helpers, editable-word updates, editor AI availability checks, and publish-related helper calls
- [src/englishbot/telegram/callback_tokens.py](/workspaces/EnglishBot/src/englishbot/telegram/callback_tokens.py)
  tokenized callback helpers for editor item selection and other unstable callback payloads

## Telegram Interaction Layer

The interaction layer is intentionally thin.

It is not a scene engine or a general Telegram framework. It currently owns:

- expected-input prompt state
- named interaction ids and tags
- tracked-message replacement and finish helpers
- lesson interaction lifecycle helpers
- chat-menu lifecycle helpers
- TTS voice-message lifecycle helpers
- image-review screen lifecycle helpers
- image-review photo-attach transient state helpers
- published-word edit lifecycle helpers
- add-words raw-text and draft-edit transient state helpers
- published-word edit prompt transient state helpers
- image-review text-edit transient state helpers
- admin goal prompt/deadline transient state helpers
- admin goal creation transient state helpers
- assignment-progress interaction ids

This gives the project one reusable Telegram lifecycle layer without pulling business logic out of the existing EnglishBot use cases.

Tracked-message and notification operations sit next to that layer, not inside it:

- [src/englishbot/telegram/flow_tracking.py](/workspaces/EnglishBot/src/englishbot/telegram/flow_tracking.py) owns message deletion, replacement, registry updates, and flow cleanup helpers
- [src/englishbot/telegram/notifications.py](/workspaces/EnglishBot/src/englishbot/telegram/notifications.py) owns pending-notification storage, delivery, reminders, and dismiss behavior
- [src/englishbot/telegram/runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/runtime.py) owns the thin “ask runtime for X” surface so Telegram feature modules do not need to reach into `bot.py` for every shared dependency
- [src/englishbot/telegram/editor_runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_runtime.py) owns the thin “ask editor flow for X” surface so add-words and image-review flows do not need to pull these orchestration helpers from `bot.py` directly
- [src/englishbot/telegram/callback_tokens.py](/workspaces/EnglishBot/src/englishbot/telegram/callback_tokens.py) owns tokenized callback payload construction and resolution so editor modules do not need bot-level token wrappers

This runtime layer is now the preferred way to access shared Telegram runtime dependencies in larger feature modules such as:

- [src/englishbot/telegram/homework_admin.py](/workspaces/EnglishBot/src/englishbot/telegram/homework_admin.py)
- [src/englishbot/telegram/editor_images.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_images.py)
- [src/englishbot/telegram/editor_add_words.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_add_words.py)

The migration is intentionally incremental: feature modules can still call true cross-flow helpers from `bot.py`, but routine `tg` / UI-language / runtime-service access should move through `runtime.py`.
For editor-heavy flows, that next layer now lives in [src/englishbot/telegram/editor_runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_runtime.py), while interaction modes live in [src/englishbot/telegram/interaction.py](/workspaces/EnglishBot/src/englishbot/telegram/interaction.py) and unstable callback payloads live in [src/englishbot/telegram/callback_tokens.py](/workspaces/EnglishBot/src/englishbot/telegram/callback_tokens.py).
At this checkpoint, [src/englishbot/telegram/editor_add_words.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_add_words.py) and [src/englishbot/telegram/editor_images.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_images.py) no longer depend on direct `bot_module._...` calls.

## Rule For New Telegram Features

New Telegram features should reuse the interaction layer for transient UI state and tracked-message lifecycle.

That means new flows should prefer:

- named interaction ids and tags in [src/englishbot/telegram/interaction.py](/workspaces/EnglishBot/src/englishbot/telegram/interaction.py)
- explicit interaction helper functions for prompt state, screen replacement, and flow cleanup
- explicit dataclasses or getter/update/clear helpers for temporary `user_data` state

Avoid introducing new ad hoc `context.user_data["some_flow_mode"]` branches directly inside handlers when the state belongs to a reusable Telegram interaction pattern.

See [docs/telegram-interaction-contract.md](/workspaces/EnglishBot/docs/telegram-interaction-contract.md) for the short implementation rule set we now follow for new Telegram features.
- [src/englishbot/telegram/tts.py](/workspaces/EnglishBot/src/englishbot/telegram/tts.py)
  learner TTS buttons and current-question audio flow

## Presentation Layer

Telegram runtime uses the presentation layer for user-visible output:

- [src/englishbot/presentation/telegram_ui_text.py](/workspaces/EnglishBot/src/englishbot/presentation/telegram_ui_text.py)
  localized string catalog
- [src/englishbot/presentation/telegram_views.py](/workspaces/EnglishBot/src/englishbot/presentation/telegram_views.py)
  text and photo view objects plus send/edit helpers
- [src/englishbot/presentation/telegram_assignments_ui.py](/workspaces/EnglishBot/src/englishbot/presentation/telegram_assignments_ui.py)
  learner and assignment-related keyboards or labels
- [src/englishbot/presentation/telegram_assignments_admin_ui.py](/workspaces/EnglishBot/src/englishbot/presentation/telegram_assignments_admin_ui.py)
  admin assignment screens
- [src/englishbot/presentation/telegram_editor_ui.py](/workspaces/EnglishBot/src/englishbot/presentation/telegram_editor_ui.py)
  editor menus and related keyboards

## Important Current Tradeoff

The runtime is already modular, but the public callback surface still funnels through [src/englishbot/bot.py](/workspaces/EnglishBot/src/englishbot/bot.py).

That means:

- Telegram responsibilities are now mostly split by module
- but `bot.py` still remains the easiest place to start grepping for callback names
- for `1.0.0`, `bot.py` is acceptable as a facade, but not as the final shape for long-term growth
