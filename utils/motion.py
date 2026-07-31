from __future__ import annotations

from functools import lru_cache
import sys


@lru_cache(maxsize=1)
def motion_enabled() -> bool:
    """Respect the Windows "Show animations" accessibility preference."""
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes

        enabled = ctypes.c_int(1)
        # SPI_GETCLIENTAREAANIMATION
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(enabled.value) if ok else True
    except (AttributeError, OSError, TypeError, ValueError):
        return True
