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
    ExportImageRerankManifestUseCase,
    write_image_rerank_manifest,
)
from englishbot.image_tooling import run_export_image_rerank_manifest

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Export a JSON manifest of vocabulary items for offline AI image reranking.",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

@app.command()
def main(
    output: Annotated[
        Path,
        typer.Option("--output", help="Path to the manifest JSON file."),
    ] = Path("output/image-rerank-manifest.json"),
    topic_id: Annotated[
        str | None,
        typer.Option("--topic-id", help="Only export one topic."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Maximum number of words to export."),
    ] = None,
    only_missing_images: Annotated[
        bool,
        typer.Option("--only-missing-images", help="Export only items without image_ref."),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    run_export_image_rerank_manifest(
        output=output,
        topic_id=topic_id,
        limit=limit,
        only_missing_images=only_missing_images,
        log_level=log_level,
        repo_root=_REPO_ROOT,
        create_runtime_config_service_fn=create_cli_runtime_config_service,
        configure_cli_logging_fn=configure_cli_logging,
        create_content_store_fn=create_content_store,
        export_image_rerank_manifest_use_case_cls=ExportImageRerankManifestUseCase,
        write_image_rerank_manifest_fn=write_image_rerank_manifest,
    )


if __name__ == "__main__":
    app()
