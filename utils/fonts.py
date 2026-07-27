from __future__ import annotations

import ctypes
from pathlib import Path


FR_PRIVATE = 0x10


def load_inter_fonts(font_dir: Path) -> None:
    """Register bundled Inter faces privately for this process on Windows."""
    if not hasattr(ctypes, "windll"):
        return
    add_font = ctypes.windll.gdi32.AddFontResourceExW
    for name in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf"):
        path = font_dir / name
        if path.exists():
            add_font(str(path), FR_PRIVATE, 0)
