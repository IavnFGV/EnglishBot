import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    telegram_token: str
    log_level: str


    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not set. Add it to your environment or .env file."
            )
        return cls(
            telegram_token=token,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
