from __future__ import annotations

import logging
from pathlib import Path

from englishbot.__main__ import configure_logging


def test_configure_logging_writes_to_log_file(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "englishbot.log"

    configure_logging("INFO", log_file_path=log_path)
    logger = logging.getLogger("englishbot.test")
    logger.info("file logging works")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_path.exists()
    contents = log_path.read_text(encoding="utf-8")
    assert "INFO [englishbot.test] file logging works" in contents


def test_configure_logging_rotates_log_file(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "englishbot.log"

    configure_logging(
        "INFO",
        log_file_path=log_path,
        log_max_bytes=200,
        log_backup_count=2,
    )
    logger = logging.getLogger("englishbot.rotate")
    for index in range(20):
        logger.info("rotation message %s %s", index, "x" * 40)
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_path.exists()
    assert (log_path.parent / "englishbot.log.1").exists()
