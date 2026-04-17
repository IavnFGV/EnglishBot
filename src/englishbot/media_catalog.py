from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.application.media_catalog_use_cases import (
    ExportMediaCatalogWorkbookUseCase,
    ImportMediaCatalogWorkbookUseCase,
)
from englishbot.cli import create_cli_runtime_config_service
from englishbot.config import RuntimeConfigService, Settings
from englishbot.importing.cli import resolve_db_path
from englishbot.infrastructure.sqlite_store import SQLiteContentStore

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Export and import workbook catalogs for centralized vocabulary management.",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _runtime_config_service() -> RuntimeConfigService:
    return create_cli_runtime_config_service(repo_root=_REPO_ROOT)


@app.command("export-workbook")
def export_workbook(
    output: Annotated[
        Path,
        typer.Option("--output", help="Path to the exported XLSX workbook.", dir_okay=False),
    ],
    topic_id: Annotated[
        str | None,
        typer.Option("--topic-id", help="Optional topic id to export only one topic."),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Optional SQLite database path override.", dir_okay=False),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    configure_logging(log_level.upper())
    config_service = _runtime_config_service()
    runtime_settings = Settings.from_config_service(config_service)
    resolved_db_path = resolve_db_path(db_path, config_service=config_service)
    store = SQLiteContentStore(db_path=resolved_db_path)
    ExportMediaCatalogWorkbookUseCase(
        store=store,
        assets_dir=runtime_settings.assets_dir,
        web_app_base_url=runtime_settings.web_app_base_url,
        public_asset_signing_secret=runtime_settings.public_asset_signing_secret,
    ).execute(output_path=output, topic_id=topic_id)
    typer.echo(str(output))


@app.command("import-workbook")
def import_workbook(
    input_path: Annotated[
        Path,
        typer.Option("--input", help="Path to the XLSX workbook to import.", exists=True, dir_okay=False),
    ],
    topic_id: Annotated[
        str | None,
        typer.Option("--topic-id", help="Optional topic id filter for partial import."),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Optional SQLite database path override.", dir_okay=False),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    configure_logging(log_level.upper())
    config_service = _runtime_config_service()
    runtime_settings = Settings.from_config_service(config_service)
    resolved_db_path = resolve_db_path(db_path, config_service=config_service)
    store = SQLiteContentStore(db_path=resolved_db_path)
    result = ImportMediaCatalogWorkbookUseCase(
        store=store,
        assets_dir=runtime_settings.assets_dir,
    ).execute(input_path=input_path, topic_id=topic_id)
    backup_suffix = f" backup={result.backup_path}" if result.backup_path is not None else ""
    typer.echo(f"updated={result.updated_count} db={resolved_db_path}{backup_suffix}")


if __name__ == "__main__":
    app()
