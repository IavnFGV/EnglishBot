import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from englishbot.bot import build_application
from englishbot.config import Settings


_REPO_ROOT = Path(__file__).resolve().parents[2]


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> None:
    load_dotenv(_REPO_ROOT / ".env")
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    logger.info(
        "Runtime settings log_level=%s ollama_model=%s ollama_base_url=%s "
        "temperature=%s top_p=%s num_predict=%s extract_prompt=%s image_prompt=%s",
        settings.log_level,
        settings.ollama_model,
        settings.ollama_base_url,
        settings.ollama_temperature,
        settings.ollama_top_p,
        settings.ollama_num_predict,
        settings.ollama_extract_line_prompt_path,
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
