from __future__ import annotations

import argparse
from pathlib import Path


def _read_key_value_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _looks_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _looks_configured(value: str | None) -> bool:
    return bool(value and value.strip())


def resolve_optional_services_mode(
    *,
    explicit_mode: str | None,
    current_release_file: Path,
    shared_env_file: Path,
) -> bool:
    normalized_mode = (explicit_mode or "").strip().lower()
    if normalized_mode in {"true", "false"}:
        return normalized_mode == "true"
    if normalized_mode not in {"", "auto"}:
        raise ValueError(f"Unsupported DEPLOY_OPTIONAL_SERVICES mode: {explicit_mode}")

    current_release_values = _read_key_value_file(current_release_file)
    if _looks_truthy(current_release_values.get("ENGLISHBOT_DEPLOY_OPTIONAL_SERVICES")):
        return True

    shared_env_values = _read_key_value_file(shared_env_file)
    if _looks_configured(shared_env_values.get("WEB_APP_BASE_URL")):
        return True
    if _looks_truthy(shared_env_values.get("TTS_SERVICE_ENABLED")):
        return True
    if _looks_configured(shared_env_values.get("PUBLIC_ASSET_SIGNING_SECRET")):
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="auto")
    parser.add_argument("--current-release-file", type=Path, required=True)
    parser.add_argument("--shared-env-file", type=Path, required=True)
    args = parser.parse_args()
    enabled = resolve_optional_services_mode(
        explicit_mode=args.mode,
        current_release_file=args.current_release_file,
        shared_env_file=args.shared_env_file,
    )
    print("true" if enabled else "false")


if __name__ == "__main__":
    main()

