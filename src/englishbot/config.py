import os
from dataclasses import dataclass
from pathlib import Path


def _optional_float_from_env(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None


def _optional_int_from_env(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


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
    editor_user_ids: tuple[int, ...]
    ollama_base_url: str
    ollama_model: str
    ollama_temperature: float | None
    ollama_top_p: float | None
    ollama_num_predict: int | None
    ollama_extract_line_prompt_path: Path
    ollama_image_prompt_path: Path

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
            editor_user_ids=editor_user_ids,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=resolve_ollama_model(),
            ollama_temperature=_optional_float_from_env("OLLAMA_TEMPERATURE"),
            ollama_top_p=_optional_float_from_env("OLLAMA_TOP_P"),
            ollama_num_predict=_optional_int_from_env("OLLAMA_NUM_PREDICT"),
            ollama_extract_line_prompt_path=Path(
                os.getenv(
                    "OLLAMA_EXTRACT_LINE_PROMPT_PATH",
                    "prompts/ollama_extract_line_prompt.txt",
                )
            ),
            ollama_image_prompt_path=Path(
                os.getenv(
                    "OLLAMA_IMAGE_PROMPT_PATH",
                    "prompts/ollama_image_prompt_prompt.txt",
                )
            ),
        )
