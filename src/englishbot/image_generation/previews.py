from __future__ import annotations

from pathlib import Path
from typing import Sequence


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


def ensure_numbered_candidate_strip(
    *,
    source_paths: Sequence[Path],
    output_path: Path,
    tile_size: int = 256,
    gap: int = 12,
    background_color: tuple[int, int, int] = (255, 255, 255),
) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:
        raise RuntimeError("Pillow is required to build image previews.") from error

    normalized_sources = [Path(path) for path in source_paths]
    if not normalized_sources:
        raise ValueError("At least one source image is required to build a candidate strip.")
    if output_path.exists():
        output_mtime = output_path.stat().st_mtime
        if all(output_mtime >= source_path.stat().st_mtime for source_path in normalized_sources):
            return output_path

    preview_paths = [
        ensure_square_preview(
            source_path=source_path,
            size=tile_size,
            background_color=background_color,
        )
        for source_path in normalized_sources
    ]
    columns = min(3, len(preview_paths))
    rows = (len(preview_paths) + columns - 1) // columns
    canvas_width = columns * tile_size + (columns + 1) * gap
    canvas_height = rows * tile_size + (rows + 1) * gap
    canvas = Image.new("RGB", (canvas_width, canvas_height), background_color)
    draw = ImageDraw.Draw(canvas)
    font = _load_preview_font(size=max(tile_size // 4, 28))
    label_padding_x = max(tile_size // 18, 14)
    label_padding_y = max(tile_size // 20, 12)
    minimum_label_box_size = max(tile_size // 4, 64)
    for index, preview_path in enumerate(preview_paths):
        row_index = index // columns
        column_index = index % columns
        offset_x = gap + column_index * (tile_size + gap)
        offset_y = gap + row_index * (tile_size + gap)
        with Image.open(preview_path) as preview_image:
            tile = preview_image.convert("RGB")
            canvas.paste(tile, (offset_x, offset_y))
        label = str(index + 1)
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        label_box_width = max(text_width + 2 * label_padding_x, minimum_label_box_size)
        label_box_height = max(text_height + 2 * label_padding_y, minimum_label_box_size)
        label_box_left = offset_x + 8
        label_box_top = offset_y + 8
        draw.rounded_rectangle(
            (
                label_box_left,
                label_box_top,
                label_box_left + label_box_width,
                label_box_top + label_box_height,
            ),
            radius=14,
            fill=(0, 0, 0),
        )
        text_x = label_box_left + (label_box_width - text_width) // 2
        text_y = label_box_top + (label_box_height - text_height) // 2 - max(
            label_box_height // 7,
            6,
        )
        draw.text((text_x, text_y), label, fill=(255, 255, 255), font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="JPEG", quality=85, optimize=True)
    return output_path


def _load_preview_font(*, size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()
