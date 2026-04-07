from __future__ import annotations

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
from englishbot.image_tooling import run_apply_image_rerank_decisions

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
    run_apply_image_rerank_decisions(
        input_path=input,
        assets_dir=assets_dir,
        dry_run=dry_run,
        log_level=log_level,
        repo_root=_REPO_ROOT,
        create_runtime_config_service_fn=create_cli_runtime_config_service,
        configure_cli_logging_fn=configure_cli_logging,
        create_content_store_fn=create_content_store,
        read_image_rerank_decisions_fn=read_image_rerank_decisions,
        apply_image_rerank_decisions_use_case_cls=ApplyImageRerankDecisionsUseCase,
        remote_image_downloader_cls=RemoteImageDownloader,
    )


if __name__ == "__main__":
    app()
