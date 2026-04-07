from __future__ import annotations

import html
import tempfile
from pathlib import Path

from telegram import InputMediaPhoto
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from englishbot.presentation.assignment_progress_image import (
    AssignmentProgressSegment,
    AssignmentProgressSnapshot,
    render_assignment_progress_image,
)
from englishbot.telegram import runtime as tg_runtime
from englishbot.telegram.flow_tracking import (
    delete_tracked_flow_messages,
    delete_tracked_messages,
    track_flow_message,
)


def assignment_round_progress_view(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    kind,
    goal_id: str | None = None,
    active_session=None,
):
    import englishbot.bot as bot_module

    if goal_id is not None and tg_runtime.optional_bot_data(context, "content_store") is not None:
        store = tg_runtime.content_store(context)
        goals = store.list_user_goals(
            user_id=user_id,
            statuses=(bot_module.GoalStatus.ACTIVE, bot_module.GoalStatus.COMPLETED),
        )
        goal = next(
            (
                item
                for item in goals
                if item.id == goal_id
                and item.goal_period in assignment_periods_for_kind(kind)
                and item.goal_type in {bot_module.GoalType.NEW_WORDS, bot_module.GoalType.WORD_LEVEL_HOMEWORK}
            ),
            None,
        )
        if goal is None:
            return None
        rows = store.list_goal_word_details(goal_id=goal.id, user_id=user_id)
        completed_word_count = sum(
            1
            for row in rows
            if assignment_word_progress_value(
                store=store,
                user_id=user_id,
                goal=goal,
                row=row,
            ) >= 1.0
        )
        total_word_count = len(rows)
        remaining_word_count = max(0, total_word_count - completed_word_count)
        return bot_module._AssignmentRoundProgressView(
            completed_word_count=completed_word_count,
            total_word_count=total_word_count,
            remaining_word_count=remaining_word_count,
            variant_key=goal.id,
        )
    launch_summary_use_case = tg_runtime.optional_bot_data(
        context,
        "learner_assignment_launch_summary_use_case",
    )
    if launch_summary_use_case is None:
        return None
    launch_views = launch_summary_use_case.execute(user_id=user_id)
    launch_view = next((item for item in launch_views if item.kind is kind), None)
    if launch_view is None:
        return None
    return bot_module._AssignmentRoundProgressView(
        completed_word_count=launch_view.completed_word_count,
        total_word_count=launch_view.total_word_count,
        remaining_word_count=launch_view.remaining_word_count,
        variant_key=launch_view.progress_variant_key,
    )


def assignment_progress_variant_index(*, variant_key: str, variant_count: int) -> int:
    import englishbot.bot as bot_module

    if variant_count <= 0:
        return 0
    digest = bot_module.hashlib.sha256(variant_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % variant_count


def render_assignment_progress_track(
    *,
    completed: int,
    total: int,
    variant_key: str,
    steps: int = 17,
) -> str:
    if total <= 0:
        return ""
    bounded_completed = min(max(completed, 0), total)
    if total == 1:
        runner_index = 0 if bounded_completed < total else steps - 1
    else:
        runner_index = round((bounded_completed / total) * (steps - 1))
    variants = (
        ("🐣", "🟨", "⬜", "🏁"),
        ("🚗", "🟩", "⬜", "🏁"),
        ("🐛", "🍂", "🍃", "🌼"),
        ("🐭", "▫️", "🧀", "🏠"),
    )
    runner, completed_cell, remaining_cell, finish = variants[
        assignment_progress_variant_index(
            variant_key=variant_key,
            variant_count=len(variants),
        )
    ]
    cells = [remaining_cell] * steps
    for index in range(runner_index):
        cells[index] = completed_cell
    cells[runner_index] = runner
    return "".join(cells) + finish


def render_assignment_round_progress_text(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    kind,
    progress,
) -> str:
    if progress.total_word_count <= 0:
        return ""
    return "\n".join(
        [
            tg_runtime.tg(
                "assignment_round_progress_title",
                context=context,
                user=user,
                label=tg_runtime.assignment_kind_label(kind, context=context, user=user),
            ),
            render_assignment_progress_track(
                completed=progress.completed_word_count,
                total=progress.total_word_count,
                variant_key=progress.variant_key,
            ),
            tg_runtime.tg(
                "assignment_round_progress_status",
                context=context,
                user=user,
                done=progress.completed_word_count,
                total=progress.total_word_count,
                left=progress.remaining_word_count,
            ),
        ]
    )


def assignment_progress_flow_id(
    *,
    user_id: int,
    kind,
    goal_id: str | None = None,
) -> str:
    from englishbot.telegram.interaction import assignment_progress_interaction_id

    return assignment_progress_interaction_id(
        user_id=user_id,
        kind_value=kind.value,
        goal_id=goal_id,
    )


def assignment_periods_for_kind(kind) -> tuple:
    import englishbot.bot as bot_module

    return (bot_module.GoalPeriod(kind.value),)


def build_assignment_progress_snapshot(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    kind,
    user,
    goal_id: str | None = None,
    active_session=None,
) -> AssignmentProgressSnapshot | None:
    import englishbot.bot as bot_module

    if tg_runtime.optional_bot_data(context, "content_store") is None:
        return None
    store = tg_runtime.content_store(context)
    goals = store.list_user_goals(
        user_id=user_id,
        statuses=((bot_module.GoalStatus.ACTIVE, bot_module.GoalStatus.COMPLETED) if goal_id is not None else (bot_module.GoalStatus.ACTIVE,)),
    )
    progress_by_word: dict[str, AssignmentProgressSegment] = {}
    relevant_periods = assignment_periods_for_kind(kind)
    for goal in goals:
        if goal_id is not None and goal.id != goal_id:
            continue
        if goal.goal_period not in relevant_periods:
            continue
        if goal.goal_type not in {bot_module.GoalType.NEW_WORDS, bot_module.GoalType.WORD_LEVEL_HOMEWORK}:
            continue
        for row in store.list_goal_word_details(goal_id=goal.id, user_id=user_id):
            word_id = str(row["word_id"])
            label = str(row.get("english_word") or word_id)
            progress_value = assignment_word_progress_value(
                store=store,
                user_id=user_id,
                goal=goal,
                row=row,
            )
            existing = progress_by_word.get(word_id)
            if existing is None or progress_value > existing.progress_value:
                progress_by_word[word_id] = AssignmentProgressSegment(
                    word_id=word_id,
                    label=label,
                    progress_value=progress_value,
                    hard_clear=bool(row.get("hard_mastered")),
                )
    if not progress_by_word:
        return None
    segments = tuple(progress_by_word.values())
    completed_word_count = sum(1 for item in segments if item.progress_value >= 1.0)
    remaining_word_count = max(0, len(segments) - completed_word_count)
    return AssignmentProgressSnapshot(
        center_label=tg_runtime.tg("assignment_progress_center_label", context=context, user=user),
        legend_labels=(
            tg_runtime.tg("assignment_progress_legend_start", context=context, user=user),
            tg_runtime.tg("assignment_progress_legend_warmup", context=context, user=user),
            tg_runtime.tg("assignment_progress_legend_almost", context=context, user=user),
            tg_runtime.tg("assignment_progress_legend_done", context=context, user=user),
        ),
        hard_legend_label=tg_runtime.tg("assignment_progress_legend_hard_note", context=context, user=user),
        completed_word_count=completed_word_count,
        total_word_count=len(segments),
        remaining_word_count=remaining_word_count,
        estimated_round_count=0,
        segments=segments,
        combo_charge_streak=max(0, min(4, int(getattr(active_session, "combo_correct_streak", 0) or 0))),
        combo_hard_active=bool(getattr(active_session, "combo_hard_active", False)),
        combo_target_word_id=session_combo_target_word_id(active_session),
    )


def assignment_word_progress_value(
    *,
    store,
    user_id: int,
    goal,
    row: dict[str, object],
) -> float:
    import englishbot.bot as bot_module

    if goal.goal_type is bot_module.GoalType.WORD_LEVEL_HOMEWORK:
        required_level = int(goal.required_level or 2)
        medium_success_count = int(row.get("medium_success_count") or 0)
        if required_level <= 1 and bool(row.get("easy_mastered")):
            return 1.0
        if required_level <= 2 and bool(row.get("medium_mastered")):
            return 1.0
        if medium_success_count >= 1:
            return 0.66
        if bool(row.get("easy_mastered")):
            return 0.33
        return 0.0

    word_stats = store.get_word_stats(user_id, str(row["word_id"]))
    goal_created_at = getattr(goal, "created_at", None)
    last_correct_at = getattr(word_stats, "last_correct_at", None) if word_stats is not None else None
    if last_correct_at is not None and goal_created_at is not None and last_correct_at >= goal_created_at:
        return 1.0
    return 0.0


def assignment_progress_image_path(*, user_id: int, kind) -> Path:
    return (
        Path(tempfile.gettempdir())
        / "englishbot-assignment-progress"
        / f"user-{user_id}-{kind.value}.png"
    )


def session_combo_target_word_id(active_session) -> str | None:
    if active_session is None or not bool(getattr(active_session, "combo_hard_active", False)):
        return None
    if not hasattr(active_session, "current_item_id"):
        return None
    try:
        return active_session.current_item_id()
    except ValueError:
        return None


def assignment_progress_caption(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    snapshot: AssignmentProgressSnapshot,
    kind,
    user,
    remaining_word_count: int,
) -> str:
    return "\n".join(
        [
            f"<b>{html.escape(tg_runtime.assignment_kind_label(kind, context=context, user=user))}</b>",
            tg_runtime.tg(
                "assignment_round_progress_status",
                context=context,
                user=user,
                done=snapshot.completed_word_count,
                total=snapshot.total_word_count,
                left=remaining_word_count,
            ),
        ]
    )


async def send_or_update_assignment_progress_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
    user,
    kind,
    active_session=None,
) -> None:
    import englishbot.bot as bot_module

    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        return
    if not hasattr(message, "reply_photo"):
        return
    if active_session is None:
        active_session = tg_runtime.service(context).get_active_session(user_id=user_id)
    raw_active_session = tg_runtime.active_training_session(user_id, context)
    _, goal_id = bot_module._assignment_kind_and_goal_id_from_source_tag(
        getattr(active_session, "source_tag", None),
    )
    snapshot = build_assignment_progress_snapshot(
        context=context,
        user_id=user_id,
        kind=kind,
        user=user,
        goal_id=goal_id,
        active_session=raw_active_session,
    )
    flow_id = assignment_progress_flow_id(user_id=user_id, kind=kind, goal_id=goal_id)
    if snapshot is None:
        await delete_tracked_flow_messages(
            context,
            flow_id=flow_id,
            tag=bot_module._ASSIGNMENT_PROGRESS_TAG,
        )
        return
    output_path = render_assignment_progress_image(
        snapshot,
        output_path=assignment_progress_image_path(user_id=user_id, kind=kind),
    )
    remaining_word_count = snapshot.remaining_word_count
    caption = assignment_progress_caption(
        context=context,
        snapshot=snapshot,
        kind=kind,
        user=user,
        remaining_word_count=remaining_word_count,
    )
    registry = bot_module._telegram_flow_messages(context)
    tracked_messages = (
        registry.list(flow_id=flow_id, tag=bot_module._ASSIGNMENT_PROGRESS_TAG)
        if registry is not None
        else []
    )
    latest_tracked = tracked_messages[-1] if tracked_messages else None
    older_tracked = tracked_messages[:-1] if tracked_messages else []
    fallback_chat_id = tg_runtime.message_chat_id(message)
    if older_tracked:
        await delete_tracked_messages(context, tracked_messages=older_tracked)
    sent_message = None
    if latest_tracked is not None and getattr(context, "bot", None) is not None:
        try:
            with output_path.open("rb") as photo_file:
                await context.bot.edit_message_media(
                    chat_id=latest_tracked.chat_id,
                    message_id=latest_tracked.message_id,
                    media=InputMediaPhoto(
                        media=photo_file,
                        caption=caption,
                        parse_mode="HTML",
                    ),
                )
            sent_message = latest_tracked
        except BadRequest:
            await delete_tracked_messages(context, tracked_messages=[latest_tracked])
            latest_tracked = None
    if sent_message is None:
        try:
            with output_path.open("rb") as photo_file:
                sent_message = await message.reply_photo(
                    photo=photo_file,
                    caption=caption,
                    parse_mode="HTML",
                )
        except BadRequest:
            bot = getattr(context, "bot", None)
            if bot is None or not isinstance(fallback_chat_id, int) or not hasattr(bot, "send_photo"):
                return
            with output_path.open("rb") as photo_file:
                sent_message = await bot.send_photo(
                    chat_id=fallback_chat_id,
                    photo=photo_file,
                    caption=caption,
                    parse_mode="HTML",
                )
    track_flow_message(
        context,
        flow_id=flow_id,
        tag=bot_module._ASSIGNMENT_PROGRESS_TAG,
        message=sent_message,
        fallback_chat_id=fallback_chat_id,
    )
