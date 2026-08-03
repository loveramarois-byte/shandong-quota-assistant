from __future__ import annotations

import customtkinter as ctk

from themes.tokens import ThemeTokens
from utils.motion import motion_enabled


def blend_hex(start: str, end: str, progress: float) -> str:
    """Blend two design-token colors for short interaction transitions."""
    amount = max(0.0, min(1.0, float(progress)))
    if not (isinstance(start, str) and isinstance(end, str) and start.startswith("#") and end.startswith("#")):
        return end if amount >= 0.5 else start
    try:
        left = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
        right = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
    except (TypeError, ValueError):
        return end if amount >= 0.5 else start
    rgb = tuple(round(a + ((b - a) * amount)) for a, b in zip(left, right))
    return "#" + "".join(f"{value:02X}" for value in rgb)


class DSButton(ctk.CTkButton):
    def __init__(self, master, *, tokens: ThemeTokens, text: str = "", variant: str = "primary", **kwargs):
        self.tokens = tokens
        self.variant = variant
        self._normal_text = text
        self._normal_image = kwargs.get("image")
        self._hover_job: str | None = None
        self._hover_frame = 0
        self._hovering = False
        height = kwargs.pop("height", tokens.control_height)
        corner_radius = kwargs.pop("corner_radius", tokens.radius_sm)
        super().__init__(master, text=text, height=height, corner_radius=corner_radius, hover=False, **self._style(variant), **kwargs)
        self.configure(font=tokens.font(tokens.typography.meta, "semibold"), text_color_disabled=tokens.colors.text_muted)
        self._bind_interaction()

    def _style(self, variant: str) -> dict:
        c = self.tokens.colors
        if variant == "secondary":
            return {"fg_color": c.elevated, "hover_color": c.subtle, "text_color": c.text, "border_width": 1, "border_color": c.border}
        if variant == "ghost":
            return {"fg_color": "transparent", "hover_color": c.subtle, "text_color": c.text_secondary, "border_width": 0, "border_color": c.border}
        if variant == "danger":
            return {"fg_color": c.danger_soft, "hover_color": c.danger, "text_color": c.danger, "border_width": 0, "border_color": c.danger}
        return {"fg_color": c.accent_fill, "hover_color": c.accent_hover, "text_color": c.on_accent, "border_width": 0, "border_color": c.accent_fill}

    def _bind_interaction(self) -> None:
        self.bind("<ButtonPress-1>", self._press, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")
        self.bind("<Return>", self._keyboard_invoke, add="+")
        self.bind("<space>", self._keyboard_invoke, add="+")

    def _press(self, _event=None) -> None:
        if str(self.cget("state")) == "disabled":
            return
        c = self.tokens.colors
        self._cancel_hover_animation()
        pressed = c.accent_pressed if self.variant == "primary" else (c.danger_soft if self.variant == "danger" else c.subtle)
        self.configure(fg_color=pressed)

    def _release(self, _event=None) -> None:
        if str(self.cget("state")) == "disabled":
            return
        style = self._style(self.variant)
        self._animate_color(style["hover_color"] if self._hovering else style["fg_color"])

    def _enter(self, _event=None) -> None:
        if str(self.cget("state")) == "disabled":
            return
        self._hovering = True
        if self.variant == "danger":
            self.configure(text_color="#FFFFFF")
        self._animate_color(self._style(self.variant)["hover_color"])

    def _leave(self, _event=None) -> None:
        self._hovering = False
        if str(self.cget("state")) == "disabled":
            return
        if self.variant == "danger":
            self.configure(text_color=self._style(self.variant)["text_color"])
        self._animate_color(self._style(self.variant)["fg_color"])

    def _animate_color(self, target: str) -> None:
        current = self.cget("fg_color")
        if not motion_enabled() or self.variant == "ghost" or current == "transparent" or target == "transparent":
            self._cancel_hover_animation()
            self.configure(fg_color=target)
            return
        self._cancel_hover_animation()
        self._hover_frame = 0
        frames = 5

        def step() -> None:
            self._hover_frame += 1
            eased = 1 - (1 - (self._hover_frame / frames)) ** 2
            self.configure(fg_color=blend_hex(str(current), target, eased))
            if self._hover_frame < frames:
                self._hover_job = self.after(24, step)
            else:
                self._hover_job = None

        step()

    def _cancel_hover_animation(self) -> None:
        if self._hover_job:
            try:
                self.after_cancel(self._hover_job)
            except Exception:
                pass
            self._hover_job = None

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
            self.configure(state="normal", hover=False, **self._style(self.variant))
        else:
            self.configure(
                state="disabled",
                hover=False,
                fg_color=self.tokens.colors.subtle,
                border_color=self.tokens.colors.border,
                text_color=self.tokens.colors.text_muted,
            )

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self._cancel_hover_animation()
        self.tokens = tokens
        self.configure(font=tokens.font(tokens.typography.meta, "semibold"), text_color_disabled=tokens.colors.text_muted)
        self.set_enabled(str(self.cget("state")) != "disabled")

    def destroy(self) -> None:
        self._cancel_hover_animation()
        super().destroy()


class IconButton(DSButton):
    def __init__(self, master, *, tokens: ThemeTokens, image=None, tooltip: str = "", **kwargs):
        self.tooltip = tooltip
        width = kwargs.pop("width", 34)
        height = kwargs.pop("height", 34)
        corner_radius = kwargs.pop("corner_radius", tokens.radius_xs)
        super().__init__(master, tokens=tokens, text="", variant="ghost", image=image, width=width, height=height, corner_radius=corner_radius, **kwargs)
        if tooltip:
            self._tooltip_window = None
            self.bind("<Enter>", self._show_tooltip, add="+")
            self.bind("<Leave>", self._hide_tooltip, add="+")

    def _show_tooltip(self, _event=None):
        if self._tooltip_window or not self.tooltip:
            return
        from utils.tooltip import show_tooltip
        self._tooltip_window = show_tooltip(self, self.tooltip, self.tokens)

    def _hide_tooltip(self, _event=None):
        if self._tooltip_window:
            self._tooltip_window.destroy()
            self._tooltip_window = None
