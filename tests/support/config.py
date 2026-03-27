from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from englishbot.config import RuntimeConfigService, create_runtime_config_service


def make_test_config_service(
    overrides: Mapping[str, object | None] | None = None,
    *,
    env_file_path: Path | None = None,
) -> RuntimeConfigService:
    service = create_runtime_config_service(env_file_path=env_file_path, environ={})
    if overrides:
        service.update(overrides)
    return service
