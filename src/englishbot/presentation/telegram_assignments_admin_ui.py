from __future__ import annotations

from collections.abc import Callable

from telegram import InlineKeyboardMarkup

from englishbot.domain.models import GoalPeriod
from englishbot.presentation.telegram_ui_text import DEFAULT_TELEGRAM_UI_LANGUAGE
from englishbot.telegram.buttons import InlineKeyboardButton

TelegramTextGetter = Callable[..., str]


def page_range_label(
    *,
    tg: TelegramTextGetter,
    page: int,
    page_size: int,
    total: int,
    language: str,
) -> str:
    if total <= 0:
        return tg("page_range", language=language, start=0, end=0, total=0)
    start = page * page_size + 1
    end = min(total, page * page_size + page_size)
    return tg("page_range", language=language, start=start, end=end, total=total)


def assignment_user_label(item) -> str:
    username = f"@{item.username}" if item.username else "no username"
    role_names = [role for role in item.roles if role != "user"]
    role_text = ", ".join(role_names) if role_names else "user"
    return f"{username} | id={item.user_id} | {role_text}"


def render_assignment_user_detail_text(
    *,
    tg: TelegramTextGetter,
    item,
    goals,
) -> str:
    lines = [
        tg(
            "assign_user_detail_title",
            username=(f"@{item.username}" if item.username else "-"),
            user_id=item.user_id,
            roles=(", ".join(role for role in item.roles if role != "user") or "user"),
        ),
        tg(
            "assign_user_detail_summary",
            active=item.active_goals_count,
            completed=item.completed_goals_count,
            percent=item.aggregate_percent,
            last_activity=(item.last_activity_at.date().isoformat() if item.last_activity_at else "-"),
        ),
    ]
    if goals:
        lines.append(tg("assign_user_goals_title"))
        for goal in goals:
            lines.append(
                tg(
                    "assign_user_goal_line",
                    period=goal.goal.goal_period.value,
                    goal_type=goal.goal.goal_type.value,
                    progress=goal.goal.progress_count,
                    target=goal.goal.target_count,
                    percent=goal.progress_percent,
                    status=goal.goal.status.value,
                )
            )
    else:
        lines.append(tg("assign_user_goals_empty"))
    return "\n".join(lines)


def render_assignment_goal_detail_text(
    *,
    tg: TelegramTextGetter,
    detail,
) -> str:
    lines = [
        tg(
            "assign_goal_detail_title",
            period=detail.goal.goal_period.value,
            goal_type=detail.goal.goal_type.value,
            status=detail.goal.status.value,
            progress=detail.goal.progress_count,
            target=detail.goal.target_count,
            percent=detail.progress_percent,
        )
    ]
    if detail.words:
        lines.append(tg("assign_goal_detail_words_title"))
        for word in detail.words:
            if word.homework_mode is None:
                lines.append(
                    tg(
                        "assign_goal_word_line",
                        english=word.english_word,
                        translation=word.translation,
                        mode="-",
                        stage="-",
                    )
                )
                continue
            stages: list[str] = []
            stages.append("easy" if word.easy_mastered else "easy...")
            stages.append("medium" if word.medium_mastered else "medium...")
            if word.hard_skipped:
                stages.append("hard-skip")
            elif word.hard_mastered:
                stages.append("hard")
            else:
                stages.append("hard...")
            lines.append(
                tg(
                    "assign_goal_word_line",
                    english=word.english_word,
                    translation=word.translation,
                    mode=word.homework_mode.value,
                    stage=", ".join(stages),
                )
            )
    else:
        lines.append(tg("assign_goal_detail_words_empty"))
    return "\n".join(lines)


def admin_goal_manual_keyboard(
    *,
    tg: TelegramTextGetter,
    items,
    selected_word_ids: set[str],
    page: int,
    back_callback_data: str = "assign:admin_goal_source_menu",
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> tuple[InlineKeyboardMarkup, int]:
    page_size = 8
    total = len(items)
    pages = max(1, (total + page_size - 1) // page_size)
    normalized_page = max(0, min(page, pages - 1))
    rows: list[list[InlineKeyboardButton]] = []
    for item in items[normalized_page * page_size : normalized_page * page_size + page_size]:
        marker = "✅" if item.id in selected_word_ids else "☑️"
        rows.append([InlineKeyboardButton(f"{marker} {item.english_word[:24]}", callback_data=f"words:admin_goal_manual:toggle:{item.id}")])
    nav: list[InlineKeyboardButton] = []
    if normalized_page > 0:
        nav.append(InlineKeyboardButton(tg("previous_6", language=language), callback_data=f"words:admin_goal_manual:page:{normalized_page-1}"))
    if normalized_page + 1 < pages:
        nav.append(InlineKeyboardButton(tg("next_6", language=language), callback_data=f"words:admin_goal_manual:page:{normalized_page+1}"))
    if nav:
        rows.append(
            [
                *nav,
                InlineKeyboardButton(
                    page_range_label(
                        tg=tg,
                        page=normalized_page,
                        page_size=page_size,
                        total=total,
                        language=language,
                    ),
                    callback_data="assign:noop",
                ),
            ]
        )
    elif total > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    page_range_label(
                        tg=tg,
                        page=normalized_page,
                        page_size=page_size,
                        total=total,
                        language=language,
                    ),
                    callback_data="assign:noop",
                )
            ]
        )
    rows.append([InlineKeyboardButton(tg("goal_manual_done", language=language), callback_data="words:admin_goal_manual:done")])
    rows.append([InlineKeyboardButton(tg("back", language=language), callback_data=back_callback_data)])
    return InlineKeyboardMarkup(rows), normalized_page


def admin_goal_recipients_keyboard(
    *,
    tg: TelegramTextGetter,
    items,
    selected_user_ids: set[int],
    page: int,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> tuple[InlineKeyboardMarkup, int]:
    page_size = 8
    total = len(items)
    pages = max(1, (total + page_size - 1) // page_size)
    normalized_page = max(0, min(page, pages - 1))
    rows: list[list[InlineKeyboardButton]] = []
    for item in items[normalized_page * page_size : normalized_page * page_size + page_size]:
        marker = "✅" if item.user_id in selected_user_ids else "☑️"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker} {assignment_user_label(item)[:48]}",
                    callback_data=f"assign:admin_goal_recipients:toggle:{item.user_id}",
                )
            ]
        )
    nav: list[InlineKeyboardButton] = []
    if normalized_page > 0:
        nav.append(
            InlineKeyboardButton(
                tg("previous_6", language=language),
                callback_data=f"assign:admin_goal_recipients:page:{normalized_page-1}",
            )
        )
    if normalized_page + 1 < pages:
        nav.append(
            InlineKeyboardButton(
                tg("next_6", language=language),
                callback_data=f"assign:admin_goal_recipients:page:{normalized_page+1}",
            )
        )
    if nav:
        rows.append(
            [
                *nav,
                InlineKeyboardButton(
                    page_range_label(
                        tg=tg,
                        page=normalized_page,
                        page_size=page_size,
                        total=total,
                        language=language,
                    ),
                    callback_data="assign:noop",
                ),
            ]
        )
    elif total > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    page_range_label(
                        tg=tg,
                        page=normalized_page,
                        page_size=page_size,
                        total=total,
                        language=language,
                    ),
                    callback_data="assign:noop",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                tg("assign_select_users_done", language=language),
                callback_data="assign:admin_goal_recipients:done",
            )
        ]
    )
    rows.append([InlineKeyboardButton(tg("back", language=language), callback_data="assign:admin_goal_source_menu")])
    return InlineKeyboardMarkup(rows), normalized_page


def assignment_users_keyboard(
    *,
    tg: TelegramTextGetter,
    users=None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in users or []:
        emoji = "🧑‍🎓"
        role_names = [role for role in item.roles if role != "user"]
        if "admin" in role_names:
            emoji = "🛡️"
        elif "editor" in role_names:
            emoji = "🛠️"
        label = item.username and f"@{item.username}" or f"id={item.user_id}"
        rows.append([InlineKeyboardButton(f"{emoji} {label}", callback_data=f"assign:user:{item.user_id}")])
    rows.append([InlineKeyboardButton(tg("back", language=language), callback_data="assign:menu")])
    return InlineKeyboardMarkup(rows)


def assignment_user_goals_keyboard(
    *,
    tg: TelegramTextGetter,
    user_id: int,
    goals,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in goals:
        emoji = "📘" if item.goal.goal_period is GoalPeriod.HOMEWORK else "🎯"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{emoji} {item.goal.goal_period.value} {item.progress_percent}%",
                    callback_data=f"assign:goal:{user_id}:{item.goal.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(tg("back", language=language), callback_data="assign:users")])
    return InlineKeyboardMarkup(rows)


def assignment_goal_detail_keyboard(
    *,
    tg: TelegramTextGetter,
    user_id: int,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(tg("back", language=language), callback_data=f"assign:user:{user_id}")]]
    )


def goal_source_topic_keyboard(
    *,
    tg: TelegramTextGetter,
    topics,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(topic.title[:40], callback_data=f"words:admin_goal_source:topic:{topic.id}")]
        for topic in topics
    ]
    rows.append([InlineKeyboardButton(tg("back", language=language), callback_data="assign:admin_goal_source_menu")])
    return InlineKeyboardMarkup(rows)


def admin_goal_manual_topic_keyboard(
    *,
    tg: TelegramTextGetter,
    topics,
    selected_topic_id: str | None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(
            f"{'✅ ' if selected_topic_id is None else ''}{tg('goal_source_manual_all_words', language=language)}",
            callback_data="words:admin_goal_manual_topic:all",
        )
    ]]
    for topic in topics:
        marker = "✅ " if topic.id == selected_topic_id else ""
        rows.append(
            [InlineKeyboardButton(f"{marker}{topic.title[:40]}", callback_data=f"words:admin_goal_manual_topic:{topic.id}")]
        )
    rows.append([InlineKeyboardButton(tg("back", language=language), callback_data="assign:admin_goal_source_menu")])
    return InlineKeyboardMarkup(rows)
