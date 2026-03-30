from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import parse_qsl


@dataclass(frozen=True, slots=True)
class TelegramWebAppSession:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    roles: tuple[str, ...]
    is_admin: bool
    is_verified: bool
    is_dev_mode: bool = False


def parse_init_data(init_data: str) -> dict[str, str]:
    return dict(parse_qsl(init_data, keep_blank_values=True))


def verify_init_data(init_data: str, *, bot_token: str) -> bool:
    parsed = parse_init_data(init_data)
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return False
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(calculated_hash, received_hash)


def session_from_init_data(
    init_data: str,
    *,
    bot_token: str,
    roles_by_user: Mapping[int, tuple[str, ...]],
) -> TelegramWebAppSession | None:
    if not verify_init_data(init_data, bot_token=bot_token):
        return None
    parsed = parse_init_data(init_data)
    user_raw = parsed.get("user")
    if not user_raw:
        return None
    user_data = json.loads(user_raw)
    telegram_id = int(user_data["id"])
    roles = _normalize_roles(roles_by_user.get(telegram_id, ()))
    return TelegramWebAppSession(
        telegram_id=telegram_id,
        username=_optional_str(user_data.get("username")),
        first_name=_optional_str(user_data.get("first_name")),
        last_name=_optional_str(user_data.get("last_name")),
        language_code=_optional_str(user_data.get("language_code")),
        roles=roles,
        is_admin="admin" in roles,
        is_verified=True,
    )


def build_dev_session(
    *,
    telegram_id: int,
    roles_by_user: Mapping[int, tuple[str, ...]],
    profile_by_user: Mapping[int, Mapping[str, str | None]] | None = None,
) -> TelegramWebAppSession:
    profile = {} if profile_by_user is None else dict(profile_by_user.get(telegram_id, {}))
    roles = _normalize_roles(roles_by_user.get(telegram_id, ()))
    return TelegramWebAppSession(
        telegram_id=telegram_id,
        username=_optional_str(profile.get("username")),
        first_name=_optional_str(profile.get("first_name")),
        last_name=_optional_str(profile.get("last_name")),
        language_code=_optional_str(profile.get("language_code")),
        roles=roles,
        is_admin="admin" in roles,
        is_verified=False,
        is_dev_mode=True,
    )


def _normalize_roles(roles: tuple[str, ...]) -> tuple[str, ...]:
    normalized = set(roles)
    normalized.add("user")
    return tuple(sorted(normalized))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
