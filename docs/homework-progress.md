# Homework + Progress in Telegram

## Overview

The learner-facing assignment flow is now homework-only.

The old split between `daily`, `weekly`, and `all assignments` was removed from the active Telegram UX. The bot now presents one clear homework flow with:

- one homework entry point
- one homework summary
- one homework round launcher
- one homework progress model
- an optional deadline shown directly in the menu

This keeps the learner experience simpler while preserving the existing training, scoring, weekly points, and word-level business rules.

## `/words`

`/words` stays focused on vocabulary work:

- start training by topic
- add words
- edit published words
- edit published images
- manage personal goals

Homework is no longer mixed into this menu as separate daily or weekly sections.

## `/assign`

`/assign` is the dedicated homework area.

All users can open it and see:

- **🎯 My homework**
- **📈 My progress**
- **👥 Users**

Admins additionally see:

- **🛠 Assign homework**

## `/start`

`/start` is the personal launch screen.

It shows:

- **🎮 Start game**
- **📘 Homework**

Behavior:

- the homework button is enabled only when there are remaining assigned words
- disabled homework stays visible but does not start a round
- the status line shows:
  - assigned / not assigned
  - remaining words
  - estimated rounds
  - deadline, when present
- when the learner starts homework, the bot first asks how many words to take into this round

## Homework rounds

Homework rounds are independent from topics.

That means:

- the learner does not have to open each topic manually
- tapping the homework button first opens a round-size picker
- after choosing the round size, the bot starts a round from the remaining assigned words
- round size is still batched
- after a round is completed, Telegram offers **Next round** when more homework words remain

## How homework progress works

Progress is tracked per assigned word, not per topic.

Current rules:

- `new_words` homework treats a word as completed when the learner answers that assigned word correctly
- `word_level_homework` treats a word as completed only when it reaches the required homework level
- one successful round may still leave homework active if some words need more progress
- a homework for 10 words is not the same as 10 rounds

Difficulty progress inside homework is intentionally stricter than plain topic practice:

- one correct `easy` answer warms the word up
- two correct `medium` answers finish the base homework path for the word
- after that, the bot may occasionally offer one optional bonus `hard` step
- the bonus `hard` step does not add to homework-left or round-left counters
- when bonus `hard` is ready or cleared, the progress circle marks that word with `🔥`

Round flow also has a separate combo mechanic:

- after `4` correct answers in a row, the next base homework word is asked in `hard`
- every additional correct combo-hard answer keeps the next base homework word in `hard`
- one mistake resets the combo chain
- the combo chain is session-based, not a permanent homework requirement
- when a word closes with a random bonus `hard` and a combo activates at the same time, the bonus `hard` stays on that same word first, and the combo-hard continues on the next base word
- the progress circle shows a compact `4-dot` combo indicator while the streak charges
- when the combo is active, all `4` dots light up

The deadline helps organize the task, but homework is finished only when the assigned words actually reach their required state.

## Homework feedback in chat

During a homework round, the learner now sees:

- the regular answer feedback
- weekly points feedback
- a homework progress line with remaining words and estimated rounds
- a homework progress visual message that is updated across the flow

This feedback is shown without creating a separate scoring path. The existing answer validation and scoring logic remain the source of truth.

## Admin homework flow

Admins are resolved through the runtime role table, with `ADMIN_USER_IDS` only used to bootstrap the first elevated users into that table.

### Assign homework

1. Open `/assign`.
2. Tap **Assign homework**.
3. Choose the homework format.
4. Choose source:
   - `recent`
   - `topic`
   - `manual`
5. Select recipients from the known Telegram users list.
6. Confirm homework for the selected users.

Notes:

- admins no longer type raw `user_id` values by hand in the Telegram dialog
- active learner UX always launches homework
- if no explicit deadline is provided for homework, the current runtime uses a default deadline
- `topic` assigns all words from the chosen topic
- `manual` assigns all explicitly selected words
- `recent` assigns the full recent-word set available for that learner
- the learner, not the admin, chooses the round batch size at homework start

## Admin drill-down

Admins can inspect homework in depth:

1. Open **Users**.
2. Choose a visible user.
3. Review that user's homework list, including active/history status.
4. Open a specific homework.
5. Review homework details:
   - type
   - status
   - progress
   - attached words
   - homework stage status for each word when relevant

## Callback routes in active use

- `assign:menu`
- `assign:goals`
- `assign:progress`
- `assign:users`
- `assign:user:*`
- `assign:goal:*`
- `assign:admin_assign_goal`
- `assign:admin_goal_recipients:toggle:*`
- `assign:admin_goal_recipients:page:*`
- `assign:admin_goal_recipients:done`
- `start:launch:homework`
- `words:goal_period:homework`
- `words:goal_target:*`
- `words:goal_source:*`
- `words:goal_reset:*`
- `words:admin_goal_period:homework`
- `words:admin_goal_target:*`
- `words:admin_goal_source:*`
- `words:admin_goal_manual:toggle:*`
- `words:admin_goal_manual:page:*`
- `words:admin_goal_manual:done`
