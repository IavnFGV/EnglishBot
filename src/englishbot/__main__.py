import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from englishbot.bot import build_application
from englishbot.config import Settings


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
    load_dotenv(_REPO_ROOT / ".env")
    settings = Settings.from_env()
    configure_logging(
        settings.log_level,
        log_file_path=settings.log_file_path,
        log_max_bytes=settings.log_max_bytes,
        log_backup_count=settings.log_backup_count,
    )
    logger = logging.getLogger(__name__)
    logger.info(
        "Runtime settings log_level=%s log_file_path=%s log_max_bytes=%s log_backup_count=%s ollama_model=%s ollama_model_file=%s ollama_base_url=%s "
        "timeout=%s extraction_mode=%s temperature=%s top_p=%s num_predict=%s extract_line_prompt=%s extract_text_prompt=%s image_prompt=%s",
        settings.log_level,
        settings.log_file_path,
        settings.log_max_bytes,
        settings.log_backup_count,
        settings.ollama_model,
        settings.ollama_model_file_path,
        settings.ollama_base_url,
        settings.ollama_timeout_sec,
        settings.ollama_extraction_mode,
        settings.ollama_temperature,
        settings.ollama_top_p,
        settings.ollama_num_predict,
        settings.ollama_extract_line_prompt_path,
        settings.ollama_extract_text_prompt_path,
        settings.ollama_image_prompt_path,
    )
    app = build_application(settings)
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
