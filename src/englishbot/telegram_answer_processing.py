from __future__ import annotations

from collections.abc import Callable


async def process_answer(
    update,
    context,
    answer: str,
    *,
    service: Callable,
    clear_medium_task_state: Callable,
    tg: Callable,
    assignment_kind_from_session: Callable,
    record_assignment_activity: Callable,
    delete_tracked_flow_messages: Callable,
    training_question_tag: str,
    send_game_feedback: Callable,
    expects_text_answer_for_question: Callable,
    send_question: Callable,
    finish_game_session: Callable,
    raw_training_session_by_id: Callable,
    assignment_kind_and_goal_id_from_source_tag: Callable,
    start_assignment_round_use_case_or_none: Callable,
    execute_assignment_start_use_case: Callable,
    telegram_ui_language: Callable,
    collect_goal_feedback_update: Callable,
    send_feedback: Callable,
    send_or_update_assignment_progress_message: Callable,
    schedule_goal_completed_notifications: Callable,
    flush_pending_notifications_for_user: Callable,
    homework_progress_use_case: Callable,
    answer_outcome_type,
    invalid_session_state_error_type,
    application_error_type,
) -> None:
    resolved_service = service(context)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    clear_medium_task_state(context)
    active_session_before_submit = resolved_service.get_active_session(user_id=user.id)
    feedback_update = None
    if context.application.bot_data.get("homework_progress_use_case") is not None:
        before_summary = homework_progress_use_case(context).get_summary(user_id=user.id)
    else:
        before_summary = None
    try:
        outcome = resolved_service.submit_answer(user_id=user.id, answer=answer)
    except invalid_session_state_error_type:
        context.user_data["awaiting_text_answer"] = False
        clear_medium_task_state(context)
        await message.reply_text(tg("no_active_session_begin", context=context, user=user))
        return
    except application_error_type as error:
        await message.reply_text(str(error))
        return
    if assignment_kind_from_session(active_session_before_submit) is not None:
        record_assignment_activity(context, user_id=user.id)
    active_session_id = getattr(active_session_before_submit, "session_id", None)
    if isinstance(active_session_id, str):
        await delete_tracked_flow_messages(
            context,
            flow_id=active_session_id,
            tag=training_question_tag,
        )
    game_state = context.user_data.get("game_mode_state")
    if isinstance(game_state, dict) and game_state.get("active"):
        await send_game_feedback(message, outcome, context)
        if outcome.next_question is not None:
            context.user_data["awaiting_text_answer"] = expects_text_answer_for_question(
                outcome.next_question
            )
            await send_question(update, context, outcome.next_question)
        else:
            context.user_data["awaiting_text_answer"] = False
            clear_medium_task_state(context)
            await finish_game_session(message, outcome, context)
        return
    context.user_data["awaiting_text_answer"] = bool(
        outcome.next_question is not None
        and expects_text_answer_for_question(outcome.next_question)
    )
    raw_completed_assignment_session = raw_training_session_by_id(
        context,
        session_id=active_session_id,
    )
    continuation_question = None
    assignment_kind = assignment_kind_from_session(active_session_before_submit)
    _, assignment_goal_id = assignment_kind_and_goal_id_from_source_tag(
        getattr(active_session_before_submit, "source_tag", None),
    )
    start_assignment_use_case = start_assignment_round_use_case_or_none(context)
    if (
        outcome.next_question is None
        and outcome.summary is not None
        and assignment_kind is not None
        and start_assignment_use_case is not None
    ):
        raw_goal_id = None
        if raw_completed_assignment_session is not None:
            _, raw_goal_id = assignment_kind_and_goal_id_from_source_tag(
                getattr(raw_completed_assignment_session, "source_tag", None),
            )
        try:
            continuation_question = execute_assignment_start_use_case(
                start_assignment_use_case,
                user_id=user.id,
                kind=assignment_kind,
                goal_id=raw_goal_id or assignment_goal_id,
                combo_correct_streak=int(
                    getattr(raw_completed_assignment_session, "combo_correct_streak", 0) or 0
                ),
                combo_hard_active=bool(
                    getattr(raw_completed_assignment_session, "combo_hard_active", False)
                ),
                ui_language=telegram_ui_language(context, user),
            )
        except ValueError:
            continuation_question = None
    if continuation_question is not None:
        context.user_data["awaiting_text_answer"] = expects_text_answer_for_question(
            continuation_question
        )
    active_session_for_feedback = service(context).get_active_session(user_id=user.id)
    if before_summary is not None:
        feedback_update = collect_goal_feedback_update(
            context=context,
            user=user,
            before_summary=before_summary,
        )
    feedback_outcome = outcome
    if continuation_question is not None and outcome.summary is not None:
        feedback_outcome = answer_outcome_type(
            result=outcome.result,
            summary=None,
            next_question=None,
        )
    await send_feedback(
        message,
        feedback_outcome,
        context=context,
        active_session=active_session_for_feedback or active_session_before_submit,
        user=user,
        feedback_update=feedback_update,
    )
    if assignment_kind is not None:
        await send_or_update_assignment_progress_message(
            context,
            message=message,
            user=user,
            kind=assignment_kind,
            active_session=active_session_for_feedback or active_session_before_submit,
        )
    if feedback_update is not None and feedback_update.completed_goals:
        schedule_goal_completed_notifications(
            context,
            learner=user,
            completed_goals=feedback_update.completed_goals,
        )
    if continuation_question is not None:
        await send_question(update, context, continuation_question)
    elif outcome.next_question is not None:
        await send_question(update, context, outcome.next_question)
    else:
        await flush_pending_notifications_for_user(context, user_id=user.id)


async def send_feedback(
    message,
    outcome,
    *,
    context,
    active_session=None,
    user=None,
    feedback_update=None,
    build_answer_feedback_view: Callable,
    assignment_kind_from_session: Callable,
    assignment_kind_and_goal_id_from_source_tag: Callable,
    assignment_round_progress_view: Callable,
    render_assignment_round_progress_text: Callable,
    assignment_round_complete_keyboard: Callable,
    telegram_ui_language: Callable,
    compact_assignment_feedback_text: Callable,
    render_feedback_update_text: Callable,
    delete_tracked_flow_messages: Callable,
    track_flow_message: Callable,
    training_feedback_tag: str,
    message_chat_id: Callable,
    tg: Callable,
) -> None:
    feedback_user = user if user is not None else getattr(message, "from_user", None)
    feedback_user_id = getattr(feedback_user, "id", None)
    view = build_answer_feedback_view(
        outcome,
        translate=tg,
        user=feedback_user,
    )
    reply_markup = None
    assignment_progress_text = ""
    assignment_kind = assignment_kind_from_session(active_session) if active_session is not None else None
    assignment_goal_id = None
    if active_session is not None:
        _, assignment_goal_id = assignment_kind_and_goal_id_from_source_tag(
            getattr(active_session, "source_tag", None),
        )
    compact_assignment_feedback = assignment_kind is not None and hasattr(message, "reply_photo")
    round_progress = None
    if assignment_kind is not None and feedback_user_id is not None:
        round_progress = assignment_round_progress_view(
            context=context,
            user_id=feedback_user_id,
            kind=assignment_kind,
            goal_id=assignment_goal_id,
            active_session=active_session,
        )
        if round_progress is not None:
            assignment_progress_text = render_assignment_round_progress_text(
                context=context,
                user=feedback_user,
                kind=assignment_kind,
                progress=round_progress,
            )
    if outcome.summary is not None and assignment_kind is not None and feedback_user_id is not None:
        reply_markup = assignment_round_complete_keyboard(
            assignment_kind,
            has_more=False,
            remaining_word_count=None,
            round_batch_size=None,
            language=telegram_ui_language(context, feedback_user),
        )
    text = view.text
    if compact_assignment_feedback:
        text = compact_assignment_feedback_text(
            base_text=view.text,
            context=context,
            user=feedback_user,
            feedback_update=feedback_update,
        )
    elif feedback_update is not None:
        update_text = render_feedback_update_text(
            context=context,
            user=feedback_user,
            update=feedback_update,
        )
        if update_text:
            text = f"{text}\n\n{update_text}"
    if assignment_progress_text and not compact_assignment_feedback:
        text = f"{text}\n\n{assignment_progress_text}"
    flow_id = getattr(active_session, "session_id", None)
    if isinstance(flow_id, str):
        await delete_tracked_flow_messages(
            context,
            flow_id=flow_id,
            tag=training_feedback_tag,
        )
    sent_message = await message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode=view.parse_mode,
    )
    if isinstance(flow_id, str):
        track_flow_message(
            context,
            flow_id=flow_id,
            tag=training_feedback_tag,
            message=sent_message,
            fallback_chat_id=message_chat_id(message),
        )
