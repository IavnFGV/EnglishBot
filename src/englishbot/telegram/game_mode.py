from __future__ import annotations

import random
from datetime import UTC, datetime

from telegram import Update
from telegram.ext import ContextTypes

from englishbot import bot as bot_module
from englishbot.presentation.telegram_assignments_ui import start_menu_keyboard
from englishbot.presentation.telegram_game_ui import game_result_keyboard
from englishbot.presentation.telegram_views import build_start_menu_view


async def game_next_round_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    game_state = bot_module._game_state(context)
    user = update.effective_user
    if user is None:
        return
    topic_id = game_state.get("topic_id")
    lesson_id = game_state.get("lesson_id")
    mode_value = game_state.get("mode_value")
    if not topic_id or not mode_value:
        await query.edit_message_text(
            bot_module._tg("no_active_session_send_start", context=context, user=user)
        )
        return
    try:
        question = bot_module._start_training_session_with_ui_language(
            bot_module._service(context),
            user_id=user.id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=bot_module.TrainingMode(str(mode_value)),
            adaptive_per_word=True,
            ui_language=bot_module._telegram_ui_language(context, user),
        )
    except (bot_module.ApplicationError, ValueError) as error:
        await query.edit_message_text(str(error))
        return
    streak_days = bot_module._content_store(context).update_game_streak(
        user_id=user.id,
        played_at=datetime.now(UTC),
    )
    bot_module._set_user_data(
        context,
        bot_module._GAME_STATE_KEY,
        {
            "active": True,
            "topic_id": topic_id,
            "lesson_id": lesson_id,
            "mode_value": mode_value,
            "session_stars": 0,
            "correct_answers": 0,
            "streak_days": streak_days,
        },
    )
    bot_module._set_user_data(
        context,
        "awaiting_text_answer",
        bot_module._expects_text_answer_for_question(question),
    )
    await query.edit_message_text(
        bot_module._tg("game_round_started", context=context, user=user, streak_days=streak_days)
    )
    await bot_module._send_question(update, context, question)


async def game_repeat_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    bot_module._pop_user_data(context, bot_module._GAME_STATE_KEY, default=None)
    bot_module._clear_medium_task_state(context)
    await query.edit_message_text(bot_module._tg("start_menu_title", context=context, user=user))
    summary = bot_module._learner_assignment_launch_summary_use_case(context).execute(user_id=user.id)
    await bot_module.send_telegram_view(
        query.message,
        build_start_menu_view(
            text=bot_module._render_start_menu_text(context=context, user=user, summary=summary),
            reply_markup=start_menu_keyboard(
                tg=bot_module._tg,
                summary=summary,
                guide_web_app_url=bot_module._assignment_guide_web_app_url(context, user=user),
                admin_web_app_url=bot_module._admin_web_app_url(context, user=user),
                language=bot_module._telegram_ui_language(context, user),
            ),
        ),
    )


async def send_game_feedback(
    message,
    outcome,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    game_state = bot_module._game_state(context)
    if not isinstance(game_state, dict):
        return
    session_stars = int(game_state.get("session_stars", 0))
    correct_answers = int(game_state.get("correct_answers", 0))
    if outcome.result.is_correct:
        session_stars += bot_module._GAME_STAR_REWARD_CORRECT
        correct_answers += 1
        feedback = bot_module._tg("game_correct", context=context, user=getattr(message, "from_user", None))
    else:
        feedback = bot_module._tg("game_almost", context=context, user=getattr(message, "from_user", None))
    game_state["session_stars"] = session_stars
    game_state["correct_answers"] = correct_answers
    if outcome.summary is not None:
        progress = outcome.summary.total_questions
    else:
        active_session = bot_module._service(context).get_active_session(user_id=message.from_user.id)
        progress = 1 if active_session is None else max(1, active_session.current_position - 1)
    text = bot_module._tg(
        "game_feedback",
        context=context,
        user=getattr(message, "from_user", None),
        feedback=feedback,
        progress=progress,
        total=5,
        stars=session_stars,
    )
    await message.reply_text(text)


async def finish_game_session(
    message,
    outcome,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    user = getattr(message, "from_user", None)
    if user is None:
        return
    game_state = bot_module._game_state(context)
    if not isinstance(game_state, dict):
        return
    session_stars = int(game_state.get("session_stars", 0))
    chest_stars = random.choice(bot_module._GAME_CHEST_REWARDS)
    total_earned = session_stars + chest_stars
    total_stars = bot_module._content_store(context).add_game_stars(user_id=user.id, stars=total_earned)
    streak_days = bot_module._content_store(context).update_game_streak(
        user_id=user.id,
        played_at=datetime.now(UTC),
    )
    await message.reply_text(
        bot_module._tg(
            "game_session_complete",
            context=context,
            user=user,
            session_stars=session_stars,
            chest_stars=chest_stars,
            total_earned=total_earned,
            total_stars=total_stars,
            streak_days=streak_days,
        ),
        reply_markup=game_result_keyboard(
            tg=bot_module._tg,
            language=bot_module._telegram_ui_language(context, user),
        ),
    )
    bot_module._set_user_data(
        context,
        bot_module._GAME_STATE_KEY,
        {
            "active": False,
            "topic_id": game_state.get("topic_id"),
            "lesson_id": game_state.get("lesson_id"),
            "mode_value": game_state.get("mode_value"),
        },
    )
    await bot_module._flush_pending_notifications_for_user(context, user_id=user.id)
