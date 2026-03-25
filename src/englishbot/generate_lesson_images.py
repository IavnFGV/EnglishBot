from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.image_generation.clients import LocalPlaceholderImageGenerationClient
from englishbot.image_generation.pipeline import ContentPackImageEnricher

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Generate local image assets for a content pack.",
)


@app.command()
def main(
    input_path: Annotated[
        Path,
        typer.Option("--input", help="Path to the content pack JSON.", exists=True, dir_okay=False),
    ],
    assets_dir: Annotated[
        Path,
        typer.Option("--assets-dir", help="Directory where generated assets are stored."),
    ] = Path("assets"),
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Regenerate images even if image_ref already points to an existing file.",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    configure_logging(log_level.upper())
    enricher = ContentPackImageEnricher(LocalPlaceholderImageGenerationClient())
    enriched_pack = enricher.enrich_file(
        input_path=input_path,
        assets_dir=assets_dir,
        force=force,
    )
    logging.getLogger(__name__).info(
        "Image generation completed item_count=%s input_path=%s",
        len(enriched_pack.get("vocabulary_items", [])),
        input_path,
    )


if __name__ == "__main__":
    app()
