from __future__ import annotations

from collections.abc import Callable

from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes

from englishbot.application.homework_progress_use_cases import (
    AssignmentLaunchView,
    AssignmentSessionKind,
    GoalProgressView,
    LearnerProgressSummary,
)
from englishbot.domain.models import GoalPeriod, GoalStatus, GoalType
from englishbot.presentation.telegram_ui_text import DEFAULT_TELEGRAM_UI_LANGUAGE
from englishbot.telegram_buttons import InlineKeyboardButton

TelegramTextGetter = Callable[..., str]


def goal_period_label(*, tg: TelegramTextGetter, context: ContextTypes.DEFAULT_TYPE, user, value: str) -> str:
    key = {
        GoalPeriod.HOMEWORK.value: "goal_period_homework",
    }.get(value)
    return tg(key, context=context, user=user) if key is not None else value


def goal_type_label(*, tg: TelegramTextGetter, context: ContextTypes.DEFAULT_TYPE, user, value: str) -> str:
    key = {
        GoalType.NEW_WORDS.value: "goal_type_new_words",
        GoalType.ROUNDS.value: "goal_type_rounds",
        GoalType.TOPICS.value: "goal_type_topics",
        GoalType.ACTIVE_DAYS.value: "goal_type_active_days",
        GoalType.WORD_LEVEL_HOMEWORK.value: "goal_type_word_level_homework",
    }.get(value)
    return tg(key, context=context, user=user) if key is not None else value


def goal_rule_text(
    *,
    tg: TelegramTextGetter,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    goal_type: GoalType,
) -> str:
    key = {
        GoalType.NEW_WORDS: "goal_rule_new_words",
        GoalType.ROUNDS: "goal_rule_rounds",
        GoalType.TOPICS: "goal_rule_topics",
        GoalType.ACTIVE_DAYS: "goal_rule_active_days",
        GoalType.WORD_LEVEL_HOMEWORK: "goal_rule_word_level_homework",
    }.get(goal_type, "goal_rule_fallback")
    return tg(key, context=context, user=user)


def render_goal_progress_line(
    *,
    tg: TelegramTextGetter,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    goal_view: GoalProgressView,
) -> str:
    return tg(
        "progress_goal_line",
        context=context,
        user=user,
        period=goal_period_label(tg=tg, context=context, user=user, value=goal_view.goal.goal_period.value),
        goal_type=goal_type_label(tg=tg, context=context, user=user, value=goal_view.goal.goal_type.value),
        progress=goal_view.goal.progress_count,
        target=goal_view.goal.target_count,
        percent=goal_view.progress_percent,
    )


def render_progress_text(
    *,
    tg: TelegramTextGetter,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    summary: LearnerProgressSummary,
    history: list[GoalProgressView],
    assignment_summary: list[AssignmentLaunchView],
) -> str:
    visible_active_goals = [
        item for item in summary.active_goals if item.goal.goal_period is not GoalPeriod.HOMEWORK
    ]
    completed_goals = [
        item
        for item in history
        if item.goal.status is GoalStatus.COMPLETED and item.goal.goal_period is not GoalPeriod.HOMEWORK
    ][:3]
    lines = [
        tg("progress_summary_title", context=context, user=user),
        tg(
            "progress_summary_stats",
            context=context,
            user=user,
            correct=summary.correct_answers,
            incorrect=summary.incorrect_answers,
            streak=summary.game_streak_days,
            weekly_points=summary.weekly_points,
        ),
        tg("progress_points_rule", context=context, user=user),
    ]
    current_assignments = [
        item
        for item in assignment_summary
        if item.kind is AssignmentSessionKind.HOMEWORK and item.total_word_count > 0
    ]
    if current_assignments:
        lines.append(tg("progress_assignments_title", context=context, user=user))
        for item in current_assignments:
            line = tg(
                "progress_assignment_line",
                context=context,
                user=user,
                label=assignment_kind_label(item.kind, tg=tg, context=context, user=user),
                left=item.remaining_word_count,
                total=item.total_word_count,
                rounds=item.estimated_round_count,
            )
            if item.deadline_date:
                line = f"{line} {_deadline_suffix(tg=tg, context=context, user=user, deadline_date=item.deadline_date)}"
            lines.append(line)
    if visible_active_goals:
        lines.append(tg("progress_active_goals", context=context, user=user))
        for goal in visible_active_goals:
            lines.append(render_goal_progress_line(tg=tg, context=context, user=user, goal_view=goal))
            lines.append(
                tg(
                    "progress_goal_rule_line",
                    context=context,
                    user=user,
                    rule=goal_rule_text(tg=tg, context=context, user=user, goal_type=goal.goal.goal_type),
                )
            )
    elif not current_assignments:
        lines.append(tg("progress_no_goals", context=context, user=user))
    if completed_goals:
        lines.append(tg("progress_completed_goals", context=context, user=user))
        for goal in completed_goals:
            lines.append(render_goal_progress_line(tg=tg, context=context, user=user, goal_view=goal))
    return "\n".join(lines)


def assignment_kind_label(
    kind: AssignmentSessionKind,
    *,
    tg: TelegramTextGetter,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> str:
    return tg("start_homework_button", context=context, user=user)


def render_start_menu_text(
    *,
    tg: TelegramTextGetter,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    summary: list[AssignmentLaunchView],
) -> str:
    lines = [tg("start_menu_title", context=context, user=user), ""]
    for item in summary:
        if item.kind is not AssignmentSessionKind.HOMEWORK:
            continue
        line = tg(
            "start_menu_status_line",
            context=context,
            user=user,
            label=assignment_kind_label(item.kind, tg=tg, context=context, user=user),
            words=item.remaining_word_count,
            rounds=item.estimated_round_count,
            status=(
                tg("start_menu_status_ready", context=context, user=user)
                if item.available
                else tg("start_menu_status_empty", context=context, user=user)
            ),
        )
        if item.deadline_date:
            line = f"{line} {_deadline_suffix(tg=tg, context=context, user=user, deadline_date=item.deadline_date)}"
        lines.append(line)
    return "\n".join(lines)


def start_assignment_button_label(
    kind: AssignmentSessionKind,
    *,
    tg: TelegramTextGetter,
    available: bool,
    language: str,
) -> str:
    prefix = "" if available else f"{tg('start_disabled_prefix', language=language)} "
    return f"{prefix}{tg('start_homework_button', language=language)}"


def goal_setup_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tg("goal_period_homework", language=language), callback_data="words:goal_period:homework")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="assign:menu")],
        ]
    )


def goal_target_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("5", callback_data="words:goal_target:5"),
                InlineKeyboardButton("10", callback_data="words:goal_target:10"),
                InlineKeyboardButton("20", callback_data="words:goal_target:20"),
            ],
            [InlineKeyboardButton(tg("goal_target_custom", language=language), callback_data="words:goal_target:custom")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="assign:goal_setup")],
        ]
    )


def goal_source_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tg("goal_source_recent", language=language), callback_data="words:goal_source:recent")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="assign:goal_target_menu")],
        ]
    )


def goal_custom_target_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(tg("back", language=language), callback_data="assign:goal_target_menu")]]
    )


def goal_list_keyboard(
    *,
    tg: TelegramTextGetter,
    goals,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(tg("progress_button", language=language), callback_data="assign:progress")],
        [InlineKeyboardButton(tg("back", language=language), callback_data="assign:menu")],
    ]
    for index, goal in enumerate(goals, start=1):
        start_callback = "start:launch:homework" if goal.goal.goal_period is GoalPeriod.HOMEWORK else None
        if start_callback is not None:
            rows.append(
                [
                    InlineKeyboardButton(
                        tg("goal_list_start_button", language=language, number=index),
                        callback_data=start_callback,
                    ),
                    InlineKeyboardButton(
                        tg("goal_list_reset_button", language=language, number=index),
                        callback_data=f"words:goal_reset:{goal.goal.id}",
                    ),
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        tg("goal_list_reset_button", language=language, number=index),
                        callback_data=f"words:goal_reset:{goal.goal.id}",
                    )
                ]
            )
    return InlineKeyboardMarkup(rows)


def admin_goal_period_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tg("goal_period_homework", language=language), callback_data="words:admin_goal_period:homework")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="assign:menu")],
        ]
    )


def admin_goal_target_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("5", callback_data="words:admin_goal_target:5"),
                InlineKeyboardButton("10", callback_data="words:admin_goal_target:10"),
                InlineKeyboardButton("20", callback_data="words:admin_goal_target:20"),
            ],
            [InlineKeyboardButton(tg("goal_target_custom", language=language), callback_data="words:admin_goal_target:custom")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="assign:admin_assign_goal")],
        ]
    )


def admin_goal_custom_target_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(tg("back", language=language), callback_data="assign:admin_goal_target_menu")]]
    )


def admin_goal_source_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tg("goal_source_recent", language=language), callback_data="words:admin_goal_source:recent")],
            [InlineKeyboardButton(tg("goal_source_topic", language=language), callback_data="words:admin_goal_source:topic")],
            [InlineKeyboardButton(tg("goal_source_manual", language=language), callback_data="words:admin_goal_source:manual")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="assign:admin_assign_goal")],
        ]
    )


def admin_goal_deadline_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(tg("admin_goal_deadline_today", language=language), callback_data="words:admin_goal_deadline:today"),
                InlineKeyboardButton(tg("admin_goal_deadline_tomorrow", language=language), callback_data="words:admin_goal_deadline:tomorrow"),
                InlineKeyboardButton(tg("admin_goal_deadline_end_of_week", language=language), callback_data="words:admin_goal_deadline:week_end"),
            ],
            [InlineKeyboardButton(tg("admin_goal_deadline_custom", language=language), callback_data="words:admin_goal_deadline:custom")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="assign:admin_goal_recipients:page:0")],
        ]
    )


def assignment_round_batch_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("3", callback_data="start:launch:homework:batch:3"),
                InlineKeyboardButton("5", callback_data="start:launch:homework:batch:5"),
                InlineKeyboardButton("10", callback_data="start:launch:homework:batch:10"),
            ],
            [InlineKeyboardButton(tg("back", language=language), callback_data="start:menu")],
        ]
    )


def start_menu_keyboard(
    *,
    tg: TelegramTextGetter,
    summary: list[AssignmentLaunchView],
    guide_web_app_url: str | None = None,
    admin_web_app_url: str | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    homework_summary = next(
        (item for item in summary if item.kind is AssignmentSessionKind.HOMEWORK),
        AssignmentLaunchView(AssignmentSessionKind.HOMEWORK, False, 0, 0),
    )
    rows = [
        [InlineKeyboardButton(tg("start_game_button", language=language), callback_data="start:game")],
        [
            InlineKeyboardButton(
                start_assignment_button_label(
                    AssignmentSessionKind.HOMEWORK,
                    tg=tg,
                    available=homework_summary.available,
                    language=language,
                ),
                callback_data=(
                    "start:launch:homework"
                    if homework_summary.available
                    else "start:disabled:homework"
                ),
            )
        ],
    ]
    if guide_web_app_url:
        rows.append([InlineKeyboardButton(tg("assignment_guide_button", language=language), url=guide_web_app_url)])
    if admin_web_app_url:
        rows.append([InlineKeyboardButton("Admin Panel", url=admin_web_app_url)])
    return InlineKeyboardMarkup(rows)


def _deadline_suffix(
    *,
    tg: TelegramTextGetter,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    deadline_date: str,
) -> str:
    return tg("assignment_due_suffix", context=context, user=user, date=deadline_date)


def assignment_round_complete_keyboard(
    kind: AssignmentSessionKind,
    *,
    tg: TelegramTextGetter,
    has_more: bool,
    remaining_word_count: int | None = None,
    round_batch_size: int | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            *(
                [[
                    InlineKeyboardButton(
                        tg(
                            "assignment_next_round_button_with_count",
                            language=language,
                            words=remaining_word_count,
                        )
                        if remaining_word_count is not None and remaining_word_count > 0
                        else tg("assignment_next_round_button", language=language),
                        callback_data=(
                            f"start:launch:{kind.value}:batch:{round_batch_size}"
                            if round_batch_size is not None and round_batch_size > 0
                            else f"start:launch:{kind.value}"
                        ),
                    )
                ]]
                if has_more
                else []
            ),
            [InlineKeyboardButton(tg("goal_setup_button", language=language), callback_data="assign:menu")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="start:menu")],
        ]
    )


def assign_menu_keyboard(
    *,
    tg: TelegramTextGetter,
    is_admin: bool,
    guide_web_app_url: str | None = None,
    admin_web_app_url: str | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tg("goal_setup_button", language=language), callback_data="assign:goals")],
        [InlineKeyboardButton(tg("progress_button", language=language), callback_data="assign:progress")],
        [InlineKeyboardButton(tg("assign_users_button", language=language), callback_data="assign:users")],
    ]
    if guide_web_app_url:
        rows.append([InlineKeyboardButton(tg("assignment_guide_button", language=language), url=guide_web_app_url)])
    if is_admin:
        rows.insert(0, [InlineKeyboardButton(tg("admin_assign_goal_button", language=language), callback_data="assign:admin_assign_goal")])
        if admin_web_app_url:
            rows.insert(1, [InlineKeyboardButton("Admin Panel", url=admin_web_app_url)])
    return InlineKeyboardMarkup(rows)
