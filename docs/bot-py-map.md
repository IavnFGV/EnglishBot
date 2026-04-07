# `bot.py` Map

This document exists because [src/englishbot/bot.py](/workspaces/EnglishBot/src/englishbot/bot.py) is still large enough that a quick skim is hard.

## What `bot.py` Is Now

`bot.py` is no longer the whole Telegram application.

Today it is mostly:

- shared Telegram helper functions
- runtime accessors for `bot_data` and `user_data`
- callback-token helpers
- keyboard and small view builders that have not been moved yet
- public wrapper handlers that call the real implementation modules under [src/englishbot/telegram/](/workspaces/EnglishBot/src/englishbot/telegram)

After the Telegram interaction-layer work, `bot.py` no longer owns most prompt state or tracked-message lifecycle rules directly.
Those are expected to live in [src/englishbot/telegram/interaction.py](/workspaces/EnglishBot/src/englishbot/telegram/interaction.py).

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

- callback token creation and consumption
- message cleanup helpers
- tracked flow wrappers
- assignment notification scheduling
- some keyboard composition that is still reused across flows

## Why It Still Feels Big

`bot.py` is still large because it mixes three kinds of code in one file:

- facade wrappers
- Telegram interaction plumbing
- residual view and keyboard helpers

So the size is no longer only “too many handlers”. A lot of it is helper surface.

## What To Do With `bot.py`

For `1.0.0`, treat `bot.py` as a facade and shared-helper file.

That means:

- it does not have to become tiny before release
- but it does need to stay explainable
- future cleanup should be driven by responsibility, not just by line count

## Best Future Candidates To Move Out

If the file is reduced further after `1.0.0`, the best targets are:

- shared Telegram interaction state
- residual keyboard-builder blocks
- remaining callback-token helper logic
- remaining notification or tracked-message plumbing that can live in focused Telegram modules
