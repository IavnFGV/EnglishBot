from __future__ import annotations

from pathlib import Path
from typing import Protocol

from englishbot.logging_utils import logged_service_call


class ImageGenerationClient(Protocol):
    def generate(
        self,
        *,
        prompt: str,
        english_word: str,
        output_path: Path,
    ) -> None:
        ...


class FakeImageGenerationClient:
    @logged_service_call(
        "FakeImageGenerationClient.generate",
        transforms={
            "prompt": lambda value: {"prompt": value},
            "english_word": lambda value: {"english_word": value},
            "output_path": lambda value: {"output_path": value},
        },
    )
    def generate(
        self,
        *,
        prompt: str,
        english_word: str,
        output_path: Path,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"fake-image:{english_word}|{prompt}".encode())


class LocalPlaceholderImageGenerationClient:
    """Simple local placeholder image generator for offline development."""

    @logged_service_call(
        "LocalPlaceholderImageGenerationClient.generate",
        transforms={
            "english_word": lambda value: {"english_word": value},
            "output_path": lambda value: {"output_path": value},
        },
    )
    def generate(
        self,
        *,
        prompt: str,
        english_word: str,
        output_path: Path,
    ) -> None:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as error:
            raise RuntimeError(
                "Pillow is required for local placeholder image generation."
            ) from error

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1024, 1024), color=(248, 244, 232))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        draw.rounded_rectangle(
            (80, 80, 944, 944),
            radius=48,
            fill=(255, 252, 246),
            outline=(64, 92, 118),
            width=6,
        )
        draw.ellipse((120, 120, 280, 280), fill=(255, 208, 122), outline=(64, 92, 118), width=4)
        draw.rectangle((744, 120, 904, 280), fill=(154, 208, 194), outline=(64, 92, 118), width=4)

        draw.text((120, 340), english_word[:48], fill=(35, 47, 62), font=font)
        prompt_lines = _wrap_text(prompt, max_line_length=38)[:8]
        y = 430
        for line in prompt_lines:
            draw.text((120, y), line, fill=(70, 82, 94), font=font)
            y += 40

        image.save(output_path, format="PNG")


def _wrap_text(text: str, *, max_line_length: int) -> list[str]:
    words = text.strip().split()
    if not words:
        return []
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) <= max_line_length:
            current.append(word)
            continue
        lines.append(" ".join(current))
        current = [word]
    if current:
        lines.append(" ".join(current))
    return lines
