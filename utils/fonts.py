from __future__ import annotations

import ctypes
from pathlib import Path


FR_PRIVATE = 0x10
_INTER_FACES = (
    "Inter-Regular.ttf",
    "Inter-Medium.ttf",
    "Inter-SemiBold.ttf",
    "Inter-Bold.ttf",
)


def load_inter_fonts(font_dir: Path) -> int:
    """Register bundled Inter faces privately for this process on Windows."""
    if not hasattr(ctypes, "windll"):
        return 0
    try:
        add_font = ctypes.windll.gdi32.AddFontResourceExW
    except (AttributeError, OSError):
        return 0
    registered = 0
    for name in _INTER_FACES:
        path = font_dir / name
        if path.exists():
            try:
                registered += int(add_font(str(path), FR_PRIVATE, 0) or 0)
            except (OSError, TypeError):
                continue
    return registered
