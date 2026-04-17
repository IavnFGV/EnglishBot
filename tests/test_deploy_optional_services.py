from pathlib import Path

import pytest

from englishbot.deploy.optional_services import resolve_optional_services_mode


def test_resolve_optional_services_mode_respects_explicit_true(tmp_path: Path) -> None:
    assert resolve_optional_services_mode(
        explicit_mode="true",
        current_release_file=tmp_path / "current-release.env",
        shared_env_file=tmp_path / ".env",
    ) is True


def test_resolve_optional_services_mode_respects_explicit_false(tmp_path: Path) -> None:
    assert resolve_optional_services_mode(
        explicit_mode="false",
        current_release_file=tmp_path / "current-release.env",
        shared_env_file=tmp_path / ".env",
    ) is False


def test_resolve_optional_services_mode_uses_previous_release_flag(tmp_path: Path) -> None:
    current_release_file = tmp_path / "current-release.env"
    current_release_file.write_text(
        "ENGLISHBOT_DEPLOY_OPTIONAL_SERVICES=true\n",
        encoding="utf-8",
    )

    assert resolve_optional_services_mode(
        explicit_mode="auto",
        current_release_file=current_release_file,
        shared_env_file=tmp_path / ".env",
    ) is True


def test_resolve_optional_services_mode_uses_shared_env_webapp_config(tmp_path: Path) -> None:
    shared_env_file = tmp_path / ".env"
    shared_env_file.write_text(
        "WEB_APP_BASE_URL=https://example.com\n",
        encoding="utf-8",
    )

    assert resolve_optional_services_mode(
        explicit_mode="auto",
        current_release_file=tmp_path / "current-release.env",
        shared_env_file=shared_env_file,
    ) is True


def test_resolve_optional_services_mode_uses_shared_env_tts_config(tmp_path: Path) -> None:
    shared_env_file = tmp_path / ".env"
    shared_env_file.write_text(
        "TTS_SERVICE_ENABLED=true\n",
        encoding="utf-8",
    )

    assert resolve_optional_services_mode(
        explicit_mode="auto",
        current_release_file=tmp_path / "current-release.env",
        shared_env_file=shared_env_file,
    ) is True


def test_resolve_optional_services_mode_defaults_to_false_when_unconfigured(tmp_path: Path) -> None:
    assert resolve_optional_services_mode(
        explicit_mode="auto",
        current_release_file=tmp_path / "current-release.env",
        shared_env_file=tmp_path / ".env",
    ) is False


def test_resolve_optional_services_mode_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_optional_services_mode(
            explicit_mode="maybe",
            current_release_file=tmp_path / "current-release.env",
            shared_env_file=tmp_path / ".env",
        )
