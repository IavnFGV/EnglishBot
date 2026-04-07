# `bot.py` Map

This document exists because [src/englishbot/bot.py](/workspaces/EnglishBot/src/englishbot/bot.py) is still large enough that a quick skim is hard.

## What `bot.py` Is Now

`bot.py` is no longer the whole Telegram application.

Current checkpoint:

- about `4058` lines
- about `326` top-level `def/async def`
- `0` direct `view/keyboard/status` helper dependencies from Telegram feature modules back into `bot.py`

Today it is mostly:

- shared Telegram helper functions
- runtime accessors for `bot_data` and `user_data`
- callback-token helpers
- keyboard and small view builders that have not been moved yet
- public wrapper handlers that call the real implementation modules under [src/englishbot/telegram/](/workspaces/EnglishBot/src/englishbot/telegram)

After the Telegram interaction-layer work, `bot.py` no longer owns most prompt state or tracked-message lifecycle rules directly.
Those are expected to live in [src/englishbot/telegram/interaction.py](/workspaces/EnglishBot/src/englishbot/telegram/interaction.py).
The same direction now applies to shared runtime lookups: feature modules should prefer [src/englishbot/telegram/runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/runtime.py) for common `tg`, `service`, `content_store`, and UI-language access instead of treating `bot.py` as a global service locator.
That migration is now underway in the heaviest Telegram feature modules too, especially homework-admin and editor/image-review flows.
At this point the biggest remaining `bot_module._...` clusters in those modules are no longer generic runtime lookups, but more domain-specific cross-flow helpers such as active draft/image-review flow operations and editor publish orchestration.
That editor-specific migration has now started moving into [src/englishbot/telegram/editor_runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_runtime.py), so the next reductions in `bot.py` should come from that layer rather than from more generic runtime-access cleanup.
That editor cleanup wave is now effectively complete for the two main editor modules: [src/englishbot/telegram/editor_add_words.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_add_words.py) and [src/englishbot/telegram/editor_images.py](/workspaces/EnglishBot/src/englishbot/telegram/editor_images.py) no longer call `bot_module._...` directly. They now use `presentation`, `interaction`, `runtime`, `editor_runtime`, and `callback_tokens` as their stable seams.

## Main Sections

Read the file in this order.

### 1. Runtime and user-state access

Near the top of the file:

- `_required_bot_data(...)`
- `_optional_bot_data(...)`
- `_set_bot_data(...)`
- `_optional_user_data(...)`
- `_set_user_data(...)`
- `_pop_user_data(...)`

These are the normalized access points for Telegram runtime state.
New Telegram feature modules should usually consume them indirectly through [src/englishbot/telegram/runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/runtime.py), not by importing `bot.py` as a grab bag.

### 2. Runtime service accessors

The next large block is full of helpers such as:

- `_content_store(...)`
- `_start_add_words_flow(...)`
- `_homework_progress_use_case(...)`
- `_generate_image_review_candidates(...)`

These are just typed accessors into `app.bot_data`, not business logic.

### 3. Telegram text and keyboard helpers

The middle of the file contains many helper functions that build:

- localized text snippets
- start menu or words menu views
- assignment keyboards
- image review keyboards
- callback payloads

This is one reason the file still feels big even after the handler split.

### 4. Public handler wrappers

Most `async def ..._handler(...)` functions in the middle and lower half are now wrappers.

They usually call the real implementation from [src/englishbot/telegram/](/workspaces/EnglishBot/src/englishbot/telegram).

Examples:

- learner entry handlers
- answer handlers
- add-words handlers
- image review handlers
- TTS handlers
- homework admin handlers

### 5. Remaining shared Telegram glue

The file still owns some cross-cutting Telegram glue:

- callback token wrappers that delegate into [src/englishbot/telegram/callback_tokens.py](/workspaces/EnglishBot/src/englishbot/telegram/callback_tokens.py)
- training/TTS markup wrappers that delegate into [src/englishbot/telegram/training_markup.py](/workspaces/EnglishBot/src/englishbot/telegram/training_markup.py)
- tokenized editor keyboard wrappers that delegate into [src/englishbot/presentation/telegram_editor_ui.py](/workspaces/EnglishBot/src/englishbot/presentation/telegram_editor_ui.py)
- message cleanup helpers
- tracked flow wrappers
- assignment notification scheduling
- some keyboard composition that is still reused across flows

New editor Telegram flows should prefer calling presentation-layer keyboard builders directly and use `bot.py` only when a compatibility wrapper is still needed.
The same applies to simple status/progress views such as `build_status_view(...)`: feature modules should import them from presentation directly instead of routing them through `bot.py`.
Topic/word list views and editor cancel menus should follow the same rule: build them in the editor Telegram module with direct presentation imports unless there is a deliberate compatibility reason to keep a bot-level wrapper.
Small game-mode UI pieces such as result keyboards should also live in presentation modules instead of growing new Telegram-specific wrappers in `bot.py`.
Admin/homework Telegram modules should also prefer direct assignment presentation imports for menus and detail keyboards, keeping `bot.py` focused on shared runtime access and true cross-flow helpers.
Draft review previews and follow-up editor menus belong to the same rule: editor modules should compose them from presentation helpers directly instead of routing through `bot.py`.
Checkpoint: Telegram feature modules no longer depend on `bot.py` for direct `view/keyboard/status` builders; remaining `bot.py` usage is mostly runtime access, wrapper compatibility, and shared cross-flow glue.
The same is now true for the common tracked-message and notification helper surface: Telegram feature modules call `flow_tracking` / `notifications` helpers directly instead of routing those operations back through `bot.py`.
Tracked-message registry access has also been normalized one level deeper: modules such as `flow_tracking`, `interaction`, `assignment_progress`, and `image_review_support` now go through [src/englishbot/telegram/runtime.py](/workspaces/EnglishBot/src/englishbot/telegram/runtime.py) for flow-message registry and `chat_id` lookup instead of pulling those bot-private helpers directly.
The same is now true for the main editor modules: direct editor runtime, interaction-mode, and tokenized callback work no longer flows through `bot.py`.
Assignment progress is one step more conservative: the real implementation already lives in [src/englishbot/telegram/assignment_progress.py](/workspaces/EnglishBot/src/englishbot/telegram/assignment_progress.py), but a small bot-level wrapper surface is still intentionally kept because existing bot-handler tests and monkeypatch-based compatibility checks use it directly.
Notifications are similar: the module now owns its fixed dismiss callback, timing windows, and requeue wiring, but the `_PendingNotification` compatibility surface is still intentionally preserved in `bot.py` for wrapper-level tests and callers.
Shared Telegram facade dataclasses now also live outside `bot.py`: `AssignmentRoundProgressView` and `PendingNotification` are defined in [src/englishbot/telegram/models.py](/workspaces/EnglishBot/src/englishbot/telegram/models.py), while `bot.py` keeps compatibility aliases for existing tests and import paths.
The same cleanup now applies to TTS transient Telegram state: selected voice, repeat cooldown tracking, and per-user TTS locks live in [src/englishbot/telegram/tts_state.py](/workspaces/EnglishBot/src/englishbot/telegram/tts_state.py), while `bot.py` keeps compatibility wrappers and stable test constants.

## Why It Still Feels Big

`bot.py` is still large because it mixes three kinds of code in one file:

- facade wrappers
- Telegram interaction plumbing
- residual shared helper blocks that are still useful across multiple flows

So the size is no longer only “too many handlers”. A lot of it is helper surface.

The important improvement is that it is no longer the presentation hub for Telegram modules.
That responsibility has moved to `presentation/...` and focused modules under `telegram/...`.

## What To Do With `bot.py`

For `1.0.0`, treat `bot.py` as a facade and shared-helper file.

That means:

- it does not have to become tiny before release
- but it does need to stay explainable
- future cleanup should be driven by responsibility, not just by line count

## Best Future Candidates To Move Out

If the file is reduced further after `1.0.0`, the best targets are:

- shared runtime accessor blocks if they can be grouped into a smaller runtime/context helper module without harming readability
- assignment progress helpers if we want to separate rendering glue from runtime access even further
- larger cross-flow orchestration helpers such as `_known_assignment_users(...)` or `_finish_admin_goal_creation(...)` if we find a clean home for them

## What Probably Stays

Some large pieces are now reasonable to keep in `bot.py` for `1.0.0`:

- typed runtime access to `bot_data` and `user_data`
- compatibility wrappers that keep the refactor incremental and testable
- shared Telegram glue used across several feature modules
- a small number of cross-feature orchestration helpers that do not belong cleanly to one Telegram submodule yet

That means the next wave should not aim for “smallest possible file”.
It should only move a block when the new home is clearly more understandable than the current facade placement.
