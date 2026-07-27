from __future__ import annotations

import os
import re
import tkinter as tk
from pathlib import Path, PureWindowsPath

import customtkinter as ctk

from themes.tokens import ThemeTokens
from utils.formatting import discipline_label, normalize_unit
from utils.paths import resource_path
from utils.svg import svg_image
from .button import DSButton, IconButton

DISCLAIMER = (
    "AI 辅助解释仅用于检索复核，正式使用前应由专业造价人员结合当地现行定额及项目实际情况复核。"
    "编码、单位、换算、工作内容及最终套项，请以现行标准、合同约定、现场条件及原书为准；"
    "无本地资料引用的结论不得直接用于报量结算。"
)
UI_DISCLAIMER = "候选来自本地资料库；正式套项请结合原书、合同约定和现场条件复核。"


def _unit(item: dict) -> str:
    return normalize_unit(item.get("unit"))


def _edition(item: dict) -> str:
    return str(item.get("quota_edition") or item.get("edition") or "").strip()


def _source_name(value: str | None) -> str:
    if not value:
        return "来源文件未挂页"
    return PureWindowsPath(str(value).replace("/", "\\")).name or "来源文件未挂页"


def _source_exists(value: str | None) -> bool:
    if not value:
        return False
    try:
        return Path(str(value)).exists()
    except OSError:
        return False


def _display_text(value: object, limit: int = 900) -> str:
    text = str(value or "").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


def _candidate_state(item: dict, tokens: ThemeTokens) -> tuple[str, str, str]:
    c = tokens.colors
    if item.get("conflicts"):
        return "需复核", c.danger, c.danger_soft
    if item.get("missing_conditions"):
        return "待补条件", c.warning, c.warning_soft
    if item.get("match_reasons"):
        return "条件匹配", c.success, c.success_soft
    return "候选", c.text_secondary, c.subtle


def candidate_copy_lines(items: list[dict]) -> str:
    """Tab-separated candidate rows: 编码\\t名称\\t单位, not a pricing result."""
    lines = []
    for item in items:
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        lines.append("\t".join((code, str(item.get("title") or "").strip(), _unit(item))))
    return "\n".join(lines)


# Kept for callers saved by earlier builds. The UI no longer calls this a
# pricing format because the product has no quantity, price or fee model.
pricing_lines = candidate_copy_lines


def item_markdown(item: dict, kind: str) -> str:
    lines = [f"- 编码：{item.get('code') or '未确认'}", f"  名称：{item.get('title') or '未命名'}", f"  单位：{_unit(item) or '未标注'}", f"  专业：{discipline_label(item.get('discipline'))} · 版本：{_edition(item) or '未标注'}"]
    if item.get("pdf_page"):
        lines.append(f"  页码：第 {item['pdf_page']} 页")
    for label, key in (("项目特征", "characteristics"), ("工程量计算规则", "calculation_rule"), ("工作内容", "work_content"), ("适用条件", "condition_text")):
        value = item.get(key)
        if value:
            lines.append(f"  {label}：{_display_text(value, 400)}")
    if kind == "link" and item.get("factor") is not None:
        lines.append(f"  关联系数：{item['factor']}（来自清单 {item.get('bill_code') or '未标注'}）")
    if item.get("match_reasons"):
        lines.append(f"  命中原因：{'；'.join(item['match_reasons'])}")
    if item.get("conflicts"):
        lines.append(f"  冲突提示：{'；'.join(item['conflicts'])}")
    return "\n".join(lines)


def result_markdown(result: dict, selections: dict | None = None, ai_text: str | None = None) -> str:
    lines = ["# 本地检索记录", ""]
    lines.append(f"- 查询：{result.get('query') or ''}")
    lines.append(f"- 定额版本：山东 {result.get('quota_edition') or '-'} · 清单依据：山东 {result.get('standard_edition') or '-'}")
    timing = result.get("timing") or {}
    if timing.get("local_ms") is not None:
        lines.append(f"- 本地检索耗时：{timing['local_ms']:g}ms")
    selections = selections or {}
    primary = selections.get("primary") or {}
    if primary:
        lines.append("")
        lines.append("## 已暂存候选")
        for key, label in (("bill", "清单候选"), ("quota", "定额候选")):
            item = primary.get(key)
            if item:
                lines.append(f"- {label}：{item.get('code', '')} {item.get('title', '')}（{item.get('unit') or '单位未标注'}）")
    for group, title, kind in (("bills", "清单候选", "bill"), ("quotas", "定额候选", "quota"), ("links", "关联定额", "link"), ("guidance", "规则与换算", "guidance")):
        items = result.get(group) or []
        if not items:
            continue
        lines.append("")
        lines.append(f"## {title}")
        for item in items:
            ref = f"[{item.get('reference')}] " if item.get("reference") else ""
            lines.append(f"{ref}{item_markdown(item, kind)}")
    if ai_text:
        lines.append("")
        lines.append("## AI 解释（仅供参考，需人工复核）")
        lines.append("")
        lines.append(ai_text.strip())
    lines.append("")
    lines.append("---")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


class CandidateRow(ctk.CTkFrame):
    def __init__(self, master, *, tokens: ThemeTokens, item: dict, kind: str, on_set_primary=None, **kwargs):
        self.tokens = tokens
        self.item = item
        self.kind = kind
        self.on_set_primary = on_set_primary
        self.is_primary = False
        self.link_focused = False
        self._labels: list[ctk.CTkLabel] = []
        self._detail_labels: list[ctk.CTkLabel] = []
        self._details_visible = False
        self._detail_frame: ctk.CTkFrame | None = None
        self._wrap_width = 0
        self._images: dict[str, ctk.CTkImage] = {}
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build()

    def _label(self, master, **kwargs):
        label = ctk.CTkLabel(master, **kwargs)
        self._labels.append(label)
        return label

    def _icon(self, name: str, color: str | None = None) -> ctk.CTkImage | None:
        color = color or self.tokens.colors.text_secondary
        key = f"{name}:{color}"
        if key not in self._images:
            path = resource_path("assets", "icons", f"{name}.svg")
            if not path.exists():
                return None
            try:
                self._images[key] = svg_image(path, (16, 16), color=color)
            except Exception:
                return None
        return self._images.get(key)

    def _build(self) -> None:
        c = self.tokens.colors
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        code = self.item.get("code") or "未确认"
        if self.item.get("reference"):
            code = f"[{self.item['reference']}]  {code}"
        self.code_label = self._label(self, text=code, text_color=c.accent, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="w")
        self.code_label.grid(row=0, column=0, padx=(14, 12), pady=(11, 0), sticky="nw")
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.grid(row=0, column=1, padx=(0, 10), pady=(10, 0), sticky="ew")
        title_row.grid_columnconfigure(0, weight=1)
        self.title_label = self._label(title_row, text=self.item.get("title") or "未命名候选", text_color=c.text, font=self.tokens.font(self.tokens.typography.body, "medium"), anchor="w", justify="left", wraplength=400)
        self.title_label.grid(row=0, column=0, sticky="ew")
        self.primary_badge = self._label(title_row, text="已暂存", text_color=c.accent, font=self.tokens.font(self.tokens.typography.caption, "bold"), anchor="e")
        confidence = self.item.get("confidence")
        confidence_text = f"置信度 {float(confidence):.0%}" if isinstance(confidence, (int, float)) else ""
        details = [x for x in (_edition(self.item), discipline_label(self.item.get("discipline")), _unit(self.item), confidence_text, f"第 {self.item.get('pdf_page')} 页" if self.item.get("pdf_page") else "来源页未挂载") if x]
        if self.kind == "link" and self.item.get("factor") is not None:
            details.append(f"系数 {self.item.get('factor')}")
        state_text, _state_color, _state_surface = _candidate_state(self.item, self.tokens)
        self.code_label.grid_configure(rowspan=2)
        self.meta_label = self._label(self, text=" · ".join([state_text, *details]), text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.meta), anchor="w")
        self.meta_label.grid(row=1, column=1, padx=(0, 10), pady=(5, 11), sticky="ew")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=0, column=2, rowspan=2, padx=(0, 8), pady=5, sticky="ne")
        self.detail_button = IconButton(actions, tokens=self.tokens, image=self._icon("chevron-down"), tooltip="展开依据", command=self._toggle_details)
        self.detail_button.pack(side="left")
        self.full_copy_button = IconButton(actions, tokens=self.tokens, image=self._icon("clipboard"), tooltip="复制整条", command=self._copy_full)
        self.full_copy_button.pack(side="left")
        self.copy_button = IconButton(actions, tokens=self.tokens, image=self._icon("copy"), tooltip="复制编码", command=self._copy_code)
        self.copy_button.pack(side="left")
        if self.on_set_primary and self.kind in {"bill", "quota"}:
            self.primary_button = DSButton(actions, tokens=self.tokens, text="暂存", variant="ghost", width=58, height=30, command=self._set_primary)
            self.primary_button.pack(side="left", padx=(2, 0))
        else:
            self.primary_button = None
        self.actions = actions

        self.divider = ctk.CTkFrame(self, height=1, fg_color=c.border)
        self.divider.grid(row=3, column=0, columnspan=3, padx=12, sticky="ew")

    def _set_primary(self) -> None:
        if self.on_set_primary:
            self.on_set_primary(self.kind, self.item, self)

    def set_primary_state(self, is_primary: bool) -> None:
        self.is_primary = is_primary
        if is_primary:
            self.primary_badge.grid(row=0, column=1, sticky="e", padx=(8, 0))
            self.configure(fg_color=self.tokens.colors.accent_soft)
        else:
            self.primary_badge.grid_remove()
            self.configure(fg_color="transparent")

    def _build_details(self) -> None:
        c = self.tokens.colors
        if self._detail_frame is None:
            return
        details: list[tuple[str, str]] = []
        if self.kind == "bill":
            details.extend((("项目特征", self.item.get("characteristics", "")), ("工程量计算规则", self.item.get("calculation_rule", "")), ("工作内容", self.item.get("work_content", ""))))
        elif self.kind == "quota":
            details.extend((("工作内容", self.item.get("work_content", "")), ("人材机", "；".join(self.item.get("resources") or []))))
        elif self.kind == "link":
            details.extend((("关联清单", f"{self.item.get('bill_code') or '未标注'}  {self.item.get('bill_title') or ''}"), ("适用条件", self.item.get("condition_text", ""))))
        else:
            details.extend((("规则名称", self.item.get("rule_title") or self.item.get("title") or ""), ("规则说明", self.item.get("rule_text") or "")))
        if self.item.get("match_reasons"):
            details.append(("命中原因", "；".join(self.item["match_reasons"])))
        if self.item.get("missing_conditions"):
            details.append(("待补条件", "；".join(self.item["missing_conditions"])))
        if self.item.get("conflicts"):
            details.append(("冲突提示", "；".join(self.item["conflicts"])))
        if self.item.get("remark") and self.kind in {"bill", "quota"}:
            details.append(("备注", self.item["remark"]))
        if self.kind == "bill":
            edition_text = f"清单 {self.item.get('edition') or '未标注'}"
        elif self.kind == "link":
            edition_text = f"清单 {self.item.get('standard_edition') or self.item.get('edition') or '未标注'} · 定额 {self.item.get('quota_edition') or '未标注'}"
        else:
            edition_text = f"定额 {self.item.get('edition') or '未标注'}"
        details.append(("依据", f"{edition_text} · {_source_name(self.item.get('source_path'))}"))
        for name, value in details:
            value = _display_text(value)
            if not value:
                continue
            row = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(10 if not self._detail_labels else 0, 8))
            row.grid_columnconfigure(1, weight=1)
            label = ctk.CTkLabel(row, text=name, width=100, text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="nw")
            label.grid(row=0, column=0, padx=(0, 10), sticky="nw")
            value_label = ctk.CTkLabel(row, text=value, text_color=c.text, font=self.tokens.font(self.tokens.typography.meta), anchor="nw", justify="left", wraplength=400)
            value_label.grid(row=0, column=1, sticky="ew")
            self._detail_labels.extend((label, value_label))
        source_path = self.item.get("source_path")
        if _source_exists(source_path):
            open_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
            open_row.pack(fill="x", padx=14, pady=(0, 10))
            page = self.item.get("pdf_page")
            caption = f"打开来源（第 {page} 页）" if page else "打开来源文件"
            open_button = DSButton(open_row, tokens=self.tokens, text=caption, variant="secondary", width=170, height=30, command=lambda: self._open_source(str(source_path)))
            open_button.pack(anchor="w")

    def _open_source(self, path: str) -> None:
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            pass

    def _ensure_details(self) -> None:
        if self._detail_frame is not None:
            return
        self._detail_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._build_details()
        self._detail_frame.grid(row=2, column=0, columnspan=3, padx=12, pady=(0, 9), sticky="ew")
        if self._wrap_width:
            self._apply_wraplength(self._wrap_width)

    def _toggle_details(self) -> None:
        self._details_visible = not self._details_visible
        if self._details_visible:
            self._ensure_details()
            self._detail_frame.grid()
            self.detail_button.configure(image=self._icon("chevron-up"))
            self.detail_button.tooltip = "收起依据"
        else:
            self._detail_frame.grid_remove()
            self.detail_button.configure(image=self._icon("chevron-down"))
            self.detail_button.tooltip = "展开依据"

    def _copy_code(self) -> None:
        code = str(self.item.get("code") or "").strip()
        if not code:
            return
        self._copy(code, self.copy_button)

    def _copy_full(self) -> None:
        lines = [
            f"引用：[{self.item.get('reference')}]" if self.item.get("reference") else "",
            f"编码：{self.item.get('code') or '未确认'}",
            f"名称：{self.item.get('title') or '未命名候选'}",
            f"单位：{_unit(self.item) or '未标注'}",
            f"专业：{discipline_label(self.item.get('discipline'))}",
            f"版本：{_edition(self.item) or '未标注'}",
        ]
        for label, key in (("项目特征", "characteristics"), ("工程量计算规则", "calculation_rule"), ("工作内容", "work_content"), ("适用条件", "condition_text"), ("人材机", "resources")):
            value = self.item.get(key)
            if isinstance(value, list):
                value = "；".join(value)
            if value:
                lines.append(f"{label}：{value}")
        if self.item.get("match_reasons"):
            lines.append(f"命中原因：{'；'.join(self.item['match_reasons'])}")
        if self.item.get("missing_conditions"):
            lines.append(f"待补条件：{'；'.join(self.item['missing_conditions'])}")
        if self.item.get("conflicts"):
            lines.append(f"冲突提示：{'；'.join(self.item['conflicts'])}")
        self._copy("\n".join(line for line in lines if line), self.full_copy_button)

    def _copy(self, text: str, button: DSButton) -> None:
        try:
            root = self.winfo_toplevel()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update_idletasks()
            original = "clipboard" if button is self.full_copy_button else "copy"
            button.configure(image=self._icon("check", self.tokens.colors.success), fg_color=self.tokens.colors.success_soft)
            old_tooltip = button.tooltip
            button.tooltip = "已复制"
            self.after(1100, lambda: self._restore_copy_button(button, original, old_tooltip))
        except tk.TclError:
            pass

    def _restore_copy_button(self, button: IconButton, icon_name: str, tooltip: str) -> None:
        if not self.winfo_exists():
            return
        button.configure(image=self._icon(icon_name), fg_color="transparent")
        button.tooltip = tooltip

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self._images.clear()
        if self.is_primary:
            self.configure(fg_color=c.accent_soft)
        elif self.link_focused:
            self.configure(fg_color=c.success_soft)
        else:
            self.configure(fg_color="transparent")
        self.code_label.configure(text_color=c.accent, font=tokens.font(tokens.typography.meta, "semibold"))
        self.title_label.configure(text_color=c.text, font=tokens.font(tokens.typography.body, "medium"))
        self.primary_badge.configure(text_color=c.accent, font=tokens.font(tokens.typography.caption, "bold"))
        self.meta_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.meta))
        if self._detail_frame is not None:
            self._detail_frame.configure(fg_color="transparent")
        self.divider.configure(fg_color=c.border)
        for index, label in enumerate(self._detail_labels):
            label.configure(text_color=c.text_secondary if index % 2 == 0 else c.text, font=tokens.font(tokens.typography.meta, "semibold" if index % 2 == 0 else "regular"))
        self.detail_button.apply_theme(tokens)
        self.copy_button.apply_theme(tokens)
        self.full_copy_button.apply_theme(tokens)
        if self.primary_button is not None:
            self.primary_button.apply_theme(tokens)
        self.detail_button.configure(image=self._icon("chevron-up" if self._details_visible else "chevron-down"))
        self.copy_button.configure(image=self._icon("copy"))
        self.full_copy_button.configure(image=self._icon("clipboard"))

    def set_wraplength(self, width: int) -> None:
        width = max(320, width)
        if width == self._wrap_width:
            return
        self._wrap_width = width
        self._apply_wraplength(width)

    def _apply_wraplength(self, width: int) -> None:
        self.title_label.configure(wraplength=max(240, width - 300))
        for index, label in enumerate(self._detail_labels):
            if index % 2 == 1:
                label.configure(wraplength=max(240, width - 160))


class CandidateSection(ctk.CTkFrame):
    INITIAL_ROWS = 2
    ROW_BATCH = 3

    def __init__(self, master, *, tokens: ThemeTokens, title: str, items: list[dict], kind: str, total_count: int | None = None, empty_text: str = "没有可靠命中", on_set_primary=None, **kwargs):
        self.tokens = tokens
        self.items = items
        self.kind = kind
        self.on_set_primary = on_set_primary
        self.total_count = total_count if total_count is not None else len(items)
        self.rows: list[CandidateRow] = []
        self._visible_count = 0
        self._wrap_width = 0
        self.more_button: DSButton | None = None
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build(title, empty_text)

    def _build(self, title: str, empty_text: str) -> None:
        c = self.tokens.colors
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 3))
        self.title_label = ctk.CTkLabel(header, text=title, text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="w")
        self.title_label.pack(side="left")
        self.count_label = ctk.CTkLabel(header, text="", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="e")
        self.count_label.pack(side="right")
        if not self.items:
            self.empty_label = ctk.CTkLabel(self, text=empty_text, text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.meta), anchor="w")
            self.empty_label.pack(fill="x", padx=12, pady=(4, 12))
            return
        self.rows_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.rows_frame.pack(fill="x")
        self._render_until(min(self.INITIAL_ROWS, len(self.items)))
        if self._visible_count < len(self.items):
            self.more_button = DSButton(
                self,
                tokens=self.tokens,
                text=self._more_button_text(),
                variant="ghost",
                width=116,
                height=34,
                command=self._show_more,
            )
            self.more_button.pack(anchor="w", padx=12, pady=(5, 8))
        self._update_count()

    def _render_until(self, count: int) -> None:
        for item in self.items[self._visible_count:count]:
            row = CandidateRow(self.rows_frame, tokens=self.tokens, item=item, kind=self.kind, on_set_primary=self.on_set_primary)
            row.pack(fill="x")
            if self._wrap_width:
                row.set_wraplength(self._wrap_width)
            self.rows.append(row)
        self._visible_count = count

    def _more_button_text(self) -> str:
        return f"再显示 {min(self.ROW_BATCH, len(self.items) - self._visible_count)} 条"

    def _update_count(self) -> None:
        if self._visible_count < self.total_count:
            text = f"显示 {self._visible_count}/{self.total_count}"
        else:
            text = f"共 {self.total_count} 条"
        self.count_label.configure(text=text)

    def _show_more(self) -> None:
        self._render_until(min(len(self.items), self._visible_count + self.ROW_BATCH))
        self._update_count()
        if self.more_button is None:
            return
        if self._visible_count >= len(self.items):
            self.more_button.pack_forget()
        else:
            self.more_button.configure(text=self._more_button_text())

    def clear_primary_badges(self) -> None:
        for row in self.rows:
            row.set_primary_state(False)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.title_label.configure(text_color=c.text_secondary, font=tokens.font(tokens.typography.meta, "semibold"))
        self.count_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        if hasattr(self, "empty_label"):
            self.empty_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.meta))
        if hasattr(self, "rows_frame"):
            self.rows_frame.configure(fg_color="transparent")
        if self.more_button:
            self.more_button.apply_theme(tokens)
        for row in self.rows:
            row.apply_theme(tokens)

    def set_wraplength(self, width: int) -> None:
        if width == self._wrap_width:
            return
        self._wrap_width = width
        for row in self.rows:
            row.set_wraplength(width)


class ResultPanel(ctk.CTkFrame):
    """Local evidence block shown before the AI answer, with primary-selection workflow."""

    def __init__(self, master, *, tokens: ThemeTokens, result: dict, on_primary_changed=None, on_export=None, **kwargs):
        self.tokens = tokens
        self.result = result
        self.on_primary_changed = on_primary_changed
        self.on_export = on_export
        self.sections: list[CandidateSection] = []
        self.primary: dict[str, dict] = {}
        self._wrap_width = 0
        super().__init__(master, fg_color="transparent", border_width=0, corner_radius=0, **kwargs)
        self._build()

    def _build(self) -> None:
        c = self.tokens.colors
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(15, 4))
        self.eyebrow_label = ctk.CTkLabel(header, text="本地候选", text_color=c.accent, font=self.tokens.font(self.tokens.typography.caption, "semibold"), anchor="w")
        self.eyebrow_label.pack(anchor="w")
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x", pady=(2, 0))
        self.title_label = ctk.CTkLabel(title_row, text="候选清单与定额", text_color=c.text, font=self.tokens.font(self.tokens.typography.section, "semibold"), anchor="w")
        self.title_label.pack(side="left")
        export_frame = ctk.CTkFrame(title_row, fg_color="transparent")
        export_frame.pack(side="right")
        self.export_md_button = DSButton(export_frame, tokens=self.tokens, text="导出记录", variant="ghost", width=88, height=28, command=lambda: self._export("markdown"))
        self.export_md_button.pack(side="left", padx=(4, 0))
        self.export_excel_button = DSButton(export_frame, tokens=self.tokens, text="导出表格", variant="ghost", width=88, height=28, command=lambda: self._export("excel"))
        self.export_excel_button.pack(side="left", padx=(4, 0))
        self.copy_pricing_button = DSButton(export_frame, tokens=self.tokens, text="复制候选", variant="ghost", width=88, height=28, command=lambda: self._export("candidate_copy"))
        self.copy_pricing_button.pack(side="left", padx=(4, 0))
        edition = self.result.get("quota_edition") or "-"
        standard = self.result.get("standard_edition") or "-"
        discipline = discipline_label(self.result.get("discipline")) if self.result.get("discipline") else "全部专业"
        self.meta_label = ctk.CTkLabel(header, text=f"山东 {edition} 定额 / {standard} 清单 · {discipline}", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.meta), anchor="w")
        self.meta_label.pack(fill="x", anchor="w", pady=(4, 0))
        self.summary_label = ctk.CTkLabel(self, text=self._count_summary(), text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.meta), anchor="w")
        self.summary_label.pack(fill="x", padx=16, pady=(2, 7))

        self.primary_bar = ctk.CTkFrame(self, fg_color=c.subtle, corner_radius=8)
        self.primary_bar.pack(fill="x", padx=12, pady=(0, 6))
        self.primary_label = ctk.CTkLabel(self.primary_bar, text=self._primary_text(), text_color=c.text, font=self.tokens.font(self.tokens.typography.meta), anchor="w", justify="left", wraplength=440)
        self.primary_label.pack(fill="x", padx=12, pady=7)

        conditions = self._condition_labels()
        if conditions:
            self.condition_bar = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
            self.condition_bar.pack(fill="x", padx=12, pady=(0, 6))
            self.condition_caption = ctk.CTkLabel(self.condition_bar, text="已识别条件", text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.caption, "semibold"), anchor="nw")
            self.condition_caption.pack(side="left", padx=(0, 8), pady=8, anchor="n")
            self.condition_text = ctk.CTkLabel(self.condition_bar, text=" · ".join(conditions), text_color=c.text, font=self.tokens.font(self.tokens.typography.meta), anchor="nw", justify="left", wraplength=400)
            self.condition_text.pack(side="left", fill="x", expand=True, padx=(0, 11), pady=8)
        else:
            self.condition_bar = None
            self.condition_caption = None
            self.condition_text = None

        hints = self.result.get("hints") or []
        if hints:
            self.hints_label = ctk.CTkLabel(self, text="建议补充：" + "；".join(hints), text_color=c.warning, font=self.tokens.font(self.tokens.typography.meta), anchor="w", justify="left", wraplength=440)
            self.hints_label.pack(fill="x", padx=16, pady=(0, 6))
        else:
            self.hints_label = None

        groups = (
            ("清单候选", (self.result.get("bills") or [])[:6], "bill"),
            ("定额候选", (self.result.get("quotas") or [])[:6], "quota"),
            ("关联定额", (self.result.get("links") or [])[:8], "link"),
            ("规则与换算", (self.result.get("guidance") or [])[:6], "guidance"),
        )
        for title, items, kind in groups:
            if not items and kind == "guidance":
                continue
            total = len(self.result.get({"bill": "bills", "quota": "quotas", "link": "links", "guidance": "guidance"}[kind]) or [])
            section = CandidateSection(self, tokens=self.tokens, title=title, items=items, kind=kind, total_count=total, on_set_primary=self._set_primary)
            section.pack(fill="x")
            self.sections.append(section)
        self.footnote = ctk.CTkLabel(self, text=UI_DISCLAIMER, text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w", justify="left", wraplength=440)
        self.footnote.pack(fill="x", padx=16, pady=(8, 14))

    def _export(self, fmt: str) -> None:
        if self.on_export:
            self.on_export(fmt, self)

    def _primary_text(self) -> str:
        bill = (self.primary.get("bill") or {}).get("item")
        quota = (self.primary.get("quota") or {}).get("item")
        parts = []
        if bill:
            parts.append(f"清单暂存：{bill.get('code', '')} {bill.get('title', '')}")
        if quota:
            parts.append(f"定额暂存：{quota.get('code', '')} {quota.get('title', '')}")
        if not parts:
            return "暂存候选：可暂存一条清单和一条定额用于对照；这不是计价成果或正式套项。"
        risks = sum(1 for group in ("bills", "quotas") for item in (self.result.get(group) or [])[:4] if item.get("conflicts"))
        suffix = f" · 有 {risks} 条候选存在条件冲突，导出前请复核" if risks else ""
        return "；".join(parts) + suffix

    def _set_primary(self, kind: str, item: dict, row: CandidateRow) -> None:
        for section in self.sections:
            if section.kind == kind:
                section.clear_primary_badges()
        row.set_primary_state(True)
        self.primary[kind] = {"item": item}
        self.primary_bar.configure(fg_color=self.tokens.colors.accent_soft)
        self.primary_label.configure(text=self._primary_text())
        if kind == "bill":
            self._filter_links_for_bill(str(item.get("code") or ""))
        if self.on_primary_changed:
            self.on_primary_changed(kind, item)

    def _filter_links_for_bill(self, bill_code: str) -> None:
        """P1-5.3: after a bill is chosen, its links stay in focus; others dim."""
        if not bill_code:
            return
        for section in self.sections:
            if section.kind != "link":
                continue
            for link_row in section.rows:
                related = str(link_row.item.get("bill_code") or "").strip()
                link_row.link_focused = related == bill_code
                link_row.configure(fg_color=self.tokens.colors.success_soft if link_row.link_focused else "transparent")

    def selected_items(self) -> list[dict]:
        items = []
        for key in ("bill", "quota"):
            entry = self.primary.get(key)
            if entry:
                items.append(entry["item"])
        return items

    def restore_primary(self, selections: dict | None) -> None:
        """Re-apply persisted primary selections after a session is reloaded."""
        primary = (selections or {}).get("primary") or {}
        for kind in ("bill", "quota"):
            saved = primary.get(kind)
            if not saved:
                continue
            record_id = str(saved.get("record_id") or "").strip()
            code = str(saved.get("code") or "").strip()
            for section in self.sections:
                if section.kind != kind:
                    continue
                for row in section.rows:
                    current_id = str(row.item.get("record_id") or "").strip()
                    # New sessions persist the composite record identity. Keep
                    # the code fallback only for legacy V1 session recovery.
                    if (record_id and current_id == record_id) or (not record_id and str(row.item.get("code") or "").strip() == code):
                        self.primary[kind] = {"item": row.item}
                        row.set_primary_state(True)
                        break
        self.primary_label.configure(text=self._primary_text())

    def pricing_text(self) -> str:
        selected = self.selected_items()
        pool = selected or [*(self.result.get("bills") or [])[:1], *(self.result.get("quotas") or [])[:3], *(self.result.get("links") or [])[:4]]
        return candidate_copy_lines(pool)

    def _count_summary(self) -> str:
        counts = []
        for key, label in (("bills", "清单"), ("quotas", "定额"), ("links", "关联"), ("guidance", "规则")):
            count = len(self.result.get(key) or [])
            if count:
                counts.append(f"{label} {count}")
        timing = self.result.get("timing") or {}
        if timing.get("local_ms") is not None:
            counts.append(f"本地 {timing['local_ms']:g}ms")
        confidence = self.result.get("confidence")
        status_labels = {
            "exact_match": "精确编码命中",
            "candidate_review": "候选可复核",
            "needs_more_conditions": "需补条件",
            "no_reliable_candidate": "无可靠候选",
        }
        if isinstance(confidence, (int, float)):
            counts.append(f"{status_labels.get(self.result.get('decision_status'), '候选状态')} {confidence:.0%}")
        return " · ".join(counts) if counts else "没有找到可靠候选，建议补充规格、深度、土类或运距。"

    def _condition_labels(self) -> list[str]:
        conditions = self.result.get("conditions") or {}
        condition_labels = []
        if conditions.get("object_type"):
            condition_labels.append(str(conditions["object_type"]))
        if conditions.get("soil_type"):
            condition_labels.append(str(conditions["soil_type"]))
        if conditions.get("depth_m") is not None:
            condition_labels.append(f"深度 {conditions['depth_m']:g}m")
        if conditions.get("distance_m") is not None:
            condition_labels.append(f"运距 {conditions['distance_m']:g}m")
        if conditions.get("thickness_mm") is not None:
            condition_labels.append(f"厚度 {conditions['thickness_mm']:g}mm")
        if conditions.get("diameter_mm") is not None:
            condition_labels.append(f"直径 {conditions['diameter_mm']:g}mm")
        if conditions.get("strength_grade"):
            condition_labels.append(str(conditions["strength_grade"]))
        if conditions.get("method"):
            condition_labels.append(f"{conditions['method']}施工")
        return condition_labels

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.configure(fg_color="transparent", border_width=0)
        self.eyebrow_label.configure(text_color=c.accent, font=tokens.font(tokens.typography.caption, "semibold"))
        self.title_label.configure(text_color=c.text, font=tokens.font(tokens.typography.section, "semibold"))
        self.meta_label.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.meta))
        self.summary_label.configure(text_color=c.text_secondary, font=tokens.font(tokens.typography.meta))
        self.primary_bar.configure(fg_color=c.accent_soft if self.primary else c.subtle)
        self.primary_label.configure(text_color=c.text, font=tokens.font(tokens.typography.meta))
        self.export_md_button.apply_theme(tokens)
        self.export_excel_button.apply_theme(tokens)
        self.copy_pricing_button.apply_theme(tokens)
        self.footnote.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        if self.hints_label is not None:
            self.hints_label.configure(text_color=c.warning, font=tokens.font(tokens.typography.meta))
        if self.condition_bar is not None:
            self.condition_bar.configure(fg_color="transparent")
            self.condition_caption.configure(text_color=c.text_secondary, font=tokens.font(tokens.typography.caption, "semibold"))
            self.condition_text.configure(text_color=c.text, font=tokens.font(tokens.typography.meta))
        for section in self.sections:
            section.apply_theme(tokens)

    def set_wraplength(self, width: int) -> None:
        width = max(360, width)
        if width == self._wrap_width:
            return
        self._wrap_width = width
        self.footnote.configure(wraplength=max(320, width - 36))
        self.primary_label.configure(wraplength=max(300, width - 60))
        if self.hints_label is not None:
            self.hints_label.configure(wraplength=max(300, width - 60))
        if self.condition_text is not None:
            self.condition_text.configure(wraplength=max(220, width - 150))
        for section in self.sections:
            section.set_wraplength(width)


class WarningStrip(ctk.CTkFrame):
    def __init__(self, master, *, tokens: ThemeTokens, text: str, action_text: str = "", command=None, **kwargs):
        self.tokens = tokens
        super().__init__(master, fg_color="transparent", border_width=0, corner_radius=0, **kwargs)
        # CTkFrame defaults to 200px tall; keep this document-style strip content-sized.
        body = ctk.CTkFrame(self, fg_color="transparent", height=1)
        body.pack(fill="x", padx=0, pady=8)
        body.grid_columnconfigure(1, weight=1)
        self.rule = ctk.CTkFrame(body, width=2, height=1, fg_color=tokens.colors.warning, corner_radius=0)
        self.rule.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.label = ctk.CTkLabel(body, text=text, text_color=tokens.colors.text_secondary, font=tokens.font(tokens.typography.meta), anchor="w", justify="left", wraplength=440)
        self.label.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self.action_button = None
        if action_text and command:
            self.action_button = DSButton(body, tokens=tokens, text=action_text, variant="ghost", width=88, height=28, corner_radius=7, command=command)
            self.action_button.grid(row=0, column=2, sticky="e")

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        self.configure(fg_color="transparent", border_width=0)
        self.rule.configure(fg_color=tokens.colors.warning)
        self.label.configure(text_color=tokens.colors.text_secondary, font=tokens.font(tokens.typography.meta))
        if self.action_button:
            self.action_button.apply_theme(tokens)

    def set_wraplength(self, width: int) -> None:
        self.label.configure(wraplength=max(260, width - (120 if self.action_button else 24)))
