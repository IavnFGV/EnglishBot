from __future__ import annotations

from pathlib import Path
import re


def build_item_asset_path(*, assets_dir: Path, topic_id: str, item_id: str) -> Path:
    return assets_dir / topic_id / f"{item_id}.png"


def build_item_image_ref(*, assets_dir: Path, topic_id: str, item_id: str) -> str:
    return build_item_asset_path(
        assets_dir=assets_dir,
        topic_id=topic_id,
        item_id=item_id,
    ).as_posix()


def _audio_voice_suffix(voice_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", voice_name).strip("_")
    return normalized or "voice"


def build_item_audio_path(
    *,
    assets_dir: Path,
    topic_id: str,
    item_id: str,
    voice_name: str | None = None,
) -> Path:
    if voice_name:
        return assets_dir / topic_id / "audio" / f"{item_id}__{_audio_voice_suffix(voice_name)}.ogg"
    return assets_dir / topic_id / "audio" / f"{item_id}.ogg"


def build_item_audio_ref(
    *,
    assets_dir: Path,
    topic_id: str,
    item_id: str,
    voice_name: str | None = None,
) -> str:
    return build_item_audio_path(
        assets_dir=assets_dir,
        topic_id=topic_id,
        item_id=item_id,
        voice_name=voice_name,
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


def resolve_existing_audio_path(audio_ref: str | None) -> Path | None:
    if audio_ref is None:
        return None
    candidate = Path(audio_ref)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if candidate.is_file():
        return candidate
    return None
