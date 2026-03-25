from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.image_generation.clients import (
    ComfyUIImageGenerationClient,
    LocalPlaceholderImageGenerationClient,
)
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
    backend: Annotated[
        str,
        typer.Option("--backend", help="Image generation backend: placeholder or comfyui."),
    ] = "placeholder",
    comfyui_base_url: Annotated[
        str,
        typer.Option("--comfyui-base-url", help="Base URL for a local ComfyUI server."),
    ] = "http://127.0.0.1:8188",
    comfyui_checkpoint: Annotated[
        str,
        typer.Option("--comfyui-checkpoint", help="Checkpoint name available inside ComfyUI."),
    ] = "v1-5-pruned-emaonly.safetensors",
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
    if backend == "placeholder":
        image_client = LocalPlaceholderImageGenerationClient()
    elif backend == "comfyui":
        image_client = ComfyUIImageGenerationClient(
            base_url=comfyui_base_url,
            checkpoint_name=comfyui_checkpoint,
        )
    else:
        raise typer.BadParameter(
            "Backend must be one of: placeholder, comfyui.",
            param_hint="--backend",
        )

    enricher = ContentPackImageEnricher(image_client)
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
