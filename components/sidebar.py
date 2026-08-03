from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
import time

import customtkinter as ctk

from themes.tokens import ThemeTokens
from .button import DSButton, IconButton
from .scrollable import PointerScrollableFrame


def _session_title(value: str) -> str:
    """Normalize whitespace before fitting the title to the rail."""
    return " ".join(str(value or "").split())


def _session_updated_at(value: object) -> float:
    """Keep session refresh resilient to incomplete or legacy summaries."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _session_date(updated_at: float) -> str:
    if not updated_at:
        return ""
    try:
        return time.strftime("%m-%d", time.localtime(updated_at))
    except (OverflowError, OSError, ValueError):
        return ""


def _ellipsize(text: str, max_width: int, face: tkfont.Font) -> str:
    """Fit a mixed Chinese/Latin title to pixels instead of character count."""
    if not text or face.measure(text) <= max_width:
        return text
    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if face.measure(text[:middle] + ellipsis) <= max_width:
            low = middle
        else:
            high = middle - 1
    return (text[:low] + ellipsis) if low else ellipsis


class SessionRow(ctk.CTkFrame):
    def __init__(self, master, *, tokens: ThemeTokens, session_id: str, title: str, updated_at: float, on_select, **kwargs):
        self.tokens = tokens
        self.session_id = session_id
        self.on_select = on_select
        self._raw_title = _session_title(title)
        self.updated_at = _session_updated_at(updated_at)
        self._active = False
        self._tooltip_window = None
        self._tooltip_job = None
        super().__init__(master, fg_color="transparent", corner_radius=tokens.radius_sm, height=38, **kwargs)
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)
        c = tokens.colors
        self.indicator = ctk.CTkFrame(self, width=3, height=20, fg_color="transparent", corner_radius=2)
        self.indicator.grid(row=0, column=0, padx=(6, 8), pady=9)
        self.title_label = ctk.CTkLabel(
            self,
            text="",
            text_color=c.text_secondary,
            font=tokens.font(tokens.typography.meta, "medium"),
            anchor="w",
        )
        self.title_label.grid(row=0, column=1, padx=(0, 8), pady=3, sticky="ew")
        date_text = _session_date(self.updated_at)
        self.date_label = ctk.CTkLabel(self, text=date_text, width=38, text_color=c.text_muted, font=tokens.font(tokens.typography.caption), anchor="e")
        # The chronological order already conveys recency. Hiding repeated
        # dates keeps narrow navigation rows readable and gives titles room.
        self.date_label.grid_remove()
        for widget in (self, self.indicator, self.title_label, self.date_label):
            widget.bind("<Button-1>", self._clicked, add="+")
            widget.bind("<Enter>", self._hover_in, add="+")
            widget.bind("<Leave>", self._hover_out, add="+")
        self.bind("<Configure>", self._schedule_title_fit, add="+")
        self.after_idle(self._fit_title)

    def _schedule_title_fit(self, _event=None) -> None:
        if self._tooltip_job:
            try:
                self.after_cancel(self._tooltip_job)
            except tk.TclError:
                pass
        self.after_idle(self._fit_title)

    def _fit_title(self) -> None:
        if not self.winfo_exists():
            return
        width = self.winfo_width() or self.tokens.sidebar_width
        available = max(120, width - 30)
        face = tkfont.Font(font=self.tokens.font(self.tokens.typography.meta, "medium"))
        try:
            display = _ellipsize(self._raw_title, available, face)
        finally:
            # ``tkinter.font.Font`` does not expose ``destroy`` on all
            # supported Tk builds (including the bundled Windows Tk 8.6).
            # Its ``__del__`` releases the generated named font; calling a
            # missing method here used to abort the whole theme refresh.
            close = getattr(face, "destroy", None)
            if callable(close):
                close()
        if self.title_label.cget("text") != display:
            self.title_label.configure(text=display)

    def _clicked(self, _event=None) -> None:
        self.on_select(self.session_id)

    def _hover_in(self, _event=None) -> None:
        if not self._active:
            self.configure(fg_color=self.tokens.colors.subtle)
        self._tooltip_job = self.after(460, self._show_full_title)

    def _hover_out(self, _event=None) -> None:
        if not self._active:
            self.configure(fg_color="transparent")
        if self._tooltip_job:
            try:
                self.after_cancel(self._tooltip_job)
            except tk.TclError:
                pass
            self._tooltip_job = None
        self._hide_full_title()

    def _show_full_title(self) -> None:
        self._tooltip_job = None
        if self._tooltip_window or self.title_label.cget("text") == self._raw_title:
            return
        from utils.tooltip import show_tooltip
        self._tooltip_window = show_tooltip(
            self, self._raw_title, self.tokens, clamp_to_screen=True
        )

    def _hide_full_title(self) -> None:
        if self._tooltip_window:
            self._tooltip_window.destroy()
            self._tooltip_window = None

    def update_session(self, *, title: str, updated_at: float) -> bool:
        """Refresh only the visible session metadata that has actually changed."""
        raw_title = _session_title(title)
        timestamp = _session_updated_at(updated_at)
        title_changed = raw_title != self._raw_title
        time_changed = timestamp != self.updated_at
        if not title_changed and not time_changed:
            return False

        self._raw_title = raw_title
        self.updated_at = timestamp
        if time_changed:
            self.date_label.configure(text=_session_date(timestamp))
        if title_changed:
            self._hide_full_title()
            self.after_idle(self._fit_title)
        return True

    def matches_session(self, *, title: str, updated_at: float) -> bool:
        """Return whether an incoming summary needs any visual refresh."""
        return (
            _session_title(title) == self._raw_title
            and _session_updated_at(updated_at) == self.updated_at
        )

    def set_active(self, active: bool) -> None:
        active = bool(active)
        if active == self._active:
            return
        self._active = active
        c = self.tokens.colors
        self.configure(fg_color=c.accent_soft if active else "transparent")
        self.indicator.configure(fg_color=c.accent if active else "transparent")
        self.title_label.configure(text_color=c.accent if active else c.text_secondary)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.configure(fg_color=c.accent_soft if self._active else "transparent")
        self.indicator.configure(fg_color=c.accent if self._active else "transparent")
        self.title_label.configure(text_color=c.accent if self._active else c.text_secondary, font=tokens.font(tokens.typography.meta, "medium"))
        self.date_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        self._fit_title()

    def destroy(self) -> None:
        if self._tooltip_job:
            try:
                self.after_cancel(self._tooltip_job)
            except tk.TclError:
                pass
            self._tooltip_job = None
        self._hide_full_title()
        super().destroy()


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
        self.right_rule = ctk.CTkFrame(self, width=1, fg_color=c.sidebar_border, corner_radius=0)
        self.right_rule.place(relx=1, rely=0, relheight=1, anchor="ne")
        self.brand = ctk.CTkFrame(self, fg_color="transparent", height=68)
        self.brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(8, 0))
        self.brand.grid_propagate(False)
        self.mark = ctk.CTkLabel(self.brand, text="", image=self.brand_image, width=34, height=34, corner_radius=self.tokens.radius_sm, fg_color=c.accent_soft)
        self.mark.pack(side="left", pady=15)
        brand_text = ctk.CTkFrame(self.brand, fg_color="transparent")
        brand_text.pack(side="left", padx=(10, 0), pady=14)
        self.brand_title = ctk.CTkLabel(brand_text, text="山东定额助手", text_color=c.text, font=self.tokens.font(self.tokens.typography.section, "semibold"), anchor="w")
        self.brand_title.pack(anchor="w")
        self.brand_subtitle = ctk.CTkLabel(brand_text, text="AI 套价", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w")
        self.brand_subtitle.pack(anchor="w", pady=(1, 0))
        self.new_button = DSButton(self, tokens=self.tokens, text="新分析", image=self.new_image, compound="left", variant="secondary", height=38, command=self.on_new, anchor="w")
        self.new_button.grid(row=1, column=0, padx=16, pady=(2, 18), sticky="ew")

        self.section_row = ctk.CTkFrame(self, fg_color="transparent")
        self.section_row.grid(row=2, column=0, padx=18, sticky="ew")
        self.section_label = ctk.CTkLabel(self.section_row, text="最近分析", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption, "semibold"), anchor="w")
        self.section_label.pack(side="left")
        self.rename_button = IconButton(self.section_row, tokens=self.tokens, image=self.rename_image, tooltip="重命名分析", width=28, height=28, command=self._rename_active)
        self.delete_button = IconButton(self.section_row, tokens=self.tokens, image=self.delete_image, tooltip="删除分析", width=28, height=28, command=self._delete_active)
        self._session_actions_visible = False
        self._set_session_actions_visible(False)

        self.session_list = PointerScrollableFrame(self, fg_color=c.sidebar, corner_radius=0, scrollbar_button_color=c.border, scrollbar_button_hover_color=c.border_strong)
        self.session_list.grid(row=3, column=0, padx=12, pady=(7, 0), sticky="nsew")
        self.session_list.grid_columnconfigure(0, weight=1)
        self.empty_label = ctk.CTkLabel(self.session_list, text="暂无历史分析", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w", justify="left", wraplength=196)
        self.empty_label.grid(row=0, column=0, padx=6, pady=10, sticky="w")

        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(row=4, column=0, padx=18, pady=(10, 16), sticky="sew")
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
        self.update_button = DSButton(self.footer, tokens=self.tokens, text="", variant="ghost", width=166, height=28, command=self.on_open_about, anchor="w")
        self.update_button.grid(row=4, column=0, sticky="w", pady=(5, 0))
        self.update_button.grid_remove()

    def _set_session_actions_visible(self, visible: bool) -> None:
        """Keep destructive history controls out of the idle navigation state."""
        visible = bool(visible)
        if visible == self._session_actions_visible:
            return
        self._session_actions_visible = visible
        if visible:
            self.rename_button.pack(side="right", padx=(3, 0))
            self.delete_button.pack(side="right")
        else:
            self.rename_button.pack_forget()
            self.delete_button.pack_forget()

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
            wraplength=196,
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

    def set_update_available(self, version: str | None) -> None:
        if not version:
            self.update_button.grid_remove()
            return
        self.update_button.configure(text=f"发现 v{version} 更新")
        self.update_button.grid()

    def refresh_sessions(self, sessions: list[dict], active_id: str | None = None) -> None:
        new_ids = [s["id"] for s in sessions]
        old_ids = [r.session_id for r in self._session_rows]
        self._active_session_id = active_id
        self._set_session_actions_visible(bool(active_id))

        if new_ids == old_ids:
            # The common save path keeps its order.  Do not touch geometry or
            # recreate Canvas widgets; update a row only when its display data
            # actually changed, then refresh the active highlight.
            for row, session in zip(self._session_rows, sessions):
                if not row.matches_session(title=session["title"], updated_at=session.get("updated_at") or 0):
                    row.update_session(
                        title=session["title"],
                        updated_at=session.get("updated_at") or 0,
                    )
                row.set_active(row.session_id == active_id)
            if sessions:
                self.empty_label.grid_remove()
            else:
                self.empty_label.grid(row=0, column=0, padx=6, pady=8, sticky="w")
            return

        if not sessions:
            for row in self._session_rows:
                row.destroy()
            self._session_rows = []
            self.empty_label.grid(row=0, column=0, padx=6, pady=8, sticky="w")
            return

        self.empty_label.grid_remove()
        old_positions = {row.session_id: index for index, row in enumerate(self._session_rows)}
        reusable_rows = {row.session_id: row for row in self._session_rows}
        refreshed_rows: list[SessionRow] = []
        for index, session in enumerate(sessions):
            session_id = session["id"]
            row = reusable_rows.pop(session_id, None)
            if row is None:
                row = SessionRow(
                    self.session_list,
                    tokens=self.tokens,
                    session_id=session_id,
                    title=session["title"],
                    updated_at=session.get("updated_at") or 0,
                    on_select=self._select,
                )
                row.grid(row=index, column=0, sticky="ew", pady=(0, 2))
            else:
                if not row.matches_session(title=session["title"], updated_at=session.get("updated_at") or 0):
                    row.update_session(
                        title=session["title"],
                        updated_at=session.get("updated_at") or 0,
                    )
                if old_positions.get(session_id) != index:
                    row.grid(row=index, column=0, sticky="ew", pady=(0, 2))
            row.set_active(session["id"] == active_id)
            refreshed_rows.append(row)

        for row in reusable_rows.values():
            row.destroy()
        self._session_rows = refreshed_rows

    def _select(self, session_id: str) -> None:
        accepted = self.on_select_session(session_id)
        if accepted is False:
            return
        self._active_session_id = session_id
        self._set_session_actions_visible(True)
        for row in self._session_rows:
            row.set_active(row.session_id == session_id)

    def mark_active(self, session_id: str | None) -> None:
        self._active_session_id = session_id
        self._set_session_actions_visible(bool(session_id))
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
        self.right_rule.configure(fg_color=c.sidebar_border)
        self.brand.configure(fg_color="transparent")
        self.mark.configure(fg_color=c.accent_soft)
        self.brand_title.configure(text_color=c.text, font=tokens.font(tokens.typography.section, "semibold"))
        self.brand_subtitle.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        self.section_row.configure(fg_color="transparent")
        self.section_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption, "semibold"))
        self.footer.configure(fg_color="transparent")
        self.footer_rule.configure(fg_color=c.border)
        self.footer_title.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        self.session_list.apply_surface_color(c.sidebar)
        self.session_list.configure(scrollbar_button_color=c.border, scrollbar_button_hover_color=c.border_strong)
        self.empty_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        self.new_button.apply_theme(tokens)
        self.rename_button.apply_theme(tokens)
        self.delete_button.apply_theme(tokens)
        self.settings_button.apply_theme(tokens)
        self.about_button.apply_theme(tokens)
        self.update_button.apply_theme(tokens)
        self.library_info.configure(text_color=c.success if self.library_available else c.text_muted, font=tokens.font(tokens.typography.caption))
        for row in self._session_rows:
            row.apply_theme(tokens)
