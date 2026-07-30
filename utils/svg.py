from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw


def svg_image(path: Path, size: tuple[int, int], color: str = "#656862") -> ctk.CTkImage:
    """Render a bundled SVG, with a pure-Pillow fallback for clean Windows installs."""
    image = _render_svg_cached(str(path.resolve()), size, color)
    return ctk.CTkImage(light_image=image, dark_image=image, size=size)


@lru_cache(maxsize=96)
def _render_svg_cached(path_value: str, size: tuple[int, int], color: str) -> Image.Image:
    path = Path(path_value)
    try:
        import cairosvg

        source = path.read_text(encoding="utf-8").replace("currentColor", color)
        png = cairosvg.svg2png(bytestring=source.encode("utf-8"), output_width=size[0] * 2, output_height=size[1] * 2)
        image = Image.open(BytesIO(png)).convert("RGBA")
    except Exception:
        image = _fallback_icon(path, size, color)
    return image


def _fallback_icon(path: Path, size: tuple[int, int], color: str) -> Image.Image:
    scale = size[0] * 2 / 24
    width, height = size[0] * 2, size[1] * 2
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    pen = max(2, round(1.8 * scale))

    def point(x: float, y: float) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    name = path.stem
    if name == "plus":
        draw.line([point(12, 5), point(12, 19)], fill=color, width=pen)
        draw.line([point(5, 12), point(19, 12)], fill=color, width=pen)
    elif name == "send":
        draw.polygon([point(3, 10.5), point(21, 3), point(13.5, 21), point(9.2, 13.8)], outline=color)
        draw.line([point(9.2, 13.8), point(13.7, 9.3)], fill=color, width=pen)
    elif name == "database":
        draw.ellipse([point(5, 2), point(19, 8)], outline=color, width=pen)
        draw.line([point(5, 5), point(5, 19)], fill=color, width=pen)
        draw.line([point(19, 5), point(19, 19)], fill=color, width=pen)
        draw.arc([point(5, 10), point(19, 16)], 0, 180, fill=color, width=pen)
        draw.arc([point(5, 16), point(19, 22)], 0, 180, fill=color, width=pen)
    elif name == "sun":
        draw.ellipse([point(8.5, 8.5), point(15.5, 15.5)], outline=color, width=pen)
        for start, end in (((12, 2), (12, 5)), ((12, 19), (12, 22)), ((2, 12), (5, 12)), ((19, 12), (22, 12)), ((4.9, 4.9), (6.3, 6.3)), ((17.7, 17.7), (19.1, 19.1)), ((4.9, 19.1), (6.3, 17.7)), ((17.7, 6.3), (19.1, 4.9))):
            draw.line([point(*start), point(*end)], fill=color, width=pen)
    elif name == "chevron-down":
        draw.line([point(6, 9), point(12, 15), point(18, 9)], fill=color, width=pen, joint="curve")
    elif name == "chevron-up":
        draw.line([point(6, 15), point(12, 9), point(18, 15)], fill=color, width=pen, joint="curve")
    elif name == "check":
        draw.line([point(5, 12), point(9, 16), point(19, 6)], fill=color, width=pen, joint="curve")
    elif name == "x":
        draw.line([point(6, 6), point(18, 18)], fill=color, width=pen)
        draw.line([point(18, 6), point(6, 18)], fill=color, width=pen)
    elif name == "copy":
        draw.rounded_rectangle([point(9, 9), point(20, 20)], radius=max(2, round(2 * scale)), outline=color, width=pen)
        draw.line([point(5, 15), point(4, 15), point(4, 4), point(15, 4), point(15, 5)], fill=color, width=pen)
    elif name == "clipboard":
        draw.rounded_rectangle([point(5, 4), point(19, 21)], radius=max(2, round(2 * scale)), outline=color, width=pen)
        draw.line([point(9, 4), point(9, 3), point(15, 3), point(15, 4)], fill=color, width=pen)
        draw.line([point(8, 9), point(16, 9)], fill=color, width=pen)
        draw.line([point(8, 13), point(14, 13)], fill=color, width=pen)
    else:
        draw.arc([point(4, 3), point(21, 21)], 40, 300, fill=color, width=pen)
    return image
