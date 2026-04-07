from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


def log_tts_capability_settings(*, settings) -> None:
    tts = settings.tts
    logger.info(
        "TTS capability settings enabled=%s service_base_url=%s service_timeout_sec=%s "
        "voice_name=%s voice_variants=%s",
        tts.enabled,
        tts.service_base_url,
        tts.service_timeout_sec,
        tts.voice_name,
        tts.voice_variants,
    )


def register_tts_capability(*, app, settings) -> None:
    log_tts_capability_settings(settings=settings)
    app.bot_data["tts_enabled"] = settings.tts.enabled
