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


def test_telegram_ui_text_returns_localized_assignment_progress_legend() -> None:
    assert telegram_ui_text("assignment_progress_legend_warmup", language="en") == "warm-up"
    assert telegram_ui_text("assignment_progress_legend_warmup", language="ru") == "разминка"
    assert telegram_ui_text("assignment_progress_legend_warmup", language="uk") == "розігрів"


def test_telegram_ui_text_returns_localized_assignment_progress_hard_note() -> None:
    assert telegram_ui_text("assignment_progress_legend_hard_note", language="en") == "hard clear"
    assert telegram_ui_text("assignment_progress_legend_hard_note", language="ru") == "hard пройден"
    assert telegram_ui_text("assignment_progress_legend_hard_note", language="uk") == "hard пройдено"


def test_telegram_ui_text_returns_localized_tts_strings() -> None:
    assert telegram_ui_text("tts_play_button", language="en") == "🔊 Play"
    assert telegram_ui_text("tts_voice_menu_button", language="en") == "🎙 Voice"
    assert telegram_ui_text("tts_play_button", language="ru") == "🔊 Слушать"
    assert telegram_ui_text("tts_voice_menu_button", language="ru") == "🎙 Голос"
    assert telegram_ui_text("tts_play_button", language="uk") == "🔊 Слухати"
    assert telegram_ui_text("tts_voice_menu_button", language="uk") == "🎙 Голос"
    assert telegram_ui_text("tts_unavailable", language="en") == "Audio is unavailable right now."
    assert telegram_ui_text("tts_already_sending", language="en") == "Sending audio..."
    assert telegram_ui_text("tts_recently_sent", language="en") == "Audio was just sent."
