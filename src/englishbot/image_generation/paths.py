from __future__ import annotations

from pathlib import Path


def build_item_asset_path(*, assets_dir: Path, topic_id: str, item_id: str) -> Path:
    return assets_dir / topic_id / f"{item_id}.png"


def build_item_image_ref(*, assets_dir: Path, topic_id: str, item_id: str) -> str:
    return build_item_asset_path(
        assets_dir=assets_dir,
        topic_id=topic_id,
        item_id=item_id,
    ).as_posix()


def resolve_existing_image_path(image_ref: str | None) -> Path | None:
    if image_ref is None:
        return None
    candidate = Path(image_ref)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if candidate.is_file():
        return candidate
    return None
