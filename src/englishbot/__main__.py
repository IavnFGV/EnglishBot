from dotenv import load_dotenv

from englishbot.bot import build_application
from englishbot.config import Settings


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    app = build_application(settings.telegram_token)
    app.run_polling()


if __name__ == "__main__":
    main()
