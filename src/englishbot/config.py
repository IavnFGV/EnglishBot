import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    telegram_token: str
    log_level: str
    editor_user_ids: tuple[int, ...]
    ollama_base_url: str
    ollama_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not set. Add it to your environment or .env file."
            )
        raw_editor_ids = os.getenv("EDITOR_USER_IDS", "")
        editor_user_ids = tuple(
            int(value.strip())
            for value in raw_editor_ids.split(",")
            if value.strip()
        )
        return cls(
            telegram_token=token,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            editor_user_ids=editor_user_ids,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("OLLAMA_PULL_MODEL", "llama3.2:3b"),
        )
