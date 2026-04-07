from __future__ import annotations

from pathlib import Path

from englishbot.__main__ import configure_logging
from englishbot.config import RuntimeConfigService, create_runtime_config_service
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


def resolve_repo_root(module_file: str) -> Path:
    return Path(module_file).resolve().parents[2]


def create_cli_runtime_config_service(
    *,
    module_file: str | None = None,
    repo_root: Path | None = None,
) -> RuntimeConfigService:
    resolved_repo_root = repo_root or resolve_repo_root(module_file or __file__)
    env_file_path = resolved_repo_root / ".env"
    return create_runtime_config_service(env_file_path=env_file_path)


def configure_cli_logging(
    *,
    log_level: str | None,
    config_service: RuntimeConfigService,
) -> None:
    resolved_log_level = (log_level or "").upper() or config_service.get_str("log_level")
    configure_logging(
        resolved_log_level,
        log_file_path=config_service.get_path("log_file_path"),
        log_max_bytes=config_service.get_int("log_max_bytes"),
        log_backup_count=config_service.get_int("log_backup_count"),
    )


def create_content_store(*, config_service: RuntimeConfigService) -> SQLiteContentStore:
    store = SQLiteContentStore(
        db_path=config_service.get_path("content_db_path") or Path("data/englishbot.db")
    )
    store.initialize()
    return store
