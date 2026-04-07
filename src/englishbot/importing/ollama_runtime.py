from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_runtime_ollama_model(*, default_model: str, model_file_path: Path | None) -> str:
    if model_file_path is not None:
        try:
            file_value = model_file_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            logger.debug("Ollama model file is missing path=%s. Using configured default.", model_file_path)
        except OSError:
            logger.warning("Could not read Ollama model file path=%s", model_file_path, exc_info=True)
        else:
            if file_value:
                return file_value
            logger.debug("Ollama model file is empty path=%s. Using configured default.", model_file_path)
    return default_model
