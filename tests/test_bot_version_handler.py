from types import SimpleNamespace

import pytest

from englishbot.bot import help_handler, version_handler
from englishbot.runtime_version import RuntimeVersionInfo


class _FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str, reply_markup=None, parse_mode=None) -> None:  # noqa: ARG002
        self.replies.append(text)


@pytest.mark.anyio
async def test_version_handler_shows_runtime_version_info() -> None:
    message = _FakeMessage()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=1, language_code="en"),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "telegram_ui_language": "en",
                "runtime_version_info": RuntimeVersionInfo(
                    package_version="0.1.0",
                    build_number="3",
                    git_sha="abc1234",
                    git_branch="main",
                ),
            }
        )
    )

    await version_handler(update, context)  # type: ignore[arg-type]

    assert message.replies == [
        "Bot version\nVersion: 0.1.0\nBuild: 3\nGit SHA: abc1234\nBranch: main"
    ]


@pytest.mark.anyio
async def test_help_handler_lists_version_command() -> None:
    message = _FakeMessage()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=1, language_code="en"),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "telegram_ui_language": "en",
                "editor_user_ids": set(),
            }
        )
    )

    await help_handler(update, context)  # type: ignore[arg-type]

    assert "/version - show the current bot version" in message.replies[0]
