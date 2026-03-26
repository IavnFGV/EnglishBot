from __future__ import annotations

from pathlib import Path


def build_square_preview_path(*, source_path: Path, size: int) -> Path:
    return source_path.with_name(f"{source_path.stem}--preview-{size}.jpg")


def ensure_square_preview(
    *,
    source_path: Path,
    size: int = 256,
    background_color: tuple[int, int, int] = (255, 255, 255),
) -> Path:
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise RuntimeError("Pillow is required to build image previews.") from error

    output_path = build_square_preview_path(source_path=source_path, size=size)
    if output_path.exists() and output_path.stat().st_mtime >= source_path.stat().st_mtime:
        return output_path

    with Image.open(source_path) as image:
        normalized = image.convert("RGBA")
        contained = ImageOps.contain(normalized, (size, size))
        canvas = Image.new("RGBA", (size, size), background_color + (255,))
        offset_x = (size - contained.width) // 2
        offset_y = (size - contained.height) // 2
        canvas.paste(contained, (offset_x, offset_y), contained)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.convert("RGB").save(output_path, format="JPEG", quality=85, optimize=True)
    return output_path
