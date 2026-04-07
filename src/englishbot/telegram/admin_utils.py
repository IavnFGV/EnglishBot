from __future__ import annotations

import hmac
import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def makeadmin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import englishbot.bot as bot_module

    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    bot_module._telegram_user_login_repository(context).record(
        user_id=user.id,
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
        language_code=getattr(user, "language_code", None),
    )

    if not context.args:
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(
                text="Usage: /makeadmin <telegram_id> [bootstrap_secret]"
            ),
        )
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(text="The target telegram_id must be an integer."),
        )
        return

    provided_secret = context.args[1] if len(context.args) > 1 else ""
    role_repository = bot_module._telegram_user_role_repository(context)
    admin_ids = role_repository.list_memberships().get("admin", frozenset())
    requester_is_admin = user.id in admin_ids
    bootstrap_secret = str(
        bot_module._optional_bot_data(context, "admin_bootstrap_secret", default="")
    ).strip()
    secret_is_valid = bool(
        bootstrap_secret and provided_secret and hmac.compare_digest(provided_secret, bootstrap_secret)
    )

    if not requester_is_admin and not secret_is_valid:
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(
                text=(
                    "Access denied. Current admins can use /makeadmin directly. "
                    "Otherwise provide a valid bootstrap secret."
                )
            ),
        )
        return

    try:
        role_repository.grant(user_id=target_user_id, role="admin")
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to grant admin role via /makeadmin target_user_id=%s requester_user_id=%s",
            target_user_id,
            user.id,
        )
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(text="Failed to grant the admin role."),
        )
        return

    updated_admin_ids = role_repository.list_memberships().get("admin", frozenset())
    if target_user_id not in updated_admin_ids:
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(text="Failed to grant the admin role."),
        )
        return

    await bot_module.send_telegram_view(
        message,
        bot_module.build_status_view(
            text=f"Admin role granted to Telegram user {target_user_id}."
        ),
    )


async def clear_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import englishbot.bot as bot_module

    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    if len(context.args) != 2:
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(text="Usage: /clearuser <telegram_id> <bootstrap_secret>"),
        )
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(text="The target telegram_id must be an integer."),
        )
        return

    provided_secret = str(context.args[1]).strip()
    bootstrap_secret = str(
        bot_module._optional_bot_data(context, "admin_bootstrap_secret", default="")
    ).strip()
    requester_is_admin = bot_module._is_admin(user.id, context)
    secret_is_valid = bool(
        bootstrap_secret and provided_secret and hmac.compare_digest(provided_secret, bootstrap_secret)
    )
    if not requester_is_admin and not secret_is_valid:
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(
                text=(
                    "Access denied. Current admins can use /clearuser directly. "
                    "Otherwise provide a valid bootstrap secret."
                )
            ),
        )
        return

    try:
        bot_module._service(context).discard_active_session(user_id=target_user_id)
        cleared = bot_module._content_store(context).clear_user_learning_data(user_id=target_user_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to clear learning data target_user_id=%s requester_user_id=%s",
            target_user_id,
            user.id,
        )
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(text="Failed to clear the user's learning data."),
        )
        return

    recent_activity = bot_module._optional_bot_data(context, "recent_assignment_activity_by_user")
    if isinstance(recent_activity, dict):
        recent_activity.pop(target_user_id, None)
    preview_ids = bot_module._optional_bot_data(context, "word_import_preview_message_ids")
    if isinstance(preview_ids, dict):
        preview_ids.pop(target_user_id, None)
    cancel_add_words = bot_module._optional_bot_data(context, "add_words_cancel_use_case")
    execute_cancel = getattr(cancel_add_words, "execute", None)
    if callable(execute_cancel):
        try:
            execute_cancel(user_id=target_user_id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to discard add-words flow target_user_id=%s", target_user_id)

    await bot_module.send_telegram_view(
        message,
        bot_module.build_status_view(
            text=(
                f"Learning data cleared for Telegram user {target_user_id}. "
                f"Goals: {cleared['goals']}, sessions: {cleared['sessions']}, "
                f"stats: {cleared['word_stats']}."
            )
        ),
    )
