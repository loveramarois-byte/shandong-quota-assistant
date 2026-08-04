"""Small, application-owned PyQt6 widgets for the Qt desktop surface.

The widgets deliberately use QSS and native layouts instead of a theme
framework.  This keeps the warm-neutral design tokens readable and makes the
runtime small enough for a Windows installer.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
)


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont("Inter")
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


class PanelCard(QFrame):
    def __init__(self, parent: QWidget | None = None, *, elevated: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("elevatedCard" if elevated else "surfaceCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        if elevated:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(18)
            shadow.setOffset(0, 3)
            shadow.setColor(QColor(39, 36, 30, 22))
            self.setGraphicsEffect(shadow)


class MessageFeed(QWidget):
    """A compact, virtual-friendly conversation column."""

    content_added = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 18, 0, 18)
        self.layout.setSpacing(12)
        self.layout.addStretch(1)

    def _insert(self, widget: QWidget) -> QWidget:
        self.layout.insertWidget(self.layout.count() - 1, widget)
        QTimer.singleShot(0, self.content_added.emit)
        return widget

    def clear_feed(self) -> None:
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_welcome(self, examples: list[str], on_example: Callable[[str], None]) -> QWidget:
        card = PanelCard(elevated=True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 24)
        kicker = QLabel("山东定额助手")
        kicker.setObjectName("kicker")
        kicker.setFont(_font(12, QFont.Weight.DemiBold))
        title = QLabel("先说清楚施工做法")
        title.setObjectName("welcomeTitle")
        title.setFont(_font(25, QFont.Weight.DemiBold))
        title.setWordWrap(True)
        detail = QLabel("我会先从山东定额与清单资料中检索，再给出可复核的套项建议。")
        detail.setObjectName("secondaryText")
        detail.setWordWrap(True)
        layout.addWidget(kicker)
        layout.addWidget(title)
        layout.addWidget(detail)
        for example in examples:
            button = QPushButton(example)
            button.setObjectName("exampleButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=example: on_example(value))
            layout.addWidget(button)
        return self._insert(card)

    def add_user(self, text: str) -> QWidget:
        card = PanelCard()
        card.setObjectName("userMessage")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 13, 18, 13)
        label = QLabel(text)
        label.setFont(_font(14))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        return self._insert(card)

    def add_status(self, title: str, detail: str = "") -> QWidget:
        card = PanelCard()
        card.setObjectName("statusCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        heading = QLabel(title)
        heading.setFont(_font(14, QFont.Weight.DemiBold))
        layout.addWidget(heading)
        if detail:
            body = QLabel(detail)
            body.setObjectName("secondaryText")
            body.setWordWrap(True)
            layout.addWidget(body)
        return self._insert(card)

    def add_result(self, result: dict) -> QWidget:
        card = PanelCard(elevated=True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 19, 22, 18)
        title = QLabel("本地套价草案")
        title.setFont(_font(16, QFont.Weight.DemiBold))
        layout.addWidget(title)
        summary = QLabel(_result_summary(result))
        summary.setObjectName("secondaryText")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        proposals = result.get("proposals") or []
        for index, proposal in enumerate(proposals[:6], 1):
            row = QFrame()
            row.setObjectName("proposalRow")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(12, 9, 12, 9)
            code = str(proposal.get("bill_code") or "待确认清单")
            item_title = str(proposal.get("bill_title") or "未命名工作项")
            line = QLabel(f"{index}. {code}  {item_title}")
            line.setFont(_font(13, QFont.Weight.DemiBold))
            line.setWordWrap(True)
            row_layout.addWidget(line)
            meta = QLabel(_proposal_meta(proposal))
            meta.setObjectName("secondaryText")
            meta.setWordWrap(True)
            row_layout.addWidget(meta)
            for quota in proposal.get("quota_lines") or []:
                quota_text = "  ".join(
                    value for value in (
                        str(quota.get("code") or ""),
                        str(quota.get("title") or ""),
                        str(quota.get("unit") or ""),
                    ) if value
                )
                if quota_text:
                    quota_label = QLabel("定额  " + quota_text)
                    quota_label.setObjectName("quotaLine")
                    quota_label.setWordWrap(True)
                    row_layout.addWidget(quota_label)
            layout.addWidget(row)
        if not proposals:
            empty = QLabel("没有找到可直接确认的方案，请补充规格、厚度或施工部位。")
            empty.setObjectName("secondaryText")
            empty.setWordWrap(True)
            layout.addWidget(empty)
        return self._insert(card)

    def add_ai(self, text: str) -> QWidget:
        card = PanelCard(elevated=True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 19, 22, 19)
        heading = QLabel("AI 复核意见")
        heading.setFont(_font(16, QFont.Weight.DemiBold))
        layout.addWidget(heading)
        body = QLabel(text)
        body.setObjectName("aiText")
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.MarkdownText)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body)
        return self._insert(card)

    def add_warning(self, text: str, *, error: bool = False) -> QWidget:
        label = QLabel(text)
        label.setObjectName("errorText" if error else "warningText")
        label.setWordWrap(True)
        return self._insert(label)


class Composer(QWidget):
    send_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.edit = QPlainTextEdit(self)
        self.edit.setPlaceholderText("描述施工做法，例如：地下室外墙 4mm 厚 SBS 防水卷材")
        self.edit.setMinimumHeight(78)
        self.edit.setMaximumHeight(150)
        self.edit.setTabChangesFocus(False)
        self.send_button = QPushButton("分析")
        self.send_button.setObjectName("primaryButton")
        self.send_button.setMinimumHeight(38)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self.send_requested)
        self.edit.installEventFilter(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.edit)
        footer = QHBoxLayout()
        footer.addWidget(QLabel("本地资料优先，AI 仅做复核"), 0, Qt.AlignmentFlag.AlignVCenter)
        footer.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        footer.addWidget(self.send_button)
        layout.addLayout(footer)

    def eventFilter(self, watched: QWidget, event) -> bool:
        if watched is self.edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.send_requested.emit()
                return True
        return super().eventFilter(watched, event)

    def text(self) -> str:
        return self.edit.toPlainText().strip()

    def clear(self) -> None:
        self.edit.clear()

    def set_text(self, value: str) -> None:
        self.edit.setPlainText(value)
        self.edit.setFocus()


class SessionList(QListWidget):
    session_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sessionList")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.itemClicked.connect(lambda item: self.session_selected.emit(str(item.data(Qt.ItemDataRole.UserRole))))

    def set_sessions(self, sessions: list[dict]) -> None:
        self.clear()
        for summary in sessions:
            item = QListWidgetItem(str(summary.get("title") or "新的检索"))
            item.setData(Qt.ItemDataRole.UserRole, str(summary.get("id") or ""))
            item.setToolTip(str(summary.get("title") or "新的检索"))
            self.addItem(item)


def _result_summary(result: dict) -> str:
    items = result.get("work_items") or []
    proposals = result.get("proposals") or []
    discipline = {"building": "建筑", "decoration": "装饰", "installation": "安装", "municipal": "市政", "landscape": "园林"}.get(
        result.get("discipline") or result.get("requested_discipline"), "建筑"
    )
    return f"{discipline}专业 · 识别 {len(items)} 个工作项 · 形成 {len(proposals)} 个候选方案"


def _proposal_meta(proposal: dict) -> str:
    unit = proposal.get("bill_unit") or ""
    status = {"ready": "可复核", "needs_input": "待补条件", "review": "需复核"}.get(str(proposal.get("status") or ""), "本地资料")
    return " · ".join(value for value in (str(unit), status) if value)
