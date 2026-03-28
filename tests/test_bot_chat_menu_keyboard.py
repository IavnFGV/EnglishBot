from englishbot.bot import _chat_menu_keyboard


def test_chat_menu_keyboard_is_temporary_for_regular_users() -> None:
    keyboard = _chat_menu_keyboard(is_editor=False)

    assert keyboard.one_time_keyboard is True
    assert keyboard.is_persistent is False
    assert [[button.text for button in row] for row in keyboard.keyboard] == [
        ["/start", "/help"],
        ["/words"],
    ]


def test_chat_menu_keyboard_includes_editor_commands() -> None:
    keyboard = _chat_menu_keyboard(is_editor=True)

    assert [[button.text for button in row] for row in keyboard.keyboard] == [
        ["/start", "/help"],
        ["/words"],
        ["/add_words", "/cancel"],
    ]
