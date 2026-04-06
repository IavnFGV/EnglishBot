from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from englishbot.__main__ import configure_logging
from englishbot.application.image_rerank_manifest_use_cases import (
    ApplyImageRerankDecisionsUseCase,
    read_image_rerank_decisions,
)
from englishbot.config import create_runtime_config_service
from englishbot.image_generation.pixabay import RemoteImageDownloader
from englishbot.infrastructure.sqlite_store import SQLiteContentStore

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Apply an offline image-rerank decisions JSON back into runtime assets and the SQLite database.",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@app.command()
def main(
    input: Annotated[
        Path,
        typer.Option("--input", help="Path to the decisions JSON file."),
    ] = Path("output/image-rerank-decisions.json"),
    assets_dir: Annotated[
        Path,
        typer.Option("--assets-dir", help="Directory where downloaded assets are stored."),
    ] = Path("assets"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate and log without downloading or updating the database."),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    env_file_path = _REPO_ROOT / ".env"
    load_dotenv(env_file_path, override=True)
    config_service = create_runtime_config_service(env_file_path=env_file_path)
    configure_logging(
        log_level.upper() or config_service.get_str("log_level"),
        log_file_path=config_service.get_path("log_file_path"),
        log_max_bytes=config_service.get_int("log_max_bytes"),
        log_backup_count=config_service.get_int("log_backup_count"),
    )
    store = SQLiteContentStore(
        db_path=config_service.get_path("content_db_path") or Path("data/englishbot.db")
    )
    store.initialize()
    decisions = read_image_rerank_decisions(input_path=input)
    summary = ApplyImageRerankDecisionsUseCase(
        store=store,
        remote_image_downloader=RemoteImageDownloader(),
        assets_dir=assets_dir,
    ).execute(
        decisions=decisions,
        dry_run=dry_run,
    )
    logging.getLogger(__name__).info(
        "Image rerank decisions applied input=%s updated=%s failed=%s dry_run=%s",
        input,
        summary["updated_count"],
        summary["failed_count"],
        dry_run,
    )


if __name__ == "__main__":
    app()
