from __future__ import annotations

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from englishbot import bot as bot_module
from englishbot.application.homework_progress_use_cases import GoalWordSource, LearnerProgressSummary
from englishbot.domain.models import GoalPeriod, GoalType
from englishbot.presentation.telegram_assignments_admin_ui import (
    admin_goal_manual_keyboard as ui_admin_goal_manual_keyboard,
    admin_goal_recipients_keyboard as ui_admin_goal_recipients_keyboard,
    assignment_goal_detail_keyboard as ui_assignment_goal_detail_keyboard,
    assignment_user_goals_keyboard as ui_assignment_user_goals_keyboard,
    assignment_users_keyboard as ui_assignment_users_keyboard,
)
from englishbot.presentation.telegram_assignments_ui import (
    admin_goal_custom_target_keyboard as ui_admin_goal_custom_target_keyboard,
    admin_goal_deadline_keyboard as ui_admin_goal_deadline_keyboard,
    admin_goal_period_keyboard as ui_admin_goal_period_keyboard,
    admin_goal_source_keyboard as ui_admin_goal_source_keyboard,
    admin_goal_target_keyboard as ui_admin_goal_target_keyboard,
    assign_menu_keyboard as ui_assign_menu_keyboard,
    goal_list_keyboard as ui_goal_list_keyboard,
)
from englishbot.presentation.telegram_views import build_assignment_menu_view
from englishbot.telegram.flow_tracking import delete_message_if_possible


def _admin_goal_manual_keyboard(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    page: int,
):
    from englishbot.telegram.interaction import get_admin_goal_creation_state

    items = bot_module._content_store(context).list_all_vocabulary()
    selected = set(get_admin_goal_creation_state(context).manual_word_ids)
    keyboard, normalized_page = ui_admin_goal_manual_keyboard(
        tg=bot_module._tg,
        items=items,
        selected_word_ids=selected,
        page=page,
        language=bot_module._telegram_ui_language(context, user),
    )
    bot_module._set_user_data(context, "admin_goal_manual_page", normalized_page)
    return keyboard


def _admin_goal_recipients_keyboard(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    page: int,
):
    from englishbot.telegram.interaction import get_admin_goal_creation_state

    items = bot_module._known_assignment_users(
        context,
        viewer_user_id=user.id,
        viewer_username=getattr(user, "username", None),
    )
    selected = set(get_admin_goal_creation_state(context).recipient_user_ids)
    keyboard, normalized_page = ui_admin_goal_recipients_keyboard(
        tg=bot_module._tg,
        items=items,
        selected_user_ids=selected,
        page=page,
        language=bot_module._telegram_ui_language(context, user),
    )
    bot_module._set_user_data(context, "admin_goal_recipients_page", normalized_page)
    return keyboard


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
            reply_markup=ui_goal_list_keyboard(
                tg=bot_module._tg,
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
    from englishbot.telegram.interaction import clear_self_goal_target_interaction

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    clear_self_goal_target_interaction(context)
    await query.edit_message_text(
        bot_module._tg("self_goal_setup_disabled", context=context, user=user),
        reply_markup=build_assignment_menu_view(
            text=bot_module._tg("assign_menu_title", context=context, user=user),
            reply_markup=ui_assign_menu_keyboard(
                tg=bot_module._tg,
                is_admin=bool(user and bot_module._is_admin(user.id, context)),
                guide_web_app_url=bot_module._assignment_guide_web_app_url(context, user=user),
                admin_web_app_url=bot_module._admin_web_app_url(context, user=user),
                language=bot_module._telegram_ui_language(context, user),
            ),
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
    from englishbot.telegram.interaction import start_admin_goal_creation_state

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not bot_module._is_admin(user.id, context):
        await query.edit_message_text(bot_module._tg("admin_only", context=context, user=user))
        return
    start_admin_goal_creation_state(context)
    await query.edit_message_text(
        bot_module._tg("assign_setup_intro", context=context, user=user),
        reply_markup=ui_admin_goal_period_keyboard(
            tg=bot_module._tg,
            language=bot_module._telegram_ui_language(context, user)
        ),
    )


async def admin_goal_period_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram.interaction import update_admin_goal_creation_state

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    update_admin_goal_creation_state(
        context,
        goal_period=GoalPeriod.HOMEWORK.value,
        goal_type=GoalType.WORD_LEVEL_HOMEWORK.value,
    )
    await query.edit_message_text(
        bot_module._tg("goal_source_prompt", context=context, user=user),
        reply_markup=ui_admin_goal_source_keyboard(
            tg=bot_module._tg,
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
        reply_markup=ui_admin_goal_target_keyboard(
            tg=bot_module._tg,
            language=bot_module._telegram_ui_language(context, user)
        ),
    )


async def admin_goal_target_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram.interaction import start_admin_goal_prompt_interaction
    from englishbot.telegram.interaction import update_admin_goal_creation_state

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    target = query.data.split(":")[-1]
    if target == "custom":
        start_admin_goal_prompt_interaction(
            context,
            mode=bot_module._ADMIN_GOAL_AWAITING_TARGET_TEXT,
            chat_id=getattr(getattr(query, "message", None), "chat_id", None),
            message_id=getattr(getattr(query, "message", None), "message_id", None),
        )
        await query.edit_message_text(
            bot_module._tg("goal_target_custom_prompt", context=context, user=user),
            reply_markup=ui_admin_goal_custom_target_keyboard(
                tg=bot_module._tg,
                language=bot_module._telegram_ui_language(context, user)
            ),
        )
        return
    update_admin_goal_creation_state(context, target_count=int(target))
    await query.edit_message_text(
        bot_module._tg("goal_source_prompt", context=context, user=user),
        reply_markup=ui_admin_goal_source_keyboard(
            tg=bot_module._tg,
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
        reply_markup=ui_admin_goal_source_keyboard(
            tg=bot_module._tg,
            language=bot_module._telegram_ui_language(context, user)
        ),
    )


async def admin_goal_source_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram.interaction import update_admin_goal_creation_state

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    if query.data.startswith("words:admin_goal_source:topic:"):
        update_admin_goal_creation_state(
            context,
            source=f"topic:{query.data.split(':', 4)[-1]}",
        )
        await query.edit_message_text(
            bot_module._tg("assign_select_users_prompt", context=context, user=user),
            reply_markup=_admin_goal_recipients_keyboard(context=context, user=user, page=0),
        )
        return
    source = query.data.split(":")[-1]
    update_admin_goal_creation_state(context, source=source)
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
        update_admin_goal_creation_state(context, manual_word_ids=set())
        await query.edit_message_text(
            bot_module._tg("goal_source_manual_prompt", context=context, user=user),
            reply_markup=_admin_goal_manual_keyboard(context=context, user=user, page=0),
        )
        return
    await query.edit_message_text(
        bot_module._tg("assign_select_users_prompt", context=context, user=user),
        reply_markup=_admin_goal_recipients_keyboard(context=context, user=user, page=0),
    )


async def admin_goal_manual_toggle_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram.interaction import (
        get_admin_goal_creation_state,
        update_admin_goal_creation_state,
    )

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    state = get_admin_goal_creation_state(context)
    if query.data.startswith("words:admin_goal_manual:page:"):
        page = int(query.data.split(":")[-1])
    else:
        word_id = query.data.split(":", 4)[-1]
        selected = set(state.manual_word_ids)
        if word_id in selected:
            selected.remove(word_id)
        else:
            selected.add(word_id)
        page = int(context.user_data.get("admin_goal_manual_page", 0))
        update_admin_goal_creation_state(context, manual_word_ids=selected)
    await query.edit_message_text(
        bot_module._tg("goal_source_manual_prompt", context=context, user=user),
        reply_markup=_admin_goal_manual_keyboard(context=context, user=user, page=page),
    )


async def admin_goal_manual_done_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram.interaction import get_admin_goal_creation_state

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not get_admin_goal_creation_state(context).manual_word_ids:
        await query.edit_message_text(bot_module._tg("goal_manual_empty", context=context, user=user))
        return
    await query.edit_message_text(
        bot_module._tg("assign_select_users_prompt", context=context, user=user),
        reply_markup=_admin_goal_recipients_keyboard(context=context, user=user, page=0),
    )


async def admin_goal_recipients_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram.interaction import (
        clear_admin_goal_prompt_interaction,
        get_admin_goal_creation_state,
        start_admin_goal_prompt_interaction,
        update_admin_goal_creation_state,
    )

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    if query.data.startswith("assign:admin_goal_recipients:page:"):
        if context.user_data.get("words_flow_mode") == bot_module._ADMIN_GOAL_AWAITING_DEADLINE_TEXT:
            clear_admin_goal_prompt_interaction(context)
        page = int(query.data.split(":")[-1])
    elif query.data == "assign:admin_goal_recipients:done":
        if not get_admin_goal_creation_state(context).recipient_user_ids:
            await query.edit_message_text(bot_module._tg("assign_select_users_empty", context=context, user=user))
            return
        context.user_data.pop("admin_goal_deadline_date", None)
        start_admin_goal_prompt_interaction(
            context,
            mode=bot_module._ADMIN_GOAL_AWAITING_DEADLINE_TEXT,
            chat_id=getattr(getattr(query, "message", None), "chat_id", None),
            message_id=getattr(getattr(query, "message", None), "message_id", None),
        )
        await query.edit_message_text(
            bot_module._tg("admin_goal_deadline_prompt", context=context, user=user),
            reply_markup=ui_admin_goal_deadline_keyboard(
                tg=bot_module._tg,
                language=bot_module._telegram_ui_language(context, user)
            ),
        )
        return
    else:
        target_user_id = int(query.data.split(":")[-1])
        state = get_admin_goal_creation_state(context)
        selected = set(state.recipient_user_ids)
        if target_user_id in selected:
            selected.remove(target_user_id)
        else:
            selected.add(target_user_id)
        update_admin_goal_creation_state(context, recipient_user_ids=selected)
        page = state.recipients_page
    await query.edit_message_text(
        bot_module._tg("assign_select_users_prompt", context=context, user=user),
        reply_markup=_admin_goal_recipients_keyboard(context=context, user=user, page=page),
    )


async def admin_goal_deadline_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram.interaction import start_admin_goal_prompt_interaction
    from englishbot.telegram.interaction import update_admin_goal_creation_state

    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer()
    option = query.data.split(":")[-1]
    if option == "custom":
        start_admin_goal_prompt_interaction(
            context,
            mode=bot_module._ADMIN_GOAL_AWAITING_DEADLINE_TEXT,
            chat_id=getattr(getattr(query, "message", None), "chat_id", None),
            message_id=getattr(getattr(query, "message", None), "message_id", None),
        )
        await query.edit_message_text(
            bot_module._tg("admin_goal_deadline_custom_prompt", context=context, user=user),
            reply_markup=ui_admin_goal_deadline_keyboard(
                tg=bot_module._tg,
                language=bot_module._telegram_ui_language(context, user)
            ),
        )
        return
    if option == "none":
        context.user_data["admin_goal_deadline_date"] = None
    elif option == "today":
        update_admin_goal_creation_state(
            context,
            deadline_date=bot_module.datetime.now(bot_module.UTC).date().isoformat(),
        )
    elif option == "tomorrow":
        update_admin_goal_creation_state(
            context,
            deadline_date=(
            bot_module.datetime.now(bot_module.UTC).date() + bot_module.timedelta(days=1)
        ).isoformat(),
        )
    elif option == "week_end":
        today = bot_module.datetime.now(bot_module.UTC).date()
        days_until_sunday = 6 - today.weekday()
        update_admin_goal_creation_state(
            context,
            deadline_date=(
            today + bot_module.timedelta(days=max(days_until_sunday, 0))
        ).isoformat(),
        )
    else:
        days = int(option.removesuffix("d"))
        update_admin_goal_creation_state(
            context,
            deadline_date=(
            bot_module.datetime.now(bot_module.UTC).date() + bot_module.timedelta(days=days)
        ).isoformat(),
        )
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
        reply_markup=ui_assignment_users_keyboard(
            tg=bot_module._tg,
            users=users,
            language=bot_module._telegram_ui_language(context, user),
        ),
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
        reply_markup=ui_assignment_user_goals_keyboard(
            tg=bot_module._tg,
            user_id=target_user_id,
            goals=goals,
            language=bot_module._telegram_ui_language(context, user),
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
        reply_markup=ui_assignment_goal_detail_keyboard(
            tg=bot_module._tg,
            user_id=target_user_id,
            language=bot_module._telegram_ui_language(context, user),
        ),
    )


async def goal_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from englishbot.telegram.interaction import (
        clear_admin_goal_prompt_interaction,
        clear_self_goal_target_interaction,
        get_admin_goal_prompt_mode,
        is_self_goal_target_interaction,
        update_admin_goal_creation_state,
    )

    message = update.effective_message
    user = update.effective_user
    if message is None or message.text is None or user is None:
        return
    if is_self_goal_target_interaction(context):
        clear_self_goal_target_interaction(context)
        await bot_module.send_telegram_view(
            message,
            bot_module.build_status_view(
                text=bot_module._tg("self_goal_setup_disabled", context=context, user=user),
                reply_markup=build_assignment_menu_view(
                    text=bot_module._tg("assign_menu_title", context=context, user=user),
                    reply_markup=ui_assign_menu_keyboard(
                        tg=bot_module._tg,
                        is_admin=bool(user and bot_module._is_admin(user.id, context)),
                        guide_web_app_url=bot_module._assignment_guide_web_app_url(context, user=user),
                        admin_web_app_url=bot_module._admin_web_app_url(context, user=user),
                        language=bot_module._telegram_ui_language(context, user),
                    ),
                ).reply_markup,
            ),
        )
        return
    flow_mode = get_admin_goal_prompt_mode(context)
    if flow_mode not in {
        bot_module._ADMIN_GOAL_AWAITING_TARGET_TEXT,
        bot_module._ADMIN_GOAL_AWAITING_DEADLINE_TEXT,
    }:
        return
    if flow_mode == bot_module._ADMIN_GOAL_AWAITING_TARGET_TEXT:
        prompt_reply_markup = ui_admin_goal_custom_target_keyboard(
            tg=bot_module._tg,
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
        update_admin_goal_creation_state(context, target_count=target_count)
        clear_admin_goal_prompt_interaction(context)
        next_reply_markup = ui_admin_goal_source_keyboard(
            tg=bot_module._tg,
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
        await delete_message_if_possible(context, message=message)
        return

    deadline_text = message.text.strip()
    try:
        parsed_deadline = bot_module.datetime.strptime(deadline_text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        prompt_reply_markup = ui_admin_goal_deadline_keyboard(
            tg=bot_module._tg,
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
    update_admin_goal_creation_state(context, deadline_date=parsed_deadline)
    clear_admin_goal_prompt_interaction(context)
    await delete_message_if_possible(context, message=message)
    await bot_module._finish_admin_goal_creation(query_or_message=message, context=context, user=user)
