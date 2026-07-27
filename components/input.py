from __future__ import annotations

import customtkinter as ctk

from themes.tokens import ThemeTokens
from .button import DSButton

EXAMPLE_CHIPS = [
    ("土方", "人工挖沟槽土方，三类土，槽深2.5m，弃土运距50m"),
    ("混凝土垫层", "C15混凝土垫层，厚度100mm"),
    ("砌砖", "M5混合砂浆砌实心砖墙，墙厚240mm"),
    ("电气配管", "电气配管 DN20 暗配"),
    ("给排水", "室内给水管道安装 DN25"),
]

_SOIL_OPTIONS = ["未指定", "普通土(一、二类)", "坚土(三类)", "砂砾坚土(四类)"]
_SOIL_QUERY = {"普通土(一、二类)": "普通土", "坚土(三类)": "三类土", "砂砾坚土(四类)": "四类土"}
_METHOD_OPTIONS = ["未指定", "人工", "机械"]


class FilterSelect(ctk.CTkOptionMenu):
    def __init__(self, master, *, tokens: ThemeTokens, values: list[str], **kwargs):
        self.tokens = tokens
        height = kwargs.pop("height", tokens.control_height)
        super().__init__(master, values=values, fg_color=tokens.colors.elevated, button_color=tokens.colors.elevated, button_hover_color=tokens.colors.subtle, text_color=tokens.colors.text, dropdown_fg_color=tokens.colors.elevated, dropdown_hover_color=tokens.colors.subtle, dropdown_text_color=tokens.colors.text, font=tokens.font(tokens.typography.meta), dropdown_font=tokens.font(tokens.typography.meta), corner_radius=tokens.radius_sm, height=height, **kwargs)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.configure(fg_color=c.elevated, button_color=c.elevated, button_hover_color=c.subtle, text_color=c.text, dropdown_fg_color=c.elevated, dropdown_hover_color=c.subtle, dropdown_text_color=c.text, font=tokens.font(tokens.typography.meta), dropdown_font=tokens.font(tokens.typography.meta))


class ConditionBar(ctk.CTkFrame):
    """Optional structured conditions merged into the query text (P1-5.1)."""

    def __init__(self, master, *, tokens: ThemeTokens, **kwargs):
        self.tokens = tokens
        super().__init__(master, fg_color="transparent", **kwargs)
        c = tokens.colors
        self.grid_columnconfigure((1, 3, 5, 7), weight=1)
        caption_font = tokens.font(tokens.typography.caption)
        ctk.CTkLabel(self, text="土类", text_color=c.text_muted, font=caption_font).grid(row=0, column=0, padx=(0, 4))
        self.soil = FilterSelect(self, tokens=tokens, values=_SOIL_OPTIONS, width=132, height=30)
        self.soil.set("未指定")
        self.soil.grid(row=0, column=1, sticky="w", padx=(0, 10))
        ctk.CTkLabel(self, text="深度m", text_color=c.text_muted, font=caption_font).grid(row=0, column=2, padx=(0, 4))
        self.depth = ctk.CTkEntry(self, placeholder_text="如2.5", width=64, height=30, font=tokens.font(tokens.typography.meta), fg_color=c.elevated, border_color=c.border, text_color=c.text)
        self.depth.grid(row=0, column=3, sticky="w", padx=(0, 10))
        ctk.CTkLabel(self, text="运距m", text_color=c.text_muted, font=caption_font).grid(row=0, column=4, padx=(0, 4))
        self.distance = ctk.CTkEntry(self, placeholder_text="如50", width=64, height=30, font=tokens.font(tokens.typography.meta), fg_color=c.elevated, border_color=c.border, text_color=c.text)
        self.distance.grid(row=0, column=5, sticky="w", padx=(0, 10))
        ctk.CTkLabel(self, text="方法", text_color=c.text_muted, font=caption_font).grid(row=0, column=6, padx=(0, 4))
        self.method = FilterSelect(self, tokens=tokens, values=_METHOD_OPTIONS, width=88, height=30)
        self.method.set("未指定")
        self.method.grid(row=0, column=7, sticky="w")

    def conditions_text(self) -> str:
        parts: list[str] = []
        soil = _SOIL_QUERY.get(self.soil.get())
        if soil:
            parts.append(soil)
        depth = self.depth.get().strip()
        if depth:
            parts.append(f"深度{depth}m")
        distance = self.distance.get().strip()
        if distance:
            parts.append(f"运距{distance}m")
        method = self.method.get()
        if method and method != "未指定":
            parts.append(method)
        return "，".join(parts)

    def clear(self) -> None:
        self.soil.set("未指定")
        self.depth.delete(0, "end")
        self.distance.delete(0, "end")
        self.method.set("未指定")

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.configure(fg_color="transparent")
        for child in self.winfo_children():
            if isinstance(child, ctk.CTkLabel):
                child.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        self.soil.apply_theme(tokens)
        self.method.apply_theme(tokens)
        for entry in (self.depth, self.distance):
            entry.configure(font=tokens.font(tokens.typography.meta), fg_color=c.elevated, border_color=c.border, text_color=c.text)


class Composer(ctk.CTkFrame):
    MAX_CHARS = 500

    def __init__(self, master, *, tokens: ThemeTokens, on_send, on_cancel=None, send_image=None, on_limit=None, **kwargs):
        self.tokens = tokens
        self.on_send = on_send
        self.on_cancel = on_cancel
        self.on_limit = on_limit
        self.placeholder = "例：人工挖沟槽，三类土，槽深 2.5m，弃土装车；或直接输入编码 010102002"
        self._placeholder_active = True
        self._error_job = None
        self._enter_send = False
        self._last_sent = ""
        self._conditions_visible = False
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build(send_image)

    def _build(self, send_image) -> None:
        c = self.tokens.colors
        self.chips_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.chips_frame.pack(fill="x", pady=(0, 6))
        self.condition_toggle = DSButton(self.chips_frame, tokens=self.tokens, text="条件 +", variant="ghost", width=64, height=26, command=self._toggle_conditions)
        self.condition_toggle.pack(side="left", padx=(0, 6))
        self._chip_buttons: list[DSButton] = []
        for label, sample in EXAMPLE_CHIPS:
            chip = DSButton(self.chips_frame, tokens=self.tokens, text=label, variant="ghost", width=64, height=26, command=lambda text=sample: self._fill_example(text))
            chip.pack(side="left", padx=(0, 4))
            self._chip_buttons.append(chip)
        self.char_label = ctk.CTkLabel(self.chips_frame, text=f"0/{self.MAX_CHARS}", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="e")
        self.char_label.pack(side="right")

        self.condition_bar = ConditionBar(self, tokens=self.tokens)

        self.shell = ctk.CTkFrame(self, fg_color=c.elevated, border_color=c.border, border_width=1, corner_radius=self.tokens.radius_md)
        self.shell.pack(fill="x")
        self.textbox = ctk.CTkTextbox(self.shell, height=64, fg_color="transparent", border_width=0, text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.body), wrap="word", activate_scrollbars=False)
        self.textbox.pack(side="left", fill="both", expand=True, padx=(16, 4), pady=9)
        self.textbox.insert("1.0", self.placeholder)
        self.textbox.bind("<FocusIn>", self._clear_placeholder)
        self.textbox.bind("<FocusOut>", self._restore_placeholder)
        self.textbox.bind("<Control-Return>", self._send_event)
        self.textbox.bind("<KeyRelease>", self._update_char_count, add="+")
        self.textbox.bind("<Up>", self._restore_last_sent)
        self.cancel_button = DSButton(self.shell, tokens=self.tokens, text="停止", variant="secondary", width=68, command=self.on_cancel or (lambda: None))
        self.send_button = DSButton(self.shell, tokens=self.tokens, text="分析", variant="primary", image=send_image, compound="left", width=88, command=self.on_send)
        self.send_button.pack(side="right", padx=12, pady=12, anchor="s")
        self.textbox.bind("<FocusIn>", lambda _e: self.shell.configure(border_color=self.tokens.colors.accent), add="+")
        self.textbox.bind("<FocusOut>", lambda _e: self.shell.configure(border_color=self.tokens.colors.border), add="+")

    def _toggle_conditions(self) -> None:
        self._conditions_visible = not self._conditions_visible
        if self._conditions_visible:
            self.condition_bar.pack(fill="x", pady=(0, 6), before=self.shell)
            self.condition_toggle.configure(text="条件 −")
        else:
            self.condition_bar.pack_forget()
            self.condition_toggle.configure(text="条件 +")

    def _fill_example(self, text: str) -> None:
        if self._placeholder_active:
            self.textbox.delete("1.0", "end")
            self._placeholder_active = False
        self.textbox.configure(text_color=self.tokens.colors.text)
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)
        self._update_char_count()
        self.textbox.focus_set()

    def set_enter_send(self, enabled: bool) -> None:
        self._enter_send = bool(enabled)
        if self._enter_send:
            self.textbox.bind("<Return>", self._enter_send_event)
            self.textbox.unbind("<Control-Return>")
        else:
            self.textbox.unbind("<Return>")
            self.textbox.bind("<Control-Return>", self._send_event)

    def _enter_send_event(self, _event=None) -> str | None:
        if _event is not None and (_event.state & 0x1):  # Shift held -> newline
            return None
        self.on_send()
        return "break"

    def _update_char_count(self, _event=None) -> None:
        length = 0 if self._placeholder_active else len(self.textbox.get("1.0", "end").strip())
        over = length > self.MAX_CHARS
        self.char_label.configure(text=f"{length}/{self.MAX_CHARS}", text_color=self.tokens.colors.danger if over else self.tokens.colors.text_muted)
        if over and self.on_limit:
            self.on_limit()

    def _restore_last_sent(self, _event=None) -> str | None:
        current = "" if self._placeholder_active else self.textbox.get("1.0", "end").strip()
        if current or not self._last_sent:
            return None
        self.textbox.configure(text_color=self.tokens.colors.text)
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", self._last_sent)
        self._placeholder_active = False
        self.textbox.mark_set("insert", "end")
        self._update_char_count()
        return "break"

    def remember_sent(self, text: str) -> None:
        self._last_sent = text.strip()

    def _clear_placeholder(self, _event=None) -> None:
        if self._placeholder_active:
            self.textbox.delete("1.0", "end")
            self.textbox.configure(text_color=self.tokens.colors.text)
            self._placeholder_active = False

    def _restore_placeholder(self, _event=None) -> None:
        if not self.textbox.get("1.0", "end").strip():
            self.textbox.insert("1.0", self.placeholder)
            self.textbox.configure(text_color=self.tokens.colors.text_muted)
            self._placeholder_active = True

    def _send_event(self, _event=None) -> str:
        self.on_send()
        return "break"

    def get_text(self) -> str:
        value = self.textbox.get("1.0", "end").strip()
        if value == self.placeholder:
            value = ""
        # Some accessibility/input drivers can insert text before Tk emits FocusIn.
        # Treat the visible value as the source of truth and discard the stale placeholder.
        if value.startswith(self.placeholder):
            value = value[len(self.placeholder):].lstrip()
        if value:
            self._placeholder_active = False
            self.textbox.configure(text_color=self.tokens.colors.text)
        conditions = self.condition_bar.conditions_text()
        if conditions:
            value = f"{value}，{conditions}" if value else conditions
        return value

    def is_over_limit(self) -> bool:
        if self._placeholder_active:
            return False
        return len(self.textbox.get("1.0", "end").strip()) > self.MAX_CHARS

    def clear(self) -> None:
        self.textbox.delete("1.0", "end")
        self._restore_placeholder()
        self._update_char_count()

    def set_send_image(self, image) -> None:
        self.send_button.configure(image=image)
        self.send_button._normal_image = image

    def show_error(self) -> None:
        self.shell.configure(border_color=self.tokens.colors.danger)
        if self._error_job:
            self.after_cancel(self._error_job)
        self._error_job = self.after(1400, self._clear_error)

    def _clear_error(self) -> None:
        self._error_job = None
        color = self.tokens.colors.accent if self.textbox.focus_get() == self.textbox else self.tokens.colors.border
        self.shell.configure(border_color=color)

    def set_busy(self, busy: bool) -> None:
        self.send_button.set_loading(busy, "查库中…")
        self.textbox.configure(state="disabled" if busy else "normal")
        if not busy:
            self.cancel_button.pack_forget()

    def set_ai_cancel_available(self, available: bool, *, search_running: bool = False) -> None:
        if available:
            self.cancel_button.configure(text="停止检索" if search_running else "停止 AI")
            if not self.cancel_button.winfo_manager():
                self.cancel_button.pack(side="right", padx=(0, 0), pady=12, anchor="s", before=self.send_button)
            if not search_running:
                # AI is a per-turn background task. A returned local result
                # must not block the next query or session navigation.
                self.send_button.set_loading(False)
                self.send_button.set_enabled(True)
        else:
            self.cancel_button.pack_forget()
            if str(self.textbox.cget("state")) != "disabled":
                self.send_button.set_loading(False)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.configure(fg_color="transparent")
        self.chips_frame.configure(fg_color="transparent")
        self.shell.configure(fg_color=c.elevated, border_color=c.border)
        self.textbox.configure(text_color=c.text_muted if self._placeholder_active else c.text, font=tokens.font(tokens.typography.body))
        self.char_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        self.condition_toggle.apply_theme(tokens)
        for chip in self._chip_buttons:
            chip.apply_theme(tokens)
        self.condition_bar.apply_theme(tokens)
        self.send_button.apply_theme(tokens)
        self.cancel_button.apply_theme(tokens)
