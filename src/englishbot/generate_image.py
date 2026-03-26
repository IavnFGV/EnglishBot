from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.image_generation.clients import (
    ComfyUIImageGenerationClient,
    DEFAULT_COMFYUI_CHECKPOINT_NAME,
    LocalPlaceholderImageGenerationClient,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Generate a single image from a prompt.",
)


@app.command()
def main(
    prompt: Annotated[
        str,
        typer.Option("--prompt", help="Full image prompt."),
    ],
    output_path: Annotated[
        Path,
        typer.Option("--output", help="Output image path."),
    ],
    english_word: Annotated[
        str,
        typer.Option(
            "--english-word",
            help="Word used for negative-prompt tuning and file metadata.",
        ),
    ] = "image",
    backend: Annotated[
        str,
        typer.Option("--backend", help="Image generation backend: placeholder or comfyui."),
    ] = "comfyui",
    comfyui_base_url: Annotated[
        str,
        typer.Option("--comfyui-base-url", help="Base URL for a local ComfyUI server."),
    ] = "http://127.0.0.1:8188",
    comfyui_checkpoint: Annotated[
        str,
        typer.Option("--comfyui-checkpoint", help="Checkpoint name available inside ComfyUI."),
    ] = DEFAULT_COMFYUI_CHECKPOINT_NAME,
    comfyui_vae: Annotated[
        str | None,
        typer.Option("--comfyui-vae", help="Optional VAE filename available inside ComfyUI."),
    ] = None,
    width: Annotated[
        int,
        typer.Option("--width", help="Output width in pixels."),
    ] = 512,
    height: Annotated[
        int,
        typer.Option("--height", help="Output height in pixels."),
    ] = 512,
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
            vae_name=comfyui_vae,
            width=width,
            height=height,
        )
    else:
        raise typer.BadParameter(
            "Backend must be one of: placeholder, comfyui.",
            param_hint="--backend",
        )

    image_client.generate(
        prompt=prompt,
        english_word=english_word,
        output_path=output_path,
    )
    logging.getLogger(__name__).info(
        "Single image generation completed output_path=%s english_word=%s",
        output_path,
        english_word,
    )


if __name__ == "__main__":
    app()
