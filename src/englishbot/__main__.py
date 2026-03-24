import asyncio
import logging

from dotenv import load_dotenv

from englishbot.bot import build_application
from englishbot.config import Settings


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    app = build_application(settings.telegram_token)
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
