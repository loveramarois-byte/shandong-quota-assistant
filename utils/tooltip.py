from __future__ import annotations

import tkinter as tk

from themes.tokens import ThemeTokens


def show_tooltip(
    widget: tk.Widget,
    text: str,
    tokens: ThemeTokens,
    *,
    clamp_to_screen: bool = False,
) -> "tk.Toplevel | None":
    """Create a dark tooltip Toplevel anchored below *widget*.

    Returns the window so the caller can store a reference and destroy it
    later, or None when the geometry call fails (e.g. during app shutdown).

    Pass ``clamp_to_screen=True`` when the widget is near the right edge of
    the screen and the tooltip should not overflow (e.g. sidebar session rows).
    """
    window = tk.Toplevel(widget)
    window.overrideredirect(True)
    bg = tokens.colors.text
    fg = tokens.colors.elevated
    window.configure(bg=bg)
    tk.Label(
        window,
        text=text,
        bg=bg,
        fg=fg,
        font=tokens.font(tokens.typography.caption),
        padx=8,
        pady=5,
    ).pack()
    window.update_idletasks()
    x = widget.winfo_rootx()
    if clamp_to_screen:
        try:
            x = min(x, max(0, widget.winfo_screenwidth() - window.winfo_width() - 8))
        except tk.TclError:
            pass
    try:
        window.geometry(f"+{x}+{widget.winfo_rooty() + widget.winfo_height() + 4}")
    except tk.TclError:
        window.destroy()
        return None
    return window
