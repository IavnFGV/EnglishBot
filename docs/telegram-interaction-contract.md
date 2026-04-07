# Telegram Interaction Contract

This document is the short contract for adding or changing Telegram flows in this repository.

## Goal

We keep Telegram interaction state thin, explicit, and reusable.

Business logic still lives in `application/` use cases.
Telegram-specific transient state and tracked-message lifecycle should go through the interaction layer in [src/englishbot/telegram/interaction.py](/workspaces/EnglishBot/src/englishbot/telegram/interaction.py).

## Use The Interaction Layer For

- named interaction ids and tags
- tracked message replacement
- flow cleanup
- expected-input prompt state
- temporary `user_data` state for Telegram-only subflows

Examples already covered:

- lesson question and feedback lifecycle
- chat menu lifecycle
- TTS voice replacement
- image review screen lifecycle
- image review text and photo subflows
- add-words raw-text and draft-edit state
- published-word edit prompt state
- admin goal prompt and admin goal creation state

## Rule For New Features

When a new Telegram feature needs temporary UI state, prefer one of these patterns:

1. Add a named interaction id or tag helper in [src/englishbot/telegram/interaction.py](/workspaces/EnglishBot/src/englishbot/telegram/interaction.py).
2. Add explicit `start/get/update/clear/finish` helpers there for the new Telegram subflow.
3. If the subflow needs structured temporary state, add a small dataclass in the same module.

## Avoid

- adding raw `context.user_data["some_random_key"]` branches directly in handlers
- adding new tracked-message cleanup logic ad hoc inside feature modules
- spreading one Telegram subflow across several unrelated helper conventions
- treating Telegram screen state as the source of truth for business data

## Preferred Shape

For a new Telegram subflow, aim for this shape:

- a use case in `application/` for business work
- a handler in `telegram/`
- a view in `presentation/` if needed
- a small interaction helper in `telegram/interaction.py` for temporary Telegram state

## Practical Check

Before adding a new Telegram feature, ask:

- Does it need a tracked message?
- Does it need a prompt or expected input?
- Does it need temporary `user_data` state?
- Does it need cleanup when the flow ends?

If the answer to any of these is yes, the default place for that lifecycle code is [src/englishbot/telegram/interaction.py](/workspaces/EnglishBot/src/englishbot/telegram/interaction.py).
