from __future__ import annotations

import time

import customtkinter as ctk

from themes.tokens import ThemeTokens
from .button import DSButton, IconButton
from .scrollable import PointerScrollableFrame


class SessionRow(ctk.CTkFrame):
    def __init__(self, master, *, tokens: ThemeTokens, session_id: str, title: str, updated_at: float, on_select, **kwargs):
        self.tokens = tokens
        self.session_id = session_id
        self.on_select = on_select
        self._active = False
        super().__init__(master, fg_color="transparent", corner_radius=tokens.radius_xs, height=40, **kwargs)
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)
        c = tokens.colors
        self.indicator = ctk.CTkFrame(self, width=2, height=20, fg_color="transparent", corner_radius=0)
        self.indicator.grid(row=0, column=0, padx=(7, 6), pady=10)
        self.title_label = ctk.CTkLabel(self, text=title[:22], text_color=c.text_secondary, font=tokens.font(tokens.typography.meta, "medium"), anchor="w", justify="left")
        self.title_label.grid(row=0, column=1, pady=7, sticky="ew")
        date_text = time.strftime("%m-%d", time.localtime(updated_at)) if updated_at else ""
        self.date_label = ctk.CTkLabel(self, text=date_text, width=38, text_color=c.text_muted, font=tokens.font(tokens.typography.caption), anchor="e")
        self.date_label.grid(row=0, column=2, padx=(5, 9), pady=7, sticky="e")
        for widget in (self, self.indicator, self.title_label, self.date_label):
            widget.bind("<Button-1>", self._clicked, add="+")
            widget.bind("<Enter>", self._hover_in, add="+")
            widget.bind("<Leave>", self._hover_out, add="+")

    def _clicked(self, _event=None) -> None:
        self.on_select(self.session_id)

    def _hover_in(self, _event=None) -> None:
        if not self._active:
            self.configure(fg_color=self.tokens.colors.subtle)

    def _hover_out(self, _event=None) -> None:
        if not self._active:
            self.configure(fg_color="transparent")

    def set_active(self, active: bool) -> None:
        self._active = active
        c = self.tokens.colors
        self.configure(fg_color=c.elevated if active else "transparent")
        self.indicator.configure(fg_color=c.accent if active else "transparent")
        self.title_label.configure(text_color=c.accent if active else c.text_secondary)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.configure(fg_color=c.elevated if self._active else "transparent")
        self.indicator.configure(fg_color=c.accent if self._active else "transparent")
        self.title_label.configure(text_color=c.accent if self._active else c.text_secondary, font=tokens.font(tokens.typography.meta, "medium"))
        self.date_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, *, tokens: ThemeTokens, on_new, on_select_session=None, on_rename_session=None, on_delete_session=None, on_open_settings=None, on_open_about=None, library_stats: dict[str, int | None] | None = None, app_version: str = "", new_image=None, brand_image=None, rename_image=None, delete_image=None, settings_image=None, about_image=None, **kwargs):
        self.tokens = tokens
        self.on_new = on_new
        self.on_select_session = on_select_session or (lambda _sid: None)
        self.on_rename_session = on_rename_session or (lambda _sid: None)
        self.on_delete_session = on_delete_session or (lambda _sid: None)
        self.on_open_settings = on_open_settings or (lambda: None)
        self.on_open_about = on_open_about or (lambda: None)
        self.library_stats = library_stats or {}
        self.app_version = app_version
        self._session_rows: list[SessionRow] = []
        self._active_session_id: str | None = None
        self.new_image = new_image
        self.brand_image = brand_image
        self.rename_image = rename_image
        self.delete_image = delete_image
        self.settings_image = settings_image
        self.about_image = about_image
        super().__init__(master, width=tokens.sidebar_width, fg_color=tokens.colors.sidebar, corner_radius=0, **kwargs)
        self.grid_propagate(False)
        self._build()

    def _build(self) -> None:
        c = self.tokens.colors
        self.grid_rowconfigure(3, weight=1)
        self.right_rule = ctk.CTkFrame(self, width=1, fg_color=c.border, corner_radius=0)
        self.right_rule.place(relx=1, rely=0, relheight=1, anchor="ne")
        self.brand = ctk.CTkFrame(self, fg_color="transparent", height=60)
        self.brand.grid(row=0, column=0, sticky="ew", padx=14, pady=(2, 0))
        self.brand.grid_propagate(False)
        self.mark = ctk.CTkLabel(self.brand, text="", image=self.brand_image, width=30, height=30, corner_radius=self.tokens.radius_sm, fg_color=c.accent_soft)
        self.mark.pack(side="left", pady=15)
        brand_text = ctk.CTkFrame(self.brand, fg_color="transparent")
        brand_text.pack(side="left", padx=(9, 0), pady=14)
        self.brand_title = ctk.CTkLabel(brand_text, text="山东定额助手", text_color=c.text, font=self.tokens.font(self.tokens.typography.section, "semibold"), anchor="w")
        self.brand_title.pack(anchor="w")
        self.brand_subtitle = ctk.CTkLabel(brand_text, text="AI 套价", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w")
        self.brand_subtitle.pack(anchor="w", pady=(1, 0))
        self.new_button = DSButton(self, tokens=self.tokens, text="新分析", image=self.new_image, compound="left", variant="secondary", command=self.on_new, anchor="w")
        self.new_button.grid(row=1, column=0, padx=12, pady=(3, 14), sticky="ew")

        self.section_row = ctk.CTkFrame(self, fg_color="transparent")
        self.section_row.grid(row=2, column=0, padx=14, sticky="ew")
        self.section_label = ctk.CTkLabel(self.section_row, text="最近分析", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption, "semibold"), anchor="w")
        self.section_label.pack(side="left")
        self.rename_button = IconButton(self.section_row, tokens=self.tokens, image=self.rename_image, tooltip="重命名分析", width=28, height=28, command=self._rename_active)
        self.rename_button.pack(side="right", padx=(3, 0))
        self.delete_button = IconButton(self.section_row, tokens=self.tokens, image=self.delete_image, tooltip="删除分析", width=28, height=28, command=self._delete_active)
        self.delete_button.pack(side="right")

        self.session_list = PointerScrollableFrame(self, fg_color="transparent", corner_radius=0, scrollbar_button_color=c.border, scrollbar_button_hover_color=c.border_strong)
        self.session_list.grid(row=3, column=0, padx=8, pady=(6, 0), sticky="nsew")
        self.session_list.grid_columnconfigure(0, weight=1)
        self.empty_label = ctk.CTkLabel(self.session_list, text="暂无历史分析", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w", justify="left", wraplength=160)
        self.empty_label.grid(row=0, column=0, padx=6, pady=8, sticky="w")

        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(row=4, column=0, padx=14, pady=(10, 14), sticky="sew")
        self.footer.grid_columnconfigure(0, weight=1)
        self.footer_rule = ctk.CTkFrame(self.footer, height=1, fg_color=c.border, corner_radius=0)
        self.footer_rule.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._build_library_card()
        version_text = f"v{self.app_version}" if self.app_version else ""
        self.footer_title = ctk.CTkLabel(self.footer, text=f"山东定额 · {version_text}".strip(" ·"), text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w")
        self.footer_title.grid(row=2, column=0, sticky="w", pady=(6, 0))
        footer_buttons = ctk.CTkFrame(self.footer, fg_color="transparent")
        footer_buttons.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        self.settings_button = DSButton(footer_buttons, tokens=self.tokens, text="设置", image=self.settings_image, compound="left", variant="ghost", width=72, height=30, command=self.on_open_settings)
        self.settings_button.pack(side="left")
        self.about_button = DSButton(footer_buttons, tokens=self.tokens, text="关于", image=self.about_image, compound="left", variant="ghost", width=72, height=30, command=self.on_open_about)
        self.about_button.pack(side="left", padx=(4, 0))

    def _build_library_card(self) -> None:
        c = self.tokens.colors
        self.library_available = any(isinstance(value, int) for value in self.library_stats.values())
        self.library_info = ctk.CTkLabel(
            self.footer,
            text="本地资料库 · 已就绪" if self.library_available else "正在读取资料库",
            text_color=c.success if self.library_available else c.text_muted,
            font=self.tokens.font(self.tokens.typography.caption),
            anchor="w",
            justify="left",
            wraplength=168,
        )
        self.library_info.grid(row=1, column=0, sticky="nw")

    def set_library_stats(self, stats: dict[str, int | None] | None) -> None:
        """Apply asynchronously loaded counts without rebuilding the sidebar."""
        self.library_stats = stats or {}
        self.library_available = any(isinstance(value, int) for value in self.library_stats.values())
        self.library_info.configure(
            text="本地资料库 · 已就绪" if self.library_available else "资料库未连接",
            text_color=self.tokens.colors.success if self.library_available else self.tokens.colors.text_muted,
        )

    def refresh_sessions(self, sessions: list[dict], active_id: str | None = None) -> None:
        for row in self._session_rows:
            row.destroy()
        self._session_rows = []
        self._active_session_id = active_id
        if not sessions:
            self.empty_label.grid(row=0, column=0, padx=6, pady=8, sticky="w")
            return
        self.empty_label.grid_remove()
        for index, session in enumerate(sessions):
            row = SessionRow(self.session_list, tokens=self.tokens, session_id=session["id"], title=session["title"], updated_at=session.get("updated_at") or 0, on_select=self._select)
            row.grid(row=index, column=0, sticky="ew", pady=(0, 2))
            row.set_active(session["id"] == active_id)
            self._session_rows.append(row)

    def _select(self, session_id: str) -> None:
        accepted = self.on_select_session(session_id)
        if accepted is False:
            return
        self._active_session_id = session_id
        for row in self._session_rows:
            row.set_active(row.session_id == session_id)

    def mark_active(self, session_id: str | None) -> None:
        self._active_session_id = session_id
        for row in self._session_rows:
            row.set_active(row.session_id == session_id)

    def _rename_active(self) -> None:
        if self._active_session_id:
            self.on_rename_session(self._active_session_id)

    def _delete_active(self) -> None:
        if self._active_session_id:
            self.on_delete_session(self._active_session_id)

    def set_busy(self, busy: bool) -> None:
        self.new_button.set_enabled(not busy)
        self.rename_button.set_enabled(not busy)
        self.delete_button.set_enabled(not busy)

    def set_new_image(self, image) -> None:
        self.new_image = image
        self.new_button.configure(image=image)
        self.new_button._normal_image = image

    def set_action_images(self, *, brand=None, rename=None, delete=None, settings=None, about=None) -> None:
        for widget, image in (
            (self.mark, brand),
            (self.rename_button, rename),
            (self.delete_button, delete),
            (self.settings_button, settings),
            (self.about_button, about),
        ):
            if image is not None:
                widget.configure(image=image)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.configure(fg_color=c.sidebar)
        self.right_rule.configure(fg_color=c.border)
        self.brand.configure(fg_color="transparent")
        self.mark.configure(fg_color=c.accent_soft)
        self.brand_title.configure(text_color=c.text, font=tokens.font(tokens.typography.section, "semibold"))
        self.brand_subtitle.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        self.section_row.configure(fg_color="transparent")
        self.section_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption, "semibold"))
        self.footer.configure(fg_color="transparent")
        self.footer_rule.configure(fg_color=c.border)
        self.footer_title.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        self.session_list.configure(fg_color="transparent", scrollbar_button_color=c.border, scrollbar_button_hover_color=c.border_strong)
        self.empty_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        self.new_button.apply_theme(tokens)
        self.rename_button.apply_theme(tokens)
        self.delete_button.apply_theme(tokens)
        self.settings_button.apply_theme(tokens)
        self.about_button.apply_theme(tokens)
        self.library_info.configure(text_color=c.success if self.library_available else c.text_muted, font=tokens.font(tokens.typography.caption))
        for row in self._session_rows:
            row.apply_theme(tokens)
