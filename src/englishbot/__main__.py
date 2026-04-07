import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from englishbot.bot import build_application
from englishbot.config import Settings, create_runtime_config_service


_REPO_ROOT = Path(__file__).resolve().parents[2]


def configure_logging(
    level: str,
    *,
    log_file_path: Path | None = None,
    log_max_bytes: int = 10 * 1024 * 1024,
    log_backup_count: int = 5,
) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file_path is not None:
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_file_path,
                maxBytes=log_max_bytes,
                backupCount=log_backup_count,
                encoding="utf-8",
            )
        )
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> None:
    env_file_path = _REPO_ROOT / ".env"
    load_dotenv(env_file_path, override=True)
    config_service = create_runtime_config_service(env_file_path=env_file_path)
    settings = Settings.from_config_service(config_service)
    configure_logging(
        settings.log_level,
        log_file_path=settings.log_file_path,
        log_max_bytes=settings.log_max_bytes,
        log_backup_count=settings.log_backup_count,
    )
    logger = logging.getLogger(__name__)
    ai_text = settings.ai_text
    ai_images = settings.ai_images
    tts = settings.tts
    logger.info(
        "Runtime settings log_level=%s log_file_path=%s log_max_bytes=%s log_backup_count=%s "
        "ai_text.enabled=%s ai_text.model=%s ai_text.model_file=%s ai_text.trace_file=%s ai_text.base_url=%s "
        "ai_text.timeout=%s ai_text.extraction_mode=%s ai_text.temperature=%s ai_text.top_p=%s ai_text.num_predict=%s "
        "ai_text.extract_line_prompt=%s ai_text.extract_text_prompt=%s ai_text.image_prompt=%s "
        "ai_images.enabled=%s ai_images.pixabay_base_url=%s ai_images.pixabay_configured=%s "
        "tts.enabled=%s tts.base_url=%s tts.timeout=%s tts.voice_name=%s tts.voice_variants=%s",
        settings.log_level,
        settings.log_file_path,
        settings.log_max_bytes,
        settings.log_backup_count,
        ai_text.enabled,
        ai_text.model,
        ai_text.model_file_path,
        ai_text.trace_file_path,
        ai_text.base_url,
        ai_text.timeout_sec,
        ai_text.extraction_mode,
        ai_text.temperature,
        ai_text.top_p,
        ai_text.num_predict,
        ai_text.extract_line_prompt_path,
        ai_text.extract_text_prompt_path,
        ai_text.image_prompt_path,
        ai_images.enabled,
        ai_images.pixabay_base_url,
        bool(ai_images.pixabay_api_key),
        tts.enabled,
        tts.service_base_url,
        tts.service_timeout_sec,
        tts.voice_name,
        tts.voice_variants,
    )
    app = build_application(settings, config_service=config_service)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        logger.info("Starting EnglishBot polling with log level %s", settings.log_level)
        app.run_polling()
    finally:
        logger.info("Stopping EnglishBot event loop")
        loop.close()


if __name__ == "__main__":
    main()
