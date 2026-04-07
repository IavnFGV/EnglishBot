from __future__ import annotations

from collections.abc import Callable

from telegram import InlineKeyboardMarkup

from englishbot.presentation.telegram_ui_text import DEFAULT_TELEGRAM_UI_LANGUAGE
from englishbot.telegram.buttons import InlineKeyboardButton

TelegramTextGetter = Callable[..., str]


def game_result_keyboard(
    *,
    tg: TelegramTextGetter,
    language: str = DEFAULT_TELEGRAM_UI_LANGUAGE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tg("next_round", language=language), callback_data="game:next_round")],
            [InlineKeyboardButton(tg("repeat", language=language), callback_data="game:repeat")],
            [InlineKeyboardButton(tg("menu", language=language), callback_data="session:restart")],
        ]
    )
