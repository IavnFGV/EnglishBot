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
    hard_legend_label: str | None
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

    _draw_legend(
        draw,
        legend_labels=snapshot.legend_labels,
        hard_legend_label=snapshot.hard_legend_label,
        font=detail_font,
        size=size,
    )

    image.save(output_path, format="PNG")
    return output_path


def _bottom_grid(size: int) -> tuple[int, int, int]:
    bottom_padding = max(7, size // 73)
    block_height = max(100, size // 5)
    top = size - bottom_padding - block_height
    return top, max(33, size // 15), bottom_padding


def _segment_color(segment: AssignmentProgressSegment) -> str:
    if segment.bonus_hard_completed:
        return "#167a6c"
    progress_value = segment.progress_value
    if progress_value >= 1.0:
        return "#79d99a"
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
    legend_top, row_gap, _ = _bottom_grid(size)
    dot_size = min(max(18, size // 21), row_gap - 5)
    x = int(size * 0.87)
    start_y = legend_top + row_gap * 2
    active_fill = "#2f7df6" if combo_hard_active else "#85b6ff"
    active_outline = "#1f5fcc"
    inactive_fill = "#edf4ff"
    inactive_outline = "#bfd5f5"

    for index in range(4):
        y = start_y - index * row_gap
        fill = active_fill if index < filled_count else inactive_fill
        outline = active_outline if index < filled_count else inactive_outline
        draw.ellipse(
            [x, y, x + dot_size, y + dot_size],
            fill=fill,
            outline=outline,
            width=max(2, size // 180),
        )


def _draw_legend(
    draw: ImageDraw.ImageDraw,
    *,
    legend_labels: tuple[str, str, str, str],
    hard_legend_label: str | None,
    font,
    size: int,
) -> None:
    left_x = int(size * 0.12)
    right_x = int(size * 0.57)
    base_y, row_gap, _ = _bottom_grid(size)
    swatch_size = min(max(18, size // 21), row_gap - 5)
    legend_entries = [
        (left_x, base_y, "#dde7ef", legend_labels[0]),
        (right_x, base_y, "#f7d36a", legend_labels[1]),
        (left_x, base_y + row_gap, "#ffaf5f", legend_labels[2]),
        (right_x, base_y + row_gap, "#79d99a", legend_labels[3]),
    ]
    if hard_legend_label:
        legend_entries.append((left_x, base_y + row_gap * 2, "#167a6c", hard_legend_label))

    for x, y, color, label in legend_entries:
        outline = "#0f5d52" if color == "#167a6c" else None
        draw.ellipse(
            [x, y, x + swatch_size, y + swatch_size],
            fill=color,
            outline=outline,
            width=max(2, size // 180) if outline is not None else 0,
        )
        draw.text(
            (x + swatch_size + 8, y - 2),
            label,
            fill="#415364",
            font=font,
        )


def _draw_hard_legend_marker(
    draw: ImageDraw.ImageDraw,
    *,
    label: str,
    font,
    size: int,
) -> None:
    # Backward-compatible shim for tests/imports; legend now renders through _draw_legend.
    x = int(size * 0.12)
    base_y, row_gap, _ = _bottom_grid(size)
    swatch_size = min(max(18, size // 21), row_gap - 5)
    y = base_y + row_gap * 2
    draw.ellipse(
        [x, y, x + swatch_size, y + swatch_size],
        fill="#167a6c",
        outline="#0f5d52",
        width=max(2, size // 180),
    )
    draw.text(
        (x + swatch_size + 8, y - 2),
        label,
        fill="#415364",
        font=font,
    )


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size=size)
    except OSError:
        return ImageFont.load_default()
