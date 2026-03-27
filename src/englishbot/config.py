from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values, set_key, unset_key

from englishbot.presentation.telegram_ui_text import DEFAULT_TELEGRAM_UI_LANGUAGE


@dataclass(frozen=True, slots=True)
class RuntimeSettingDefinition:
    name: str
    env_keys: tuple[str, ...]
    default: object | None = None
    value_type: str = "str"
    required: bool = False


_SETTING_DEFINITIONS: dict[str, RuntimeSettingDefinition] = {
    "telegram_token": RuntimeSettingDefinition(
        name="telegram_token",
        env_keys=("TELEGRAM_BOT_TOKEN",),
        required=True,
    ),
    "log_level": RuntimeSettingDefinition("log_level", ("LOG_LEVEL",), "DEBUG"),
    "telegram_ui_language": RuntimeSettingDefinition(
        "telegram_ui_language",
        ("TELEGRAM_UI_LANGUAGE",),
        DEFAULT_TELEGRAM_UI_LANGUAGE,
    ),
    "log_file_path": RuntimeSettingDefinition("log_file_path", ("LOG_FILE_PATH",), None, "path"),
    "log_max_bytes": RuntimeSettingDefinition(
        "log_max_bytes",
        ("LOG_MAX_BYTES",),
        10 * 1024 * 1024,
        "int",
    ),
    "log_backup_count": RuntimeSettingDefinition("log_backup_count", ("LOG_BACKUP_COUNT",), 5, "int"),
    "editor_user_ids": RuntimeSettingDefinition("editor_user_ids", ("EDITOR_USER_IDS",), (), "csv_int"),
    "content_db_path": RuntimeSettingDefinition(
        "content_db_path",
        ("CONTENT_DB_PATH",),
        Path("data/englishbot.db"),
        "path",
    ),
    "pixabay_api_key": RuntimeSettingDefinition("pixabay_api_key", ("PIXABAY_API_KEY",), ""),
    "pixabay_base_url": RuntimeSettingDefinition(
        "pixabay_base_url",
        ("PIXABAY_BASE_URL",),
        "https://pixabay.com/api/",
    ),
    "pixabay_timeout_sec": RuntimeSettingDefinition("pixabay_timeout_sec", ("PIXABAY_TIMEOUT_SEC",), 30, "int"),
    "ollama_base_url": RuntimeSettingDefinition(
        "ollama_base_url",
        ("OLLAMA_BASE_URL",),
        "http://127.0.0.1:11434",
    ),
    "ollama_model": RuntimeSettingDefinition(
        "ollama_model",
        ("OLLAMA_MODEL", "OLLAMA_PULL_MODEL"),
        "qwen2.5:7b",
    ),
    "ollama_model_file_path": RuntimeSettingDefinition(
        "ollama_model_file_path",
        ("OLLAMA_MODEL_FILE_PATH",),
        None,
        "path",
    ),
    "ollama_timeout_sec": RuntimeSettingDefinition("ollama_timeout_sec", ("OLLAMA_TIMEOUT_SEC",), 120, "int"),
    "ollama_image_prompt_timeout_sec": RuntimeSettingDefinition(
        "ollama_image_prompt_timeout_sec",
        ("OLLAMA_IMAGE_PROMPT_TIMEOUT_SEC",),
        30,
        "int",
    ),
    "ollama_trace_file_path": RuntimeSettingDefinition(
        "ollama_trace_file_path",
        ("OLLAMA_TRACE_FILE_PATH",),
        None,
        "path",
    ),
    "ollama_extraction_mode": RuntimeSettingDefinition(
        "ollama_extraction_mode",
        ("OLLAMA_EXTRACTION_MODE",),
        "line_by_line",
    ),
    "ollama_temperature": RuntimeSettingDefinition(
        "ollama_temperature",
        ("OLLAMA_TEMPERATURE",),
        None,
        "float",
    ),
    "ollama_top_p": RuntimeSettingDefinition("ollama_top_p", ("OLLAMA_TOP_P",), None, "float"),
    "ollama_num_predict": RuntimeSettingDefinition("ollama_num_predict", ("OLLAMA_NUM_PREDICT",), None, "int"),
    "ollama_extract_line_prompt_path": RuntimeSettingDefinition(
        "ollama_extract_line_prompt_path",
        ("OLLAMA_EXTRACT_LINE_PROMPT_PATH",),
        Path("prompts/ollama_extract_line_prompt.txt"),
        "path",
    ),
    "ollama_extract_text_prompt_path": RuntimeSettingDefinition(
        "ollama_extract_text_prompt_path",
        ("OLLAMA_EXTRACT_TEXT_PROMPT_PATH",),
        Path("prompts/ollama_extract_text_prompt.txt"),
        "path",
    ),
    "ollama_infer_topic_prompt_path": RuntimeSettingDefinition(
        "ollama_infer_topic_prompt_path",
        ("OLLAMA_INFER_TOPIC_PROMPT_PATH",),
        Path("prompts/ollama_infer_topic_prompt.txt"),
        "path",
    ),
    "ollama_image_prompt_path": RuntimeSettingDefinition(
        "ollama_image_prompt_path",
        ("OLLAMA_IMAGE_PROMPT_PATH",),
        Path("prompts/ollama_image_prompt_prompt.txt"),
        "path",
    ),
    "comfyui_base_url": RuntimeSettingDefinition(
        "comfyui_base_url",
        ("COMFYUI_BASE_URL",),
        "http://127.0.0.1:8188",
    ),
    "comfyui_timeout_sec": RuntimeSettingDefinition("comfyui_timeout_sec", ("COMFYUI_TIMEOUT_SEC",), 300, "int"),
    "comfyui_checkpoint_name": RuntimeSettingDefinition(
        "comfyui_checkpoint_name",
        ("COMFYUI_CHECKPOINT_NAME",),
        "dreamshaper_8.safetensors",
    ),
    "comfyui_vae_name": RuntimeSettingDefinition("comfyui_vae_name", ("COMFYUI_VAE_NAME",), ""),
    "comfyui_seed": RuntimeSettingDefinition("comfyui_seed", ("COMFYUI_SEED",), 5, "int"),
}


class RuntimeConfigService:
    def __init__(
        self,
        *,
        env_file_path: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._env_file_path = env_file_path
        self._environ = dict(environ if environ is not None else os.environ)
        self._file_values = self._load_env_file()
        self._overrides: dict[str, str | None] = {}

    @property
    def env_file_path(self) -> Path | None:
        return self._env_file_path

    def get(self, name: str):
        definition = _SETTING_DEFINITIONS[name]
        raw_value = self._raw_value(definition)
        return self._coerce_value(definition, raw_value)

    def get_str(self, name: str) -> str:
        value = self.get(name)
        return "" if value is None else str(value)

    def get_int(self, name: str) -> int:
        value = self.get(name)
        return int(value)

    def get_float(self, name: str) -> float | None:
        value = self.get(name)
        return None if value is None else float(value)

    def get_path(self, name: str) -> Path | None:
        value = self.get(name)
        return None if value is None else Path(value)

    def set(self, name: str, value: object | None, *, persist: bool = False) -> None:
        definition = _SETTING_DEFINITIONS[name]
        serialized = self._serialize_value(definition, value)
        primary_key = definition.env_keys[0]
        self._overrides[primary_key] = serialized
        if persist:
            self._persist(primary_key, serialized)

    def update(self, values: Mapping[str, object | None], *, persist: bool = False) -> None:
        for name, value in values.items():
            self.set(name, value, persist=persist)

    def save(self) -> None:
        for key, value in self._overrides.items():
            self._persist(key, value)

    def reload(self) -> None:
        self._file_values = self._load_env_file()
        self._overrides.clear()

    def _load_env_file(self) -> dict[str, str]:
        if self._env_file_path is None or not self._env_file_path.exists():
            return {}
        return {
            key: str(value)
            for key, value in dotenv_values(self._env_file_path).items()
            if value is not None
        }

    def _raw_value(self, definition: RuntimeSettingDefinition) -> str | None:
        for key in definition.env_keys:
            if key in self._overrides:
                return self._overrides[key]
            value = self._environ.get(key)
            if value is not None and value.strip():
                return value.strip()
            value = self._file_values.get(key)
            if value is not None and value.strip():
                return value.strip()
        return None

    def _coerce_value(self, definition: RuntimeSettingDefinition, raw_value: str | None):
        if raw_value is None or raw_value == "":
            if definition.required:
                env_key = definition.env_keys[0]
                raise RuntimeError(f"{env_key} is not set. Add it to your environment or .env file.")
            return definition.default
        if definition.value_type == "int":
            return int(raw_value)
        if definition.value_type == "float":
            return float(raw_value)
        if definition.value_type == "path":
            return Path(raw_value)
        if definition.value_type == "csv_int":
            return tuple(int(value.strip()) for value in raw_value.split(",") if value.strip())
        if definition.name == "ollama_extraction_mode":
            lowered = raw_value.strip().lower()
            if lowered in {"line_by_line", "full_text"}:
                return lowered
            return definition.default
        if definition.name == "telegram_ui_language":
            return raw_value.strip().lower() or DEFAULT_TELEGRAM_UI_LANGUAGE
        if definition.name == "log_level":
            return raw_value.strip().upper()
        return raw_value

    def _serialize_value(self, definition: RuntimeSettingDefinition, value: object | None) -> str | None:
        if value is None:
            return None
        if definition.value_type == "path":
            return str(value)
        if definition.value_type == "csv_int":
            return ",".join(str(item) for item in value)
        return str(value)

    def _persist(self, key: str, value: str | None) -> None:
        if self._env_file_path is None:
            raise RuntimeError("This config service was created without an env_file_path.")
        self._env_file_path.parent.mkdir(parents=True, exist_ok=True)
        if value is None or value == "":
            if self._env_file_path.exists():
                unset_key(str(self._env_file_path), key, quote_mode="never")
                self._file_values.pop(key, None)
            return
        set_key(str(self._env_file_path), key, value, quote_mode="never")
        self._file_values[key] = value


def create_runtime_config_service(
    *,
    env_file_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> RuntimeConfigService:
    return RuntimeConfigService(env_file_path=env_file_path, environ=environ)


def resolve_ollama_extraction_mode(default: str = "line_by_line") -> str:
    service = create_runtime_config_service()
    value = service.get("ollama_extraction_mode")
    return default if value is None else str(value)


def resolve_ollama_model(default: str = "qwen2.5:7b") -> str:
    service = create_runtime_config_service()
    value = service.get("ollama_model")
    return default if value is None else str(value)


@dataclass(slots=True)
class Settings:
    telegram_token: str
    log_level: str
    telegram_ui_language: str = DEFAULT_TELEGRAM_UI_LANGUAGE
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
    ollama_trace_file_path: Path | None = None
    ollama_extraction_mode: str = "line_by_line"
    ollama_temperature: float | None = None
    ollama_top_p: float | None = None
    ollama_num_predict: int | None = None
    ollama_extract_line_prompt_path: Path = Path("prompts/ollama_extract_line_prompt.txt")
    ollama_extract_text_prompt_path: Path = Path("prompts/ollama_extract_text_prompt.txt")
    ollama_image_prompt_path: Path = Path("prompts/ollama_image_prompt_prompt.txt")

    @classmethod
    def from_config_service(cls, service: RuntimeConfigService) -> "Settings":
        return cls(
            telegram_token=service.get_str("telegram_token"),
            log_level=service.get_str("log_level"),
            telegram_ui_language=service.get_str("telegram_ui_language"),
            log_file_path=service.get_path("log_file_path"),
            log_max_bytes=service.get_int("log_max_bytes"),
            log_backup_count=service.get_int("log_backup_count"),
            editor_user_ids=tuple(service.get("editor_user_ids")),
            content_db_path=service.get_path("content_db_path") or Path("data/englishbot.db"),
            pixabay_api_key=service.get_str("pixabay_api_key"),
            pixabay_base_url=service.get_str("pixabay_base_url"),
            ollama_base_url=service.get_str("ollama_base_url"),
            ollama_model=service.get_str("ollama_model"),
            ollama_model_file_path=service.get_path("ollama_model_file_path"),
            ollama_timeout_sec=service.get_int("ollama_timeout_sec"),
            ollama_trace_file_path=service.get_path("ollama_trace_file_path"),
            ollama_extraction_mode=service.get_str("ollama_extraction_mode"),
            ollama_temperature=service.get_float("ollama_temperature"),
            ollama_top_p=service.get_float("ollama_top_p"),
            ollama_num_predict=service.get("ollama_num_predict"),
            ollama_extract_line_prompt_path=service.get_path("ollama_extract_line_prompt_path")
            or Path("prompts/ollama_extract_line_prompt.txt"),
            ollama_extract_text_prompt_path=service.get_path("ollama_extract_text_prompt_path")
            or Path("prompts/ollama_extract_text_prompt.txt"),
            ollama_image_prompt_path=service.get_path("ollama_image_prompt_path")
            or Path("prompts/ollama_image_prompt_prompt.txt"),
        )

    @classmethod
    def from_env(cls) -> "Settings":
        return cls.from_config_service(create_runtime_config_service())
