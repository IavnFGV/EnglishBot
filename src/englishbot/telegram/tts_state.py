from __future__ import annotations

import asyncio

from telegram.ext import ContextTypes

from englishbot.telegram import runtime as tg_runtime

TTS_TASK_LOCK_KEY = "tts_task_lock"
TTS_TASK_RECENT_KEY = "tts_task_recent"
TTS_SELECTED_VOICE_KEY = "tts_selected_voice_by_item"


def _user_data_or_none(context: ContextTypes.DEFAULT_TYPE):
    user_data = getattr(context, "user_data", None)
    return user_data if isinstance(user_data, dict) else None


def tts_task_lock(context: ContextTypes.DEFAULT_TYPE) -> asyncio.Lock:
    user_data = _user_data_or_none(context)
    if user_data is None:
        return asyncio.Lock()
    lock = user_data.get(TTS_TASK_LOCK_KEY)
    if isinstance(lock, asyncio.Lock):
        return lock
    created_lock = asyncio.Lock()
    user_data[TTS_TASK_LOCK_KEY] = created_lock
    return created_lock


def tts_selected_voice_store(context: ContextTypes.DEFAULT_TYPE) -> dict[str, str]:
    user_data = _user_data_or_none(context)
    if user_data is None:
        return {}
    current = user_data.get(TTS_SELECTED_VOICE_KEY)
    if isinstance(current, dict):
        return current
    created: dict[str, str] = {}
    user_data[TTS_SELECTED_VOICE_KEY] = created
    return created


def tts_selected_voice_name(context: ContextTypes.DEFAULT_TYPE, *, item_id: str) -> str | None:
    variants = tg_runtime.tts_voice_variants(context)
    if not variants:
        return None
    selected = tts_selected_voice_store(context).get(item_id)
    if selected in variants:
        return selected
    selected = variants[0]
    tts_selected_voice_store(context)[item_id] = selected
    return selected


def advance_tts_selected_voice_name(context: ContextTypes.DEFAULT_TYPE, *, item_id: str) -> str | None:
    variants = tg_runtime.tts_voice_variants(context)
    if not variants:
        return None
    current = tts_selected_voice_name(context, item_id=item_id)
    if current not in variants:
        next_voice_name = variants[0]
    else:
        next_voice_name = variants[(variants.index(current) + 1) % len(variants)]
    tts_selected_voice_store(context)[item_id] = next_voice_name
    return next_voice_name


def tts_recent_request(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, str, float] | None:
    value = tg_runtime.optional_user_data(context, TTS_TASK_RECENT_KEY)
    if (
        isinstance(value, tuple)
        and len(value) == 3
        and isinstance(value[0], str)
        and isinstance(value[1], str)
        and isinstance(value[2], (int, float))
    ):
        return value[0], value[1], float(value[2])
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], (int, float))
    ):
        return value[0], "", float(value[1])
    return None


def set_tts_recent_request(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    item_id: str,
    voice_name: str,
    sent_at: float,
) -> None:
    tg_runtime.set_user_data(context, TTS_TASK_RECENT_KEY, (item_id, voice_name, sent_at))
