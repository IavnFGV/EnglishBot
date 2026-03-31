from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True, slots=True)
class AssignmentProgressSegment:
    word_id: str
    label: str
    progress_value: float


@dataclass(frozen=True, slots=True)
class AssignmentProgressSnapshot:
    label: str
    completed_word_count: int
    total_word_count: int
    segments: tuple[AssignmentProgressSegment, ...]


def render_assignment_progress_image(
    snapshot: AssignmentProgressSnapshot,
    *,
    output_path: Path,
    size: int = 640,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (size, size), "#fff8ef")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(max(20, size // 18))
    count_font = _load_font(max(34, size // 9))
    detail_font = _load_font(max(16, size // 28))

    center_x = size // 2
    center_y = int(size * 0.56)
    outer_radius = int(size * 0.32)
    inner_radius = int(size * 0.11)
    segment_count = max(1, len(snapshot.segments))
    start_angle = -90.0
    sweep_angle = 360.0 / segment_count
    gap = min(4.0, sweep_angle * 0.12)

    title = snapshot.label
    title_box = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_box[2] - title_box[0]
    draw.text(
        ((size - title_width) / 2, int(size * 0.08)),
        title,
        fill="#243447",
        font=title_font,
    )

    for index, segment in enumerate(snapshot.segments):
        segment_start = start_angle + index * sweep_angle + gap / 2
        segment_end = start_angle + (index + 1) * sweep_angle - gap / 2
        draw.pieslice(
            [
                center_x - outer_radius,
                center_y - outer_radius,
                center_x + outer_radius,
                center_y + outer_radius,
            ],
            start=segment_start,
            end=segment_end,
            fill="#dde7ef",
        )
        progress_radius = inner_radius + int((outer_radius - inner_radius) * max(0.0, min(1.0, segment.progress_value)))
        fill_color = _segment_color(segment.progress_value)
        draw.pieslice(
            [
                center_x - progress_radius,
                center_y - progress_radius,
                center_x + progress_radius,
                center_y + progress_radius,
            ],
            start=segment_start,
            end=segment_end,
            fill=fill_color,
        )

    draw.ellipse(
        [
            center_x - inner_radius,
            center_y - inner_radius,
            center_x + inner_radius,
            center_y + inner_radius,
        ],
        fill="#fffdf7",
        outline="#f2d9b6",
        width=4,
    )

    count_text = f"{snapshot.completed_word_count}/{max(1, snapshot.total_word_count)}"
    count_box = draw.textbbox((0, 0), count_text, font=count_font)
    count_width = count_box[2] - count_box[0]
    count_height = count_box[3] - count_box[1]
    draw.text(
        ((size - count_width) / 2, center_y - count_height / 2 - 8),
        count_text,
        fill="#243447",
        font=count_font,
    )

    detail_text = "words done"
    detail_box = draw.textbbox((0, 0), detail_text, font=detail_font)
    detail_width = detail_box[2] - detail_box[0]
    draw.text(
        ((size - detail_width) / 2, center_y + inner_radius // 2),
        detail_text,
        fill="#6c7a89",
        font=detail_font,
    )

    legend_items = [
        ("#dde7ef", "not started"),
        ("#f7d36a", "easy"),
        ("#ffaf5f", "medium"),
        ("#5ec27f", "done"),
    ]
    legend_y = int(size * 0.88)
    legend_x = int(size * 0.1)
    for color, label in legend_items:
        draw.ellipse([legend_x, legend_y, legend_x + 16, legend_y + 16], fill=color)
        draw.text((legend_x + 24, legend_y - 3), label, fill="#415364", font=detail_font)
        legend_x += int(size * 0.2)

    image.save(output_path, format="PNG")
    return output_path


def _segment_color(progress_value: float) -> str:
    if progress_value >= 1.0:
        return "#5ec27f"
    if progress_value >= 0.66:
        return "#ffaf5f"
    if progress_value > 0:
        return "#f7d36a"
    return "#dde7ef"


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size=size)
    except OSError:
        return ImageFont.load_default()
