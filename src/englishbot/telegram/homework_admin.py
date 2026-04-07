from __future__ import annotations

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from englishbot import bot as bot_module
from englishbot.domain.models import GoalPeriod, GoalType
from englishbot.application.homework_progress_use_cases import GoalWordSource, LearnerProgressSummary


async def words_goals_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    summary = bot_module._homework_progress_use_case(context).get_summary(user_id=user.id)
    homework_goals = [
        item for item in summary.active_goals if item.goal.goal_period is GoalPeriod.HOMEWORK
    ]
    filtered_summary = LearnerProgressSummary(
        correct_answers=summary.correct_answers,
        incorrect_answers=summary.incorrect_answers,
        game_streak_days=summary.game_streak_days,
        weekly_points=summary.weekly_points,
        active_goals=homework_goals,
    )
    try:
        await query.edit_message_text(
            bot_module._render_progress_text(context=context, user=user),
            reply_markup=bot_module._goal_list_keyboard(
                goals=filtered_summary.active_goals,
                language=bot_module._telegram_ui_language(context, user),
            ),
        )
    except BadRequest as error:
        if "Message is not modified" not in str(error):
            raise


async def words_progress_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await words_goals_callback_handler(update, context)


async def goal_setup_disabled_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    bot_module._clear_self_goal_setup_state(context)
    await query.edit_message_text(
        bot_module._tg("self_goal_setup_disabled", context=context, user=user),
        reply_markup=bot_module._assign_menu_view(
            text=bot_module._tg("assign_menu_title", context=context, user=user),
            context=context,
            user=user,
        ).reply_markup,
    )


async def goal_type_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    return


async def goal_reset_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    goal_id = query.data.split(":")[-1]
    reset = bot_module._homework_progress_use_case(context).reset_goal(
        user_id=user.id,
        goal_id=goal_id,
    )
    await query.edit_message_text(
        bot_module._tg(
            "goal_reset_done" if reset else "goal_reset_not_found",
            context=context,
            user=user,
        )
    )


async def admin_assign_goal_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not bot_module._is_admin(user.id, context):
        await query.edit_message_text(bot_module._tg("admin_only", context=context, user=user))
        return
    for key in (
        "admin_goal_period",
        "admin_goal_type",
        "admin_goal_target_count",
        "admin_goal_source",
        "admin_goal_deadline_date",
        "admin_goal_manual_word_ids",
        "admin_goal_recipient_user_ids",
        "admin_goal_recipients_page",
    ):
        context.user_data.pop(key, None)
    context.user_data["admin_goal_recipient_user_ids"] = set()
    await query.edit_message_text(
        bot_module._tg("assign_setup_intro", context=context, user=user),
        reply_markup=bot_module._admin_goal_period_keyboard(
            language=bot_module._telegram_ui_language(context, user)
        ),
    )


async def admin_goal_period_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    context.user_data["admin_goal_period"] = GoalPeriod.HOMEWORK.value
    context.user_data["admin_goal_type"] = GoalType.WORD_LEVEL_HOMEWORK.value
    await query.edit_message_text(
        bot_module._tg("goal_source_prompt", context=context, user=user),
        reply_markup=bot_module._admin_goal_source_keyboard(
            language=bot_module._telegram_ui_language(context, user)
        ),
    )


async def admin_goal_target_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await query.edit_message_text(
        bot_module._tg("goal_target_prompt", context=context, user=user),
        reply_markup=bot_module._admin_goal_target_keyboard(
            language=bot_module._telegram_ui_language(context, user)
        ),
    )


async def admin_goal_target_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    target = query.data.split(":")[-1]
    if target == "custom":
        context.user_data["words_flow_mode"] = bot_module._ADMIN_GOAL_AWAITING_TARGET_TEXT
        bot_module._remember_expected_user_input(
            context,
            chat_id=getattr(getattr(query, "message", None), "chat_id", None),
            message_id=getattr(getattr(query, "message", None), "message_id", None),
        )
        await query.edit_message_text(
            bot_module._tg("goal_target_custom_prompt", context=context, user=user),
            reply_markup=bot_module._admin_goal_custom_target_keyboard(
                language=bot_module._telegram_ui_language(context, user)
            ),
        )
        return
    context.user_data["admin_goal_target_count"] = int(target)
    await query.edit_message_text(
        bot_module._tg("goal_source_prompt", context=context, user=user),
        reply_markup=bot_module._admin_goal_source_keyboard(
            language=bot_module._telegram_ui_language(context, user)
        ),
    )


async def admin_goal_source_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    await query.edit_message_text(
        bot_module._tg("goal_source_prompt", context=context, user=user),
        reply_markup=bot_module._admin_goal_source_keyboard(
            language=bot_module._telegram_ui_language(context, user)
        ),
    )


async def admin_goal_source_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    if query.data.startswith("words:admin_goal_source:topic:"):
        context.user_data["admin_goal_source"] = f"topic:{query.data.split(':', 4)[-1]}"
        await query.edit_message_text(
            bot_module._tg("assign_select_users_prompt", context=context, user=user),
            reply_markup=bot_module._admin_goal_recipients_keyboard(context=context, user=user, page=0),
        )
        return
    source = query.data.split(":")[-1]
    context.user_data["admin_goal_source"] = source
    if source == GoalWordSource.TOPIC.value:
        topics = bot_module._service(context).list_topics()
        keyboard = bot_module.ui_goal_source_topic_keyboard(
            tg=bot_module._tg,
            topics=topics,
            language=bot_module._telegram_ui_language(context, user),
        )
        await query.edit_message_text(
            bot_module._tg("goal_source_topic_prompt", context=context, user=user),
            reply_markup=keyboard,
        )
        return
    if source == GoalWordSource.MANUAL.value:
        context.user_data["admin_goal_manual_word_ids"] = set()
        await query.edit_message_text(
            bot_module._tg("goal_source_manual_prompt", context=context, user=user),
            reply_markup=bot_module._admin_goal_manual_keyboard(context=context, user=user, page=0),
        )
        return
    await query.edit_message_text(
        bot_module._tg("assign_select_users_prompt", context=context, user=user),
        reply_markup=bot_module._admin_goal_recipients_keyboard(context=context, user=user, page=0),
    )


async def admin_goal_manual_toggle_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    if query.data.startswith("words:admin_goal_manual:page:"):
        page = int(query.data.split(":")[-1])
    else:
        word_id = query.data.split(":", 4)[-1]
        selected = set(context.user_data.get("admin_goal_manual_word_ids", set()))
        if word_id in selected:
            selected.remove(word_id)
        else:
            selected.add(word_id)
        context.user_data["admin_goal_manual_word_ids"] = selected
        page = int(context.user_data.get("admin_goal_manual_page", 0))
    await query.edit_message_text(
        bot_module._tg("goal_source_manual_prompt", context=context, user=user),
        reply_markup=bot_module._admin_goal_manual_keyboard(context=context, user=user, page=page),
    )


async def admin_goal_manual_done_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not context.user_data.get("admin_goal_manual_word_ids"):
        await query.edit_message_text(bot_module._tg("goal_manual_empty", context=context, user=user))
        return
    await query.edit_message_text(
        bot_module._tg("assign_select_users_prompt", context=context, user=user),
        reply_markup=bot_module._admin_goal_recipients_keyboard(context=context, user=user, page=0),
    )


async def admin_goal_recipients_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    if query.data.startswith("assign:admin_goal_recipients:page:"):
        if context.user_data.get("words_flow_mode") == bot_module._ADMIN_GOAL_AWAITING_DEADLINE_TEXT:
            context.user_data.pop("words_flow_mode", None)
            bot_module._clear_expected_user_input(context)
        page = int(query.data.split(":")[-1])
    elif query.data == "assign:admin_goal_recipients:done":
        if not context.user_data.get("admin_goal_recipient_user_ids"):
            await query.edit_message_text(bot_module._tg("assign_select_users_empty", context=context, user=user))
            return
        context.user_data.pop("admin_goal_deadline_date", None)
        context.user_data["words_flow_mode"] = bot_module._ADMIN_GOAL_AWAITING_DEADLINE_TEXT
        bot_module._remember_expected_user_input(
            context,
            chat_id=getattr(getattr(query, "message", None), "chat_id", None),
            message_id=getattr(getattr(query, "message", None), "message_id", None),
        )
        await query.edit_message_text(
            bot_module._tg("admin_goal_deadline_prompt", context=context, user=user),
            reply_markup=bot_module._admin_goal_deadline_keyboard(
                language=bot_module._telegram_ui_language(context, user)
            ),
        )
        return
    else:
        target_user_id = int(query.data.split(":")[-1])
        selected = set(context.user_data.get("admin_goal_recipient_user_ids", set()))
        if target_user_id in selected:
            selected.remove(target_user_id)
        else:
            selected.add(target_user_id)
        context.user_data["admin_goal_recipient_user_ids"] = selected
        page = int(context.user_data.get("admin_goal_recipients_page", 0))
    await query.edit_message_text(
        bot_module._tg("assign_select_users_prompt", context=context, user=user),
        reply_markup=bot_module._admin_goal_recipients_keyboard(context=context, user=user, page=page),
    )


async def admin_goal_deadline_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    option = query.data.split(":")[-1]
    if option == "custom":
        context.user_data["words_flow_mode"] = bot_module._ADMIN_GOAL_AWAITING_DEADLINE_TEXT
        bot_module._remember_expected_user_input(
            context,
            chat_id=getattr(getattr(query, "message", None), "chat_id", None),
            message_id=getattr(getattr(query, "message", None), "message_id", None),
        )
        await query.edit_message_text(
            bot_module._tg("admin_goal_deadline_custom_prompt", context=context, user=user),
            reply_markup=bot_module._admin_goal_deadline_keyboard(
                language=bot_module._telegram_ui_language(context, user)
            ),
        )
        return
    if option == "none":
        context.user_data["admin_goal_deadline_date"] = None
    elif option == "today":
        context.user_data["admin_goal_deadline_date"] = bot_module.datetime.now(bot_module.UTC).date().isoformat()
    elif option == "tomorrow":
        context.user_data["admin_goal_deadline_date"] = (
            bot_module.datetime.now(bot_module.UTC).date() + bot_module.timedelta(days=1)
        ).isoformat()
    elif option == "week_end":
        today = bot_module.datetime.now(bot_module.UTC).date()
        days_until_sunday = 6 - today.weekday()
        context.user_data["admin_goal_deadline_date"] = (
            today + bot_module.timedelta(days=max(days_until_sunday, 0))
        ).isoformat()
    else:
        days = int(option.removesuffix("d"))
        context.user_data["admin_goal_deadline_date"] = (
            bot_module.datetime.now(bot_module.UTC).date() + bot_module.timedelta(days=days)
        ).isoformat()
    await bot_module._finish_admin_goal_creation(query_or_message=query, context=context, user=user)


async def admin_users_progress_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    users = bot_module._known_assignment_users(
        context,
        viewer_user_id=user.id,
        viewer_username=getattr(user, "username", None),
    )
    if not users:
        await query.edit_message_text(bot_module._tg("assign_users_empty", context=context, user=user))
        return
    lines = [bot_module._tg("assign_users_title", context=context, user=user)]
    for item in users:
        lines.append(
            bot_module._tg(
                "assign_users_line",
                context=context,
                user=user,
                user_id=item.user_id,
                username=(f"@{item.username}" if item.username else "-"),
                roles=(", ".join(role for role in item.roles if role != "user") or "user"),
                active=item.active_goals_count,
                completed=item.completed_goals_count,
                percent=item.aggregate_percent,
                last_activity=(item.last_activity_at.date().isoformat() if item.last_activity_at else "-"),
            )
        )
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=bot_module._assignment_users_keyboard(context=context, user=user, users=users),
    )


async def assign_user_detail_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    target_user_id = int(query.data.split(":")[-1])
    users = bot_module._known_assignment_users(
        context,
        viewer_user_id=user.id,
        viewer_username=getattr(user, "username", None),
    )
    target = next((item for item in users if item.user_id == target_user_id), None)
    if target is None:
        await query.edit_message_text(bot_module._tg("assign_users_empty", context=context, user=user))
        return
    goals = bot_module._admin_user_goals_use_case(context).execute(user_id=target_user_id, include_history=True)
    await query.edit_message_text(
        bot_module._render_assignment_user_detail_text(context=context, user=user, item=target, goals=goals),
        reply_markup=bot_module._assignment_user_goals_keyboard(
            context=context,
            user_id=target_user_id,
            goals=goals,
            user=user,
        ),
    )


async def assign_goal_detail_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    _, _, user_id_raw, goal_id = query.data.split(":", 3)
    target_user_id = int(user_id_raw)
    detail = bot_module._admin_goal_detail_use_case(context).execute(user_id=target_user_id, goal_id=goal_id)
    if detail is None:
        await query.edit_message_text(bot_module._tg("assign_goal_detail_missing", context=context, user=user))
        return
    await query.edit_message_text(
        bot_module._render_assignment_goal_detail_text(context=context, user=user, detail=detail),
        reply_markup=bot_module._assignment_goal_detail_keyboard(
            context=context,
            user_id=target_user_id,
            user=user,
        ),
    )


async def goal_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or message.text is None or user is None:
        return
    flow_mode = context.user_data.get("words_flow_mode")
    if flow_mode == bot_module._GOAL_AWAITING_TARGET_TEXT:
        bot_module._clear_self_goal_setup_state(context)
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(
                text=bot_module._tg("self_goal_setup_disabled", context=context, user=user),
                reply_markup=bot_module._assign_menu_view(
                    text=bot_module._tg("assign_menu_title", context=context, user=user),
                    context=context,
                    user=user,
                ).reply_markup,
            ),
        )
        return
    if flow_mode not in {
        bot_module._ADMIN_GOAL_AWAITING_TARGET_TEXT,
        bot_module._ADMIN_GOAL_AWAITING_DEADLINE_TEXT,
    }:
        return
    if flow_mode == bot_module._ADMIN_GOAL_AWAITING_TARGET_TEXT:
        prompt_reply_markup = bot_module._admin_goal_custom_target_keyboard(
            language=bot_module._telegram_ui_language(context, user)
        )
        try:
            target_count = int(message.text.strip())
        except ValueError:
            edited = await bot_module._edit_expected_user_input_prompt(
                context,
                text=bot_module._tg("goal_target_custom_prompt", context=context, user=user),
                reply_markup=prompt_reply_markup,
            )
            if not edited:
                await message.reply_text(
                    bot_module._tg("goal_target_custom_prompt", context=context, user=user),
                    reply_markup=prompt_reply_markup,
                )
            return
        if target_count <= 0:
            edited = await bot_module._edit_expected_user_input_prompt(
                context,
                text=bot_module._tg("goal_target_custom_prompt", context=context, user=user),
                reply_markup=prompt_reply_markup,
            )
            if not edited:
                await message.reply_text(
                    bot_module._tg("goal_target_custom_prompt", context=context, user=user),
                    reply_markup=prompt_reply_markup,
                )
            return
        context.user_data["admin_goal_target_count"] = target_count
        context.user_data.pop("words_flow_mode", None)
        next_reply_markup = bot_module._admin_goal_source_keyboard(
            language=bot_module._telegram_ui_language(context, user)
        )
        edited = await bot_module._edit_expected_user_input_prompt(
            context,
            text=bot_module._tg("goal_source_prompt", context=context, user=user),
            reply_markup=next_reply_markup,
        )
        if not edited:
            await message.reply_text(
                bot_module._tg("goal_source_prompt", context=context, user=user),
                reply_markup=next_reply_markup,
            )
        await bot_module._delete_message_if_possible(context, message=message)
        bot_module._clear_expected_user_input(context)
        return

    deadline_text = message.text.strip()
    try:
        parsed_deadline = bot_module.datetime.strptime(deadline_text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        prompt_reply_markup = bot_module._admin_goal_deadline_keyboard(
            language=bot_module._telegram_ui_language(context, user)
        )
        edited = await bot_module._edit_expected_user_input_prompt(
            context,
            text=bot_module._tg("admin_goal_deadline_custom_prompt", context=context, user=user),
            reply_markup=prompt_reply_markup,
        )
        if not edited:
            await message.reply_text(
                bot_module._tg("admin_goal_deadline_custom_prompt", context=context, user=user),
                reply_markup=prompt_reply_markup,
            )
        return
    context.user_data["admin_goal_deadline_date"] = parsed_deadline
    context.user_data.pop("words_flow_mode", None)
    await bot_module._delete_message_if_possible(context, message=message)
    await bot_module._finish_admin_goal_creation(query_or_message=message, context=context, user=user)
