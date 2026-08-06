"""Small, application-owned PyQt6 widgets for the Qt desktop surface.

The widgets deliberately use QSS and native layouts instead of a theme
framework.  This keeps the warm-neutral design tokens readable and makes the
runtime small enough for a Windows installer.
"""
from __future__ import annotations

import os
from functools import lru_cache
from html import escape
from typing import Callable

from PyQt6.QtCore import QAbstractAnimation, QByteArray, QEasingCurve, QEvent, QMimeData, QPropertyAnimation, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFrame,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
)

from utils.paths import resource_path
from utils.ai_presentation import build_ai_suggestion_view_model, option_presentation
from utils.formatting import candidate_row_tsv, candidate_row_values, discipline_label


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal, *, display: bool = False) -> QFont:
    font = QFont("Source Han Serif SC" if display else "Source Han Sans SC")
    # Inter is the Latin UI face; keep an explicit CJK fallback so labels do
    # not become tofu when platform font fallback is disabled.
    if display:
        font.setFamilies(["Source Han Serif SC", "Noto Serif CJK SC", "SimSun", "serif"])
    else:
        font.setFamilies(["Source Han Sans SC", "Noto Sans CJK SC", "Microsoft YaHei UI", "sans-serif"])
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def candidate_row_mime(item: dict) -> QMimeData:
    fields = candidate_row_values(item)
    mime = QMimeData()
    mime.setText(candidate_row_tsv(item))
    cells = "".join(f'<td style="mso-number-format:\'\\@\';">{escape(value)}</td>' for value in fields)
    mime.setHtml(f"<table><tr>{cells}</tr></table>")
    return mime


def _copy_row_button(item: dict) -> QPushButton:
    button = QPushButton("复制整行")
    button.setObjectName("copyRowButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setAccessibleName("复制整行到剪贴板")
    timer = QTimer(button)
    timer.setSingleShot(True)

    def restore() -> None:
        button.setText("复制整行")
        button.setEnabled(True)

    def copy_row() -> None:
        QApplication.clipboard().setMimeData(candidate_row_mime(item))
        button.setText("已复制")
        button.setEnabled(False)
        timer.start(1500)

    timer.timeout.connect(restore)
    button.clicked.connect(copy_row)
    return button


def _pricing_summary_row(kind: str, item: dict) -> QFrame:
    row = QFrame()
    row.setObjectName("aiPricingLine")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 8, 0, 8)
    layout.setSpacing(12)
    kind_label = QLabel(kind)
    kind_label.setObjectName("aiPricingType")
    kind_label.setFixedWidth(36)
    layout.addWidget(kind_label, 0, Qt.AlignmentFlag.AlignTop)
    code = QLabel(str(item.get("code") or "待确认"))
    code.setObjectName("aiPricingCode")
    code.setMinimumWidth(112)
    code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(code, 0, Qt.AlignmentFlag.AlignTop)
    name_group = QWidget()
    name_layout = QVBoxLayout(name_group)
    name_layout.setContentsMargins(0, 0, 0, 0)
    name_layout.setSpacing(3)
    name = QLabel(str(item.get("name") or "未获取到"))
    name.setObjectName("aiPricingName")
    name.setWordWrap(True)
    name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    name_layout.addWidget(name)
    work_summary = str(item.get("work_summary") or "").strip()
    if kind == "定额" and work_summary:
        work = QLabel(work_summary)
        work.setObjectName("aiPricingWork")
        work.setWordWrap(True)
        work.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        name_layout.addWidget(work)
    layout.addWidget(name_group, 1)
    unit = str(item.get("unit") or "").strip()
    if unit and unit != "未获取到":
        unit_label = QLabel(unit)
        unit_label.setObjectName("aiPricingUnit")
        layout.addWidget(unit_label, 0, Qt.AlignmentFlag.AlignTop)
    layout.addWidget(_copy_row_button(item), 0, Qt.AlignmentFlag.AlignTop)
    return row


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


@lru_cache(maxsize=128)
def _svg_pixmap(name: str, color: str, size: int) -> QPixmap:
    path = resource_path("assets", "icons", f"{name}.svg")
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    if not path.exists():
        return pixmap
    source = path.read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(source.encode("utf-8")))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


def svg_icon(name: str, color: str, size: int = 17) -> QIcon:
    return QIcon(_svg_pixmap(name, color, size))


class ChevronComboBox(QComboBox):
    """Combo box with an application-owned, always-visible chevron."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chevron = QLabel(self)
        self.chevron.setObjectName("comboChevron")
        self.chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.chevron.setFixedSize(16, 16)
        self.chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_icon_color("#77736B")

    def set_icon_color(self, color: str) -> None:
        self.chevron.setPixmap(_svg_pixmap("chevron-down", color, 14))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.chevron.move(self.width() - 24, max(0, (self.height() - self.chevron.height()) // 2))
        self.chevron.raise_()


class SvgIconButton(QPushButton):
    """Application-owned icon button with consistent optical sizing."""

    def __init__(
        self,
        icon_name: str,
        tooltip: str,
        *,
        size: int = 36,
        icon_size: int = 17,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self.icon_pixel_size = icon_size
        self.setObjectName("iconButton")
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_icon_color(self, color: str) -> None:
        self.setIcon(QIcon(_svg_pixmap(self.icon_name, color, self.icon_pixel_size)))


class CheckRow(QPushButton):
    """Large, theme-aware check target used for settings and consent rows."""

    def __init__(self, text: str, *, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("checkRow")
        self.setCheckable(True)
        self.setChecked(checked)
        self.setMinimumHeight(38)
        self.setIconSize(QSize(15, 15))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(text)
        self._checked_color = "#64705E"
        self.toggled.connect(self._refresh_icon)
        self._refresh_icon()

    def set_icon_color(self, checked_color: str) -> None:
        self._checked_color = checked_color
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        if self.isChecked():
            self.setIcon(QIcon(_svg_pixmap("check", self._checked_color, 15)))
            return
        blank = QPixmap(30, 30)
        blank.fill(Qt.GlobalColor.transparent)
        blank.setDevicePixelRatio(2)
        self.setIcon(QIcon(blank))


class SmoothScrollArea(QScrollArea):
    """Mouse-wheel smoothing that yields immediately to manual reading."""

    user_scroll_started = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scroll_target = 0
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(105)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutQuad)

    def cancel_scroll_motion(self) -> None:
        self._scroll_animation.stop()
        self._scroll_target = self.verticalScrollBar().value()

    def wheelEvent(self, event) -> None:
        pixel_delta = event.pixelDelta().y()
        angle_delta = event.angleDelta().y()
        if pixel_delta:
            self.user_scroll_started.emit()
            bar = self.verticalScrollBar()
            self._scroll_animation.stop()
            bar.setValue(max(bar.minimum(), min(bar.maximum(), bar.value() - pixel_delta)))
            self._scroll_target = bar.value()
            event.accept()
            return
        if not angle_delta:
            super().wheelEvent(event)
            return
        self.user_scroll_started.emit()
        bar = self.verticalScrollBar()
        if self._scroll_animation.state() != QAbstractAnimation.State.Running:
            self._scroll_target = bar.value()
        steps = angle_delta / 120.0
        self._scroll_target = max(bar.minimum(), min(bar.maximum(), round(self._scroll_target - steps * 68)))
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(self._scroll_target)
        self._scroll_animation.start()
        event.accept()


class LoadingSpinner(QWidget):
    """Small token-aware progress indicator for transient analysis states."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("loadingSpinner")
        self.setAccessibleName("正在处理")
        self.setFixedSize(16, 16)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._advance)
        if os.environ.get("SHANDONG_REDUCED_MOTION") != "1" and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self._timer.start()

    def _advance(self) -> None:
        self._angle = (self._angle - 22) % 360
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(QPalette.ColorRole.WindowText)
        color.setAlpha(175)
        painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(self.rect().adjusted(2, 2, -2, -2), self._angle * 16, 270 * 16)


class MessageFeed(QWidget):
    """A compact, virtual-friendly conversation column."""

    content_added = pyqtSignal()
    interaction_started = pyqtSignal()
    clarification_selected = pyqtSignal(str, str)
    confirmation_changed = pyqtSignal(str, int, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("messageFeed")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.layout = QVBoxLayout(self)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.layout.setContentsMargins(0, 24, 0, 24)
        self.layout.setSpacing(14)
        self.layout.addStretch(1)
        self._animations: list[QPropertyAnimation] = []
        self._transient_status: QWidget | None = None

    def _insert(self, widget: QWidget, *, align: Qt.AlignmentFlag | None = None, animate: bool = True) -> QWidget:
        if align is None:
            self.layout.insertWidget(self.layout.count() - 1, widget)
        else:
            self.layout.insertWidget(self.layout.count() - 1, widget, 0, align)
        if animate:
            self._fade_in(widget)
        QTimer.singleShot(0, self.content_added.emit)
        return widget

    def _fade_in(self, widget: QWidget) -> None:
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or os.environ.get("SHANDONG_REDUCED_MOTION") == "1":
            return
        from PyQt6.QtWidgets import QApplication, QGraphicsOpacityEffect

        if QApplication.instance() is None:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(150)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: self._animations.remove(animation) if animation in self._animations else None)
        self._animations.append(animation)
        animation.start()

    def clear_feed(self) -> None:
        self._transient_status = None
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _clear_transient(self) -> None:
        if self._transient_status is None:
            return
        self.layout.removeWidget(self._transient_status)
        self._transient_status.hide()
        self._transient_status.setParent(None)
        self._transient_status.deleteLater()
        self._transient_status = None

    def remove_widget(self, widget: QWidget | None) -> None:
        if widget is None:
            return
        if widget is self._transient_status:
            self._transient_status = None
        self.layout.removeWidget(widget)
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()

    def add_welcome(self, examples: list[str], on_example: Callable[[str], None]) -> QWidget:
        card = QFrame()
        card.setObjectName("welcomePanel")
        card.setMaximumWidth(720)
        card.setMinimumWidth(560)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 44, 18, 32)
        layout.setSpacing(10)
        mark = QLabel("定")
        mark.setObjectName("welcomeMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(40, 40)
        kicker = QLabel("山东定额助手 · AI 套价")
        kicker.setObjectName("kicker")
        kicker.setFont(_font(12, QFont.Weight.DemiBold))
        title = QLabel("把施工做法交给我")
        title.setObjectName("welcomeTitle")
        title.setFont(_font(27, QFont.Weight.DemiBold, display=True))
        title.setWordWrap(True)
        detail = QLabel("从山东清单与定额资料中定位候选项，再由 AI 帮你梳理成可复核的建议。")
        detail.setObjectName("secondaryText")
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(kicker)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.setAlignment(kicker, Qt.AlignmentFlag.AlignHCenter)
        layout.setAlignment(title, Qt.AlignmentFlag.AlignHCenter)
        examples_label = QLabel("可以这样问")
        examples_label.setObjectName("sectionLabel")
        layout.addSpacing(10)
        layout.addWidget(examples_label)
        for example in examples:
            button = QPushButton(example)
            button.setObjectName("exampleButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(42)
            button.clicked.connect(lambda _checked=False, value=example: on_example(value))
            layout.addWidget(button)
        return self._insert(card, align=Qt.AlignmentFlag.AlignHCenter)

    def add_user(self, text: str) -> QWidget:
        card = PanelCard()
        card.setObjectName("userMessage")
        card.setMaximumWidth(620)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 13, 18, 13)
        label = QLabel(text)
        label.setFont(_font(14))
        readable_width = min(584, max(96, label.fontMetrics().horizontalAdvance(text)))
        label.setMinimumWidth(readable_width)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        return self._insert(card, align=Qt.AlignmentFlag.AlignRight)

    def add_status(self, title: str, detail: str = "") -> QWidget:
        self._clear_transient()
        card = PanelCard()
        card.setObjectName("statusCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)
        header = QHBoxLayout()
        header.setSpacing(8)
        spinner = LoadingSpinner(card)
        header.addWidget(spinner, 0, Qt.AlignmentFlag.AlignVCenter)
        heading = QLabel(title)
        heading.setFont(_font(14, QFont.Weight.DemiBold))
        header.addWidget(heading)
        header.addStretch(1)
        layout.addLayout(header)
        if detail:
            body = QLabel(detail)
            body.setObjectName("secondaryText")
            body.setWordWrap(True)
            layout.addWidget(body)
        self._transient_status = card
        return self._insert(card)

    def add_result(self, result: dict) -> QWidget:
        self._clear_transient()
        card = PanelCard()
        card.setObjectName("resultCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        proposals = result.get("proposals") or []
        bill_records = {
            str(value.get("record_id") or ""): value
            for value in result.get("bills") or []
            if isinstance(value, dict) and value.get("record_id")
        }
        quota_records = {
            str(value.get("record_id") or ""): value
            for value in result.get("quotas") or []
            if isinstance(value, dict) and value.get("record_id")
        }
        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("本地匹配")
        title.setObjectName("resultTitle")
        title.setFont(_font(17, QFont.Weight.DemiBold, display=True))
        header.addWidget(title)
        header.addStretch(1)
        count = QLabel(f"{len(proposals)} 个方案")
        count.setObjectName("countBadge")
        header.addWidget(count)
        layout.addLayout(header)
        summary = QLabel(_result_summary(result))
        summary.setObjectName("secondaryText")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        for index, proposal in enumerate(proposals[:6], 1):
            row = QFrame()
            row.setObjectName("primaryProposal" if index == 1 else "proposalRow")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(14, 12, 14, 12)
            row_layout.setSpacing(7)
            code = str(proposal.get("bill_code") or "待确认清单")
            item_title = str(proposal.get("bill_title") or "未命名工作项")
            title_row = QHBoxLayout()
            rank = QLabel(f"{index:02d}")
            rank.setObjectName("rankBadge")
            rank.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rank.setFixedSize(28, 24)
            title_row.addWidget(rank)
            line = QLabel(item_title)
            line.setObjectName("proposalTitle")
            line.setFont(_font(14, QFont.Weight.DemiBold))
            line.setWordWrap(True)
            title_row.addWidget(line, 1)
            status = QLabel(_proposal_status(proposal))
            status.setObjectName("proposalStatus")
            title_row.addWidget(status)
            bill_source = bill_records.get(str(proposal.get("bill_record_id") or ""), {})
            title_row.addWidget(
                _copy_row_button(
                    {
                        "code": code,
                        "title": item_title,
                        "unit": proposal.get("bill_unit"),
                        "version": bill_source.get("edition") or result.get("standard_edition"),
                        "discipline": bill_source.get("discipline") or result.get("discipline"),
                        "pdf_page": bill_source.get("pdf_page"),
                    }
                )
            )
            row_layout.addLayout(title_row)
            meta = QLabel(" · ".join(value for value in (code, str(proposal.get("bill_unit") or "")) if value))
            meta.setObjectName("secondaryText")
            meta.setWordWrap(True)
            row_layout.addWidget(meta)
            for quota in proposal.get("quota_lines") or []:
                quota_row = QFrame()
                quota_row.setObjectName("quotaLine")
                quota_layout = QHBoxLayout(quota_row)
                quota_layout.setContentsMargins(9, 6, 9, 6)
                quota_layout.setSpacing(9)
                quota_code = QLabel(str(quota.get("code") or "定额"))
                quota_code.setObjectName("quotaCode")
                quota_layout.addWidget(quota_code)
                quota_title = QLabel(str(quota.get("title") or "待确认定额"))
                quota_title.setWordWrap(True)
                quota_layout.addWidget(quota_title, 1)
                unit = str(quota.get("unit") or "")
                if unit:
                    quota_unit = QLabel(unit)
                    quota_unit.setObjectName("secondaryText")
                    quota_layout.addWidget(quota_unit)
                quota_source = quota_records.get(str(quota.get("record_id") or ""), {})
                quota_layout.addWidget(
                    _copy_row_button(
                        {
                            "code": quota.get("code"),
                            "title": quota.get("title"),
                            "unit": quota.get("unit"),
                            "version": quota_source.get("edition") or result.get("quota_edition"),
                            "discipline": quota_source.get("discipline") or result.get("discipline"),
                            "pdf_page": quota_source.get("pdf_page"),
                        }
                    )
                )
                row_layout.addWidget(quota_row)
            review_candidates = proposal.get("review_candidates") or []
            if not (proposal.get("quota_lines") or []) and review_candidates:
                candidate_heading = QLabel("候选定额，补充条件后确定")
                candidate_heading.setObjectName("candidateHeading")
                row_layout.addWidget(candidate_heading)
                for quota in review_candidates[:3]:
                    quota_row = QFrame()
                    quota_row.setObjectName("candidateQuotaLine")
                    quota_layout = QHBoxLayout(quota_row)
                    quota_layout.setContentsMargins(9, 6, 9, 6)
                    quota_layout.setSpacing(9)
                    quota_code = QLabel(str(quota.get("code") or "定额"))
                    quota_code.setObjectName("quotaCode")
                    quota_layout.addWidget(quota_code)
                    quota_title = QLabel(str(quota.get("title") or "待确认定额"))
                    quota_title.setWordWrap(True)
                    quota_layout.addWidget(quota_title, 1)
                    quota_unit = QLabel(str(quota.get("unit") or ""))
                    quota_unit.setObjectName("secondaryText")
                    quota_layout.addWidget(quota_unit)
                    quota_source = quota_records.get(str(quota.get("record_id") or ""), {})
                    quota_layout.addWidget(
                        _copy_row_button(
                            {
                                "code": quota.get("code"),
                                "title": quota.get("title"),
                                "unit": quota.get("unit"),
                                "version": quota_source.get("edition") or result.get("quota_edition"),
                                "discipline": quota_source.get("discipline") or result.get("discipline"),
                                "pdf_page": quota_source.get("pdf_page"),
                            }
                        )
                    )
                    row_layout.addWidget(quota_row)
            layout.addWidget(row)
        questions = [value for value in result.get("clarification_questions") or [] if isinstance(value, dict)]
        if questions:
            divider = QFrame()
            divider.setObjectName("clarificationRule")
            layout.addWidget(divider)
            question = questions[0]
            prompt = QLabel(str(question.get("question") or "请选择需要补充的施工条件"))
            prompt.setObjectName("clarificationTitle")
            prompt.setWordWrap(True)
            layout.addWidget(prompt)
            reason = QLabel("选择后立即重新匹配清单与定额")
            reason.setObjectName("clarificationHint")
            layout.addWidget(reason)
            choices = QVBoxLayout()
            choices.setSpacing(7)
            question_id = str(question.get("id") or "")
            for option in question.get("options") or []:
                value = str(option)
                button = QPushButton(option_presentation(value)["display"])
                button.setObjectName("choiceButton")
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setAccessibleName(f"补充条件：{value}")
                button.clicked.connect(
                    lambda _checked=False, selected=value, target=question_id: self.clarification_selected.emit(target, selected)
                )
                choices.addWidget(button)
            layout.addLayout(choices)
        if not proposals:
            empty = QLabel("没有找到可直接确认的方案，请补充规格、厚度或施工部位。")
            empty.setObjectName("secondaryText")
            empty.setWordWrap(True)
            layout.addWidget(empty)
        return self._insert(card, animate=False)

    def add_ai(self, text: str, result: dict | None = None, *, context_id: str = "") -> QWidget:
        self._clear_transient()
        card = PanelCard()
        card.setObjectName("aiSuggestionCard")
        card.setAccessibleName("AI 套价建议")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 26)
        layout.setSpacing(10)
        view = build_ai_suggestion_view_model(text, result)

        header = QHBoxLayout()
        header.setSpacing(10)
        kicker = QLabel("复核结论")
        kicker.setObjectName("aiKicker")
        kicker.setFont(_font(13, QFont.Weight.DemiBold))
        header.addWidget(kicker)
        header.addStretch(1)
        state = QLabel(str(view["state_label"]))
        state.setObjectName("aiState")
        state.setProperty("state", str(view["state"]))
        header.addWidget(state)
        layout.addLayout(header)

        headline = QLabel(str(view["headline"]))
        headline.setObjectName("aiHeadline")
        headline.setFont(_font(20, QFont.Weight.DemiBold, display=True))
        headline.setWordWrap(True)
        headline.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(headline)

        note = QLabel(str(view["note"]))
        note.setObjectName("aiNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        question = view.get("question")
        if isinstance(question, dict):
            prompt = QLabel(str(question.get("prompt") or f"请确认{question.get('label') or '关键信息'}"))
            prompt.setObjectName("aiNextStep")
            prompt.setWordWrap(True)
            layout.addSpacing(3)
            layout.addWidget(prompt)
            help_text = QLabel("选择现场实际做法后，我会重新匹配对应的清单和定额。")
            help_text.setObjectName("aiNote")
            help_text.setWordWrap(True)
            layout.addWidget(help_text)
            choices = QVBoxLayout()
            choices.setSpacing(7)
            question_id = str(question.get("id") or "")
            for option in question.get("options") or []:
                option_data = dict(option)
                value = str(option_data.get("value") or "")
                button = QPushButton(str(option_data.get("display") or value))
                button.setObjectName("choiceButton")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setAccessibleName(f"补充条件：{value}")
                button.clicked.connect(
                    lambda _checked=False, selected=value, target=question_id: self.clarification_selected.emit(target, selected)
                )
                choices.addWidget(button)
            layout.addLayout(choices)
        elif view.get("state") in {"ready", "partial"}:
            summary_title = QLabel("建议套用")
            summary_title.setObjectName("aiSectionTitle")
            layout.addSpacing(8)
            layout.addWidget(summary_title)
            summary = QFrame()
            summary.setObjectName("aiPricingSummary")
            summary_layout = QVBoxLayout(summary)
            summary_layout.setContentsMargins(0, 0, 0, 0)
            summary_layout.setSpacing(0)
            summary_layout.addWidget(_pricing_summary_row("清单", dict(view["bill"])))
            quotas = list(view.get("quotas") or [])
            if quotas:
                for quota in quotas[:3]:
                    summary_layout.addWidget(_pricing_summary_row("定额", dict(quota)))
            else:
                summary_layout.addWidget(_pricing_summary_row("定额", {}))
            layout.addWidget(summary)

            if view.get("confirmable"):
                confirm = QPushButton("已人工确认" if view.get("confirmed") else "人工确认")
                confirm.setObjectName("confirmButton")
                confirm.setCheckable(True)
                confirm.setChecked(bool(view.get("confirmed")))
                confirm.setCursor(Qt.CursorShape.PointingHandCursor)
                confirm.setAccessibleName("取消人工确认" if view.get("confirmed") else "人工确认当前套价方案")

                def toggle_confirmation(confirmed: bool) -> None:
                    confirm.setText("已人工确认" if confirmed else "人工确认")
                    confirm.setAccessibleName("取消人工确认" if confirmed else "人工确认当前套价方案")
                    self.confirmation_changed.emit(context_id, 0, confirmed)

                confirm.toggled.connect(toggle_confirmation)
                layout.addSpacing(7)
                layout.addWidget(confirm, 0, Qt.AlignmentFlag.AlignLeft)

        reasons = list(view.get("reasons") or [])[:4]
        if reasons:
            reason_title = QLabel("匹配依据")
            reason_title.setObjectName("aiSectionTitle")
            layout.addSpacing(8)
            layout.addWidget(reason_title)
            reason_panel = QFrame()
            reason_panel.setObjectName("aiReasonPanel")
            reason_layout = QVBoxLayout(reason_panel)
            reason_layout.setContentsMargins(0, 0, 0, 0)
            reason_layout.setSpacing(1)
            for reason in reasons:
                row = QFrame()
                row.setObjectName("aiReasonRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 5, 0, 5)
                row_layout.setSpacing(8)
                marker = QLabel("?" if reason.get("status") == "missing" else "✓")
                marker.setObjectName("aiReasonMarker")
                marker.setProperty("missing", reason.get("status") == "missing")
                marker.setFixedWidth(16)
                row_layout.addWidget(marker)
                label = QLabel(str(reason.get("label") or "信息"))
                label.setObjectName("aiReasonLabel")
                label.setFixedWidth(76)
                row_layout.addWidget(label)
                value = QLabel(str(reason.get("value") or "未获取到"))
                value.setObjectName("aiReasonValue")
                value.setWordWrap(True)
                row_layout.addWidget(value, 1)
                reason_layout.addWidget(row)
            layout.addWidget(reason_panel)

        details = QFrame()
        details.setObjectName("aiDetails")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(12, 9, 12, 9)
        details_layout.setSpacing(6)
        bill = dict(view.get("bill") or {})
        for label_text, value in (("清单名称", bill.get("name")), ("清单编码", bill.get("code")), ("清单单位", bill.get("unit")), ("匹配来源", bill.get("sources"))):
            detail = QLabel(f"{label_text}  ·  {value or '未获取到'}")
            detail.setObjectName("aiDetailLine")
            detail.setWordWrap(True)
            detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            details_layout.addWidget(detail)
        for index, quota in enumerate(view.get("quotas") or [], 1):
            for label_text, value in ((f"定额 {index} 名称", quota.get("name")), ("定额编号", quota.get("code")), ("定额单位", quota.get("unit")), ("匹配来源", quota.get("sources"))):
                detail = QLabel(f"{label_text}  ·  {value or '未获取到'}")
                detail.setObjectName("aiDetailLine")
                detail.setWordWrap(True)
                detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                details_layout.addWidget(detail)
        details.setVisible(False)
        details.setAccessibleName("专业套价明细")

        detail_button = QPushButton("查看专业明细")
        detail_button.setObjectName("aiDetailsButton")
        detail_button.setCheckable(True)
        detail_button.setCursor(Qt.CursorShape.PointingHandCursor)
        detail_button.setAccessibleName("展开专业套价明细")

        def toggle_details(expanded: bool) -> None:
            self.interaction_started.emit()
            details.setVisible(expanded)
            detail_button.setText("收起专业明细" if expanded else "查看专业明细")
            detail_button.setAccessibleName("收起专业套价明细" if expanded else "展开专业套价明细")

        detail_button.toggled.connect(toggle_details)
        if view.get("has_details"):
            layout.addWidget(detail_button, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(details)
        return self._insert(card, animate=False)

    def add_warning(self, text: str, *, error: bool = False) -> QWidget:
        self._clear_transient()
        label = QLabel(text)
        label.setObjectName("errorText" if error else "warningText")
        label.setWordWrap(True)
        return self._insert(label)


class Composer(QFrame):
    send_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("composer")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setMaximumHeight(146)
        self.setMaximumWidth(820)
        self.setMinimumWidth(760)
        self.status_row = QFrame(self)
        self.status_row.setObjectName("composerStatusRow")
        status_layout = QHBoxLayout(self.status_row)
        status_layout.setContentsMargins(2, 0, 2, 0)
        status_layout.setSpacing(8)
        self.status_label = QLabel("描述施工做法，获取清单与定额建议")
        self.status_label.setObjectName("composerStatus")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch(1)
        self.input_shell = QFrame(self)
        self.input_shell.setObjectName("composerInputShell")
        shell_layout = QHBoxLayout(self.input_shell)
        shell_layout.setContentsMargins(7, 6, 7, 6)
        shell_layout.setSpacing(8)
        self.edit = QPlainTextEdit(self.input_shell)
        self.edit.setObjectName("composerEdit")
        self.edit.setPlaceholderText("描述施工做法，例如：地下室外墙 4mm 厚 SBS 防水卷材")
        self.edit.setMinimumHeight(62)
        self.edit.setMaximumHeight(84)
        self.edit.setTabChangesFocus(False)
        self.send_button = SvgIconButton("send", "开始分析", size=42, icon_size=18, parent=self.input_shell)
        self.send_button.setObjectName("composerAction")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setAccessibleName("开始分析")
        self.send_button.clicked.connect(self.send_requested)
        self.edit.installEventFilter(self)
        shell_layout.addWidget(self.edit, 1)
        shell_layout.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        layout.addWidget(self.status_row)
        layout.addWidget(self.input_shell)

    def eventFilter(self, watched: QWidget, event) -> bool:
        if watched is self.edit:
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                self.input_shell.setProperty("focused", event.type() == QEvent.Type.FocusIn)
                self.input_shell.style().unpolish(self.input_shell)
                self.input_shell.style().polish(self.input_shell)
            if event.type() == QEvent.Type.KeyPress:
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                ):
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

    def focus_input(self) -> None:
        self.edit.setFocus()

    def set_busy(self, busy: bool) -> None:
        self.send_button.icon_name = "x" if busy else "send"
        self.status_label.setText("正在匹配本地资料与 AI 复核…" if busy else "描述施工做法，获取清单与定额建议")
        self.send_button.setAccessibleName("停止当前分析" if busy else "开始分析")
        self.send_button.setProperty("busy", busy)
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)

    def apply_icon_color(self, color: str, busy_color: str) -> None:
        self.send_button.set_icon_color(busy_color if self.send_button.property("busy") else color)


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
        if not sessions:
            empty = QListWidgetItem("暂无历史分析")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.addItem(empty)
            return
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
    return f"{discipline}专业，识别 {len(items)} 个工作项，形成 {len(proposals)} 个候选方案"


def _proposal_meta(proposal: dict) -> str:
    unit = proposal.get("bill_unit") or ""
    status = {
        "ready_for_review": "可复核",
        "needs_clarification": "待补条件",
        "multiple_valid_options": "多个方案",
        "no_reliable_match": "未匹配",
    }.get(str(proposal.get("status") or ""), "本地资料")
    return " · ".join(value for value in (str(unit), status) if value)


def _proposal_status(proposal: dict) -> str:
    return {
        "ready_for_review": "建议优先",
        "needs_clarification": "待补条件",
        "multiple_valid_options": "多个方案",
        "no_reliable_match": "未匹配",
    }.get(str(proposal.get("status") or ""), "本地候选")
