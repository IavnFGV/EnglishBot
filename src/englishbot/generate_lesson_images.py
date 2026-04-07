from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.image_generation.clients import (
    ComfyUIImageGenerationClient,
    LocalPlaceholderImageGenerationClient,
)
from englishbot.image_generation.pipeline import ContentPackImageEnricher
from englishbot.image_tooling import run_generate_lesson_images

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
    comfyui_vae: Annotated[
        str | None,
        typer.Option("--comfyui-vae", help="Optional VAE filename available inside ComfyUI."),
    ] = None,
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
    run_generate_lesson_images(
        input_path=input_path,
        assets_dir=assets_dir,
        backend=backend,
        comfyui_base_url=comfyui_base_url,
        comfyui_checkpoint=comfyui_checkpoint,
        comfyui_vae=comfyui_vae,
        force=force,
        log_level=log_level,
        configure_logging_fn=configure_logging,
        comfyui_client_cls=ComfyUIImageGenerationClient,
        placeholder_client_factory=LocalPlaceholderImageGenerationClient,
        content_pack_image_enricher_cls=ContentPackImageEnricher,
    )


if __name__ == "__main__":
    app()
