# Homework + Progress in Telegram

## User flow

1. Open `/words`.
2. Tap **🎯 Мои ДЗ / 🎯 My homework** to see active goals and create a new one.
3. Goal setup supports:
   - period: `daily`, `weekly`, `homework`
   - target count (preset or custom)
   - source: recent words or all words
4. Tap **📈 Мой прогресс / 📈 My progress** to see:
   - correct / incorrect answers
   - streak
   - weekly points
   - active goals with completion percent

## Admin flow

Admins are resolved through `ADMIN_USER_IDS` (runtime config). In `/words` admins also see:

- **🛠 Назначить ДЗ / Assign homework**
- **👥 Прогресс пользователей / Users progress**

### Assign homework

1. Open **Assign homework**.
2. Send one or many `user_id` values (`1,2,3` format).
3. Choose period.
4. Choose target count.
5. Choose source:
   - `recent`
   - `topic`
   - `all`
   - `manual` (checkbox-like pagination in callback UI)

### Users progress

Admin overview shows per user:

- active goals count
- completed goals count
- aggregate progress percent
- last activity date

## Added callback routes

- `words:admin_assign_goal`
- `words:admin_goal_period:*`
- `words:admin_goal_target:*`
- `words:admin_goal_source:*`
- `words:admin_goal_manual:toggle:*`
- `words:admin_goal_manual:page:*`
- `words:admin_goal_manual:done`
- `words:admin_users_progress`

## Current limitations

- Admin assignment currently defaults goal type to `new_words` in Telegram UI.
- User-facing goal source selector in Telegram keeps the lightweight mode (`recent`/`all`).
