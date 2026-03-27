from __future__ import annotations

import logging
from types import SimpleNamespace
from pathlib import Path

import englishbot.__main__ as main_module
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


def test_main_loads_env_file_with_override_and_prefers_file_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=test-token",
                "LOG_LEVEL=INFO",
                "CONTENT_DB_PATH=data/test.db",
                "OLLAMA_BASE_URL=http://127.0.0.1:12434",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(main_module, "_REPO_ROOT", tmp_path)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    captured: dict[str, object] = {}

    def fake_build_application(settings, *, config_service):
        captured["ollama_base_url"] = settings.ollama_base_url
        captured["config_ollama_base_url"] = config_service.get_str("ollama_base_url")

        class _FakeApp:
            def run_polling(self) -> None:
                return None

        return _FakeApp()

    monkeypatch.setattr(main_module, "build_application", fake_build_application)
    monkeypatch.setattr(main_module, "configure_logging", lambda *args, **kwargs: None)

    main_module.main()

    assert captured["ollama_base_url"] == "http://127.0.0.1:12434"
    assert captured["config_ollama_base_url"] == "http://127.0.0.1:12434"
