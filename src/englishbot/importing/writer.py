from __future__ import annotations

import json
import logging
from pathlib import Path

from englishbot.importing.models import CanonicalContentPack

logger = logging.getLogger(__name__)


class JsonContentPackWriter:
    def write(self, *, content_pack: CanonicalContentPack, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(content_pack.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("JsonContentPackWriter wrote content pack to %s", output_path)
