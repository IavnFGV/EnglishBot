from types import SimpleNamespace

import pytest
from telegram.error import NetworkError, RetryAfter

from englishbot import bot


@pytest.mark.anyio
async def test_error_handler_logs_retry_after_as_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="englishbot.bot"):
        await bot.error_handler(
            {"update_id": 1},
            SimpleNamespace(error=RetryAfter(retry_after=5)),
        )

    assert "Telegram flood control requested" in caplog.text
    assert "Unhandled Telegram update error" not in caplog.text


@pytest.mark.anyio
async def test_error_handler_logs_network_error_as_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="englishbot.bot"):
        await bot.error_handler(
            {"update_id": 2},
            SimpleNamespace(error=NetworkError("Bad Gateway")),
        )

    assert "Temporary Telegram network error" in caplog.text
    assert "Unhandled Telegram update error" not in caplog.text


@pytest.mark.anyio
async def test_error_handler_keeps_unexpected_errors_as_exceptions(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("ERROR", logger="englishbot.bot"):
        await bot.error_handler(
            {"update_id": 3},
            SimpleNamespace(error=RuntimeError("boom")),
        )

    assert "Unhandled Telegram update error" in caplog.text
