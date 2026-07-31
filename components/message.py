from __future__ import annotations

import re

import customtkinter as ctk

from themes.tokens import ThemeTokens
from utils.evidence import open_source_page
from utils.lottie import LottiePulse
from utils.paths import resource_path
from .button import DSButton
from .result import ResultPanel, WarningStrip
from .scrollable import PointerScrollableFrame


_AI_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_AI_INLINE_HEADING_RE = re.compile(
    r"^\s*(?:\d{1,2}[.、)]\s*)?"
    r"(结论|推荐方案|建议候选|主选|首选|备选|判断依据|依据|工程量(?:与|及|和)换算|风险(?:提示)?|待确认|待补条件)"
    r"\s*[：:]?\s*(.*)$"
)
_AI_BULLET_RE = re.compile(r"^\s*(?:[-*•▪◦]|\d{1,2}[.、)])\s*")
_AI_REFERENCE_RE = re.compile(r"R(\d+)", re.IGNORECASE)
_AI_REFERENCE_GROUP_RE = re.compile(r"\[\s*R\d+(?:\s*[,，、/]\s*R?\d+)*\s*\]", re.IGNORECASE)
_AI_DISCLAIMER_RE = re.compile(r"^本(?:建议|分析|结果).{0,30}(?:仅供|复核参考).*$")
_AI_SECTION_ALIASES = {
    "推荐方案": "建议候选",
    "主选": "建议候选",
    "首选": "建议候选",
    "判断依据": "依据",
    "工程量及换算": "工程量与换算",
    "工程量和换算": "工程量与换算",
    "风险提示": "风险",
    "待补条件": "待确认",
}
_AI_SECTION_ORDER = ("结论", "建议候选", "备选", "依据", "工程量与换算", "风险", "待确认", "AI 分析")


def _clean_ai_body(value: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in value.replace("\r", "").split("\n"):
        line = raw_line.strip()
        if not line:
            if cleaned_lines and cleaned_lines[-1]:
                cleaned_lines.append("")
            continue
        line = re.sub(r"^>\s*", "", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        if _AI_DISCLAIMER_RE.match(line):
            continue
        if _AI_BULLET_RE.match(line):
            line = "- " + _AI_BULLET_RE.sub("", line).strip()
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    text = re.sub(r"(?<=\])\s*(?=\[R\d+\])", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_ai_heading(value: str) -> str:
    heading = re.sub(r"[*_`]+", "", value).strip().rstrip("：:")
    heading = re.sub(r"^\d{1,2}[.、)]\s*", "", heading)
    return _AI_SECTION_ALIASES.get(heading, heading[:24] or "AI 分析")


def parse_ai_sections(text: str) -> list[tuple[str, str]]:
    """Turn the constrained Markdown response into display-ready sections."""
    sections: list[tuple[str, str]] = []
    current_heading = "AI 分析"
    current_lines: list[str] = []

    def flush() -> None:
        body = _clean_ai_body("\n".join(current_lines))
        empty_check = _AI_BULLET_RE.sub("", body).strip().rstrip("。")
        if body and empty_check not in {"无", "暂无", "不适用"}:
            sections.append((current_heading, body))

    for line in str(text or "").replace("\r", "").split("\n"):
        markdown_heading = _AI_HEADING_RE.match(line)
        inline_heading = _AI_INLINE_HEADING_RE.match(line)
        if markdown_heading or inline_heading:
            flush()
            current_lines = []
            if markdown_heading:
                current_heading = _normalize_ai_heading(markdown_heading.group(1))
            else:
                current_heading = _normalize_ai_heading(inline_heading.group(1))
                if inline_heading.group(2).strip():
                    current_lines.append(inline_heading.group(2).strip())
            continue
        current_lines.append(line)
    flush()
    if not sections:
        return [("AI 分析", "模型未返回可读解释。")]
    merged: dict[str, list[str]] = {}
    for heading, body in sections:
        merged.setdefault(heading, []).append(body)
    order = {heading: index for index, heading in enumerate(_AI_SECTION_ORDER)}
    return [
        (heading, "\n".join(merged[heading]))
        for heading in sorted(merged, key=lambda item: order.get(item, len(order)))
    ]


def parse_ai_items(body: str) -> list[str]:
    """Split a section into scan-friendly statements without Markdown noise."""
    items: list[str] = []
    for raw_line in _clean_ai_body(body).splitlines():
        line = _AI_BULLET_RE.sub("", raw_line).strip()
        if line:
            items.append(line)
    return items or ["暂无可读内容"]


def ai_references(text: str) -> list[str]:
    numbers = sorted({int(value) for value in _AI_REFERENCE_RE.findall(str(text or ""))})
    return [f"R{number}" for number in numbers]


def strip_ai_reference_markers(text: str) -> str:
    """Hide internal evidence IDs from user-facing prose without changing stored text."""
    cleaned = _AI_REFERENCE_GROUP_RE.sub("", str(text or ""))
    cleaned = re.sub(r"\[\s*\]", "", cleaned)
    cleaned = re.sub(r"R\d+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]+([，。；：！？,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"([：:])\s*([。；;])", r"\2", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def evidence_button_text(item: dict) -> str:
    record_type = str(item.get("record_id") or "").partition(":")[0].lower()
    source_label = {
        "bill": "清单原书",
        "quota": "定额原书",
        "link": "关联原书",
        "guidance": "计价规则",
    }.get(record_type, "打开原书")
    page = item.get("pdf_page")
    return f"{source_label} · 第 {page} 页" if page else source_label


def logical_wrap_width(physical_width: int, widget_scaling: float = 1.0) -> int:
    """Convert Tk's physical Configure width back to CTk logical pixels."""
    try:
        scaling = max(1.0, float(widget_scaling))
    except (TypeError, ValueError):
        scaling = 1.0
    logical_width = int(max(0, physical_width - 32) / scaling)
    return max(360, min(960, (logical_width // 8) * 8))


def format_ai_plain_text(sections: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"{heading}：\n{body}" for heading, body in sections)


def _ai_section_tone(heading: str, tokens: ThemeTokens) -> tuple[str, str]:
    c = tokens.colors
    if heading == "建议候选":
        return c.accent, c.accent_soft
    if heading == "风险":
        return c.warning, c.warning_soft
    if heading == "结论":
        return c.accent, c.accent_soft
    return c.text_secondary, c.subtle


class MessageBubble(ctk.CTkFrame):
    def __init__(self, master, *, tokens: ThemeTokens, role: str, text: str, error: bool = False, **kwargs):
        self.tokens = tokens
        self.role = role
        self.error = error
        self.body_text = text.strip()
        self._wraplength = 400
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build()

    def _build(self) -> None:
        c = self.tokens.colors
        is_user = self.role == "user"
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=2, pady=(0, 18))
        row.grid_columnconfigure(0, weight=1)
        bubble_color = c.user_surface if is_user else (c.danger_soft if self.error else "transparent")
        text_color = c.user_text if is_user else (c.danger if self.error else c.text)
        bubble = ctk.CTkFrame(row, fg_color=bubble_color, border_color=c.danger if self.error else c.border, border_width=1 if self.error else 0, corner_radius=self.tokens.radius_md)
        bubble.grid(row=0, column=0, sticky="e" if is_user else "ew")
        if not is_user:
            bubble.grid_configure(sticky="ew")
        self.heading = None
        if self.error:
            self.heading = ctk.CTkLabel(bubble, text="连接提示", text_color=c.danger, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="w")
            self.heading.pack(fill="x", padx=15, pady=(10, 1))
        self.body = ctk.CTkLabel(bubble, text=self.body_text, text_color=text_color, font=self.tokens.font(self.tokens.typography.body), justify="right" if is_user else "left", anchor="e" if is_user else "w", wraplength=self._wraplength)
        self.body.pack(fill="x", padx=15 if is_user or self.error else 2, pady=(10 if is_user and not self.error else 3, 11 if is_user or self.error else 2))
        self._row, self._bubble = row, bubble

    def set_wraplength(self, width: int) -> None:
        self._wraplength = max(360, min(900, width))
        self.body.configure(wraplength=self._wraplength)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        is_user = self.role == "user"
        c = tokens.colors
        self._row.configure(fg_color="transparent")
        self._bubble.configure(fg_color=c.user_surface if is_user else (c.danger_soft if self.error else "transparent"), border_color=c.danger if self.error else c.border)
        if self.heading is not None:
            self.heading.configure(text_color=c.danger, font=tokens.font(tokens.typography.meta, "semibold"))
        self.body.configure(text_color=c.user_text if is_user else (c.danger if self.error else c.text), font=tokens.font(tokens.typography.body))


class AiAnswerCard(ctk.CTkFrame):
    """Structured AI answer with catalog validation and optional source-page actions."""

    def __init__(self, master, *, tokens: ThemeTokens, text: str, validation: dict | None = None, on_copy=None, **kwargs):
        self.tokens = tokens
        self.text = text
        self.sections = parse_ai_sections(text)
        self.display_sections = [
            (heading, strip_ai_reference_markers(body))
            for heading, body in self.sections
        ]
        self.validation = validation or {}
        self.on_copy = on_copy
        self._wraplength = 400
        self._section_records: list[dict] = []
        self._section_dividers: list[ctk.CTkFrame] = []
        self._warning_records: list[tuple[ctk.CTkLabel, ctk.CTkLabel]] = []
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build()

    def _build(self) -> None:
        c = self.tokens.colors
        self.shell = ctk.CTkFrame(self, fg_color=c.surface, border_width=0, corner_radius=self.tokens.radius_md)
        self.shell.pack(fill="x", padx=2, pady=(0, 18))
        self.header = ctk.CTkFrame(self.shell, fg_color="transparent")
        self.header.pack(fill="x", padx=18, pady=(15, 10))
        heading_group = ctk.CTkFrame(self.header, fg_color="transparent")
        heading_group.pack(side="left", fill="x", expand=True)
        self.heading = ctk.CTkLabel(heading_group, text="AI 套价结论", text_color=c.text, font=self.tokens.font(self.tokens.typography.section, "semibold"), anchor="w")
        self.heading.pack(anchor="w")
        self.subheading = ctk.CTkLabel(heading_group, text="结构化方案已通过本地资料校验", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w")
        self.subheading.pack(anchor="w", pady=(3, 0))
        self.copy_button = DSButton(self.header, tokens=self.tokens, text="复制全部", variant="ghost", width=78, height=30, command=self._copy)
        self.copy_button.pack(side="right")
        for index, (section_heading, section_body) in enumerate(self.display_sections):
            is_summary = section_heading == "结论"
            tone, surface = _ai_section_tone(section_heading, self.tokens)
            section = ctk.CTkFrame(
                self.shell,
                fg_color=surface if is_summary else "transparent",
                corner_radius=self.tokens.radius_sm if is_summary else 0,
            )
            section.pack(fill="x", padx=18, pady=(2 if index else 0, 8 if is_summary else 4))
            section.grid_columnconfigure(1, weight=1)
            rule = ctk.CTkFrame(section, width=3, height=1, fg_color=tone, corner_radius=0)
            rule.grid(row=0, column=0, rowspan=8, sticky="ns", padx=(0, 11), pady=10 if is_summary else 4)
            section_title = ctk.CTkLabel(section, text=section_heading, text_color=tone, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="w")
            section_title.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(10 if is_summary else 3, 3))
            item_records: list[tuple[ctk.CTkLabel | None, ctk.CTkLabel]] = []
            section_items = parse_ai_items(section_body)
            for row_index, item_text in enumerate(section_items, start=1):
                if is_summary:
                    bullet = None
                    body_label = ctk.CTkLabel(section, text=item_text, text_color=c.text, font=self.tokens.font(self.tokens.typography.body, "semibold"), justify="left", anchor="w", wraplength=self._wraplength - 54)
                    body_label.grid(row=row_index, column=1, sticky="ew", padx=(0, 12), pady=(1, 9 if row_index == len(section_items) else 3))
                else:
                    item_row = ctk.CTkFrame(section, fg_color="transparent", corner_radius=0)
                    item_row.grid(row=row_index, column=1, sticky="ew", padx=(0, 8), pady=(1, 5))
                    item_row.grid_columnconfigure(1, weight=1)
                    bullet = ctk.CTkLabel(item_row, text="•", width=14, text_color=tone, font=self.tokens.font(self.tokens.typography.body, "semibold"), anchor="nw")
                    bullet.grid(row=0, column=0, sticky="nw", padx=(0, 6))
                    body_label = ctk.CTkLabel(item_row, text=item_text, text_color=c.text, font=self.tokens.font(self.tokens.typography.body), justify="left", anchor="w", wraplength=self._wraplength - 70)
                    body_label.grid(row=0, column=1, sticky="ew")
                item_records.append((bullet, body_label))
            divider = ctk.CTkFrame(self.shell, height=1, fg_color=c.border, corner_radius=0)
            if index < len(self.sections) - 1:
                divider.pack(fill="x", padx=18, pady=(3, 5))
                self._section_dividers.append(divider)
            self._section_records.append({"frame": section, "title": section_title, "items": item_records, "rule": rule, "heading": section_heading, "summary": is_summary})
        warnings = self.validation.get("warnings") or []
        if warnings:
            self.warning_frame = ctk.CTkFrame(self.shell, fg_color=c.warning_soft, corner_radius=self.tokens.radius_sm)
            self.warning_frame.pack(fill="x", padx=18, pady=(7, 8))
            warning_title = ctk.CTkLabel(self.warning_frame, text="复核提醒", text_color=c.warning, font=self.tokens.font(self.tokens.typography.meta, "semibold"), anchor="w")
            warning_title.pack(fill="x", padx=12, pady=(9, 2))
            for warning in warnings:
                warning_label = ctk.CTkLabel(self.warning_frame, text=strip_ai_reference_markers(warning), text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.meta), justify="left", anchor="w", wraplength=self._wraplength - 48)
                warning_label.pack(fill="x", padx=12, pady=(1, 8))
                self._warning_records.append((warning_title, warning_label))
        else:
            self.warning_frame = None
        self.footer = ctk.CTkFrame(self.shell, fg_color="transparent")
        self.footer.pack(fill="x", padx=18, pady=(4, 13))
        located = int(self.validation.get("evidence_located") or 0)
        catalog_verified = bool(self.validation.get("catalog_verified") or self.validation.get("structured_valid"))
        if self.validation.get("source_review_required"):
            reference_text = "本地结构化资料已校验 · 建议重点复核"
            self.reference_tone = "warning"
        elif located:
            reference_text = "本地结构化资料已校验 · 原书页可查看"
            self.reference_tone = "success"
        elif catalog_verified:
            reference_text = "本地结构化资料已校验"
            self.reference_tone = "success"
        else:
            reference_text = "本地候选待确认"
            self.reference_tone = "warning"
        reference_color = getattr(c, self.reference_tone)
        self.reference_label = ctk.CTkLabel(self.footer, text=reference_text, text_color=reference_color, font=self.tokens.font(self.tokens.typography.caption, "semibold"), anchor="w")
        self.reference_label.pack(anchor="w")
        self.evidence_actions = ctk.CTkFrame(self.footer, fg_color="transparent")
        self.evidence_buttons: list[DSButton] = []
        action_row = None
        visible_sources: set[tuple[str, object]] = set()
        for item in self.validation.get("evidence") or []:
            if not item.get("located"):
                continue
            source_key = (str(item.get("source_path") or item.get("source_name") or ""), item.get("pdf_page"))
            if source_key in visible_sources:
                continue
            visible_sources.add(source_key)
            if action_row is None or len(self.evidence_buttons) % 3 == 0:
                action_row = ctk.CTkFrame(self.evidence_actions, fg_color="transparent")
                action_row.pack(fill="x")
            button = DSButton(
                action_row,
                tokens=self.tokens,
                text=evidence_button_text(item),
                variant="ghost",
                width=156,
                height=28,
                command=lambda current=item: open_source_page(current.get("source_path"), current.get("pdf_page")),
            )
            button.pack(side="left", padx=(0, 6), pady=(5, 0))
            self.evidence_buttons.append(button)
        if self.evidence_actions.winfo_children():
            self.evidence_actions.pack(fill="x")
        self.footnote = ctk.CTkLabel(self.footer, text="普通套项以本地结构化资料为依据；换算、系数或争议项建议结合原书和项目条件复核。", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption), anchor="w", justify="left", wraplength=self._wraplength)
        self.footnote.pack(fill="x", pady=(4, 0))

    def _copy(self) -> None:
        if self.on_copy:
            self.on_copy(format_ai_plain_text(self.display_sections))

    def set_wraplength(self, width: int) -> None:
        self._wraplength = max(360, min(900, width))
        for record in self._section_records:
            offset = 54 if record["summary"] else 70
            for _bullet, body in record["items"]:
                body.configure(wraplength=max(280, self._wraplength - offset))
        self.footnote.configure(wraplength=self._wraplength)
        for _title, warning in self._warning_records:
            warning.configure(wraplength=max(280, self._wraplength - 48))

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.shell.configure(fg_color=c.surface, border_color=c.border)
        self.header.configure(fg_color="transparent")
        self.heading.configure(text_color=c.text, font=tokens.font(tokens.typography.section, "semibold"))
        self.subheading.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        for record in self._section_records:
            tone, surface = _ai_section_tone(record["heading"], tokens)
            record["frame"].configure(fg_color=surface if record["summary"] else "transparent")
            record["title"].configure(text_color=tone, font=tokens.font(tokens.typography.meta, "semibold"))
            record["rule"].configure(fg_color=tone)
            for bullet, body in record["items"]:
                if bullet is not None:
                    bullet.configure(text_color=tone, font=tokens.font(tokens.typography.body, "semibold"))
                body.configure(text_color=c.text, font=tokens.font(tokens.typography.body, "semibold" if record["summary"] else "regular"))
        for divider in self._section_dividers:
            divider.configure(fg_color=c.border)
        self.footer.configure(fg_color="transparent")
        self.evidence_actions.configure(fg_color="transparent")
        self.reference_label.configure(text_color=getattr(c, self.reference_tone), font=tokens.font(tokens.typography.caption, "semibold"))
        for row in self.evidence_actions.winfo_children():
            row.configure(fg_color="transparent")
        for button in self.evidence_buttons:
            button.apply_theme(tokens)
        self.footnote.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))
        if self.warning_frame is not None:
            self.warning_frame.configure(fg_color=c.warning_soft)
            for title, warning in self._warning_records:
                title.configure(text_color=c.warning, font=tokens.font(tokens.typography.meta, "semibold"))
                warning.configure(text_color=c.text_secondary, font=tokens.font(tokens.typography.meta))
        self.copy_button.apply_theme(tokens)


class AiThinkingCard(ctk.CTkFrame):
    """Prominent in-feed state while AI turns local evidence into a conclusion."""

    def __init__(self, master, *, tokens: ThemeTokens, **kwargs):
        self.tokens = tokens
        self._wraplength = 400
        super().__init__(master, fg_color="transparent", **kwargs)
        c = tokens.colors
        self.shell = ctk.CTkFrame(self, fg_color=c.subtle, border_width=0, corner_radius=tokens.radius_sm)
        self.shell.pack(fill="x", padx=2, pady=(0, 18))
        self.row = ctk.CTkFrame(self.shell, fg_color="transparent")
        self.row.pack(fill="x", padx=18, pady=15)
        self.pulse = LottiePulse(
            self.row,
            asset=resource_path("assets", "animations", "analysis-pulse.json"),
            color=c.accent,
            background=c.subtle,
        )
        self.pulse.pack(side="left", padx=(0, 10))
        copy = ctk.CTkFrame(self.row, fg_color="transparent")
        copy.pack(side="left", fill="x", expand=True)
        self.heading = ctk.CTkLabel(copy, text="AI 正在分析", text_color=c.text, font=tokens.font(tokens.typography.section, "semibold"), anchor="w")
        self.heading.pack(anchor="w")
        self.detail = ctk.CTkLabel(copy, text="正在核对清单、定额和本地关联", text_color=c.text_muted, font=tokens.font(tokens.typography.caption), anchor="w")
        self.detail.pack(anchor="w", pady=(3, 0))
        self.pulse.start()

    def set_wraplength(self, width: int) -> None:
        self._wraplength = max(320, width)
        self.detail.configure(wraplength=max(280, self._wraplength - 80))

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        c = tokens.colors
        self.shell.configure(fg_color=c.subtle)
        self.row.configure(fg_color="transparent")
        self.pulse.apply_theme(c.accent, c.subtle)
        self.heading.configure(text_color=c.text, font=tokens.font(tokens.typography.section, "semibold"))
        self.detail.configure(text_color=c.text_muted, font=tokens.font(tokens.typography.caption))

    def destroy(self) -> None:
        self.pulse.stop()
        super().destroy()


class MessageFeed(PointerScrollableFrame):
    def __init__(self, master, *, tokens: ThemeTokens, **kwargs):
        self.tokens = tokens
        self.messages: list[MessageBubble] = []
        self.entries: list[ctk.CTkWidget] = []
        self._resize_job: str | None = None
        self._pending_wrap_width = 0
        self._wrap_width = 0
        super().__init__(master, fg_color=tokens.colors.background, scrollbar_button_color=tokens.colors.border, scrollbar_button_hover_color=tokens.colors.border_strong, **kwargs)
        self.bind("<Configure>", self._schedule_resize, add="+")

    def add(self, role: str, text: str, *, error: bool = False) -> MessageBubble:
        bubble = MessageBubble(self, tokens=self.tokens, role=role, text=text, error=error)
        bubble.pack(fill="x", expand=True)
        self.messages.append(bubble)
        self.entries.append(bubble)
        self._apply_wrap_to_entry(bubble)
        self.after_idle(self._scroll_end)
        return bubble

    def add_result(self, result: dict, on_primary_changed=None, on_export=None, on_clarify=None, *, collapsed: bool = True) -> ResultPanel:
        panel = ResultPanel(self, tokens=self.tokens, result=result, on_primary_changed=on_primary_changed, on_export=on_export, on_clarify=on_clarify, collapsed=collapsed)
        panel.pack(fill="x", padx=5, pady=(0, 16))
        self.entries.append(panel)
        self._apply_wrap_to_entry(panel)
        self.after_idle(lambda: self._scroll_to_widget(panel))
        return panel

    def add_ai_thinking(self, *, before=None) -> AiThinkingCard:
        card = AiThinkingCard(self, tokens=self.tokens)
        if before is not None and before in self.entries and before.winfo_exists():
            card.pack(fill="x", padx=5, pady=(0, 16), before=before)
            self.entries.insert(self.entries.index(before), card)
        else:
            card.pack(fill="x", padx=5, pady=(0, 16))
            self.entries.append(card)
        self._apply_wrap_to_entry(card)
        self.after_idle(lambda: self._scroll_to_widget(card))
        return card

    def remove_entry(self, entry) -> None:
        if entry is None:
            return
        if entry in self.entries:
            self.entries.remove(entry)
        if entry in self.messages:
            self.messages.remove(entry)
        try:
            entry.destroy()
        except Exception:
            pass

    def add_ai_answer(self, text: str, validation: dict | None = None, on_copy=None, before=None) -> AiAnswerCard | ResultPanel:
        if isinstance(before, ResultPanel):
            sections = [
                (heading, strip_ai_reference_markers(body))
                for heading, body in parse_ai_sections(text)
            ]
            copy_text = format_ai_plain_text(sections)
            if before.attach_ai_analysis(sections, validation, on_copy=on_copy, copy_text=copy_text):
                self._apply_wrap_to_entry(before)
                self.after_idle(lambda: self._scroll_to_widget(before))
                return before
        card = AiAnswerCard(self, tokens=self.tokens, text=text, validation=validation, on_copy=on_copy)
        if before is not None and before in self.entries and before.winfo_exists():
            card.pack(fill="x", padx=5, pady=(0, 16), before=before)
            self.entries.insert(self.entries.index(before), card)
        else:
            card.pack(fill="x", padx=5, pady=(0, 16))
            self.entries.append(card)
        self._apply_wrap_to_entry(card)
        self.after_idle(lambda: self._scroll_to_widget(card))
        return card

    def add_warning(self, text: str, *, action_text: str = "", command=None, before=None) -> WarningStrip:
        warning = WarningStrip(self, tokens=self.tokens, text=text, action_text=action_text, command=command)
        if before is not None and before in self.entries and before.winfo_exists():
            warning.pack(fill="x", padx=5, pady=(0, 16), before=before)
            self.entries.insert(self.entries.index(before), warning)
        else:
            warning.pack(fill="x", padx=5, pady=(0, 16))
            self.entries.append(warning)
        self._apply_wrap_to_entry(warning)
        if before is None:
            self.after_idle(self._scroll_end)
        return warning

    def _schedule_resize(self, event=None) -> None:
        physical_width = event.width if event else self.winfo_width()
        try:
            widget_scaling = max(1.0, float(ctk.ScalingTracker.get_widget_scaling(self)))
        except (AttributeError, TypeError, ValueError):
            widget_scaling = 1.0
        self._pending_wrap_width = logical_wrap_width(physical_width, widget_scaling)
        if self._pending_wrap_width == self._wrap_width:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._resize_messages)

    def _resize_messages(self) -> None:
        self._resize_job = None
        width = self._pending_wrap_width
        if width == self._wrap_width:
            return
        self._wrap_width = width
        for entry in self.entries:
            self._apply_wrap_to_entry(entry)

    def _apply_wrap_to_entry(self, entry) -> None:
        if not self._wrap_width or not hasattr(entry, "set_wraplength"):
            return
        entry.set_wraplength(self._wrap_width)

    def _scroll_end(self) -> None:
        self.smooth_moveto(1.0, self.tokens.transition_normal)

    def scroll_to_end(self, delay_ms: int = 0) -> None:
        """Scroll after Tk has completed deferred geometry for restored history."""
        self.after(max(0, int(delay_ms)), self._scroll_end)

    def scroll_to_entry(self, entry, delay_ms: int = 0) -> None:
        if entry in self.entries:
            self.after(max(0, int(delay_ms)), lambda: self._scroll_to_widget(entry))

    def _scroll_to_widget(self, widget) -> None:
        try:
            bounds = self._parent_canvas.bbox("all")
            if bounds and bounds[3] > 0:
                self.smooth_moveto(max(0.0, min(1.0, widget.winfo_y() / bounds[3])), self.tokens.transition_normal)
        except Exception:
            pass

    def clear(self) -> None:
        for entry in self.entries:
            entry.destroy()
        self.messages.clear()
        self.entries.clear()

    def destroy(self) -> None:
        for job in (self._resize_job,):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        super().destroy()

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self.tokens = tokens
        self.configure(fg_color=tokens.colors.background, scrollbar_button_color=tokens.colors.border, scrollbar_button_hover_color=tokens.colors.border_strong)
        for entry in self.entries:
            entry.apply_theme(tokens)
