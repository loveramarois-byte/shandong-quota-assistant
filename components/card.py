from __future__ import annotations

import customtkinter as ctk

from themes.tokens import ThemeTokens


class SurfaceCard(ctk.CTkFrame):
    def __init__(self, master, *, tokens: ThemeTokens, **kwargs):
        self.tokens = tokens
        super().__init__(master, fg_color=tokens.colors.surface, border_color=tokens.colors.border, border_width=1, corner_radius=tokens.radius_md, **kwargs)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        self.configure(fg_color=tokens.colors.surface, border_color=tokens.colors.border)
