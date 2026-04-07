from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from englishbot.cli import (
    configure_cli_logging,
    create_cli_runtime_config_service,
    create_content_store,
)
from englishbot.application.fill_word_audio_use_cases import FillWordAudioUseCase
from englishbot.audio_tooling import run_fill_word_audio
from englishbot.tts_service import TtsServiceClient

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Fill missing word audio by generating local per-word OGG assets through the TTS service.",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

@app.command()
def main(
    topic_id: Annotated[
        str | None,
        typer.Option("--topic-id", help="Only process vocabulary items from this topic."),
    ] = None,
    assets_dir: Annotated[
        Path,
        typer.Option("--assets-dir", help="Directory where generated assets are stored."),
    ] = Path("assets"),
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Maximum number of words to process."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Regenerate even when a local audio asset already exists."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be generated without saving files."),
    ] = False,
    delay_sec: Annotated[
        float,
        typer.Option("--delay-sec", min=0.0, help="Pause between TTS requests."),
    ] = 0.0,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    run_fill_word_audio(
        topic_id=topic_id,
        assets_dir=assets_dir,
        limit=limit,
        force=force,
        dry_run=dry_run,
        delay_sec=delay_sec,
        log_level=log_level,
        repo_root=_REPO_ROOT,
        create_runtime_config_service_fn=create_cli_runtime_config_service,
        configure_cli_logging_fn=configure_cli_logging,
        create_content_store_fn=create_content_store,
        fill_word_audio_use_case_cls=FillWordAudioUseCase,
        tts_service_client_cls=TtsServiceClient,
    )


if __name__ == "__main__":
    app()
