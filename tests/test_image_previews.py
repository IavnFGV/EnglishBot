from __future__ import annotations

from pathlib import Path

from englishbot.image_generation.previews import (
    ensure_numbered_candidate_strip,
    ensure_square_preview,
)


def test_ensure_square_preview_keeps_aspect_ratio_inside_256_square(tmp_path: Path) -> None:
    from PIL import Image

    source_path = tmp_path / "wide-source.png"
    Image.new("RGB", (400, 100), (255, 0, 0)).save(source_path)

    preview_path = ensure_square_preview(source_path=source_path, size=256)

    assert preview_path.exists()
    with Image.open(preview_path) as preview:
        assert preview.size == (256, 256)
        # center stays red from the source image
        assert preview.getpixel((128, 128))[:3] == (254, 0, 0)
        # top margin stays white because the aspect ratio is preserved
        assert preview.getpixel((128, 16))[:3] == (255, 255, 255)


def test_ensure_numbered_candidate_strip_builds_horizontal_collage(tmp_path: Path) -> None:
    from PIL import Image

    source_paths = []
    colors = [
        (255, 0, 0),
        (0, 180, 0),
        (0, 0, 255),
        (255, 200, 0),
        (180, 0, 255),
        (0, 200, 200),
    ]
    for index, color in enumerate(colors, start=1):
        source_path = tmp_path / f"source-{index}.png"
        Image.new("RGB", (320, 160), color).save(source_path)
        source_paths.append(source_path)

    output_path = tmp_path / "review-strip.jpg"
    strip_path = ensure_numbered_candidate_strip(
        source_paths=source_paths,
        output_path=output_path,
        tile_size=256,
        gap=12,
    )

    assert strip_path == output_path
    assert strip_path.exists()
    with Image.open(strip_path) as strip:
        assert strip.size == (3 * 256 + 4 * 12, 2 * 256 + 3 * 12)
        assert strip.getpixel((12 + 128, 12 + 128))[:3][0] >= 200
        assert strip.getpixel((12 + 256 + 12 + 128, 12 + 128))[:3][1] >= 120
        assert strip.getpixel((12 + 128, 12 + 256 + 12 + 128))[:3][0] >= 200
        assert strip.getpixel((12 + 60, 12 + 24))[:3] == (0, 0, 0)
