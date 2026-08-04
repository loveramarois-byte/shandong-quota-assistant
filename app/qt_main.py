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

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, Qt, QTimer, pyqtSignal
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

from components.qt_widgets import Composer, MessageFeed, SessionList
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
        self.ai_enabled = QPushButton("启用 AI 复核")
        self.ai_enabled.setCheckable(True)
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
        self._session: dict | None = None
        self._active_turn_id: str | None = None
        self._pending: dict[int, dict] = {}
        self._build()
        self._connect_signals()
        self._apply_theme()
        QTimer.singleShot(50, lambda: apply_window_chrome(self, self.tokens))
        QTimer.singleShot(120, self._refresh_sessions)
        self._show_welcome()

    def _build(self) -> None:
        self.setWindowTitle("山东定额助手")
        self.setMinimumSize(1120, 700)
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
        content_layout.setContentsMargins(32, 24, 32, 22)
        content_layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("分析工作台")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.edition = QComboBox(); self.edition.addItems(["2025", "2016"])
        self.standard = QComboBox(); self.standard.addItems(["2024", "2013"])
        self.discipline = QComboBox(); self.discipline.addItems(list(DISCIPLINE_OPTIONS))
        for widget in (self.edition, self.standard, self.discipline):
            widget.setMinimumWidth(96)
            header.addWidget(widget)
        self.ai_status = QLabel()
        self.ai_status.setObjectName("statusPill")
        header.addWidget(self.ai_status)
        self.theme_button = QPushButton("外观")
        self.theme_button.setObjectName("quietButton")
        self.theme_button.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_button)
        settings_button = QPushButton("设置")
        settings_button.setObjectName("quietButton")
        settings_button.clicked.connect(self._open_settings)
        header.addWidget(settings_button)
        content_layout.addLayout(header)
        self.rule = QFrame(); self.rule.setFrameShape(QFrame.Shape.HLine); self.rule.setObjectName("rule")
        content_layout.addWidget(self.rule)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("feedScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.feed = MessageFeed()
        self.feed.content_added.connect(self._scroll_to_latest)
        self.scroll.setWidget(self.feed)
        content_layout.addWidget(self.scroll, 1)
        self.composer = Composer()
        content_layout.addWidget(self.composer)
        outer.addWidget(content, 1)
        self._set_controls_from_settings()

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(12)
        brand = QLabel("山东定额助手\nAI 套价工作台")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        new_button = QPushButton("＋  新建分析")
        new_button.setObjectName("newButton")
        new_button.clicked.connect(self._new_session)
        layout.addWidget(new_button)
        label = QLabel("最近分析")
        label.setObjectName("sectionLabel")
        layout.addWidget(label)
        self.sessions = SessionList()
        self.sessions.session_selected.connect(self._select_session)
        layout.addWidget(self.sessions, 1)
        self.library_label = QLabel("本地资料加载中…")
        self.library_label.setObjectName("secondaryText")
        self.library_label.setWordWrap(True)
        layout.addWidget(self.library_label)
        version = QLabel(f"山东定额 · v{APP_VERSION}")
        version.setObjectName("secondaryText")
        layout.addWidget(version)
        return sidebar

    def _connect_signals(self) -> None:
        self.composer.send_requested.connect(self._send)
        self.signals.local_result.connect(self._on_local_result)
        self.signals.ai_answer.connect(self._on_ai_answer)
        self.signals.ai_error.connect(self._on_ai_error)
        self.signals.ai_skipped.connect(self._on_ai_skipped)
        self.signals.search_error.connect(self._on_search_error)

    def _apply_theme(self) -> None:
        c = self.tokens.colors
        self.setStyleSheet(f"""
        QWidget {{ color: {c.text}; font-family: Inter, 'Microsoft YaHei UI'; font-size: 14px; }}
        QMainWindow, #root {{ background: {c.background}; }}
        #sidebar {{ background: {c.sidebar}; border-right: 1px solid {c.sidebar_border}; }}
        #brand {{ color: {c.text}; font-size: 17px; font-weight: 650; line-height: 1.35; }}
        #sectionLabel {{ color: {c.text_muted}; font-size: 12px; font-weight: 600; padding-top: 8px; }}
        #pageTitle {{ font-size: 22px; font-weight: 650; }}
        #secondaryText {{ color: {c.text_secondary}; }}
        #statusPill {{ color: {c.success}; background: {c.success_soft}; border-radius: 12px; padding: 5px 10px; font-size: 12px; }}
        #rule {{ color: {c.border}; max-height: 1px; }}
        QComboBox, QPlainTextEdit {{ background: {c.elevated}; border: 1px solid {c.border}; border-radius: 8px; padding: 8px 10px; selection-background-color: {c.accent_soft}; }}
        QComboBox:focus, QPlainTextEdit:focus {{ border-color: {c.focus}; }}
        #surfaceCard, #elevatedCard {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 10px; }}
        #elevatedCard {{ background: {c.elevated}; }}
        #userMessage {{ background: {c.user_surface}; border: 0; border-radius: 10px; }}
        #statusCard {{ background: {c.subtle}; border: 0; border-radius: 8px; }}
        #proposalRow {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 7px; }}
        #quotaLine {{ color: {c.text_secondary}; background: {c.subtle}; border-radius: 5px; padding: 6px 8px; }}
        #kicker {{ color: {c.accent}; }}
        #welcomeTitle {{ font-size: 25px; margin: 4px 0 2px; }}
        #aiText {{ line-height: 1.55; }}
        #warningText {{ color: {c.warning}; padding: 8px 4px; }}
        #errorText {{ color: {c.danger}; padding: 8px 4px; }}
        #primaryButton, #newButton {{ color: {c.on_accent}; background: {c.accent_fill}; border: 0; border-radius: 8px; padding: 8px 16px; font-weight: 650; }}
        #primaryButton:hover, #newButton:hover {{ background: {c.accent_hover}; }}
        #primaryButton:pressed, #newButton:pressed {{ background: {c.accent_pressed}; }}
        #quietButton, #exampleButton {{ color: {c.text_secondary}; background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 7px 10px; }}
        #quietButton:hover, #exampleButton:hover {{ background: {c.subtle}; color: {c.text}; }}
        #sessionList {{ background: transparent; color: {c.text_secondary}; padding: 4px 0; }}
        #sessionList::item {{ padding: 9px 10px; border-radius: 7px; margin: 1px 0; }}
        #sessionList::item:selected {{ background: {c.subtle}; color: {c.text}; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {c.border_strong}; border-radius: 5px; min-height: 28px; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        QDialog {{ background: {c.background}; }}
        #dialogTitle {{ font-size: 19px; font-weight: 650; }}
        """)
        self.ai_status.setText(self._ai_status_text())

    def _set_controls_from_settings(self) -> None:
        self.edition.setCurrentText(str(self.settings.get("quota_edition") or "2025"))
        self.standard.setCurrentText(str(self.settings.get("standard_edition") or "2024"))
        self.discipline.setCurrentText(str(self.settings.get("discipline") or "建筑"))

    def _ai_status_text(self) -> str:
        if self.settings.get("ai_enabled") and self.settings.get("ai_model"):
            return f"AI · {provider_config(self.settings.get('ai_provider')).label}"
        return "AI 未启用"

    def _show_welcome(self) -> None:
        self.feed.add_welcome(["地下室外墙 4mm 厚 SBS 防水卷材", "现浇 C30 混凝土柱，泵送施工"], self.composer.set_text)

    def _refresh_sessions(self) -> None:
        try:
            summaries = session_store.list_sessions()
            self.sessions.set_sessions(summaries)
            stats = _safe_library_stats()
            if stats:
                self.library_label.setText(f"本地资料\n定额 {stats.get('quotas', 0):,} 条 · 清单 {stats.get('bills', 0):,} 条")
        except Exception:
            self.library_label.setText("本地资料已内置")

    def _new_session(self) -> None:
        self._save_session()
        self._session = None
        self._active_turn_id = None
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
        self._cancel = cancel
        self.composer.send_button.setText("停止")
        self.composer.send_button.clicked.disconnect()
        self.composer.send_button.clicked.connect(self._cancel_active)
        job = AnalysisJob(request_id, effective, dict(self.settings), cancel)
        job.signals.local_result.connect(self.signals.local_result)
        job.signals.ai_answer.connect(self.signals.ai_answer)
        job.signals.ai_error.connect(self.signals.ai_error)
        job.signals.ai_skipped.connect(self.signals.ai_skipped)
        job.signals.search_error.connect(self.signals.search_error)
        self.pool.start(job)

    def _finish_job(self) -> None:
        self._cancel = None
        self.composer.send_button.setText("分析")
        try:
            self.composer.send_button.clicked.disconnect()
        except TypeError:
            pass
        self.composer.send_button.clicked.connect(self._send)

    def _scroll_to_latest(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

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
        if pending["ai_enabled"]:
            self.feed.add_status("AI 正在复核", "只基于本地候选方案生成解释，不替换本地证据。")
        else:
            self.feed.add_status("本地方案已就绪", "请确认候选项后再导出或进入下一轮分析。")

    def _on_ai_answer(self, request_id: int, text: str, validation: dict) -> None:
        pending = self._pending.get(request_id)
        if not pending:
            return
        session_store.finish_ai_attempt(session_store_save_target(pending), pending["turn_id"], request_id=request_id, status="completed", response=text, validation=validation)
        self._save_session()
        self.feed.add_ai(text)
        self._finish_job()

    def _on_ai_skipped(self, request_id: int) -> None:
        self._finish_job()

    def _on_ai_error(self, request_id: int, detail: str) -> None:
        self.feed.add_warning(f"AI 暂不可用：{detail}。本地套价草案仍可继续使用。", error=True)
        self._finish_job()

    def _on_search_error(self, request_id: int, detail: str) -> None:
        self.feed.add_warning(f"本地资料检索失败：{detail}", error=True)
        self._finish_job()

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
        if self._cancel:
            self._cancel.set()
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
    for name in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf"):
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
