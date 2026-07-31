from __future__ import annotations

import ctypes
import sys

from themes.tokens import ThemeTokens


def hex_to_colorref(value: str) -> int:
    """Convert #RRGGBB to the BGR COLORREF used by Windows DWM."""
    text = str(value or "").lstrip("#")
    if len(text) != 6:
        raise ValueError("expected a six-digit hex color")
    red, green, blue = (int(text[index:index + 2], 16) for index in (0, 2, 4))
    return red | (green << 8) | (blue << 16)


def apply_window_chrome(window, tokens: ThemeTokens) -> None:
    """Align the native Windows caption and border with the app theme."""
    if not sys.platform.startswith("win"):
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.c_void_p(int(window.winfo_id()))
        parent = ctypes.windll.user32.GetParent(hwnd)
        if parent:
            hwnd = ctypes.c_void_p(parent)
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        dark_mode = ctypes.c_int(1 if tokens.name == "dark" else 0)
        caption = ctypes.c_uint(hex_to_colorref(tokens.colors.sidebar))
        border = ctypes.c_uint(hex_to_colorref(tokens.colors.border))
        text = ctypes.c_uint(hex_to_colorref(tokens.colors.text))
        dwm(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        dwm(hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))
        dwm(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
        dwm(hwnd, 36, ctypes.byref(text), ctypes.sizeof(text))
    except (AttributeError, OSError, TypeError, ValueError):
        return
