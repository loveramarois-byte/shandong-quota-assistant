from __future__ import annotations

import webbrowser

import customtkinter as ctk

from themes.tokens import ThemeTokens
from .button import DSButton

SHORTCUTS = [
    ("Ctrl+Enter / Enter*", "发送分析（*可在设置中开启 Enter 发送）"),
    ("↑（输入框为空时）", "恢复上一条发送内容"),
    ("Ctrl+K", "聚焦输入框"),
    ("Esc", "关闭弹窗"),
]

DISCLAIMER = (
    "本工具提供山东定额/清单资料检索与辅助分析，不替代注册造价人员的职业判断。"
    "编码、单位、换算、工作内容及最终套项，请以现行标准、合同约定、现场条件及原书为准。"
    "AI 解释仅供参考；无本地资料引用的结论不得直接用于报量结算。"
)


class AboutDialog(ctk.CTkToplevel):
    """Version, independent filter scope, shortcuts and diagnostics export."""

    def __init__(self, master, *, tokens: ThemeTokens, info: dict, on_export_diagnostics=None, on_check_updates=None, **kwargs):
        self.tokens = tokens
        self.on_export_diagnostics = on_export_diagnostics
        self.on_check_updates = on_check_updates
        self._update_url = ""
        super().__init__(master, fg_color=tokens.colors.background, **kwargs)
        self.title("关于 山东定额助手")
        self.geometry("540x620")
        self.minsize(460, 460)
        self.transient(master)
        self.grab_set()
        self._build(info)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _build(self, info: dict) -> None:
        c = self.tokens.colors
        pad = {"padx": 26}
        body = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=c.border,
            scrollbar_button_hover_color=c.border_strong,
        )
        body.pack(fill="both", expand=True)
        ctk.CTkLabel(body, text="山东定额助手", text_color=c.text, font=self.tokens.font(self.tokens.typography.section, "semibold"), anchor="w").pack(anchor="w", pady=(22, 4), **pad)
        ctk.CTkLabel(body, text=f"应用版本 v{info.get('app_version', '-')}", text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.meta), anchor="w").pack(anchor="w", **pad)
        update_row = ctk.CTkFrame(body, fg_color="transparent")
        update_row.pack(fill="x", pady=(8, 0), **pad)
        update_row.grid_columnconfigure(0, weight=1)
        self.update_status = ctk.CTkLabel(update_row, text="可自动检查 GitHub / Gitee 是否有新版本", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w")
        self.update_status.grid(row=0, column=0, sticky="w")
        if self.on_check_updates:
            self.update_button = DSButton(update_row, tokens=self.tokens, text="检查更新", variant="ghost", width=82, height=28, command=self._check_updates)
            self.update_button.grid(row=0, column=1, padx=(8, 0), sticky="e")

        rows = [
            ("资料库路径", info.get("database", "-")),
            ("资料版本", info.get("library", "山东 2016 / 2025 定额 · 2013 / 2024 清单")),
            ("版本口径", "定额版本与清单依据独立选择；适用性按合同、招标文件和政策确认"),
            ("检索后端", info.get("search_backend", "fts")),
            ("日志目录", info.get("logs", "-")),
            ("数据说明", info.get("data_note", "定额数据来源于本地资料库，仅供内部学习核验；商业使用授权情况请由使用单位自行确认。")),
        ]
        form = ctk.CTkFrame(body, fg_color="transparent")
        form.pack(fill="x", pady=(14, 0), **pad)
        form.grid_columnconfigure(1, weight=1)
        for index, (name, value) in enumerate(rows):
            ctk.CTkLabel(form, text=name, text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="nw", width=86).grid(row=index, column=0, sticky="nw", pady=4)
            ctk.CTkLabel(form, text=str(value), text_color=c.text, font=self.tokens.font(self.tokens.typography.meta), anchor="w", justify="left", wraplength=330).grid(row=index, column=1, sticky="ew", pady=4)

        ctk.CTkLabel(body, text="快捷键", text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="w").pack(anchor="w", pady=(14, 2), **pad)
        keys = ctk.CTkFrame(body, fg_color="transparent")
        keys.pack(fill="x", **pad)
        keys.grid_columnconfigure(1, weight=1)
        for index, (key, desc) in enumerate(SHORTCUTS):
            ctk.CTkLabel(keys, text=key, text_color=c.accent, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="w", width=150).grid(row=index, column=0, sticky="w", pady=2)
            ctk.CTkLabel(keys, text=desc, text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.meta), anchor="w", justify="left", wraplength=280).grid(row=index, column=1, sticky="ew", pady=2)

        ctk.CTkLabel(body, text="风险声明", text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="w").pack(anchor="w", pady=(14, 2), **pad)
        ctk.CTkLabel(body, text=DISCLAIMER, text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w", justify="left", wraplength=440).pack(anchor="w", pady=(0, 18), **pad)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=26, pady=14)
        if self.on_export_diagnostics:
            DSButton(buttons, tokens=self.tokens, text="导出诊断包", variant="secondary", width=100, command=self._export_diagnostics).pack(side="right", padx=(8, 0))
        DSButton(buttons, tokens=self.tokens, text="关闭", width=74, command=self.destroy).pack(side="right")

    def _export_diagnostics(self) -> None:
        if self.on_export_diagnostics:
            self.on_export_diagnostics()

    def _check_updates(self) -> None:
        self.set_update_checking()
        if self.on_check_updates:
            self.on_check_updates()

    def set_update_checking(self) -> None:
        if hasattr(self, "update_button"):
            self.update_button.set_loading(True, "检查中…")
        self.update_status.configure(text="正在检查版本…", text_color=self.tokens.colors.text_muted)

    def set_update_result(self, release=None) -> None:
        if hasattr(self, "update_button"):
            self.update_button.set_loading(False)
        if release is None:
            self._update_url = ""
            self.update_status.configure(text="当前已经是最新版本，或暂时无法连接更新服务。", text_color=self.tokens.colors.text_muted)
            if hasattr(self, "update_button"):
                self.update_button.configure(text="重新检查", command=self._check_updates)
            return
        self._update_url = str(release.url or "")
        self.update_status.configure(text=f"发现新版本 v{release.version}（{release.source}）", text_color=self.tokens.colors.success)
        if hasattr(self, "update_button"):
            self.update_button.configure(text="打开下载页", command=self._open_update_url)

    def _open_update_url(self) -> None:
        if self._update_url:
            try:
                webbrowser.open(self._update_url, new=2)
            except OSError:
                self.update_status.configure(text=f"请在浏览器打开：{self._update_url}", text_color=self.tokens.colors.text_secondary)
