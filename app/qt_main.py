"""PyQt6 desktop surface for 山东定额助手.

The service, catalogue, persistence and validation layers remain shared with
the original application.  This module owns only the Qt presentation and the
signal-based worker boundary.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QSize, QThreadPool, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from components.qt_widgets import Composer, MessageFeed, SessionList, SvgIconButton, svg_icon
from controllers.analysis import AnalysisTaskRegistry
from themes.tokens import ThemeTokens, get_theme
from utils.ai_providers import provider_config
from utils.ai_structured import (
    build_structured_ai_prompt,
    parse_structured_ai_response,
    render_structured_ai_response,
    validate_structured_ai_response,
)
from utils.ai_validate import validate_ai_answer
from utils.ccswitch import AIRequestConfig, build_ai_request_config, call_ccswitch, fetch_models, probe_ccswitch
from utils.logging_setup import log_exception, setup_logging
from utils.paths import APP_VERSION, catalog_manifest_path, resource_path
from utils.pricing_pipeline import analyze_pricing_description, merge_clarification_context
from utils.settings import DISCIPLINE_LABEL_TO_CODE, DISCIPLINE_OPTIONS, load_settings, sanitize_settings, save_settings, validate_ai_endpoint
from utils.secrets import load_api_key, save_api_key
from utils.single_instance import SingleInstanceGuard
from utils import sessions as session_store
from utils.windows_theme import apply_window_chrome


def _clean_validation(validation: dict) -> dict:
    cleaned = dict(validation or {})
    cleaned["warnings"] = [value for value in cleaned.get("warnings") or [] if "部分关键结论未标注本地候选编号" not in str(value)]
    cleaned["uncited_lines"] = []
    return cleaned


class WorkerSignals(QObject):
    local_result = pyqtSignal(int, object)
    ai_answer = pyqtSignal(int, str, object)
    ai_error = pyqtSignal(int, str)
    ai_skipped = pyqtSignal(int)
    search_error = pyqtSignal(int, str)
    sidebar_data = pyqtSignal(object, object)


class AnalysisJob(QRunnable):
    def __init__(self, request_id: int, description: str, settings: dict, cancel: threading.Event) -> None:
        super().__init__()
        self.request_id = request_id
        self.description = description
        self.settings = settings
        self.cancel = cancel
        self.signals = WorkerSignals()

    def run(self) -> None:
        local_emitted = False
        try:
            edition = str(self.settings.get("quota_edition") or "2025")
            standard = str(self.settings.get("standard_edition") or "2024")
            discipline_label = str(self.settings.get("discipline") or "建筑")
            discipline = DISCIPLINE_LABEL_TO_CODE.get(discipline_label, "building")
            result = analyze_pricing_description(
                self.description,
                quota_edition=edition,
                standard_edition=standard,
                discipline=discipline,
                limit=6,
                cancel_event=self.cancel,
            )
            if self.cancel.is_set():
                return
            self.signals.local_result.emit(self.request_id, result)
            local_emitted = True
            if not bool(self.settings.get("ai_enabled")):
                self.signals.ai_skipped.emit(self.request_id)
                return
            config = build_ai_request_config(self.settings)
            raw = call_ccswitch(build_structured_ai_prompt(self.description, result), config=config)
            structured = parse_structured_ai_response(raw)
            checked = validate_structured_ai_response(structured, result)
            if not checked.get("valid"):
                detail = "；".join(checked.get("errors") or []) or "结果不合法"
                raise ValueError("AI 结构化方案未通过本地校验：" + detail)
            structured = checked.get("structured") or structured
            text = render_structured_ai_response(structured, result)
            validation = validate_ai_answer(text, result)
            validation["structured_valid"] = True
            validation["structured"] = structured
            self.signals.ai_answer.emit(self.request_id, text, _clean_validation(validation))
        except Exception as exc:
            log_exception("qt analysis failed")
            if self.cancel.is_set():
                return
            message = str(exc)
            if local_emitted:
                self.signals.ai_error.emit(self.request_id, message)
            else:
                self.signals.search_error.emit(self.request_id, message)


class SettingsDialog(QDialog):
    connection_result = pyqtSignal(bool, object)

    def __init__(self, settings: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(480)
        self.settings = dict(settings)
        form = QVBoxLayout(self)
        form.setContentsMargins(28, 24, 28, 22)
        form.setSpacing(10)
        title = QLabel("分析设置")
        title.setObjectName("dialogTitle")
        form.addWidget(title)
        hint = QLabel("API Key 只保存在本机凭据区；本地资料检索始终可以单独使用。")
        hint.setObjectName("secondaryText")
        hint.setWordWrap(True)
        form.addWidget(hint)
        self.provider = QComboBox()
        self.provider.addItem("ccSwitch", "ccswitch")
        self.provider.addItem("DeepSeek", "deepseek")
        self.provider.addItem("智谱 GLM", "zhipu")
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.get("ai_provider"))))
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.base_url = QLineEdit(str(settings.get("ai_base_url") or provider_config(settings.get("ai_provider")).default_base_url))
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems([str(settings.get("ai_model") or "")])
        self.model.setCurrentText(str(settings.get("ai_model") or ""))
        self.ai_enabled = QCheckBox("启用 AI 复核")
        self.ai_enabled.setChecked(bool(settings.get("ai_enabled")))
        for label, widget in (("服务商", self.provider), ("API Key", self.api_key), ("服务地址", self.base_url), ("模型", self.model), ("状态", self.ai_enabled)):
            row = QHBoxLayout()
            caption = QLabel(label)
            caption.setMinimumWidth(70)
            caption.setObjectName("secondaryText")
            row.addWidget(caption)
            row.addWidget(widget, 1)
            form.addLayout(row)
        self.connect_button = QPushButton("连接并获取模型")
        self.connect_button.setObjectName("primaryButton")
        self.connect_button.clicked.connect(self._connect_ai)
        form.addWidget(self.connect_button)
        self.connection_status = QLabel("")
        self.connection_status.setObjectName("secondaryText")
        self.connection_status.setWordWrap(True)
        form.addWidget(self.connection_status)
        self.description_consent = QCheckBox("允许发送施工描述")
        self.description_consent.setChecked(int(settings.get("ai_consent_version") or 0) >= 1)
        self.catalog_consent = QCheckBox("允许发送本地候选摘要")
        self.catalog_consent.setChecked(int(settings.get("ai_catalog_consent_version") or 0) >= 1)
        form.addWidget(self.description_consent)
        form.addWidget(self.catalog_consent)
        consent = QLabel("发送前请确认施工描述和本地候选摘要可以发送给所选服务商。")
        consent.setObjectName("warningText")
        consent.setWordWrap(True)
        form.addWidget(consent)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        save_button.setText("保存")
        save_button.setObjectName("primaryButton")
        cancel_button.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)
        self.connection_result.connect(self._connection_finished)
        self._provider_changed()

    def _provider_key(self) -> str:
        return str(self.provider.currentData() or "ccswitch")

    def _provider_changed(self) -> None:
        config = provider_config(self._provider_key())
        self.base_url.setText(config.default_base_url)
        self.api_key.clear()
        try:
            saved = bool(load_api_key(config.key))
        except (OSError, RuntimeError):
            saved = False
        self.api_key.setPlaceholderText("已安全保存在本机；留空继续使用" if saved else config.key_hint)
        self.connection_status.setText(config.novice_hint)

    def _current_key(self) -> str:
        entered = self.api_key.text().strip()
        if entered:
            return entered
        try:
            return load_api_key(self._provider_key())
        except (OSError, RuntimeError):
            return ""

    def _connect_ai(self) -> None:
        provider = self._provider_key()
        config = provider_config(provider)
        key = self._current_key()
        if config.requires_api_key and not key:
            self.connection_status.setText(f"请先填写 {config.label} API Key。")
            self.api_key.setFocus()
            return
        try:
            endpoint = validate_ai_endpoint(self.base_url.text()) or config.default_base_url
        except ValueError as exc:
            self.connection_status.setText(str(exc))
            return
        self.connect_button.setEnabled(False)
        self.connect_button.setText("连接中…")
        self.connection_status.setText("正在读取可用模型并进行一次连接测试…")

        def worker() -> None:
            try:
                models = fetch_models(provider=provider, base_url=endpoint, api_key=key, timeout=12)
                model = self.model.currentText().strip()
                if model not in models:
                    model = models[0]
                probe_ccswitch(endpoint, model=model, timeout=12, provider=provider, api_key=key)
                self.connection_result.emit(True, {"models": models, "model": model})
            except Exception as exc:
                if provider == "ccswitch" and config.fallback_models:
                    self.connection_result.emit(True, {"models": list(config.fallback_models), "model": config.fallback_models[0], "fallback": True})
                else:
                    self.connection_result.emit(False, str(exc))

        threading.Thread(target=worker, name="qt-ai-setup", daemon=True).start()

    def _connection_finished(self, success: bool, detail: object) -> None:
        self.connect_button.setEnabled(True)
        self.connect_button.setText("连接并获取模型")
        if not success:
            self.connection_status.setText("连接失败：" + str(detail))
            return
        payload = dict(detail)
        models = [str(item) for item in payload.get("models") or []]
        self.model.clear()
        self.model.addItems(models)
        self.model.setCurrentText(str(payload.get("model") or (models[0] if models else "")))
        suffix = "（使用 ccSwitch 已验证候选模型）" if payload.get("fallback") else ""
        self.connection_status.setText(f"连接成功，已获取 {len(models)} 个模型{suffix}。")

    def accept(self) -> None:
        provider = self._provider_key()
        config = provider_config(provider)
        if self.ai_enabled.isChecked():
            if config.requires_api_key and not self._current_key():
                self.connection_status.setText(f"启用 {config.label} 前需填写 API Key。")
                return
            if not self.model.currentText().strip():
                self.connection_status.setText("请先连接并选择模型。")
                return
            if not self.description_consent.isChecked() or not self.catalog_consent.isChecked():
                self.connection_status.setText("启用 AI 前，请勾选两项发送许可。")
                return
        entered_key = self.api_key.text().strip()
        if entered_key:
            try:
                save_api_key(provider, entered_key)
            except (OSError, RuntimeError):
                self.connection_status.setText("API Key 无法写入 Windows 凭据区。")
                return
        super().accept()

    def values(self) -> dict:
        return {
            "ai_provider": self._provider_key(),
            "ai_base_url": self.base_url.text().strip(),
            "ai_model": self.model.currentText().strip(),
            "ai_enabled": self.ai_enabled.isChecked(),
            "ai_consent_version": 1 if self.description_consent.isChecked() else 0,
            "ai_catalog_consent_version": 1 if self.catalog_consent.isChecked() else 0,
        }


class QuotaQtApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        setup_logging()
        self.log = logging.getLogger("qt-app")
        self.settings = load_settings()
        self.theme_name = str(self.settings.get("theme") or "light")
        self.tokens: ThemeTokens = get_theme(self.theme_name)
        self.signals = WorkerSignals()
        self.pool = QThreadPool.globalInstance()
        self.tasks = AnalysisTaskRegistry()
        self._cancel: threading.Event | None = None
        self._request_id = 0
        self._active_request_id: int | None = None
        self._session: dict | None = None
        self._active_turn_id: str | None = None
        self._pending: dict[int, dict] = {}
        self._sidebar_loading = False
        self._follow_latest = True
        self._build()
        self._connect_signals()
        self._apply_theme()
        QTimer.singleShot(50, lambda: apply_window_chrome(self, self.tokens))
        QTimer.singleShot(120, self._refresh_sessions)
        self._show_welcome()

    def _build(self) -> None:
        self.setWindowTitle("山东定额助手")
        self.setMinimumSize(1080, 680)
        self.resize(1280, 820)
        icon_path = resource_path("assets", "images", "app.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = self._build_sidebar()
        outer.addWidget(self.sidebar)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 18, 32, 20)
        content_layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(10)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(1)
        title = QLabel("套价分析")
        title.setObjectName("pageTitle")
        subtitle = QLabel("山东清单与定额智能匹配")
        subtitle.setObjectName("pageSubtitle")
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)
        header.addLayout(title_stack)
        header.addStretch(1)
        self.edition = QComboBox(); self.edition.addItems(["2025", "2016"])
        self.standard = QComboBox(); self.standard.addItems(["2024", "2013"])
        self.discipline = QComboBox(); self.discipline.addItems(list(DISCIPLINE_OPTIONS))
        filter_bar = QFrame()
        filter_bar.setObjectName("filterBar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(3, 3, 3, 3)
        filter_layout.setSpacing(5)
        for widget in (self.edition, self.standard, self.discipline):
            widget.setMinimumWidth(88)
            filter_layout.addWidget(widget)
        header.addWidget(filter_bar)
        self.ai_status = QLabel()
        self.ai_status.setObjectName("statusPill")
        header.addWidget(self.ai_status)
        self.theme_button = SvgIconButton("moon", "切换外观")
        self.theme_button.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_button)
        self.settings_button = SvgIconButton("settings", "设置 AI 与偏好")
        self.settings_button.clicked.connect(self._open_settings)
        header.addWidget(self.settings_button)
        content_layout.addLayout(header)
        self.rule = QFrame(); self.rule.setFrameShape(QFrame.Shape.HLine); self.rule.setObjectName("rule")
        content_layout.addWidget(self.rule)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("feedScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        viewport = self.scroll.viewport()
        viewport.setObjectName("feedViewport")
        viewport.setAutoFillBackground(True)
        self.feed = MessageFeed()
        self.feed.setMaximumWidth(self.tokens.content_max_width)
        self.feed.content_added.connect(self._scroll_to_latest)
        self.scroll.setWidget(self.feed)
        self.scroll.verticalScrollBar().valueChanged.connect(self._track_scroll_position)
        content_layout.addWidget(self.scroll, 1)
        self.composer = Composer()
        content_layout.addWidget(self.composer, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(content, 1)
        self._set_controls_from_settings()

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(self.tokens.sidebar_width)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(9)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        self.brand_mark = QLabel("定")
        self.brand_mark.setObjectName("brandMark")
        self.brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand_mark.setFixedSize(36, 36)
        brand_row.addWidget(self.brand_mark)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand = QLabel("山东定额助手")
        brand.setObjectName("brand")
        brand_subtitle = QLabel("AI 套价")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_text.addWidget(brand)
        brand_text.addWidget(brand_subtitle)
        brand_row.addLayout(brand_text, 1)
        layout.addLayout(brand_row)
        layout.addSpacing(5)
        self.new_button = QPushButton("新建分析")
        self.new_button.setObjectName("newButton")
        self.new_button.setAccessibleName("新建分析")
        self.new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_button.clicked.connect(self._new_session)
        layout.addWidget(self.new_button)
        label = QLabel("最近分析")
        label.setObjectName("sectionLabel")
        layout.addWidget(label)
        self.sessions = SessionList()
        self.sessions.session_selected.connect(self._select_session)
        layout.addWidget(self.sessions, 1)
        library_panel = QFrame()
        library_panel.setObjectName("libraryPanel")
        library_layout = QVBoxLayout(library_panel)
        library_layout.setContentsMargins(11, 10, 11, 10)
        library_layout.setSpacing(2)
        library_title = QLabel("本地资料")
        library_title.setObjectName("libraryTitle")
        self.library_label = QLabel("正在读取资料索引…")
        self.library_label.setObjectName("secondaryText")
        self.library_label.setWordWrap(True)
        library_layout.addWidget(library_title)
        library_layout.addWidget(self.library_label)
        layout.addWidget(library_panel)
        version = QLabel(f"山东定额 · v{APP_VERSION}")
        version.setObjectName("versionText")
        layout.addWidget(version, 0, Qt.AlignmentFlag.AlignHCenter)
        return sidebar

    def _connect_signals(self) -> None:
        self.composer.send_requested.connect(self._send)
        self.signals.local_result.connect(self._on_local_result)
        self.signals.ai_answer.connect(self._on_ai_answer)
        self.signals.ai_error.connect(self._on_ai_error)
        self.signals.ai_skipped.connect(self._on_ai_skipped)
        self.signals.search_error.connect(self._on_search_error)
        self.signals.sidebar_data.connect(self._on_sidebar_data)

    def _apply_theme(self) -> None:
        c = self.tokens.colors
        self.setStyleSheet(f"""
        QWidget {{ color: {c.text}; font-family: Inter, 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif; font-size: 14px; }}
        QMainWindow, #root {{ background: {c.background}; }}
        QToolTip {{ color: {c.text}; background: {c.elevated}; border: 1px solid {c.border}; padding: 5px 7px; }}
        #sidebar {{ background: {c.sidebar}; border-right: 1px solid {c.sidebar_border}; }}
        #brandMark, #welcomeMark {{ color: {c.accent}; background: {c.accent_soft}; border: 1px solid {c.border}; border-radius: 10px; font-size: 16px; font-weight: 700; }}
        #brand {{ color: {c.text}; font-family: 'Source Han Serif SC'; font-size: 15px; font-weight: 600; }}
        #brandSubtitle, #versionText {{ color: {c.text_muted}; font-size: 11px; }}
        #sectionLabel {{ color: {c.text_muted}; font-size: 11px; font-weight: 650; padding-top: 10px; }}
        #pageTitle {{ color: {c.text}; font-family: 'Source Han Serif SC'; font-size: 19px; font-weight: 600; }}
        #pageSubtitle {{ color: {c.text_muted}; font-size: 11px; }}
        #filterBar {{ background: {c.subtle}; border: 1px solid {c.border}; border-radius: 10px; }}
        #secondaryText {{ color: {c.text_secondary}; }}
        #statusPill {{ color: {c.success}; background: transparent; border: 0; padding: 5px 3px; font-size: 11px; font-weight: 600; }}
        #rule {{ color: {c.border}; max-height: 1px; }}
        #feedScroll, #feedViewport, #messageFeed {{ background: {c.background}; border: 0; }}
        #welcomePanel {{ background: transparent; border: 0; }}
        #welcomeTitle {{ color: {c.text}; font-family: 'Source Han Serif SC'; font-size: 28px; font-weight: 600; }}
        #kicker {{ color: {c.accent}; }}
        QComboBox, QLineEdit {{ color: {c.text}; background: {c.elevated}; border: 1px solid {c.border}; border-radius: 8px; padding: 6px 9px; min-height: 20px; selection-background-color: {c.accent_soft}; }}
        QPlainTextEdit {{ color: {c.text}; background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 7px 8px; selection-background-color: {c.accent_soft}; }}
        QComboBox:hover, QLineEdit:hover {{ border-color: {c.border_strong}; }}
        QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {c.focus}; }}
        QComboBox:disabled, QLineEdit:disabled {{ color: {c.text_muted}; background: {c.subtle}; }}
        QComboBox::drop-down {{ border: 0; width: 28px; background: transparent; }}
        QComboBox QAbstractItemView {{ background: {c.elevated}; color: {c.text}; border: 1px solid {c.border}; outline: 0; padding: 4px; selection-background-color: {c.accent_soft}; selection-color: {c.text}; }}
        QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 6px 10px; color: {c.text}; }}
        QComboBox QAbstractItemView::item:hover {{ background: {c.subtle}; color: {c.text}; }}
        #surfaceCard, #elevatedCard, #resultCard, #aiCard {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 12px; }}
        #elevatedCard {{ background: {c.elevated}; }}
        #resultCard {{ background: {c.surface}; }}
        #aiCard {{ background: {c.surface}; border-left: 3px solid {c.accent}; }}
        #userMessage {{ color: {c.user_text}; background: {c.user_surface}; border: 0; border-radius: 12px; }}
        #statusCard {{ background: {c.subtle}; border: 0; border-radius: 9px; }}
        #resultTitle {{ color: {c.text}; font-family: 'Source Han Serif SC'; font-weight: 600; }}
        #countBadge, #proposalStatus {{ color: {c.text_secondary}; background: {c.subtle}; border-radius: 8px; padding: 4px 8px; font-size: 11px; }}
        #primaryProposal {{ background: {c.accent_soft}; border: 1px solid {c.border}; border-radius: 9px; }}
        #proposalRow {{ background: transparent; border: 1px solid {c.border}; border-radius: 9px; }}
        #rankBadge {{ color: {c.on_accent}; background: {c.accent_fill}; border-radius: 12px; font-size: 11px; font-weight: 700; }}
        #proposalTitle {{ color: {c.text}; }}
        #quotaLine {{ color: {c.text_secondary}; background: {c.elevated}; border: 1px solid {c.border}; border-radius: 7px; }}
        #quotaCode {{ color: {c.accent}; font-size: 12px; font-weight: 650; }}
        #aiText {{ color: {c.text}; line-height: 1.62; }}
        #warningText {{ color: {c.warning}; background: {c.warning_soft}; border-radius: 8px; padding: 9px 11px; }}
        #errorText {{ color: {c.danger}; background: {c.danger_soft}; border-radius: 8px; padding: 9px 11px; }}
        #composer {{ background: {c.elevated}; border: 1px solid {c.border_strong}; border-radius: 14px; padding: 9px 11px 8px; }}
        #composer:hover {{ border-color: {c.focus}; }}
        #composerEdit {{ color: {c.text}; min-height: 60px; }}
        #composerHint {{ color: {c.text_muted}; font-size: 11px; padding-left: 7px; }}
        #primaryButton, #newButton {{ color: {c.on_accent}; background: {c.accent_fill}; border: 1px solid {c.accent_fill}; border-radius: 9px; padding: 7px 15px; min-height: 34px; font-weight: 650; }}
        #primaryButton:hover, #newButton:hover {{ background: {c.accent_hover}; border-color: {c.accent_hover}; }}
        #primaryButton:pressed, #newButton:pressed {{ background: {c.accent_pressed}; border-color: {c.accent_pressed}; }}
        #primaryButton:disabled, #newButton:disabled {{ color: {c.text_muted}; background: {c.subtle}; border-color: {c.border}; }}
        #primaryButton[busy="true"] {{ color: {c.danger}; background: {c.danger_soft}; border-color: {c.danger_soft}; }}
        #iconButton {{ background: transparent; border: 1px solid transparent; border-radius: 9px; padding: 8px; }}
        #iconButton:hover {{ background: {c.subtle}; border-color: {c.border}; }}
        #iconButton:pressed {{ background: {c.accent_soft}; }}
        #iconButton:focus {{ border-color: {c.focus}; }}
        #iconButton:disabled {{ background: transparent; }}
        #quietButton, #exampleButton {{ color: {c.text_secondary}; background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 7px 10px; }}
        #quietButton:hover {{ background: {c.subtle}; color: {c.text}; }}
        #exampleButton {{ color: {c.text}; background: {c.surface}; border-color: {c.border}; text-align: left; padding-left: 14px; }}
        #exampleButton:hover {{ background: {c.elevated}; border-color: {c.border_strong}; }}
        #sessionList {{ background: transparent; color: {c.text_secondary}; border: 0; padding: 3px 0; outline: 0; }}
        #sessionList::item {{ min-height: 24px; padding: 8px 10px; border-radius: 8px; margin: 1px 0; }}
        #sessionList::item:hover {{ background: {c.subtle}; color: {c.text}; }}
        #sessionList::item:selected {{ background: {c.accent_soft}; color: {c.text}; }}
        #libraryPanel {{ background: {c.subtle}; border: 1px solid {c.border}; border-radius: 9px; }}
        #libraryTitle {{ color: {c.text}; font-size: 12px; font-weight: 650; }}
        QCheckBox {{ color: {c.text_secondary}; spacing: 8px; padding: 3px 0; }}
        QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; border: 0; }}
        QScrollBar::handle:vertical {{ background: {c.border_strong}; border-radius: 4px; min-height: 30px; }}
        QScrollBar::handle:vertical:hover {{ background: {c.text_muted}; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: transparent; border: 0; }}
        QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{ width: 0; height: 0; border: 0; }}
        QAbstractScrollArea::corner {{ background: {c.background}; }}
        QDialog {{ background: {c.background}; }}
        #dialogTitle {{ font-family: 'Source Han Serif SC'; font-size: 20px; font-weight: 600; }}
        QDialogButtonBox QPushButton {{ color: {c.text}; background: {c.surface}; border: 1px solid {c.border}; border-radius: 8px; min-height: 32px; padding: 4px 14px; }}
        QDialogButtonBox QPushButton:hover {{ background: {c.subtle}; border-color: {c.border_strong}; }}
        """)
        icon_color = c.text_secondary
        self.theme_button.icon_name = "sun" if self.theme_name == "dark" else "moon"
        self.theme_button.setToolTip("切换到浅色外观" if self.theme_name == "dark" else "切换到深色外观")
        self.theme_button.set_icon_color(icon_color)
        self.settings_button.set_icon_color(icon_color)
        self.new_button.setIcon(svg_icon("plus", c.on_accent, 16))
        self.new_button.setIconSize(QSize(16, 16))
        self.ai_status.setText(self._ai_status_text())

    def _set_controls_from_settings(self) -> None:
        self.edition.setCurrentText(str(self.settings.get("quota_edition") or "2025"))
        self.standard.setCurrentText(str(self.settings.get("standard_edition") or "2024"))
        self.discipline.setCurrentText(str(self.settings.get("discipline") or "建筑"))

    def _ai_status_text(self) -> str:
        if self.settings.get("ai_enabled") and self.settings.get("ai_model"):
            return f"●  {provider_config(self.settings.get('ai_provider')).label} 已连接"
        return "○  AI 未连接"

    def _show_welcome(self) -> None:
        self.feed.add_welcome(["地下室外墙 4mm 厚 SBS 防水卷材", "现浇 C30 混凝土柱，泵送施工"], self.composer.set_text)

    def _refresh_sessions(self) -> None:
        if self._sidebar_loading:
            return
        self._sidebar_loading = True

        def worker() -> None:
            try:
                summaries = session_store.list_sessions()
                stats = _safe_library_stats()
                self.signals.sidebar_data.emit(summaries, stats)
            except Exception:
                self.signals.sidebar_data.emit([], {})

        threading.Thread(target=worker, name="qt-sidebar-data", daemon=True).start()

    def _on_sidebar_data(self, summaries: object, stats: object) -> None:
        self._sidebar_loading = False
        self.sessions.set_sessions(list(summaries or []))
        payload = dict(stats or {})
        if payload:
            self.library_label.setText(f"定额 {payload.get('quotas', 0):,} 条\n清单 {payload.get('bills', 0):,} 条")
        else:
            self.library_label.setText("山东资料库已内置")

    def _new_session(self) -> None:
        self._save_session()
        self._session = None
        self._active_turn_id = None
        self._follow_latest = True
        self.feed.clear_feed()
        self._show_welcome()
        self.composer.setFocus()

    def _select_session(self, session_id: str) -> None:
        if not session_id:
            return
        session = session_store.load_session(session_id)
        if session is None:
            return
        self._session = session
        self._follow_latest = True
        self.feed.clear_feed()
        for turn in session.get("turns") or []:
            self.feed.add_user(str(turn.get("query") or ""))
            snapshot = turn.get("retrieval_snapshot")
            if isinstance(snapshot, dict):
                self.feed.add_result(snapshot)
            for attempt in turn.get("ai_attempts") or []:
                if attempt.get("status") == "completed" and attempt.get("response"):
                    self.feed.add_ai(str(attempt["response"]))

    def _ensure_session(self, title: str) -> dict:
        if self._session is None:
            self._session = session_store.create_session(title[:60] or "新的检索")
        return self._session

    def _save_session(self) -> None:
        if self._session is not None:
            try:
                session_store.save_session(self._session)
            except OSError:
                log_exception("qt session save failed")

    def _send(self) -> None:
        if self._cancel is not None:
            return
        description = self.composer.text()
        if not description:
            self.composer.edit.setFocus()
            return
        if len(description) > 500:
            self.feed.add_warning("施工描述请控制在 500 字以内。", error=True)
            return
        previous = self._session.get("turns", [])[-1] if self._session and self._session.get("turns") else None
        merged = merge_clarification_context(previous.get("retrieval_snapshot"), description) if previous else None
        effective = merged[0] if merged else description
        self.composer.clear()
        self._follow_latest = True
        session = self._ensure_session(description.replace("\n", " ").strip()[:28])
        self._request_id += 1
        request_id = self._request_id
        edition = self.edition.currentText()
        standard = self.standard.currentText()
        discipline = DISCIPLINE_LABEL_TO_CODE.get(self.discipline.currentText(), "building")
        self.settings.update({"quota_edition": edition, "standard_edition": standard, "discipline": self.discipline.currentText()})
        save_settings(self.settings)
        turn = session_store.create_turn(session, description, quota_edition=edition, standard_edition=standard, discipline=discipline, request_id=request_id)
        self._active_turn_id = turn["turn_id"]
        self._pending[request_id] = {"session": session, "turn_id": turn["turn_id"], "description": effective, "ai_enabled": bool(self.settings.get("ai_enabled"))}
        self.feed.add_user(description)
        self.feed.add_status("正在查找本地资料", "按专业、清单标准和定额年度筛选候选项…")
        cancel = threading.Event()
        self._pending[request_id]["cancel"] = cancel
        self._cancel = cancel
        self._active_request_id = request_id
        self.composer.set_busy(True)
        self.composer.send_button.clicked.disconnect()
        self.composer.send_button.clicked.connect(self._cancel_active)
        job = AnalysisJob(request_id, effective, dict(self.settings), cancel)
        job.signals.local_result.connect(self.signals.local_result)
        job.signals.ai_answer.connect(self.signals.ai_answer)
        job.signals.ai_error.connect(self.signals.ai_error)
        job.signals.ai_skipped.connect(self.signals.ai_skipped)
        job.signals.search_error.connect(self.signals.search_error)
        self.pool.start(job)

    def _finish_job(self, request_id: int | None = None) -> None:
        if request_id is not None and self._active_request_id != request_id:
            return
        self._cancel = None
        self._active_request_id = None
        self.composer.set_busy(False)
        try:
            self.composer.send_button.clicked.disconnect()
        except TypeError:
            pass
        self.composer.send_button.clicked.connect(self._send)

    def _scroll_to_latest(self) -> None:
        if not self._follow_latest:
            return
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _track_scroll_position(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        self._follow_latest = bar.maximum() - value <= 24

    def _cancel_active(self) -> None:
        if self._cancel:
            self._cancel.set()
            self.feed.add_warning("本轮分析已取消，本地资料不会被修改。")
            self._finish_job()

    def _on_local_result(self, request_id: int, result: dict) -> None:
        pending = self._pending.get(request_id)
        if not pending:
            return
        session = pending["session"]
        turn_id = pending["turn_id"]
        session_store.set_turn_local_result(session, turn_id, result, ai_enabled=pending["ai_enabled"])
        self._save_session()
        self.feed.add_result(result)
        # Local evidence is actionable even when the remote AI is still
        # running. Release the composer now; the AI response remains bound to
        # this request and will be appended when it arrives.
        pending["local_ready"] = True
        self._finish_job(request_id)
        if pending["ai_enabled"]:
            self.feed.add_status("AI 正在复核", "只基于本地候选方案生成解释，不替换本地证据。")

    def _on_ai_answer(self, request_id: int, text: str, validation: dict) -> None:
        pending = self._pending.get(request_id)
        if not pending:
            return
        session_store.finish_ai_attempt(session_store_save_target(pending), pending["turn_id"], request_id=request_id, status="completed", response=text, validation=validation)
        self._save_session()
        self.feed.add_ai(text)
        self._pending.pop(request_id, None)

    def _on_ai_skipped(self, request_id: int) -> None:
        self._pending.pop(request_id, None)

    def _on_ai_error(self, request_id: int, detail: str) -> None:
        self.feed.add_warning(f"AI 暂不可用：{detail}。本地套价草案仍可继续使用。", error=True)
        self._pending.pop(request_id, None)

    def _on_search_error(self, request_id: int, detail: str) -> None:
        self.feed.add_warning(f"本地资料检索失败：{detail}", error=True)
        self._pending.pop(request_id, None)

    def _toggle_theme(self) -> None:
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.settings["theme"] = self.theme_name
        save_settings(self.settings)
        self.tokens = get_theme(self.theme_name)
        self._apply_theme()
        apply_window_chrome(self, self.tokens)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings = sanitize_settings({**self.settings, **dialog.values()})
        save_settings(self.settings)
        self.ai_status.setText(self._ai_status_text())

    def closeEvent(self, event) -> None:
        for pending in self._pending.values():
            cancel = pending.get("cancel")
            if cancel:
                cancel.set()
        self._save_session()
        event.accept()


def session_store_save_target(pending: dict) -> dict:
    return pending["session"]


def _safe_library_stats() -> dict:
    try:
        from utils.catalog import library_stats

        return dict(library_stats())
    except Exception:
        return {}


def _load_qt_fonts() -> None:
    for name in (
        "Inter-Regular.ttf",
        "Inter-Medium.ttf",
        "Inter-SemiBold.ttf",
        "Inter-Bold.ttf",
        "NotoSansSC-Regular.otf",
        "SourceHanSerifSC-Regular.otf",
        "SourceHanSerifSC-SemiBold.otf",
    ):
        path = resource_path("assets", "fonts", name)
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


def main() -> int:
    guard = SingleInstanceGuard(r"Local\ShandongQuotaAssistant.SessionWriter.v3")
    if not guard.acquire():
        return 0
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("山东定额助手")
        _load_qt_fonts()
        window = QuotaQtApp()
        window.show()
        return app.exec()
    finally:
        guard.release()


if __name__ == "__main__":
    raise SystemExit(main())
