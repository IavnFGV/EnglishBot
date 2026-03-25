from __future__ import annotations

import json
import logging
from pathlib import Path

from englishbot.importing.models import CanonicalContentPack
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


class JsonContentPackWriter:
    @logged_service_call(
        "JsonContentPackWriter.write",
        transforms={
            "content_pack": lambda value: {
                "item_count": len(value.data.get("vocabulary_items", []))
            },
            "output_path": lambda value: {"output_path": value},
        },
    )
    def write(self, *, content_pack: CanonicalContentPack, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(content_pack.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
