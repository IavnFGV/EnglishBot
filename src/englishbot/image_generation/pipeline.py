from __future__ import annotations

import json
import logging
from pathlib import Path

from englishbot.image_generation.clients import ImageGenerationClient
from englishbot.image_generation.paths import (
    build_item_asset_path,
    build_item_image_ref,
    resolve_existing_image_path,
)
from englishbot.image_generation.prompts import compose_image_prompt, fallback_image_prompt
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


class ContentPackImageEnricher:
    def __init__(self, image_client: ImageGenerationClient) -> None:
        self._image_client = image_client

    @logged_service_call(
        "ContentPackImageEnricher.enrich_file",
        transforms={
            "input_path": lambda value: {"input_path": value},
            "assets_dir": lambda value: {"assets_dir": value},
        },
        include=("force",),
        result=lambda value: {
            "item_count": len(value.get("vocabulary_items", [])),
        },
    )
    def enrich_file(
        self,
        *,
        input_path: Path,
        assets_dir: Path,
        force: bool = False,
    ) -> dict[str, object]:
        content_pack = json.loads(input_path.read_text(encoding="utf-8"))
        enriched = self.enrich_content_pack(
            content_pack=content_pack,
            assets_dir=assets_dir,
            force=force,
        )
        input_path.write_text(
            json.dumps(enriched, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return enriched

    @logged_service_call(
        "ContentPackImageEnricher.enrich_content_pack",
        transforms={
            "content_pack": lambda value: {
                "item_count": len(value.get("vocabulary_items", []))
                if isinstance(value, dict)
                else None
            },
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
    def enrich_content_pack(
        self,
        *,
        content_pack: dict[str, object],
        assets_dir: Path,
        force: bool = False,
    ) -> dict[str, object]:
        topic = content_pack.get("topic", {})
        topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
        if not topic_id:
            raise ValueError("Content pack topic.id is required for image generation.")

        raw_items = content_pack.get("vocabulary_items", [])
        if not isinstance(raw_items, list):
            raise ValueError("Content pack vocabulary_items must be a list.")

        updated_items: list[dict[str, object]] = []
        for raw_item in raw_items:
            item = dict(raw_item) if isinstance(raw_item, dict) else {}
            item_id = str(item.get("id", "")).strip()
            english_word = str(item.get("english_word", "")).strip()
            if not item_id or not english_word:
                updated_items.append(item)
                continue

            image_ref = item.get("image_ref")
            existing_path = resolve_existing_image_path(str(image_ref)) if image_ref else None
            if existing_path is not None and not force:
                updated_items.append(item)
                continue

            raw_prompt = str(item.get("image_prompt", "")).strip()
            prompt = (
                compose_image_prompt(raw_prompt)
                if raw_prompt
                else fallback_image_prompt(english_word)
            )
            asset_path = build_item_asset_path(
                assets_dir=assets_dir,
                topic_id=topic_id,
                item_id=item_id,
            )
            self._image_client.generate(
                prompt=prompt,
                english_word=english_word,
                output_path=asset_path,
            )
            item["image_prompt"] = prompt
            item["image_ref"] = build_item_image_ref(
                assets_dir=assets_dir,
                topic_id=topic_id,
                item_id=item_id,
            )
            updated_items.append(item)

        updated_pack = dict(content_pack)
        updated_pack["vocabulary_items"] = updated_items
        return updated_pack
