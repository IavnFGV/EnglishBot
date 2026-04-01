from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True, slots=True)
class AssignmentProgressSegment:
    word_id: str
    label: str
    progress_value: float
    bonus_hard_pending: bool = False
    bonus_hard_completed: bool = False


@dataclass(frozen=True, slots=True)
class AssignmentProgressSnapshot:
    center_label: str
    legend_labels: tuple[str, str, str, str]
    completed_word_count: int
    total_word_count: int
    remaining_word_count: int
    estimated_round_count: int
    segments: tuple[AssignmentProgressSegment, ...]
    combo_charge_streak: int = 0
    combo_hard_active: bool = False
    combo_target_word_id: str | None = None


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
    pending_bonus_angles: list[float] = []

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
        fill_color = _segment_color(segment)
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
        if segment.bonus_hard_pending:
            pending_bonus_angles.append((segment_start + segment_end) / 2)

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

    for angle_degrees in pending_bonus_angles:
        _draw_bonus_hard_arrow(
            draw,
            center_x=center_x,
            center_y=center_y,
            inner_radius=inner_radius,
            outer_radius=outer_radius,
            angle_degrees=angle_degrees,
            size=size,
        )

    _draw_combo_streak_indicator(
        draw,
        combo_charge_streak=snapshot.combo_charge_streak,
        combo_hard_active=snapshot.combo_hard_active,
        size=size,
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


def _segment_color(segment: AssignmentProgressSegment) -> str:
    if segment.bonus_hard_completed:
        return "#1f9d8b"
    progress_value = segment.progress_value
    if progress_value >= 1.0:
        return "#5ec27f"
    if progress_value >= 0.66:
        return "#ffaf5f"
    if progress_value > 0:
        return "#f7d36a"
    return "#dde7ef"


def _draw_bonus_hard_arrow(
    draw: ImageDraw.ImageDraw,
    *,
    center_x: int,
    center_y: int,
    inner_radius: int,
    outer_radius: int,
    angle_degrees: float,
    size: int,
) -> None:
    angle = math.radians(angle_degrees)
    shaft_start = max(2, size // 128)
    shaft_end = outer_radius - max(26, size // 16)
    shaft_width = max(10, size // 36)
    head_length = max(20, size // 14)
    head_width = max(16, size // 18)

    perp_x = -math.sin(angle)
    perp_y = math.cos(angle)
    dir_x = math.cos(angle)
    dir_y = math.sin(angle)

    start_x = center_x + dir_x * shaft_start
    start_y = center_y + dir_y * shaft_start
    end_x = center_x + dir_x * shaft_end
    end_y = center_y + dir_y * shaft_end
    tip_x = center_x + dir_x * (shaft_end + head_length)
    tip_y = center_y + dir_y * (shaft_end + head_length)

    shaft = [
        (start_x + perp_x * shaft_width / 2, start_y + perp_y * shaft_width / 2),
        (end_x + perp_x * shaft_width / 2, end_y + perp_y * shaft_width / 2),
        (end_x - perp_x * shaft_width / 2, end_y - perp_y * shaft_width / 2),
        (start_x - perp_x * shaft_width / 2, start_y - perp_y * shaft_width / 2),
    ]
    head = [
        (tip_x, tip_y),
        (end_x + perp_x * head_width / 2, end_y + perp_y * head_width / 2),
        (end_x - perp_x * head_width / 2, end_y - perp_y * head_width / 2),
    ]

    draw.polygon(shaft, fill="#ff9b3d")
    draw.polygon(head, fill="#ff6b1a")
    draw.line(
        [(start_x, start_y), (tip_x, tip_y)],
        fill="#ffd36b",
        width=max(2, size // 128),
    )


def _draw_combo_streak_indicator(
    draw: ImageDraw.ImageDraw,
    *,
    combo_charge_streak: int,
    combo_hard_active: bool,
    size: int,
) -> None:
    filled_count = 4 if combo_hard_active else max(0, min(4, combo_charge_streak))
    if filled_count <= 0:
        return
    dot_size = max(14, size // 24)
    gap = max(8, size // 40)
    total_height = dot_size * 4 + gap * 3
    x = size - int(size * 0.10) - dot_size
    start_y = size - int(size * 0.20) - total_height
    active_fill = "#2f7df6" if combo_hard_active else "#85b6ff"
    active_outline = "#1f5fcc"
    inactive_fill = "#edf4ff"
    inactive_outline = "#bfd5f5"

    for index in range(4):
        y = start_y + index * (dot_size + gap)
        reverse_index = 3 - index
        fill = active_fill if reverse_index < filled_count else inactive_fill
        outline = active_outline if reverse_index < filled_count else inactive_outline
        draw.ellipse(
            [x, y, x + dot_size, y + dot_size],
            fill=fill,
            outline=outline,
            width=max(2, size // 180),
        )


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size=size)
    except OSError:
        return ImageFont.load_default()
