from englishbot.presentation.telegram_ui_text import (
    DEFAULT_TELEGRAM_UI_LANGUAGE,
    supported_telegram_ui_languages,
    telegram_ui_text,
)


def test_telegram_ui_text_supports_expected_languages() -> None:
    assert supported_telegram_ui_languages() == ("en", "ru", "uk")


def test_telegram_ui_text_falls_back_to_default_language() -> None:
    assert (
        telegram_ui_text("approve_auto_images", language="de")
        == telegram_ui_text("approve_auto_images", language=DEFAULT_TELEGRAM_UI_LANGUAGE)
    )


def test_telegram_ui_text_formats_placeholders() -> None:
    assert telegram_ui_text("use_n", language="en", index=3) == "Use 3"


def test_telegram_ui_text_returns_ukrainian_copy() -> None:
    assert telegram_ui_text("continue", language="uk") == "Продовжити"
