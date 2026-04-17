from __future__ import annotations

import hashlib
import hmac
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from englishbot.image_generation.previews import ensure_square_preview

PUBLIC_ASSET_PREVIEW_SIZE_PX = 256


def build_public_asset_preview_url(
    *,
    base_url: str,
    signing_secret: str,
    image_ref: str,
    assets_dir: Path,
) -> str | None:
    normalized_base_url = base_url.rstrip("/")
    normalized_secret = signing_secret.strip()
    if not normalized_base_url or not normalized_secret:
        return None
    relative_path = normalize_public_asset_relative_path(image_ref=image_ref, assets_dir=assets_dir)
    if relative_path is None:
        return None
    source_path = resolve_public_asset_path(relative_path=relative_path, assets_dir=assets_dir)
    if not source_path.is_file():
        return None
    ensure_square_preview(source_path=source_path, size=PUBLIC_ASSET_PREVIEW_SIZE_PX)
    signature = sign_public_asset_path(
        relative_path=relative_path,
        variant="preview",
        signing_secret=normalized_secret,
    )
    encoded_path = quote(relative_path, safe="/")
    return f"{normalized_base_url}/public-assets/preview?path={encoded_path}&sig={signature}"


def sign_public_asset_path(
    *,
    relative_path: str,
    variant: str,
    signing_secret: str,
) -> str:
    payload = f"{variant}:{relative_path}".encode("utf-8")
    return hmac.new(signing_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_public_asset_signature(
    *,
    relative_path: str,
    variant: str,
    signature: str,
    signing_secret: str,
) -> bool:
    expected = sign_public_asset_path(
        relative_path=relative_path,
        variant=variant,
        signing_secret=signing_secret,
    )
    return hmac.compare_digest(expected, signature.strip())


def normalize_public_asset_relative_path(*, image_ref: str, assets_dir: Path) -> str | None:
    normalized_ref = image_ref.strip()
    if not normalized_ref:
        return None
    candidate = PurePosixPath(normalized_ref)
    if candidate.is_absolute():
        absolute_candidate = Path(normalized_ref).resolve(strict=False)
        try:
            relative = absolute_candidate.relative_to(assets_dir.resolve(strict=False))
        except ValueError:
            return None
        return relative.as_posix()
    parts = candidate.parts
    if not parts:
        return None
    if parts[0] == "assets":
        candidate = PurePosixPath(*parts[1:])
    if any(part in {"..", "."} for part in candidate.parts):
        return None
    normalized = candidate.as_posix().strip("/")
    return normalized or None


def resolve_public_asset_path(*, relative_path: str, assets_dir: Path) -> Path:
    normalized = PurePosixPath(relative_path)
    if normalized.is_absolute() or any(part in {"..", "."} for part in normalized.parts):
        raise ValueError("Invalid public asset path.")
    return assets_dir / Path(*normalized.parts)


def resolve_public_asset_preview_path(*, relative_path: str, assets_dir: Path) -> Path:
    source_path = resolve_public_asset_path(relative_path=relative_path, assets_dir=assets_dir)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    return ensure_square_preview(source_path=source_path, size=PUBLIC_ASSET_PREVIEW_SIZE_PX)
