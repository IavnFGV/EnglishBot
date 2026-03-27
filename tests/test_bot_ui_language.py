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
        )
    )
    user = SimpleNamespace(language_code="uk-UA")

    assert _telegram_ui_language(context, user) == "uk"


def test_telegram_ui_language_falls_back_to_configured_default_for_unsupported_user_locale() -> None:
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "telegram_ui_language": "ru",
            }
        )
    )
    user = SimpleNamespace(language_code="bg-BG")

    assert _telegram_ui_language(context, user) == "ru"
