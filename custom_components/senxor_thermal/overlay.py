"""Overlay drawing (colour bar, min/max markers, centre crosshair)."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .palette import get_palette
from .protocol import FRAME_HEIGHT, FRAME_WIDTH

PANEL_WIDTH = 92


def _font(size: int) -> ImageFont.ImageFont:
    try:  # Pillow >= 10 accepts a size for the built-in bitmap font
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - older Pillow
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return right - left, bottom - top
    except AttributeError:  # pragma: no cover - very old Pillow
        return draw.textsize(text, font=font)


def draw_overlay(
    canvas: Image.Image,
    stats,
    options,
    scale_min: float,
    scale_max: float,
    format_temperature,
) -> None:
    """Draw the colour bar, the min/max markers and the centre crosshair."""
    width, height = canvas.size
    font = _font(max(12, height // 30))
    inset = 6
    panel = min(PANEL_WIDTH, width // 4)
    plot_width = width - (panel if options.show_colorbar else 0)

    draw = ImageDraw.Draw(canvas)

    # --- colour bar in a translucent panel on the right ------------------
    if options.show_colorbar:
        shade = Image.new("RGBA", (panel, height), (0, 0, 0, 150))
        canvas.paste(Image.alpha_composite(canvas.crop((plot_width, 0, width, height)).convert("RGBA"), shade).convert("RGB"), (plot_width, 0))
        bar_left = plot_width + 8
        bar_width = max(10, min(18, panel // 4))
        top, bottom = inset + 4, height - inset - 4
        table = get_palette(options.palette)
        span = max(1, bottom - top - 1)
        for y in range(top, bottom):
            position = int((1.0 - (y - top) / span) * 255)
            draw.line(
                [(bar_left, y), (bar_left + bar_width, y)],
                fill=table[max(0, min(255, position))],
            )
        draw.rectangle(
            [bar_left, top, bar_left + bar_width, bottom], outline=(235, 235, 235)
        )
        text_x = bar_left + bar_width + 5
        draw.text(
            (text_x, top),
            format_temperature(scale_max, options.unit),
            fill=(255, 255, 255),
            font=font,
            anchor="lt",
        )
        draw.text(
            (text_x, bottom),
            format_temperature(scale_min, options.unit),
            fill=(255, 255, 255),
            font=font,
            anchor="lb",
        )

    # --- min / max markers ------------------------------------------------
    if options.show_markers:
        scale_x = plot_width / FRAME_WIDTH
        scale_y = height / FRAME_HEIGHT
        for (x, y), value, colour, above in (
            (stats.max_position, stats.maximum, (255, 80, 80), True),
            (stats.min_position, stats.minimum, (120, 190, 255), False),
        ):
            cx = min(plot_width - inset, max(inset, (x + 0.5) * scale_x))
            cy = min(height - inset, max(inset, (y + 0.5) * scale_y))
            radius = max(5, int(min(scale_x, scale_y) * 0.5))
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                outline=colour,
                width=2,
            )
            label = format_temperature(value, options.unit)
            text_w, text_h = _text_size(draw, label, font)
            tx = min(plot_width - inset - text_w, max(inset, cx + radius + 4))
            ty = cy - radius - text_h - 3 if above else cy + radius + 3
            ty = min(height - inset - text_h, max(inset, ty))
            draw.rectangle([tx - 2, ty - 1, tx + text_w + 2, ty + text_h + 1], fill=(0, 0, 0))
            draw.text((tx, ty), label, fill=colour, font=font)

    # --- centre crosshair -------------------------------------------------
    if options.show_crosshair:
        cx = plot_width / 2
        cy = height / 2
        arm = max(6, height // 60)
        draw.line([(cx - arm, cy), (cx + arm, cy)], fill=(255, 255, 255), width=1)
        draw.line([(cx, cy - arm), (cx, cy + arm)], fill=(255, 255, 255), width=1)
        label = format_temperature(stats.center, options.unit)
        text_w, text_h = _text_size(draw, label, font)
        tx = min(plot_width - inset - text_w, cx + arm + 4)
        ty = min(height - inset - text_h, cy + arm + 2)
        draw.rectangle([tx - 2, ty - 1, tx + text_w + 2, ty + 1 + text_h], fill=(0, 0, 0))
        draw.text((tx, ty), label, fill=(255, 255, 255), font=font)
