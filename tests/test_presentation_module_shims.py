from englishbot import assignment_progress_image
from englishbot import bot_assignments_admin_ui
from englishbot import bot_assignments_ui
from englishbot import bot_editor_ui
from englishbot.presentation import assignment_progress_image as presentation_progress_image
from englishbot.presentation import telegram_assignments_admin_ui
from englishbot.presentation import telegram_assignments_ui
from englishbot.presentation import telegram_editor_ui


def test_assignment_ui_shim_re_exports_presentation_module() -> None:
    assert bot_assignments_ui.render_progress_text is telegram_assignments_ui.render_progress_text


def test_assignment_admin_ui_shim_re_exports_presentation_module() -> None:
    assert (
        bot_assignments_admin_ui.render_assignment_user_detail_text
        is telegram_assignments_admin_ui.render_assignment_user_detail_text
    )


def test_editor_ui_shim_re_exports_presentation_module() -> None:
    assert bot_editor_ui.words_menu_keyboard is telegram_editor_ui.words_menu_keyboard


def test_assignment_progress_image_shim_re_exports_presentation_module() -> None:
    assert (
        assignment_progress_image.render_assignment_progress_image
        is presentation_progress_image.render_assignment_progress_image
    )
    assert assignment_progress_image._segment_color is presentation_progress_image._segment_color
