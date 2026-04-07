from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable


def run_fill_word_audio(
    *,
    topic_id: str | None,
    assets_dir: Path,
    limit: int | None,
    force: bool,
    dry_run: bool,
    delay_sec: float,
    log_level: str,
    repo_root: Path,
    create_runtime_config_service_fn: Callable[..., Any],
    configure_cli_logging_fn: Callable[..., None],
    create_content_store_fn: Callable[..., Any],
    fill_word_audio_use_case_cls: type[Any],
    tts_service_client_cls: type[Any],
) -> None:
    config_service = create_runtime_config_service_fn(repo_root=repo_root)
    configure_cli_logging_fn(log_level=log_level, config_service=config_service)
    store = create_content_store_fn(config_service=config_service)
    use_case = fill_word_audio_use_case_cls(
        store=store,
        tts_client=tts_service_client_cls(
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
