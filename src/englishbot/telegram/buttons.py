from __future__ import annotations

from telegram import InlineKeyboardButton as TelegramInlineKeyboardButton


def InlineKeyboardButton(*args, **kwargs) -> TelegramInlineKeyboardButton:
    """Project-local wrapper for Telegram inline buttons.

    Keep all inline button creation going through this module so callback-data
    rules and tokenization can evolve in one place.
    """

    return TelegramInlineKeyboardButton(*args, **kwargs)
