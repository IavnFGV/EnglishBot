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
    center_label: str
    legend_labels: tuple[str, str, str, str]
    completed_word_count: int
    total_word_count: int
    remaining_word_count: int
    estimated_round_count: int
    segments: tuple[AssignmentProgressSegment, ...]


def render_assignment_progress_image(
    snapshot: AssignmentProgressSnapshot,
    *,
    output_path: Path,
    size: int = 512,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (size, size), "#fff8ef")
    draw = ImageDraw.Draw(image)
    count_font = _load_font(max(26, size // 6))
    detail_font = _load_font(max(11, size // 24))

    center_x = size // 2
    center_y = int(size * 0.41)
    outer_radius = int(size * 0.38)
    inner_radius = int(size * 0.11)
    segment_count = max(1, len(snapshot.segments))
    start_angle = -90.0
    sweep_angle = 360.0 / segment_count
    gap = min(4.0, sweep_angle * 0.12)

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
        fill="#2b3d52",
        font=count_font,
        stroke_width=max(2, size // 180),
        stroke_fill="#fff8ef",
    )

    legend_items = [
        ("#dde7ef", snapshot.legend_labels[0]),
        ("#f7d36a", snapshot.legend_labels[1]),
        ("#ffaf5f", snapshot.legend_labels[2]),
        ("#5ec27f", snapshot.legend_labels[3]),
    ]
    legend_rows = [legend_items[:2], legend_items[2:]]
    row_gap = max(20, size // 13)
    base_y = int(size * 0.83)
    for row_index, row in enumerate(legend_rows):
        legend_y = base_y + row_index * row_gap
        legend_x = int(size * 0.12)
        for color, label in row:
            dot_size = max(14, size // 18)
            draw.ellipse(
                [legend_x, legend_y, legend_x + dot_size, legend_y + dot_size],
                fill=color,
            )
            draw.text(
                (legend_x + dot_size + 6, legend_y - 3),
                label,
                fill="#415364",
                font=detail_font,
            )
            legend_x += int(size * 0.44)

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
