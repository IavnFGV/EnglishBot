from types import SimpleNamespace

import pytest

from englishbot.bot import _post_init


class _FakeBot:
    def __init__(self) -> None:
        self.commands: list[object] | None = None

    async def set_my_commands(self, commands: list[object]) -> None:
        self.commands = commands


@pytest.mark.anyio
async def test_post_init_clears_telegram_command_menu() -> None:
    fake_bot = _FakeBot()
    app = SimpleNamespace(bot=fake_bot)

    await _post_init(app)  # type: ignore[arg-type]

    assert fake_bot.commands == []
