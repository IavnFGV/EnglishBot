from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from englishbot.image_generation.paths import build_item_audio_path, build_item_audio_ref, resolve_existing_audio_path
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class FillWordAudioSummary:
    scanned_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0


class FillWordAudioUseCase:
    def __init__(
        self,
        *,
        store,
        tts_client,
        assets_dir: Path,
    ) -> None:
        self._store = store
        self._tts_client = tts_client
        self._assets_dir = assets_dir

    @logged_service_call(
        "FillWordAudioUseCase.execute",
        include=("topic_id", "limit", "force", "dry_run", "delay_sec"),
        result=lambda value: {
            "scanned_count": value.scanned_count,
            "updated_count": value.updated_count,
            "skipped_count": value.skipped_count,
            "failed_count": value.failed_count,
        },
    )
    def execute(
        self,
        *,
        topic_id: str | None = None,
        limit: int | None = None,
        force: bool = False,
        dry_run: bool = False,
        delay_sec: float = 0.0,
    ) -> FillWordAudioSummary:
        scanned_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        items = [
            item
            for item in self._store.list_all_vocabulary()
            if item.is_active and (topic_id is None or item.topic_id == topic_id)
        ]
        if limit is not None:
            items = items[:limit]
        for item in items:
            scanned_count += 1
            existing_path = resolve_existing_audio_path(item.audio_ref)
            if not force and existing_path is not None:
                skipped_count += 1
                continue
            if item.topic_id is None:
                failed_count += 1
                logger.warning("Skipping audio backfill without topic_id item_id=%s", item.id)
                continue
            try:
                audio_bytes = self._tts_client.synthesize(text=item.english_word)
                output_path = build_item_audio_path(
                    assets_dir=self._assets_dir,
                    topic_id=item.topic_id,
                    item_id=item.id,
                )
                audio_ref = build_item_audio_ref(
                    assets_dir=self._assets_dir,
                    topic_id=item.topic_id,
                    item_id=item.id,
                )
                logger.info(
                    "Generated word audio item_id=%s english_word=%s output_path=%s",
                    item.id,
                    item.english_word,
                    output_path,
                )
                if not dry_run:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(audio_bytes)
                    self._store.update_word_audio(item_id=item.id, audio_ref=audio_ref)
                updated_count += 1
            except Exception:  # noqa: BLE001
                failed_count += 1
                logger.exception("Failed to backfill audio item_id=%s english_word=%s", item.id, item.english_word)
            if delay_sec > 0:
                time.sleep(delay_sec)
        return FillWordAudioSummary(
            scanned_count=scanned_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
        )
