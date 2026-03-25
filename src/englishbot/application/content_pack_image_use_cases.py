from __future__ import annotations

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
    ) -> dict[str, object]:
        return self._enricher.enrich_file(
            input_path=input_path,
            assets_dir=assets_dir,
            force=force,
        )
