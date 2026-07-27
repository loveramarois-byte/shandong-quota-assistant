from __future__ import annotations

import customtkinter as ctk

from themes.tokens import ThemeTokens


class Avatar(ctk.CTkLabel):
    def __init__(self, master, *, tokens: ThemeTokens, text: str, kind: str = "assistant", **kwargs):
        self.tokens = tokens
        self.kind = kind
        super().__init__(master, text=text, width=32, height=32, corner_radius=9, font=tokens.font(tokens.typography.meta, "semibold"), **kwargs)
        self.apply_theme(tokens)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        if self.kind == "user":
            self.configure(fg_color=tokens.colors.user_surface, text_color=tokens.colors.user_text)
        else:
            self.configure(fg_color=tokens.colors.accent_soft, text_color=tokens.colors.accent)
