from englishbot.presentation.telegram_menu_access import (
    DEFAULT_TELEGRAM_COMMAND_SPECS,
    PERMISSION_WORDS_ADD,
    PERMISSION_WORDS_EDIT,
    TelegramMenuAccessPolicy,
)


def test_access_policy_uses_legacy_editor_ids_from_bot_data() -> None:
    policy = TelegramMenuAccessPolicy.from_bot_data({"editor_user_ids": {101}})

    assert policy.has_permission(101, PERMISSION_WORDS_ADD) is True
    assert policy.has_permission(999, PERMISSION_WORDS_ADD) is False


def test_access_policy_admin_role_has_wildcard_permissions() -> None:
    policy = TelegramMenuAccessPolicy.from_bot_data({"admin_user_ids": {7}})

    assert policy.has_permission(7, PERMISSION_WORDS_ADD) is True
    assert policy.has_permission(7, "future.permission") is True


def test_access_policy_can_be_extended_with_custom_roles() -> None:
    policy = TelegramMenuAccessPolicy.from_bot_data(
        {
            "menu_role_memberships": {
                "user": set(),
                "moderator": {33},
            },
            "menu_role_permissions": {
                "user": set(),
                "moderator": {PERMISSION_WORDS_EDIT},
            },
        }
    )

    assert policy.has_permission(33, PERMISSION_WORDS_EDIT) is True
    assert policy.has_permission(33, PERMISSION_WORDS_ADD) is False


def test_visible_commands_follow_permissions() -> None:
    policy = TelegramMenuAccessPolicy.from_bot_data({"editor_user_ids": {101}})

    regular_commands = [spec.command for spec in policy.visible_commands(user_id=999)]
    editor_commands = [spec.command for spec in policy.visible_commands(user_id=101)]

    assert regular_commands == ["start", "help", "version", "words", "assign"]
    assert editor_commands == [spec.command for spec in DEFAULT_TELEGRAM_COMMAND_SPECS]
