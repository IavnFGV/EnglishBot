from __future__ import annotations


def register_tts_capability(*, app, settings) -> None:
    app.bot_data["tts_enabled"] = settings.tts.enabled
