from __future__ import annotations

from collections.abc import Callable

from telegram import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from englishbot.domain.models import Topic, TrainingMode
from englishbot.presentation.telegram_ui_text import DEFAULT_TELEGRAM_UI_LANGUAGE
from englishbot.presentation.telegram_views import (
    TelegramTextView,
    build_draft_preview_view,
    build_editable_topics_view,
    build_editable_words_view,
    build_help_view,
    build_lesson_selection_view,
    build_mode_selection_view,
    build_quick_actions_view,
    build_topic_selection_view,
    build_words_menu_view,
)
from englishbot.telegram.buttons import InlineKeyboardButton

TelegramTextGetter = Callable[..., str]


def draft_review_keyboard(
    flow_id: str,
    is_valid: bool,
    *,
    tg: TelegramTextGetter,
    show_auto_image_button: bool = True,
    show_regenerate_button: bool = True,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    action_row: list[InlineKeyboardButton] = []
    if show_auto_image_button:
        action_row.append(
            InlineKeyboardButton(
                tg("approve_auto_images", language=language),
                callback_data=f"words:approve_auto_images:{flow_id}",
            )
        )
    action_row.append(
        InlineKeyboardButton(
            tg("manual_image_review", language=language),
            callback_data=f"words:start_image_review:{flow_id}",
        )
    )
    rows = []
    if action_row:
        rows.append(action_row)
    rows.append(
        [
            InlineKeyboardButton(
                tg("publish_without_images", language=language),
                callback_data=f"words:approve_draft:{flow_id}",
            ),
        ]
    )
    edit_row: list[InlineKeyboardButton] = []
    if show_regenerate_button:
        edit_row.append(
            InlineKeyboardButton(
                tg("re_recognize_draft", language=language),
                callback_data=f"words:regenerate_draft:{flow_id}",
            )
        )
    edit_row.append(
        InlineKeyboardButton(
            tg("edit_text", language=language),
            callback_data=f"words:edit_text:{flow_id}",
        )
    )
    rows.append(edit_row)
    rows.append(
        [
            InlineKeyboardButton(
                tg("show_json", language=language),
                callback_data=f"words:show_json:{flow_id}",
            ),
            InlineKeyboardButton(
                tg("cancel", language=language),
                callback_data=f"words:cancel:{flow_id}",
            ),
        ]
    )
    if not is_valid:
        if action_row:
            if show_auto_image_button:
                rows[0][0] = InlineKeyboardButton(
                    tg("approve_disabled", language=language),
                    callback_data="words:menu",
                )
                if len(rows[0]) > 1:
                    rows[0][1] = InlineKeyboardButton(
                        tg("review_disabled", language=language),
                        callback_data="words:menu",
                    )
            else:
                rows[0][0] = InlineKeyboardButton(
                    tg("review_disabled", language=language),
                    callback_data="words:menu",
                )
        publish_row_index = 1 if action_row else 0
        rows[publish_row_index][0] = InlineKeyboardButton(
            tg("publish_disabled", language=language),
            callback_data="words:menu",
        )
    return InlineKeyboardMarkup(rows)


def draft_review_view(
    *,
    result,
    reply_markup: InlineKeyboardMarkup,
) -> TelegramTextView:
    return build_draft_preview_view(result, reply_markup=reply_markup)


def image_review_keyboard(
    *,
    tg: TelegramTextGetter,
    flow_id: str,
    current_item,
    show_generate_image_button: bool = True,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    candidate_count = len(current_item.candidates)
    pick_buttons = [
        InlineKeyboardButton(
            tg("use_n", language=language, index=index + 1),
            callback_data=f"words:image_pick:{flow_id}:{index}",
        )
        for index in range(candidate_count)
    ]
    rows = [pick_buttons[index : index + 3] for index in range(0, len(pick_buttons), 3)]
    action_row = [
        InlineKeyboardButton(
            tg("search_images", language=language),
            callback_data=f"words:image_search:{flow_id}",
        ),
    ]
    if show_generate_image_button:
        action_row.append(
            InlineKeyboardButton(
                tg("generate_image", language=language),
                callback_data=f"words:image_generate:{flow_id}",
            )
        )
    rows.append(action_row)
    if current_item.search_query:
        pagination_row: list[InlineKeyboardButton] = []
        if current_item.search_page > 1:
            pagination_row.append(
                InlineKeyboardButton(
                    tg("previous_6", language=language),
                    callback_data=f"words:image_previous:{flow_id}",
                )
            )
        pagination_row.append(
            InlineKeyboardButton(
                tg("next_6", language=language),
                callback_data=f"words:image_next:{flow_id}",
            )
        )
        rows.append(pagination_row)
    rows.append(
        [
            InlineKeyboardButton(
                tg("edit_search_query", language=language),
                callback_data=f"words:image_edit_search_query:{flow_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                tg("edit_prompt", language=language),
                callback_data=f"words:image_edit_prompt:{flow_id}",
            ),
            InlineKeyboardButton(
                tg("attach_photo", language=language),
                callback_data=f"words:image_attach_photo:{flow_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                tg("show_json", language=language),
                callback_data=f"words:image_show_json:{flow_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                tg("skip_for_now", language=language),
                callback_data=f"words:image_skip:{flow_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def words_menu_keyboard(
    *,
    tg: TelegramTextGetter,
    can_add_words: bool,
    can_edit_words: bool,
    can_edit_images: bool,
    can_manage_catalog: bool = False,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(tg("training_topics", language=language), callback_data="words:topics")]]
    if can_add_words:
        rows.append([InlineKeyboardButton(tg("add_words", language=language), callback_data="words:add_words")])
    if can_edit_words:
        rows.append([InlineKeyboardButton(tg("edit_words", language=language), callback_data="words:edit_words")])
    if can_edit_images:
        rows.append([InlineKeyboardButton(tg("edit_word_image", language=language), callback_data="words:edit_images")])
    if can_manage_catalog:
        rows.append([InlineKeyboardButton(tg("catalog_workbook", language=language), callback_data="words:catalog")])
    return InlineKeyboardMarkup(rows)


def catalog_workbook_menu_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tg("catalog_export_workbook", language=language), callback_data="words:catalog:export")],
            [InlineKeyboardButton(tg("catalog_import_workbook", language=language), callback_data="words:catalog:import")],
            [InlineKeyboardButton(tg("catalog_image_saver", language=language), callback_data="words:catalog:image_saver")],
            [InlineKeyboardButton(tg("back", language=language), callback_data="words:menu")],
        ]
    )


def catalog_workbook_import_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tg("back", language=language), callback_data="words:catalog")],
        ]
    )


def published_images_menu_keyboard(
    *,
    tg: TelegramTextGetter,
    topic_id: str,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tg("edit_word_image", language=language),
                    callback_data=f"words:edit_images_menu:{topic_id}",
                )
            ]
        ]
    )


def topic_button_label(*, title: str, item_count: int | None) -> str:
    if item_count is None:
        return title
    return f"{title} ({item_count})"


def published_image_topics_keyboard(
    topics,
    *,
    tg: TelegramTextGetter,
    topic_item_counts: dict[str, int] | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                topic_button_label(
                    title=topic.title,
                    item_count=(topic_item_counts or {}).get(topic.id),
                ),
                callback_data=f"words:edit_images_menu:{topic.id}",
            )
        ]
        for topic in topics
    ]
    if not rows:
        rows = [[InlineKeyboardButton(tg("no_topics", language=language), callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def editable_word_button_label(
    *,
    english_word: str,
    translation: str,
    has_image: bool,
) -> str:
    marker = "* " if has_image else ""
    if translation:
        return f"{marker}{english_word} — {translation}"
    return f"{marker}{english_word}"


def published_image_items_keyboard(
    *,
    tg: TelegramTextGetter,
    topic_id: str,
    raw_items: list[object],
    callback_data_for_item: Callable[[int], str],
    back_callback_data: str = "words:edit_images",
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            continue
        item_id = str(raw_item.get("id", "")).strip()
        english_word = str(raw_item.get("english_word", "")).strip()
        translation = str(raw_item.get("translation", "")).strip()
        if not item_id or not english_word:
            continue
        has_image = bool(str(raw_item.get("image_ref", "")).strip())
        label = editable_word_button_label(
            english_word=english_word,
            translation=translation,
            has_image=has_image,
        )
        rows.append(
            [
                InlineKeyboardButton(
                    label[:64],
                    callback_data=callback_data_for_item(index),
                )
            ]
        )
    if not rows:
        rows = [[InlineKeyboardButton(tg("no_items", language=language), callback_data="words:menu")]]
    rows.append([InlineKeyboardButton(tg("back", language=language), callback_data=back_callback_data)])
    return InlineKeyboardMarkup(rows)


def editable_topics_keyboard(
    topics,
    *,
    tg: TelegramTextGetter,
    topic_item_counts: dict[str, int] | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                topic_button_label(
                    title=topic.title,
                    item_count=(topic_item_counts or {}).get(topic.id),
                ),
                callback_data=f"words:edit_topic:{topic.id}",
            )
        ]
        for topic in topics
    ]
    if not rows:
        rows = [[InlineKeyboardButton(tg("no_topics", language=language), callback_data="words:menu")]]
    return InlineKeyboardMarkup(rows)


def editable_words_keyboard(
    *,
    tg: TelegramTextGetter,
    topic_id: str,
    words,
    callback_data_for_item: Callable[[int], str],
    back_callback_data: str = "words:edit_words",
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                editable_word_button_label(
                    english_word=word.english_word,
                    translation=word.translation,
                    has_image=getattr(word, "has_image", False),
                )[:64],
                callback_data=callback_data_for_item(index),
            )
        ]
        for index, word in enumerate(words)
    ]
    if not rows:
        rows = [[InlineKeyboardButton(tg("no_words", language=language), callback_data="words:menu")]]
    rows.append([InlineKeyboardButton(tg("back", language=language), callback_data=back_callback_data)])
    return InlineKeyboardMarkup(rows)


def published_word_edit_keyboard(
    *,
    tg: TelegramTextGetter,
    topic_id: str,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tg("cancel", language=language),
                    callback_data=f"words:edit_item_cancel:{topic_id}",
                )
            ]
        ]
    )


def chat_menu_keyboard(*, command_rows: list[list[str]]) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(command) for command in row] for row in command_rows]
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=True,
        is_persistent=False,
    )


def topic_keyboard(
    topics: list[Topic],
    *,
    topic_item_counts: dict[str, int] | None = None,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    topic_button_label(
                        title=topic.title,
                        item_count=(topic_item_counts or {}).get(topic.id),
                    ),
                    callback_data=f"topic:{topic.id}",
                )
            ]
            for topic in topics
        ]
    )


def lesson_keyboard(
    topic_id: str,
    lessons,
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(tg("all_topic_words", language=language), callback_data=f"lesson:{topic_id}:all")]]
    rows.extend(
        [
            [InlineKeyboardButton(lesson.title, callback_data=f"lesson:{topic_id}:{lesson.id}")]
            for lesson in lessons
        ]
    )
    return InlineKeyboardMarkup(rows)


def mode_keyboard(
    topic_id: str,
    lesson_id: str | None,
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    lesson_part = lesson_id or "all"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tg("easy", language=language),
                    callback_data=f"mode:{topic_id}:{lesson_part}:{TrainingMode.EASY.value}",
                ),
                InlineKeyboardButton(
                    tg("medium", language=language),
                    callback_data=f"mode:{topic_id}:{lesson_part}:{TrainingMode.MEDIUM.value}",
                ),
                InlineKeyboardButton(
                    tg("hard", language=language),
                    callback_data=f"mode:{topic_id}:{lesson_part}:{TrainingMode.HARD.value}",
                ),
            ],
        ]
    )


def game_mode_keyboard(
    topic_id: str,
    lesson_id: str | None,
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    lesson_part = lesson_id or "all"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"🎯 {tg('easy', language=language)}",
                    callback_data=f"gamemode:{topic_id}:{lesson_part}:{TrainingMode.EASY.value}",
                ),
                InlineKeyboardButton(
                    f"🧩 {tg('medium', language=language)}",
                    callback_data=f"gamemode:{topic_id}:{lesson_part}:{TrainingMode.MEDIUM.value}",
                ),
                InlineKeyboardButton(
                    f"⚡ {tg('hard', language=language)}",
                    callback_data=f"gamemode:{topic_id}:{lesson_part}:{TrainingMode.HARD.value}",
                ),
            ]
        ]
    )


def quick_actions_view(
    *,
    tg: TelegramTextGetter,
    reply_markup: ReplyKeyboardMarkup,
    context: ContextTypes.DEFAULT_TYPE,
    user,
) -> TelegramTextView:
    return build_quick_actions_view(
        text=tg("quick_actions_title", context=context, user=user),
        reply_markup=reply_markup,
    )


def topic_selection_view(
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> TelegramTextView:
    return build_topic_selection_view(text=text, reply_markup=reply_markup)


def lesson_selection_view(
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> TelegramTextView:
    return build_lesson_selection_view(text=text, reply_markup=reply_markup)


def mode_selection_view(
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> TelegramTextView:
    return build_mode_selection_view(text=text, reply_markup=reply_markup)


def words_menu_view(
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> TelegramTextView:
    return build_words_menu_view(text=text, reply_markup=reply_markup)


def editable_topics_view(
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> TelegramTextView:
    return build_editable_topics_view(text=text, reply_markup=reply_markup)


def editable_words_view(
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> TelegramTextView:
    return build_editable_words_view(text=text, reply_markup=reply_markup)


def help_view(
    *,
    text: str,
    reply_markup: ReplyKeyboardMarkup,
) -> TelegramTextView:
    return build_help_view(text=text, reply_markup=reply_markup)
