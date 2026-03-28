from types import SimpleNamespace

from englishbot.bot import _normalize_telegram_ui_language, _telegram_ui_language


def test_normalize_telegram_ui_language_maps_ua_to_uk() -> None:
    assert _normalize_telegram_ui_language("ua") == "uk"
    assert _normalize_telegram_ui_language("uk-UA") == "uk"


def test_telegram_ui_language_prefers_supported_user_locale_over_configured_default() -> None:
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "telegram_ui_language": "en",
            }
        ),
        user_data={},
    )
    user = SimpleNamespace(language_code="uk-UA")

    assert _telegram_ui_language(context, user) == "uk"
    assert context.user_data["telegram_ui_language"] == "uk"


def test_telegram_ui_language_falls_back_to_configured_default_for_unsupported_user_locale() -> None:
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "telegram_ui_language": "ru",
            }
        ),
        user_data={},
    )
    user = SimpleNamespace(language_code="bg-BG")

    assert _telegram_ui_language(context, user) == "ru"


def test_telegram_ui_language_reuses_last_detected_user_language_from_context() -> None:
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "telegram_ui_language": "ru",
            }
        ),
        user_data={"telegram_ui_language": "en"},
    )

    assert _telegram_ui_language(context, None) == "en"


def test_normalize_telegram_ui_language_supports_underscore_locale_separator() -> None:
    assert _normalize_telegram_ui_language("en_US") == "en"
