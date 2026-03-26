from __future__ import annotations

from pathlib import Path

from englishbot.image_generation.previews import ensure_square_preview


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
