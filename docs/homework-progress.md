# Assignments + Progress in Telegram

## `/words`

`/words` is now only for vocabulary work:

- start training by topic
- add words
- edit published words
- edit published images

Homework, challenges, assignment review, and user overview are no longer mixed into this menu.

## `/assign`

`/assign` is the dedicated assignments area.

All users can open it and see:

- **🎯 My homework**
- **📈 My progress**
- **👥 Users**

### Visible users

- A regular user sees only themself in **Users**.
- An admin sees all known users from the Telegram user login table, including:
  - other admins
  - editors
  - regular users

The user list also shows compact role and progress data.

### Admin drill-down

Admins can now inspect assignments in depth:

1. Open **Users**.
2. Choose a visible user.
3. Review that user's assignment list, including active/history status.
4. Open a specific assignment.
5. Review assignment details:
   - period
   - goal type
   - status
   - progress
   - attached words
   - homework stage status for each word when the assignment is a real homework goal

## Admin assignment flow

Admins are resolved through `ADMIN_USER_IDS` (runtime config).

In `/assign`, admins also see:

- **🛠 Assign homework**

### Assign homework

1. Open `/assign`.
2. Tap **Assign homework**.
3. Choose period:
   - `daily`
   - `weekly`
   - `homework`
4. Choose target count.
5. Choose source:
   - `recent`
   - `topic`
   - `all`
   - `manual`
6. Select recipients from the known Telegram users list.
7. Confirm assignment to the selected users.

Notes:

- Admins no longer type raw `user_id` values by hand in the Telegram dialog.
- If period is `homework`, the admin flow now creates `word_level_homework` goals, not plain `new_words` goals.

## Added callback routes

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
- `words:goal_period:*`
- `words:goal_target:*`
- `words:goal_source:*`
- `words:goal_reset:*`
- `words:admin_goal_period:*`
- `words:admin_goal_target:*`
- `words:admin_goal_source:*`
- `words:admin_goal_manual:toggle:*`
- `words:admin_goal_manual:page:*`
- `words:admin_goal_manual:done`
