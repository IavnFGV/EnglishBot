from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_prompt_text(*, path: Path | None, fallback: str) -> str:
    if path is None:
        return fallback
    try:
        return path.read_text(encoding="utf-8").strip() or fallback
    except FileNotFoundError:
        logger.warning("Prompt file is missing path=%s. Falling back to built-in prompt.", path)
        return fallback
