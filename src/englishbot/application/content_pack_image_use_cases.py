from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from englishbot.image_generation.pipeline import ContentPackImageEnricher
from englishbot.infrastructure.sqlite_store import SQLiteContentStore
from englishbot.logging_utils import logged_service_call


class GenerateContentPackImagesUseCase:
    def __init__(self, *, enricher: ContentPackImageEnricher, db_path: Path) -> None:
        self._enricher = enricher
        self._store = SQLiteContentStore(db_path=db_path)
        self._store.initialize()

    @logged_service_call(
        "GenerateContentPackImagesUseCase.execute",
        transforms={
            "topic_id": lambda value: {"topic_id": value},
            "assets_dir": lambda value: {"assets_dir": value},
        },
        include=("force",),
        exclude=("progress_callback",),
        result=lambda value: {
            "item_count": len(value.get("vocabulary_items", [])),
            "generated_count": sum(
                1 for item in value.get("vocabulary_items", []) if item.get("image_ref")
            ),
        },
    )
    def execute(
        self,
        *,
        topic_id: str,
        assets_dir: Path,
        force: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, object]:
        content_pack = self._store.get_content_pack(topic_id)
        enriched = self._enricher.enrich_content_pack(
            content_pack=content_pack,
            assets_dir=assets_dir,
            force=force,
            progress_callback=progress_callback,
        )
        self._store.upsert_content_pack(enriched)
        return enriched
