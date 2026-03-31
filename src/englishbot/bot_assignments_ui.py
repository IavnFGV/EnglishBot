from __future__ import annotations

from collections.abc import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from englishbot.application.homework_progress_use_cases import (
    AssignmentLaunchView,
    AssignmentSessionKind,
    GoalProgressView,
    LearnerProgressSummary,
)
from englishbot.domain.models import GoalPeriod, GoalStatus, GoalType
from englishbot.presentation.telegram_ui_text import DEFAULT_TELEGRAM_UI_LANGUAGE

TelegramTextGetter = Callable[..., str]


def goal_period_label(*, tg: TelegramTextGetter, context: ContextTypes.DEFAULT_TYPE, user, value: str) -> str:
    key = {
        GoalPeriod.DAILY.value: "goal_period_daily",
        GoalPeriod.WEEKLY.value: "goal_period_weekly",
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
) -> str:
    completed_goals = [item for item in history if item.goal.status is GoalStatus.COMPLETED][:3]
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
    if summary.active_goals:
        lines.append(tg("progress_active_goals", context=context, user=user))
        for goal in summary.active_goals:
            lines.append(render_goal_progress_line(tg=tg, context=context, user=user, goal_view=goal))
            lines.append(
                tg(
                    "progress_goal_rule_line",
                    context=context,
                    user=user,
                    rule=goal_rule_text(tg=tg, context=context, user=user, goal_type=goal.goal.goal_type),
                )
            )
    else:
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
    key_map = {
        AssignmentSessionKind.DAILY: "start_daily_button",
        AssignmentSessionKind.WEEKLY: "start_weekly_button",
        AssignmentSessionKind.HOMEWORK: "start_homework_button",
        AssignmentSessionKind.ALL: "start_all_assignments_button",
    }
    return tg(key_map[kind], context=context, user=user)


def render_start_menu_text(
    *,
    tg: TelegramTextGetter,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    summary: list[AssignmentLaunchView],
) -> str:
    summary_by_kind = {item.kind: item for item in summary}
    lines = [tg("start_menu_title", context=context, user=user), ""]
    for kind in (
        AssignmentSessionKind.DAILY,
        AssignmentSessionKind.WEEKLY,
        AssignmentSessionKind.HOMEWORK,
        AssignmentSessionKind.ALL,
    ):
        item = summary_by_kind[kind]
        lines.append(
            tg(
                "start_menu_status_line",
                context=context,
                user=user,
                label=assignment_kind_label(kind, tg=tg, context=context, user=user),
                words=item.remaining_word_count,
                rounds=item.estimated_round_count,
                status=(
                    tg("start_menu_status_ready", context=context, user=user)
                    if item.available
                    else tg("start_menu_status_empty", context=context, user=user)
                ),
            )
        )
    return "\n".join(lines)


def start_assignment_button_label(
    kind: AssignmentSessionKind,
    *,
    tg: TelegramTextGetter,
    available: bool,
    language: str,
) -> str:
    key_map = {
        AssignmentSessionKind.DAILY: "start_daily_button",
        AssignmentSessionKind.WEEKLY: "start_weekly_button",
        AssignmentSessionKind.HOMEWORK: "start_homework_button",
        AssignmentSessionKind.ALL: "start_all_assignments_button",
    }
    prefix = "" if available else f"{tg('start_disabled_prefix', language=language)} "
    return f"{prefix}{tg(key_map[kind], language=language)}"


def goal_setup_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tg("goal_period_daily", language=language), callback_data="words:goal_period:daily")],
            [InlineKeyboardButton(tg("goal_period_weekly", language=language), callback_data="words:goal_period:weekly")],
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
            [InlineKeyboardButton(tg("goal_source_all", language=language), callback_data="words:goal_source:all")],
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
    for goal in goals:
        rows.append([InlineKeyboardButton(tg("goal_reset_button", language=language), callback_data=f"words:goal_reset:{goal.goal.id}")])
    return InlineKeyboardMarkup(rows)


def admin_goal_period_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tg("goal_period_daily", language=language), callback_data="words:admin_goal_period:daily")],
            [InlineKeyboardButton(tg("goal_period_weekly", language=language), callback_data="words:admin_goal_period:weekly")],
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
            [InlineKeyboardButton(tg("goal_source_all", language=language), callback_data="words:admin_goal_source:all")],
            [InlineKeyboardButton(tg("goal_source_manual", language=language), callback_data="words:admin_goal_source:manual")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="assign:admin_goal_target_menu")],
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
    summary_by_kind = {item.kind: item for item in summary}
    rows = [
        [InlineKeyboardButton(tg("start_game_button", language=language), callback_data="start:game")],
        [
            InlineKeyboardButton(
                start_assignment_button_label(
                    AssignmentSessionKind.DAILY,
                    tg=tg,
                    available=summary_by_kind[AssignmentSessionKind.DAILY].available,
                    language=language,
                ),
                callback_data=(
                    "start:launch:daily"
                    if summary_by_kind[AssignmentSessionKind.DAILY].available
                    else "start:disabled:daily"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                start_assignment_button_label(
                    AssignmentSessionKind.WEEKLY,
                    tg=tg,
                    available=summary_by_kind[AssignmentSessionKind.WEEKLY].available,
                    language=language,
                ),
                callback_data=(
                    "start:launch:weekly"
                    if summary_by_kind[AssignmentSessionKind.WEEKLY].available
                    else "start:disabled:weekly"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                start_assignment_button_label(
                    AssignmentSessionKind.HOMEWORK,
                    tg=tg,
                    available=summary_by_kind[AssignmentSessionKind.HOMEWORK].available,
                    language=language,
                ),
                callback_data=(
                    "start:launch:homework"
                    if summary_by_kind[AssignmentSessionKind.HOMEWORK].available
                    else "start:disabled:homework"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                start_assignment_button_label(
                    AssignmentSessionKind.ALL,
                    tg=tg,
                    available=summary_by_kind[AssignmentSessionKind.ALL].available,
                    language=language,
                ),
                callback_data=(
                    "start:launch:all"
                    if summary_by_kind[AssignmentSessionKind.ALL].available
                    else "start:disabled:all"
                ),
            )
        ],
    ]
    if guide_web_app_url:
        rows.append([InlineKeyboardButton(tg("assignment_guide_button", language=language), url=guide_web_app_url)])
    if admin_web_app_url:
        rows.append([InlineKeyboardButton("Admin Panel", url=admin_web_app_url)])
    return InlineKeyboardMarkup(rows)


def assignment_round_complete_keyboard(
    kind: AssignmentSessionKind,
    *,
    tg: TelegramTextGetter,
    has_more: bool,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            *(
                [[InlineKeyboardButton(tg("assignment_next_round_button", language=language), callback_data=f"start:launch:{kind.value}")]]
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
