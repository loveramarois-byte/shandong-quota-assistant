from __future__ import annotations

import customtkinter as ctk

from themes.tokens import ThemeTokens


class DSButton(ctk.CTkButton):
    def __init__(self, master, *, tokens: ThemeTokens, text: str = "", variant: str = "primary", **kwargs):
        self.tokens = tokens
        self.variant = variant
        self._normal_text = text
        self._normal_image = kwargs.get("image")
        height = kwargs.pop("height", tokens.control_height)
        corner_radius = kwargs.pop("corner_radius", tokens.radius_sm)
        super().__init__(master, text=text, height=height, corner_radius=corner_radius, **self._style(variant), **kwargs)
        self.configure(font=tokens.font(tokens.typography.meta, "semibold"), text_color_disabled=tokens.colors.text_muted)
        self._bind_interaction()

    def _style(self, variant: str) -> dict:
        c = self.tokens.colors
        if variant == "secondary":
            return {"fg_color": c.elevated, "hover_color": c.subtle, "text_color": c.text, "border_width": 1, "border_color": c.border}
        if variant == "ghost":
            return {"fg_color": "transparent", "hover_color": c.subtle, "text_color": c.text_secondary, "border_width": 0, "border_color": c.border}
        return {"fg_color": c.accent, "hover_color": c.accent_hover, "text_color": "#FFFFFF", "border_width": 1, "border_color": c.accent}

    def _bind_interaction(self) -> None:
        self.bind("<ButtonPress-1>", self._press, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")
        self.bind("<Return>", self._keyboard_invoke, add="+")
        self.bind("<space>", self._keyboard_invoke, add="+")

    def _press(self, _event=None) -> None:
        if str(self.cget("state")) == "disabled":
            return
        c = self.tokens.colors
        self.configure(fg_color=c.accent_pressed if self.variant == "primary" else c.subtle)

    def _release(self, _event=None) -> None:
        if str(self.cget("state")) == "disabled":
            return
        self.configure(fg_color=self._style(self.variant)["fg_color"])

    def _focus_in(self, _event=None) -> None:
        self.configure(border_color=self.tokens.colors.focus, border_width=1)

    def _focus_out(self, _event=None) -> None:
        style = self._style(self.variant)
        self.configure(border_color=style["border_color"], border_width=style["border_width"])

    def _keyboard_invoke(self, _event=None) -> str:
        if str(self.cget("state")) != "disabled":
            self.invoke()
        return "break"

    def set_loading(self, loading: bool, loading_text: str = "处理中…") -> None:
        self.set_enabled(not loading)
        self.configure(text=loading_text if loading else self._normal_text)

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.configure(state="normal", hover=True, **self._style(self.variant))
        else:
            self.configure(
                state="disabled",
                hover=False,
                fg_color=self.tokens.colors.subtle,
                border_color=self.tokens.colors.border,
                text_color=self.tokens.colors.text_muted,
            )

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        self.configure(font=tokens.font(tokens.typography.meta, "semibold"), text_color_disabled=tokens.colors.text_muted)
        self.set_enabled(str(self.cget("state")) != "disabled")


class IconButton(DSButton):
    def __init__(self, master, *, tokens: ThemeTokens, image=None, tooltip: str = "", **kwargs):
        self.tooltip = tooltip
        super().__init__(master, tokens=tokens, text="", variant="ghost", image=image, width=40, height=40, corner_radius=tokens.radius_sm, **kwargs)
        if tooltip:
            self._tooltip_window = None
            self.bind("<Enter>", self._show_tooltip, add="+")
            self.bind("<Leave>", self._hide_tooltip, add="+")

    def _show_tooltip(self, _event=None):
        if self._tooltip_window or not self.tooltip:
            return
        window = self._tooltip_window = __import__("tkinter").Toplevel(self)
        window.overrideredirect(True)
        window.configure(bg=self.tokens.colors.text)
        __import__("tkinter").Label(
            window,
            text=self.tooltip,
            bg=self.tokens.colors.text,
            fg=self.tokens.colors.surface,
            font=self.tokens.font(self.tokens.typography.caption),
            padx=8,
            pady=5,
        ).pack()
        window.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 4}")

    def _hide_tooltip(self, _event=None):
        if self._tooltip_window:
            self._tooltip_window.destroy()
            self._tooltip_window = None
