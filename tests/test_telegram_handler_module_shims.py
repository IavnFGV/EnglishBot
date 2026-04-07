from englishbot import telegram_answer_handlers
from englishbot import telegram_answer_processing
from englishbot import telegram_editor_add_words
from englishbot import telegram_editor_images
from englishbot import telegram_entry_handlers
from englishbot import telegram_game_mode
from englishbot import telegram_homework_admin
from englishbot import telegram_image_review_support
from englishbot import telegram_learner_entry_handlers
from englishbot import telegram_medium_task_ui
from englishbot import telegram_navigation_handlers
from englishbot import telegram_question_delivery
from englishbot import telegram_tts
from englishbot.telegram import answer_handlers
from englishbot.telegram import answer_processing
from englishbot.telegram import editor_add_words
from englishbot.telegram import editor_images
from englishbot.telegram import entry_handlers
from englishbot.telegram import game_mode
from englishbot.telegram import homework_admin
from englishbot.telegram import image_review_support
from englishbot.telegram import learner_entry_handlers
from englishbot.telegram import medium_task_ui
from englishbot.telegram import navigation_handlers
from englishbot.telegram import question_delivery
from englishbot.telegram import tts


def test_answer_handlers_shim_re_exports_package_module() -> None:
    assert telegram_answer_handlers.choice_answer_handler is answer_handlers.choice_answer_handler


def test_answer_processing_shim_re_exports_package_module() -> None:
    assert telegram_answer_processing.process_answer is answer_processing.process_answer


def test_editor_add_words_shim_re_exports_package_module() -> None:
    assert telegram_editor_add_words.add_words_start_handler is editor_add_words.add_words_start_handler


def test_editor_images_shim_re_exports_package_module() -> None:
    assert telegram_editor_images.image_review_next_handler is editor_images.image_review_next_handler


def test_entry_handlers_shim_re_exports_package_module() -> None:
    assert telegram_entry_handlers.start_handler is entry_handlers.start_handler


def test_game_mode_shim_re_exports_package_module() -> None:
    assert telegram_game_mode.finish_game_session is game_mode.finish_game_session


def test_homework_admin_shim_re_exports_package_module() -> None:
    assert telegram_homework_admin.goal_text_handler is homework_admin.goal_text_handler


def test_image_review_support_shim_re_exports_package_module() -> None:
    assert telegram_image_review_support.send_image_review_step is image_review_support.send_image_review_step


def test_learner_entry_shim_re_exports_package_module() -> None:
    assert telegram_learner_entry_handlers.lesson_selected_handler is learner_entry_handlers.lesson_selected_handler


def test_medium_task_ui_shim_re_exports_package_module() -> None:
    assert telegram_medium_task_ui.medium_task_keyboard is medium_task_ui.medium_task_keyboard


def test_navigation_handlers_shim_re_exports_package_module() -> None:
    assert telegram_navigation_handlers.words_menu_handler is navigation_handlers.words_menu_handler


def test_question_delivery_shim_re_exports_package_module() -> None:
    assert telegram_question_delivery.send_question is question_delivery.send_question


def test_tts_shim_re_exports_package_module() -> None:
    assert telegram_tts.tts_current_handler is tts.tts_current_handler
