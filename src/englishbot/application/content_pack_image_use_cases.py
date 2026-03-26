from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from englishbot.image_generation.pipeline import ContentPackImageEnricher
from englishbot.logging_utils import logged_service_call


class GenerateContentPackImagesUseCase:
    def __init__(self, *, enricher: ContentPackImageEnricher) -> None:
        self._enricher = enricher

    @logged_service_call(
        "GenerateContentPackImagesUseCase.execute",
        transforms={
            "input_path": lambda value: {"input_path": value},
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
        input_path: Path,
        assets_dir: Path,
        force: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, object]:
        return self._enricher.enrich_file(
            input_path=input_path,
            assets_dir=assets_dir,
            force=force,
            progress_callback=progress_callback,
        )
