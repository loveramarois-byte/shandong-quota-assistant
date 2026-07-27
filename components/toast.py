from __future__ import annotations

import customtkinter as ctk

from themes.tokens import ThemeTokens


class Toast(ctk.CTkFrame):
    def __init__(self, master, *, tokens: ThemeTokens, text: str, kind: str = "info", **kwargs):
        self.tokens = tokens
        self.kind = kind
        super().__init__(master, fg_color=tokens.colors.surface, border_color=tokens.colors.border, border_width=1, corner_radius=tokens.radius_sm, **kwargs)
        color = tokens.colors.danger if kind == "error" else tokens.colors.text_secondary
        ctk.CTkLabel(self, text=text, text_color=color, font=tokens.font(tokens.typography.body), padx=16, pady=10).pack()
