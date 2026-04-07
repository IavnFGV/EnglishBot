import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from englishbot.bot import build_application
from englishbot.config import Settings, create_runtime_config_service


_REPO_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


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


def log_core_runtime_settings(settings: Settings) -> None:
    logger.info(
        "Core runtime settings log_level=%s log_file_path=%s log_max_bytes=%s "
        "log_backup_count=%s content_db_path=%s telegram_ui_language=%s "
        "admin_user_count=%s editor_user_count=%s web_app_enabled=%s",
        settings.log_level,
        settings.log_file_path,
        settings.log_max_bytes,
        settings.log_backup_count,
        settings.content_db_path,
        settings.telegram_ui_language,
        len(settings.admin_user_ids),
        len(settings.editor_user_ids),
        bool(settings.web_app_base_url),
    )


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
    log_core_runtime_settings(settings)
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
