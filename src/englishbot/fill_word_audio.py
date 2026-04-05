from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from englishbot.__main__ import configure_logging
from englishbot.application.fill_word_audio_use_cases import FillWordAudioUseCase
from englishbot.config import create_runtime_config_service
from englishbot.infrastructure.sqlite_store import SQLiteContentStore
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
    use_case = FillWordAudioUseCase(
        store=store,
        tts_client=TtsServiceClient(
            base_url=config_service.get_str("tts_service_base_url"),
            timeout_sec=config_service.get_int("tts_service_timeout_sec"),
        ),
        assets_dir=assets_dir,
        voice_name=config_service.get_str("tts_voice_name"),
    )
    summary = use_case.execute(
        topic_id=topic_id,
        limit=limit,
        force=force,
        dry_run=dry_run,
        delay_sec=delay_sec,
    )
    logging.getLogger(__name__).info(
        "Word audio backfill completed scanned=%s updated=%s skipped=%s failed=%s topic_id=%s dry_run=%s",
        summary.scanned_count,
        summary.updated_count,
        summary.skipped_count,
        summary.failed_count,
        topic_id,
        dry_run,
    )


if __name__ == "__main__":
    app()
