import os
from dataclasses import dataclass
from pathlib import Path


def _optional_float_from_env(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None


def _optional_int_from_env(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


def _optional_path_from_env(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    return Path(value) if value else None


def resolve_ollama_extraction_mode(default: str = "line_by_line") -> str:
    value = os.getenv("OLLAMA_EXTRACTION_MODE", "").strip().lower()
    if value in {"line_by_line", "full_text"}:
        return value
    return default


def resolve_ollama_model(default: str = "qwen2.5:7b") -> str:
    return (
        os.getenv("OLLAMA_MODEL", "").strip()
        or os.getenv("OLLAMA_PULL_MODEL", "").strip()
        or default
    )


@dataclass(slots=True)
class Settings:
    telegram_token: str
    log_level: str
    log_file_path: Path | None = None
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5
    editor_user_ids: tuple[int, ...] = ()
    content_db_path: Path = Path("data/englishbot.db")
    pixabay_api_key: str = ""
    pixabay_base_url: str = "https://pixabay.com/api/"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_model_file_path: Path | None = None
    ollama_timeout_sec: int = 120
    ollama_extraction_mode: str = "line_by_line"
    ollama_temperature: float | None = None
    ollama_top_p: float | None = None
    ollama_num_predict: int | None = None
    ollama_extract_line_prompt_path: Path = Path("prompts/ollama_extract_line_prompt.txt")
    ollama_extract_text_prompt_path: Path = Path("prompts/ollama_extract_text_prompt.txt")
    ollama_image_prompt_path: Path = Path("prompts/ollama_image_prompt_prompt.txt")

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
            log_level=os.getenv("LOG_LEVEL", "DEBUG").upper(),
            log_file_path=(
                Path(raw_log_file_path)
                if (raw_log_file_path := os.getenv("LOG_FILE_PATH", "").strip())
                else None
            ),
            log_max_bytes=int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)).strip()),
            log_backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5").strip()),
            editor_user_ids=editor_user_ids,
            content_db_path=Path(os.getenv("CONTENT_DB_PATH", "data/englishbot.db")),
            pixabay_api_key=os.getenv("PIXABAY_API_KEY", "").strip(),
            pixabay_base_url=os.getenv("PIXABAY_BASE_URL", "https://pixabay.com/api/").strip(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=resolve_ollama_model(),
            ollama_model_file_path=_optional_path_from_env("OLLAMA_MODEL_FILE_PATH"),
            ollama_timeout_sec=int(os.getenv("OLLAMA_TIMEOUT_SEC", "120").strip()),
            ollama_extraction_mode=resolve_ollama_extraction_mode(),
            ollama_temperature=_optional_float_from_env("OLLAMA_TEMPERATURE"),
            ollama_top_p=_optional_float_from_env("OLLAMA_TOP_P"),
            ollama_num_predict=_optional_int_from_env("OLLAMA_NUM_PREDICT"),
            ollama_extract_line_prompt_path=Path(
                os.getenv(
                    "OLLAMA_EXTRACT_LINE_PROMPT_PATH",
                    "prompts/ollama_extract_line_prompt.txt",
                )
            ),
            ollama_extract_text_prompt_path=Path(
                os.getenv(
                    "OLLAMA_EXTRACT_TEXT_PROMPT_PATH",
                    "prompts/ollama_extract_text_prompt.txt",
                )
            ),
            ollama_image_prompt_path=Path(
                os.getenv(
                    "OLLAMA_IMAGE_PROMPT_PATH",
                    "prompts/ollama_image_prompt_prompt.txt",
                )
            ),
        )
