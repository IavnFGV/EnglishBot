from englishbot import telegram_admin_utils
from englishbot import telegram_assignment_progress
from englishbot import telegram_command_menu
from englishbot import telegram_flow_tracking
from englishbot import telegram_notifications
from englishbot.telegram import admin_utils
from englishbot.telegram import assignment_progress
from englishbot.telegram import command_menu
from englishbot.telegram import flow_tracking
from englishbot.telegram import notifications


def test_telegram_command_menu_shim_re_exports_package_module() -> None:
    assert telegram_command_menu.visible_command_rows is command_menu.visible_command_rows


def test_telegram_assignment_progress_shim_re_exports_package_module() -> None:
    assert (
        telegram_assignment_progress.assignment_progress_variant_index
        is assignment_progress.assignment_progress_variant_index
    )


def test_telegram_notifications_shim_re_exports_package_module() -> None:
    assert telegram_notifications.pending_notifications is notifications.pending_notifications


def test_telegram_flow_tracking_shim_re_exports_package_module() -> None:
    assert telegram_flow_tracking.track_flow_message is flow_tracking.track_flow_message


def test_telegram_admin_utils_shim_re_exports_package_module() -> None:
    assert telegram_admin_utils.makeadmin_handler is admin_utils.makeadmin_handler
