from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from englishbot.cli import (
    configure_cli_logging,
    create_cli_runtime_config_service,
    create_content_store,
)
from englishbot.application.image_rerank_manifest_use_cases import (
    ApplyImageRerankDecisionsUseCase,
    read_image_rerank_decisions,
)
from englishbot.image_generation.pixabay import RemoteImageDownloader

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
    config_service = create_cli_runtime_config_service(repo_root=_REPO_ROOT)
    configure_cli_logging(log_level=log_level, config_service=config_service)
    store = create_content_store(config_service=config_service)
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
