from io import BytesIO

from PIL import Image, __version__


def test_pillow_uses_security_patched_major():
    assert int(__version__.split(".")[0]) >= 13


def test_jpeg_thumbnail_roundtrip():
    source = BytesIO()
    with Image.new("RGB", (1200, 1100), color=(40, 80, 120)) as image:
        image.save(source, format="JPEG")
    source.seek(0)
    with Image.open(source) as image:
        image.thumbnail((256, 256))
        image.load()
        assert 0 < image.width <= 256
        output = BytesIO()
        image.save(output, format="PNG")
        assert output.getvalue().startswith(b"\x89PNG\r\n\x1a\n")
