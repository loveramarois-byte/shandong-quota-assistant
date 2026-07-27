from __future__ import annotations

import customtkinter as ctk

from themes.tokens import ThemeTokens
from .button import DSButton


class ConfirmModal(ctk.CTkToplevel):
    def __init__(self, master, *, tokens: ThemeTokens, title: str, detail: str, on_confirm, **kwargs):
        self.tokens = tokens
        super().__init__(master, fg_color=tokens.colors.background, **kwargs)
        self.title(title)
        self.geometry("390x190")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        ctk.CTkLabel(self, text=title, text_color=tokens.colors.text, font=tokens.font(tokens.typography.section, "semibold")).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(self, text=detail, text_color=tokens.colors.text_secondary, font=tokens.font(tokens.typography.body), wraplength=330, justify="left").pack(anchor="w", padx=24)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(anchor="e", padx=24, pady=20)
        cancel_button = DSButton(buttons, tokens=tokens, text="取消", variant="secondary", command=self.destroy, width=74)
        cancel_button.pack(side="left", padx=(0, 8))
        confirm = lambda: (on_confirm(), self.destroy())
        DSButton(buttons, tokens=tokens, text="确认", command=confirm, width=74).pack(side="left")
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: confirm())
        cancel_button.focus_set()
