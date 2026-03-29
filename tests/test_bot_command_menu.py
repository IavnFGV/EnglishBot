from types import SimpleNamespace

import pytest

from englishbot.bot import _post_init, _visible_command_rows


class _FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[list[tuple[str, str]], object]] = []

    async def set_my_commands(self, commands, scope=None):  # noqa: ANN001
        self.calls.append(([(command.command, command.description) for command in commands], scope))


def test_visible_command_rows_include_only_accessible_commands() -> None:
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {42},
            }
        )
    )

    regular_rows = _visible_command_rows(context, user_id=7)
    editor_rows = _visible_command_rows(context, user_id=42)

    assert regular_rows == [["/start", "/help"], ["/version", "/words"], ["/assign"]]
    assert editor_rows == [
        ["/start", "/help"],
        ["/version", "/words"],
        ["/assign"],
        ["/add_words", "/cancel"],
    ]


@pytest.mark.anyio
async def test_post_init_sets_public_and_scoped_commands() -> None:
    bot = _FakeBot()
    app = SimpleNamespace(
        bot=bot,
        bot_data={
            "editor_user_ids": {42},
            "admin_user_ids": {100},
        },
    )

    await _post_init(app)  # type: ignore[arg-type]

    assert bot.calls[0][0] == [
        ("start", "Open personal start menu"),
        ("help", "Show commands"),
        ("version", "Show bot version"),
        ("words", "Open words menu"),
        ("assign", "Open assignments menu"),
    ]
    scoped_calls = bot.calls[1:]
    assert len(scoped_calls) == 2
    assert all([command for command, _description in call[0]] == [
        "start",
        "help",
        "version",
        "words",
        "assign",
        "add_words",
        "cancel",
    ] for call in scoped_calls)
