from __future__ import annotations

import csv
import json
import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog
import zipfile
from pathlib import Path

import customtkinter as ctk

from controllers.analysis import AnalysisTaskRegistry, TaskPhase, TaskToken
from components.about_dialog import AboutDialog
from components.button import DSButton, IconButton
from components.input import Composer, FilterSelect
from components.message import MessageFeed
from components.modal import ConfirmModal
from components.settings_dialog import SettingsDialog
from components.sidebar import Sidebar
from components.toast import Toast
from themes.tokens import ThemeTokens, get_theme
from utils import sessions as session_store
from utils.ai_providers import provider_config
from utils.ai_validate import validate_ai_answer
from utils.catalog import CatalogSearchCancelled, library_stats, warm_search
from utils.ccswitch import AIRequestConfig, build_ai_request_config, call_ccswitch, is_complete_ai_text
from utils.evidence import hydrate_result_sources
from utils.fonts import load_inter_fonts
from utils.logging_setup import log_exception, setup_logging
from utils.paths import APP_VERSION, catalog_manifest_path, database_path, exports_dir, logs_dir, resource_path
from utils.result_export import confirmed_proposal_payload, proposal_csv, result_csv
from utils.ai_structured import build_structured_ai_prompt, parse_structured_ai_response, render_structured_ai_response, validate_structured_ai_response
from utils.pricing_pipeline import analyze_pricing_description, merge_clarification_context
from utils.settings import DISCIPLINE_LABEL_TO_CODE, DISCIPLINE_OPTIONS, load_settings, sanitize_settings, save_settings
from utils.single_instance import SingleInstanceGuard
from utils.svg import svg_image
from components.result import result_markdown

DISCIPLINE_CODE_TO_LABEL = {code: label for label, code in DISCIPLINE_LABEL_TO_CODE.items()}


def clean_structured_validation(validation: dict) -> dict:
    """Hide legacy free-text citation noise after the JSON proposal passes local gates."""
    cleaned = dict(validation or {})
    cleaned["warnings"] = [
        value for value in cleaned.get("warnings") or []
        if "部分关键结论未标注本地候选编号" not in str(value)
    ]
    cleaned["uncited_lines"] = []
    return cleaned

def initial_window_bounds(screen_width: int, screen_height: int, window_scaling: float) -> tuple[int, int, int, int, int, int]:
    """Return stable Tk geometry bounds without double-applying Windows DPI scaling."""
    try:
        scaling = max(1.0, float(window_scaling))
    except (TypeError, ValueError):
        scaling = 1.0
    min_physical_width = min(980, max(640, screen_width - 32))
    min_physical_height = min(680, max(520, screen_height - 32))
    physical_width = max(min_physical_width, min(1360, screen_width - 96))
    physical_height = max(min_physical_height, min(860, screen_height - 96))
    # Tk geometry already maps to the DPI-aware window coordinate space. Dividing
    # again makes a 1360px work area open at about 907px on a 150% display.
    _ = scaling
    logical_width = physical_width
    logical_height = physical_height
    logical_min_width = min_physical_width
    logical_min_height = min_physical_height
    left = max(16, (screen_width - physical_width) // 2)
    top = max(16, (screen_height - physical_height) // 2)
    return logical_width, logical_height, left, top, logical_min_width, logical_min_height


def ai_connection_state(settings: dict) -> tuple[bool, str, str]:
    """Return UI-ready AI state without performing a network request."""
    enabled = bool(settings.get("ai_enabled", False))
    config = provider_config(settings.get("ai_provider"))
    model = str(settings.get("ai_model") or "").strip()
    if enabled and model:
        return True, f"{config.label} · {model}", "AI 已连接"
    return False, "AI 未连接 · 可先使用本地资料", "连接 AI"


class QuotaApp(ctk.CTk):
    def __init__(self) -> None:
        setup_logging()
        self.log = logging.getLogger("app")
        self.settings = load_settings()
        self.theme_name = self.settings.get("theme", "light")
        self.tokens: ThemeTokens = get_theme(self.theme_name)
        load_inter_fonts(resource_path("assets", "fonts"))
        ctk.set_appearance_mode("Dark" if self.theme_name == "dark" else "Light")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.title("山东定额助手")
        try:
            self.iconbitmap(resource_path("assets", "images", "app.ico"))
        except (OSError, tk.TclError):
            pass
        try:
            window_scaling = ctk.ScalingTracker.get_window_scaling(self)
        except (AttributeError, TypeError, ValueError):
            window_scaling = 1.0
        width, height, left, top, min_width, min_height = initial_window_bounds(
            self.winfo_screenwidth(), self.winfo_screenheight(), window_scaling
        )
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.minsize(min_width, min_height)
        self.configure(fg_color=self.tokens.colors.background)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.tasks = AnalysisTaskRegistry()
        self._request_id = 0
        self._last_local: tuple[str, str, str, str | None, dict] | None = None
        self._last_panel = None
        self._last_ai_text: str | None = None
        self._active_turn_id: str | None = None
        self._turn_panels: dict[str, object] = {}
        self._turn_thinking: dict[str, object] = {}
        self.session: dict | None = None
        self._toast: Toast | None = None
        self._images: dict[str, ctk.CTkImage] = {}
        self._closing = False
        self._poll_job: str | None = None
        self._resize_job: str | None = None
        self._ai_hint_job: str | None = None
        self._content_padding = 30
        self._last_layout_size: tuple[int, int] | None = None
        self._build()
        self._refresh_ai_presentation()
        # Keep keyboard submission reliable when Windows UIA focuses an outer CTk pane.
        self.bind("<Control-k>", self._focus_composer, add="+")
        self.bind("<Control-Return>", self._send_from_window, add="+")
        self.bind("<F1>", lambda _e: self._open_about(), add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._schedule_layout_update, add="+")
        threading.Thread(target=warm_search, name="catalog-prewarm", daemon=True).start()
        threading.Thread(target=self._load_library_stats, name="library-stats", daemon=True).start()
        self._poll_job = self.after(120, self._poll_events)
        self.feed.add("assistant", "请描述工程内容、规格和施工条件。\n我会结合山东清单、定额和原书证据，直接给出套项结论。")
        if not ai_connection_state(self.settings)[0]:
            self.feed.add_warning("AI 尚未连接；当前仍可查询本地清单和定额。", action_text="连接 AI", command=self._open_settings)
        self.composer.textbox.focus_set()
        self.after(200, self._restore_latest_session)
        self.log.info("app started, version=%s", APP_VERSION)

    def _load_library_stats(self) -> None:
        started = time.perf_counter()
        try:
            stats = library_stats()
        except Exception:
            stats = {}
        self.events.put(("library_stats", stats))
        self.log.info("library stats loaded in %.1fms", (time.perf_counter() - started) * 1000)

    @property
    def colors(self):
        return self.tokens.colors

    def _icon(self, name: str, size: tuple[int, int] = (17, 17)) -> ctk.CTkImage | None:
        color = self.colors.text_secondary
        key = f"{name}:{size[0]}x{size[1]}:{color}"
        if key not in self._images:
            path = resource_path("assets", "icons", f"{name}.svg")
            if path.exists():
                try:
                    self._images[key] = svg_image(path, size, color=color)
                except Exception:
                    return None
        return self._images.get(key)

    def _build(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.sidebar = Sidebar(
            self,
            tokens=self.tokens,
            on_new=self._new_session,
            on_select_session=self._select_session,
            on_rename_session=self._rename_session,
            on_delete_session=self._delete_session,
            on_open_settings=self._open_settings,
            on_open_about=self._open_about,
            # Counts touch the 2.7GB read-only catalogue; load them after the window is usable.
            library_stats={},
            app_version=APP_VERSION,
            new_image=self._icon("plus"),
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.main = ctk.CTkFrame(self, fg_color=self.colors.background, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_rowconfigure(2, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_feed()
        self.composer = Composer(self.main, tokens=self.tokens, on_send=self._send, on_cancel=self._cancel_active_task, send_image=self._icon("send"))
        self.composer.grid(row=3, column=0, padx=self._content_padding, pady=(5, 23), sticky="ew")
        self.composer.set_enter_send(bool(self.settings.get("enter_send")))
        self.sidebar.refresh_sessions(session_store.list_sessions(), None)

    def _build_header(self) -> None:
        c = self.colors
        self.header = ctk.CTkFrame(self.main, fg_color=c.background, height=112, corner_radius=0)
        self.header.grid(row=0, column=0, padx=self._content_padding, sticky="ew")
        self.header.grid_propagate(False)
        self.header.grid_columnconfigure(0, weight=1)
        self.heading = ctk.CTkFrame(self.header, fg_color="transparent")
        self.heading.grid(row=0, column=0, sticky="w", pady=(15, 10))
        self.title_label = ctk.CTkLabel(self.heading, text="AI 定额分析", text_color=c.text, font=self.tokens.font(self.tokens.typography.title, "semibold"), anchor="w")
        self.title_label.pack(anchor="w")
        self.subtitle_label = ctk.CTkLabel(self.heading, text="正在读取 AI 连接状态", text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.meta), anchor="w")
        self.subtitle_label.pack(anchor="w", pady=(4, 0))
        self.status = self.subtitle_label
        self.controls = ctk.CTkFrame(self.header, fg_color="transparent")
        self.controls.grid(row=0, column=1, sticky="e", pady=(16, 10))
        self.ai_button = DSButton(self.controls, tokens=self.tokens, text="连接 AI", variant="primary", width=92, height=34, command=self._open_settings)
        self.ai_button.pack(side="left", padx=(0, 8))
        self.theme_button = IconButton(self.controls, tokens=self.tokens, image=self._icon("moon"), tooltip="切换深色模式", command=self._toggle_theme)
        self.theme_button.pack(side="left")

        self.context_controls = ctk.CTkFrame(self.header, fg_color="transparent")
        self.context_controls.grid(row=1, column=0, sticky="w", pady=(0, 9))
        self.context_label = ctk.CTkLabel(self.context_controls, text="分析口径", text_color=c.text_secondary, font=self.tokens.font(self.tokens.typography.caption, "semibold"))
        self.context_label.pack(side="left", padx=(0, 12))
        self.edition_label = ctk.CTkLabel(self.context_controls, text="定额", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption))
        self.edition_label.pack(side="left", padx=(0, 6))
        self.edition = FilterSelect(self.context_controls, tokens=self.tokens, values=["2025", "2016"], width=78, height=32)
        self.edition.set(str(self.settings.get("quota_edition") or "2025"))
        self.edition.pack(side="left")
        self.standard_edition_label = ctk.CTkLabel(self.context_controls, text="清单", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption))
        self.standard_edition_label.pack(side="left", padx=(12, 6))
        self.standard_edition = FilterSelect(self.context_controls, tokens=self.tokens, values=["2024", "2013"], width=78, height=32)
        self.standard_edition.set(str(self.settings.get("standard_edition") or "2024"))
        self.standard_edition.pack(side="left")
        self.discipline_label = ctk.CTkLabel(self.context_controls, text="专业", text_color=c.text_muted, font=self.tokens.font(self.tokens.typography.caption))
        self.discipline_label.pack(side="left", padx=(12, 6))
        self.discipline = FilterSelect(self.context_controls, tokens=self.tokens, values=list(DISCIPLINE_OPTIONS), width=88, height=32)
        self.discipline.set(str(self.settings.get("discipline") or "建筑"))
        self.discipline.pack(side="left")
        self.divider = ctk.CTkFrame(self.main, height=1, fg_color=c.border, corner_radius=0)
        self.divider.grid(row=1, column=0, padx=self._content_padding, sticky="ew")

    def _build_feed(self) -> None:
        c = self.colors
        self.feed = MessageFeed(self.main, tokens=self.tokens)
        self.feed.grid(row=2, column=0, padx=self._content_padding, pady=(0, 0), sticky="nsew")

    def _toggle_theme(self) -> None:
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.settings["theme"] = self.theme_name
        save_settings(self.settings)
        self.tokens = get_theme(self.theme_name)
        ctk.set_appearance_mode("Dark" if self.theme_name == "dark" else "Light")
        c = self.colors
        self.configure(fg_color=c.background)
        self.main.configure(fg_color=c.background)
        self.header.configure(fg_color=c.background)
        self.heading.configure(fg_color="transparent")
        self.controls.configure(fg_color="transparent")
        self.context_controls.configure(fg_color="transparent")
        self.divider.configure(fg_color=c.border)
        self.sidebar.apply_theme(self.tokens)
        self.feed.apply_theme(self.tokens)
        self.composer.apply_theme(self.tokens)
        self.edition.apply_theme(self.tokens)
        self.standard_edition.apply_theme(self.tokens)
        self.discipline.apply_theme(self.tokens)
        self.theme_button.apply_theme(self.tokens)
        self.theme_button.tooltip = "切换浅色模式" if self.theme_name == "dark" else "切换深色模式"
        self.theme_button.configure(image=self._icon("sun" if self.theme_name == "dark" else "moon"))
        self.ai_button.apply_theme(self.tokens)
        self.sidebar.set_new_image(self._icon("plus"))
        self.composer.set_send_image(self._icon("send"))
        for label, color, font in (
            (self.title_label, c.text, self.tokens.font(self.tokens.typography.title, "semibold")),
            (self.subtitle_label, c.text_secondary, self.tokens.font(self.tokens.typography.meta)),
            (self.context_label, c.text_secondary, self.tokens.font(self.tokens.typography.caption, "semibold")),
            (self.edition_label, c.text_muted, self.tokens.font(self.tokens.typography.caption)),
            (self.standard_edition_label, c.text_muted, self.tokens.font(self.tokens.typography.caption)),
            (self.discipline_label, c.text_muted, self.tokens.font(self.tokens.typography.caption)),
            (self.status, c.text_secondary, self.tokens.font(self.tokens.typography.meta)),
        ):
            label.configure(text_color=color, font=font)
        self._refresh_ai_presentation()

    def _refresh_ai_presentation(self) -> None:
        connected, subtitle, action = ai_connection_state(self.settings)
        self.subtitle_label.configure(text=subtitle, text_color=self.colors.success if connected else self.colors.text_secondary)
        self.ai_button.variant = "secondary" if connected else "primary"
        self.ai_button._normal_text = action
        self.ai_button.configure(text=action)
        self.ai_button.set_enabled(True)
        self.composer.set_ai_mode(connected)

    def _set_status(self, text: str, tone: str = "neutral") -> None:
        c = self.colors
        color = c.danger if tone == "error" else (c.accent if tone == "busy" else c.text_secondary)
        self.status.configure(text=text, text_color=color)
        # Keep the taskbar state legible even when CustomTkinter controls are not exposed to UIA.
        title_suffix = ""
        if tone == "busy":
            title_suffix = " · 分析中"
        elif tone == "error":
            title_suffix = " · AI 未连接"
        elif "分析完成" in text:
            title_suffix = " · 已完成"
        elif "新分析" in text:
            title_suffix = " · 新分析"
        self.title(f"山东定额助手{title_suffix}")

    def _focus_composer(self, _event=None) -> str:
        self.composer.textbox.focus_set()
        return "break"

    def _send_from_window(self, _event=None) -> str:
        self._send()
        return "break"

    def _show_toast(self, text: str, kind: str = "info") -> None:
        if self._toast:
            self._toast.destroy()
        self._toast = Toast(self, tokens=self.tokens, text=text, kind=kind)
        self._toast.place(relx=0.5, y=22, anchor="n")
        self.after(2800, self._hide_toast)

    def _hide_toast(self) -> None:
        if self._toast:
            self._toast.destroy()
            self._toast = None

    def _refresh_task_controls(self) -> None:
        session_id = str(self.session.get("id") or "") if self.session else None
        searching = self.tasks.searching()
        ai_task = self.tasks.latest_ai(session_id)
        self.sidebar.set_busy(searching is not None)
        self.composer.set_busy(searching is not None)
        self.composer.set_ai_cancel_available(
            searching is not None or ai_task is not None,
            search_running=searching is not None,
        )
        if ai_task is not None and self._ai_hint_job is None:
            self._ai_hint_job = self.after(18000, self._show_ai_wait_hint)
        elif ai_task is None and self._ai_hint_job:
            self.after_cancel(self._ai_hint_job)
            self._ai_hint_job = None

    def _show_ai_wait_hint(self) -> None:
        self._ai_hint_job = None
        session_id = str(self.session.get("id") or "") if self.session else None
        if self.tasks.latest_ai(session_id) is not None:
            self._set_status("AI 正在结合本地依据判断，可能需要几十秒…", "busy")

    # ------------------------------------------------------------------ sessions

    def _refresh_session_list(self) -> None:
        active = self.session.get("id") if self.session else None
        self.sidebar.refresh_sessions(session_store.list_sessions(), active)

    def _ensure_session(self, title_hint: str = "") -> dict | None:
        if self.session is None:
            try:
                self.session = session_store.create_session((title_hint or "新的 AI 分析")[:60])
            except (OSError, ValueError):
                log_exception("session create failed")
                self._set_status("记录保存失败", "error")
                self._show_toast("无法创建本地记录，请检查磁盘空间和目录权限", "error")
                return None
            self._refresh_session_list()
            self.sidebar.mark_active(self.session["id"])
        return self.session

    def _save_current_session(self) -> bool:
        if self.session:
            try:
                session_store.save_session(self.session)
            except session_store.SessionDeletedError:
                self.session = None
                self._active_turn_id = None
                return False
            except (OSError, ValueError):
                log_exception("session save failed")
                if not self._closing:
                    self._set_status("记录未保存", "error")
                    self._show_toast("本地记录保存失败，请检查磁盘空间和目录权限", "error")
                return False
            self._refresh_session_list()
        return True

    def _new_session(self) -> None:
        if self.tasks.searching() is not None:
            return
        self.session = None
        self._last_local = None
        self._last_panel = None
        self._last_ai_text = None
        self._active_turn_id = None
        self._turn_panels.clear()
        self._turn_thinking.clear()
        self.feed.clear()
        self.sidebar.mark_active(None)
        self.composer.clear()
        self.feed.add("assistant", "请描述工程内容、规格和施工条件，我会给出新的 AI 套项结论。")
        if not ai_connection_state(self.settings)[0]:
            self.feed.add_warning("AI 尚未连接；当前仍可查询本地清单和定额。", action_text="连接 AI", command=self._open_settings)
        self._refresh_ai_presentation()
        self._refresh_task_controls()
        self.composer.textbox.focus_set()

    def _select_session(self, session_id: str) -> bool:
        if self.tasks.searching() is not None:
            self._show_toast("当前检索尚未结束，请先取消或等待完成", "info")
            return False
        session = session_store.load_session(session_id)
        if session is None:
            self._show_toast("会话读取失败，可能已损坏", "error")
            return False
        self.session = session
        self._last_local = None
        self._last_panel = None
        self._last_ai_text = None
        self._active_turn_id = None
        self._turn_panels.clear()
        self._turn_thinking.clear()
        self.feed.clear()
        turns = session.get("turns") or []
        latest_ai_card = None
        for turn in turns:
            turn_id = str(turn.get("turn_id") or "")
            query = str(turn.get("query") or "")
            if query:
                self.feed.add("user", query)
            attempts = turn.get("ai_attempts") or []
            completed_attempt = next((attempt for attempt in reversed(attempts) if attempt.get("response")), None)
            stored_result = turn.get("retrieval_snapshot")
            result = hydrate_result_sources(stored_result) if isinstance(stored_result, dict) else stored_result
            panel = None
            if isinstance(result, dict):
                panel = self.feed.add_result(
                    result,
                    on_primary_changed=lambda kind, item, tid=turn_id: self._primary_changed(tid, kind, item),
                    on_export=self._export_result,
                    on_clarify=self._clarification_selected,
                    collapsed=bool(completed_attempt or self.settings.get("ai_enabled", False)),
                )
                panel.restore_primary(turn.get("human_selections"))
                self._turn_panels[turn_id] = panel
                self._last_panel = panel
                self._last_local = (
                    query,
                    str(result.get("quota_edition") or self.edition.get()),
                    str(result.get("standard_edition") or self.standard_edition.get()),
                    result.get("discipline"),
                    result,
                )
            if completed_attempt:
                ai_text = str(completed_attempt.get("response") or "")
                if is_complete_ai_text(ai_text):
                    stored_validation = completed_attempt.get("validation") if isinstance(completed_attempt.get("validation"), dict) else {}
                    validation = validate_ai_answer(ai_text, result) if isinstance(result, dict) else dict(stored_validation)
                    if stored_validation.get("structured_valid"):
                        validation["structured_valid"] = True
                        validation["structured"] = stored_validation.get("structured")
                        validation = clean_structured_validation(validation)
                        if panel is not None:
                            panel.apply_ai_proposals(stored_validation.get("structured"))
                    latest_ai_card = self.feed.add_ai_answer(ai_text, validation, on_copy=self._copy_text, before=panel)
                    self._last_ai_text = ai_text
                else:
                    latest_ai_card = self.feed.add_warning(
                        "这条 AI 回答未完整保存，请重新生成后再使用。",
                        action_text="重新生成",
                        command=lambda tid=turn_id: self._retry_ai(tid),
                        before=panel,
                    )
            self._active_turn_id = turn_id or self._active_turn_id
        latest_result = (turns[-1].get("retrieval_snapshot") if turns else None) or {}
        if latest_result.get("quota_edition"):
            self.edition.set(str(latest_result["quota_edition"]))
        if latest_result.get("standard_edition"):
            self.standard_edition.set(str(latest_result["standard_edition"]))
        self._set_status("AI 对话已恢复 · 本地依据就绪")
        self.sidebar.mark_active(session_id)
        if latest_ai_card is not None:
            self.feed.scroll_to_entry(latest_ai_card, 120)
        else:
            self.feed.scroll_to_end(120)
        self._refresh_task_controls()
        return True

    def _rename_session(self, session_id: str) -> None:
        dialog = ctk.CTkInputDialog(text="输入新的分析名称：", title="重命名分析")
        value = dialog.get_input()
        if not value or not value.strip():
            return
        if session_store.rename_session(session_id, value.strip()):
            if self.session and self.session.get("id") == session_id:
                self.session["title"] = value.strip()[:60]
            self._refresh_session_list()
        else:
            self._show_toast("重命名失败", "error")

    def _delete_session(self, session_id: str) -> None:
        def do_delete() -> None:
            is_current = bool(self.session and self.session.get("id") == session_id)
            self.tasks.close_session(session_id)
            if not session_store.delete_session(session_id):
                self._show_toast("删除失败，请重试", "error")
                return
            if is_current:
                self.session = None
                self._new_session()
            self._refresh_session_list()
            self._refresh_task_controls()
            self._show_toast("已删除该分析", "info")

        ConfirmModal(self, tokens=self.tokens, title="删除分析", detail="该记录将移到本地回收区，并立即从历史列表隐藏。确认删除？", on_confirm=do_delete)

    def _restore_latest_session(self) -> None:
        # Do not yank the screen away from a user who already started working.
        if self.tasks.searching() is not None or self.session is not None or self._request_id > 0:
            return
        sessions = session_store.list_sessions()
        if sessions:
            self._select_session(sessions[0]["id"])

    def _primary_changed(self, turn_id: str, kind: str, item: dict) -> None:
        session = self._ensure_session()
        if session is None:
            return
        if kind == "proposals":
            session_store.set_turn_proposals(session, turn_id, list(item.get("proposals") or []))
        else:
            session_store.set_turn_selection(session, turn_id, kind, item)
        self._save_current_session()

    def _clarification_selected(self, _question: dict, option: str) -> None:
        self.composer.set_text(option)
        self._show_toast("已填入补充条件，可直接发送", "info")

    # ------------------------------------------------------------------ sending

    def _send(self) -> None:
        if self.tasks.searching() is not None:
            return
        description = self.composer.get_text()
        if not description:
            self.composer.show_error()
            self.composer.textbox.focus_set()
            return
        if self.composer.is_over_limit():
            self.composer.show_error()
            self._show_toast(f"输入过长，请控制在 {Composer.MAX_CHARS} 字以内", "error")
            return
        effective_description = description
        clarification_parent_turn_id = None
        if self.session and self.session.get("turns"):
            previous_turn = self.session["turns"][-1]
            merged = merge_clarification_context(previous_turn.get("retrieval_snapshot"), description)
            if merged:
                effective_description, _answered_question_id = merged
                clarification_parent_turn_id = str(previous_turn.get("turn_id") or "")
        self.composer.remember_sent(description)
        self.composer.clear()
        session = self._ensure_session(description.replace("\n", " ").strip()[:28])
        if session is None:
            return
        edition = self.edition.get()
        standard_edition = self.standard_edition.get()
        discipline = DISCIPLINE_LABEL_TO_CODE.get(self.discipline.get(), "building")
        self.settings["quota_edition"] = edition
        self.settings["standard_edition"] = standard_edition
        self.settings["discipline"] = self.discipline.get()
        save_settings(self.settings)
        self._request_id += 1
        request_id = self._request_id
        turn = session_store.create_turn(
            session,
            description,
            quota_edition=edition,
            standard_edition=standard_edition,
            discipline=discipline,
            request_id=request_id,
        )
        turn_id = turn["turn_id"]
        if clarification_parent_turn_id:
            turn["context_parent_turn_id"] = clarification_parent_turn_id
            turn["effective_query"] = effective_description
        session_id = session["id"]
        self._active_turn_id = turn_id
        self.feed.add("user", description)
        if not self._save_current_session():
            try:
                session.get("turns", []).remove(turn)
            except ValueError:
                pass
            self.feed.add_warning("本轮未能写入本地记录，检索没有启动。请释放磁盘空间或修复目录权限后重试。")
            return
        cancel = threading.Event()
        revision = int(session.get("revision") or 0)
        ai_enabled = bool(self.settings.get("ai_enabled", False))
        ai_config = build_ai_request_config(self.settings)
        self.tasks.start(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            revision=revision,
            cancel_event=cancel,
        )
        self._last_local = None
        self._last_panel = None
        self._last_ai_text = None
        self._set_status("查库中…", "busy")
        self._refresh_task_controls()
        threading.Thread(target=self._worker, args=(request_id, revision, cancel, session_id, turn_id, effective_description, edition, standard_edition, discipline, ai_enabled, ai_config), daemon=True).start()

    def _worker(
        self,
        request_id: int,
        revision: int,
        cancel: threading.Event,
        session_id: str,
        turn_id: str,
        description: str,
        edition: str,
        standard_edition: str,
        discipline: str | None,
        ai_enabled: bool,
        ai_config: AIRequestConfig,
    ) -> None:
        try:
            result = analyze_pricing_description(
                description,
                quota_edition=edition,
                standard_edition=standard_edition,
                discipline=discipline,
                limit=6,
                cancel_event=cancel,
            )
            self.log.info("search done backend=%s local_ms=%s", result.get("search_backend"), (result.get("timing") or {}).get("local_ms"))
            # Show local evidence as soon as SQLite returns; the network call must never hide it.
            if cancel.is_set():
                return
            self.events.put(("local", (request_id, cancel, {
                "description": description,
                "session_id": session_id,
                "turn_id": turn_id,
                "revision": revision,
                "edition": edition,
                "standard_edition": standard_edition,
                "discipline": discipline,
                "ai_enabled": ai_enabled,
                "ai_model": ai_config.model,
                "result": result,
            })))
            self._run_ai(request_id, revision, cancel, session_id, turn_id, description, result, ai_enabled, ai_config)
        except CatalogSearchCancelled:
            return
        except Exception as exc:
            log_exception("search failed")
            if not cancel.is_set():
                self.events.put(("error", (request_id, cancel, {"session_id": session_id, "turn_id": turn_id, "revision": revision, "message": self._friendly_search_error(str(exc))})))

    def _run_ai(self, request_id: int, revision: int, cancel: threading.Event, session_id: str, turn_id: str, description: str, result: dict, ai_enabled: bool, ai_config: AIRequestConfig) -> None:
        if cancel.is_set():
            return
        if not ai_enabled:
            if not cancel.is_set():
                self.events.put(("ai_skipped", (request_id, cancel, {"session_id": session_id, "turn_id": turn_id, "revision": revision})))
            return
        try:
            started = time.perf_counter()
            raw_response = call_ccswitch(
                build_structured_ai_prompt(description, result),
                config=ai_config,
            )
            self.log.info("ai done ai_ms=%s", round((time.perf_counter() - started) * 1000, 1))
            structured = parse_structured_ai_response(raw_response)
            structured_validation = validate_structured_ai_response(structured, result)
            if not structured_validation.get("valid"):
                detail = "；".join(structured_validation.get("errors") or [])
                raise ValueError("AI 结构化方案未通过本地校验：" + (detail or "结果不合法"))
            structured = structured_validation.get("structured") or structured
            ai_text = render_structured_ai_response(structured, result)
            validation = validate_ai_answer(ai_text, result)
            validation["structured_valid"] = True
            validation["structured"] = structured
            validation = clean_structured_validation(validation)
            if not cancel.is_set():
                self.events.put(("answer", (request_id, cancel, {"session_id": session_id, "turn_id": turn_id, "revision": revision, "text": ai_text, "validation": validation})))
        except Exception as exc:
            log_exception("ai failed")
            if not cancel.is_set():
                self.events.put(("ai_error", (request_id, cancel, {"session_id": session_id, "turn_id": turn_id, "revision": revision, "message": self._friendly_ai_error(str(exc))})))

    def _retry_ai(self, turn_id: str | None = None) -> None:
        if self.tasks.searching() is not None or not self.session:
            return
        target_turn_id = turn_id or self._active_turn_id
        turn = session_store.find_turn(self.session, target_turn_id)
        if turn is None or not isinstance(turn.get("retrieval_snapshot"), dict):
            self._show_toast("该轮没有可重试的本地方案", "error")
            return
        session_id = str(self.session["id"])
        if self.tasks.for_turn(session_id, str(target_turn_id)) is not None:
            self._show_toast("该轮 AI 仍在运行", "info")
            return
        description = str(turn.get("query") or "")
        result = hydrate_result_sources(turn["retrieval_snapshot"]) or turn["retrieval_snapshot"]
        ai_enabled = bool(self.settings.get("ai_enabled", False))
        if not ai_enabled:
            self._show_toast("请先在设置中启用 AI", "info")
            return
        ai_config = build_ai_request_config(self.settings)
        self._request_id += 1
        request_id = self._request_id
        attempt = session_store.start_ai_attempt(
            self.session,
            str(target_turn_id),
            request_id=request_id,
            model=ai_config.model,
        )
        if not self._save_current_session():
            try:
                turn.get("ai_attempts", []).remove(attempt)
            except ValueError:
                pass
            return
        cancel = threading.Event()
        revision = int(self.session.get("revision") or 0)
        self.tasks.start(
            session_id=session_id,
            turn_id=str(target_turn_id),
            request_id=request_id,
            revision=revision,
            cancel_event=cancel,
            phase=TaskPhase.AI_RUNNING,
        )
        self._active_turn_id = str(target_turn_id)
        panel = self._turn_panels.get(str(target_turn_id))
        self._clear_turn_thinking(str(target_turn_id))
        self._turn_thinking[str(target_turn_id)] = self.feed.add_ai_thinking(before=panel)
        self._set_status("本地套价草案已保留 · AI 重试中", "busy")
        self._refresh_task_controls()
        threading.Thread(target=self._run_ai, args=(request_id, revision, cancel, session_id, str(target_turn_id), description, result, ai_enabled, ai_config), daemon=True).start()

    def _cancel_active_task(self) -> None:
        session_id = str(self.session.get("id") or "") if self.session else None
        task = self.tasks.searching() or self.tasks.latest_ai(session_id)
        if task is None:
            return
        phase = task.phase
        request_id = task.token.request_id
        self.tasks.cancel(request_id)
        if self.session and self.session.get("id") == task.token.session_id:
            if phase == TaskPhase.SEARCHING:
                session_store.set_turn_status(self.session, task.token.turn_id, "cancelled")
            else:
                session_store.finish_ai_attempt(self.session, task.token.turn_id, request_id=request_id, status="cancelled")
            self._save_current_session()
        self.tasks.finish(request_id, TaskPhase.CLOSED)
        self._refresh_task_controls()
        if phase == TaskPhase.SEARCHING:
            self._set_status("本地检索已取消")
            self._show_toast("检索已取消", "info")
            self.feed.add_warning("本轮本地检索已取消，可修改条件后重新分析。")
        else:
            self._clear_turn_thinking(task.token.turn_id)
            self._set_status("本地套价草案已返回 · AI 已取消")
            self._show_toast("AI 已取消，本地方案与依据仍可用", "info")
            self.feed.add_warning(
                "AI 分析已取消；本地方案与资料依据仍可继续复核。",
                action_text="重试 AI",
                command=lambda tid=task.token.turn_id: self._retry_ai(tid),
            )

    def _friendly_ai_error(self, detail: str) -> str:
        config = provider_config(self.settings.get("ai_provider"))
        provider = config.key
        label = config.label
        lowered = detail.lower()
        if "额度不足" in detail or "quota" in lowered or "balance" in lowered:
            if provider == "ccswitch":
                action = "请在 ccSwitch 切换可用渠道后重试"
            else:
                action = f"请到 {label} 控制台检查余额或额度后重试"
            return f"AI 暂不可用：{label} 额度不足。{action}；本地方案与依据仍可使用。"
        if "熔断" in detail or "circuit" in lowered or "no available" in lowered:
            if provider == "ccswitch":
                action = "请恢复或切换 ccSwitch 渠道后重试"
            else:
                action = "请稍后重试，或在设置中重新获取模型"
            return f"AI 暂不可用：{label} 当前没有可用模型。{action}；本地方案与依据仍可使用。"
        if "403" in detail or "401" in detail:
            return f"AI 暂不可用：{label} 拒绝了请求。请检查 API Key 和账号权限后重试；本地方案与依据仍可使用。"
        if "timed out" in lowered or "timeout" in lowered or "超时" in detail:
            return f"AI 暂不可用：{label} 请求超时。请稍后重试；本地方案与依据仍可使用。"
        return f"AI 暂不可用：{label} 请求未完成。请在设置中测试连接后重试；本地方案与依据仍可使用。"

    @staticmethod
    def _friendly_search_error(detail: str) -> str:
        if "空" in detail or "query" in detail.lower():
            return "没有可检索的施工描述，请补充做法、规格或工程条件。"
        if "过长" in detail:
            return "施工描述过长，请精简到 500 字以内。"
        return "本地资料检索失败，请检查资料库路径后重试。"

    # ------------------------------------------------------------------ export

    def _copy_text(self, text: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._show_toast("已复制到剪贴板", "info")
        except tk.TclError:
            pass

    def _export_result(self, fmt: str, panel) -> None:
        result = panel.current_result()
        selections = {"primary": {kind: entry.get("item") for kind, entry in panel.primary.items()}}
        if fmt == "candidate_copy":
            text = panel.pricing_text()
            if not text.strip():
                self._show_toast("请先确认至少一个套价方案", "error")
                return
            self._copy_text(text)
            return
        default_dir = exports_dir()
        if fmt == "excel":
            rows = proposal_csv(result, confirmed_only=True) if result.get("proposals") else result_csv(result)
            if len(rows) <= 1:
                self._show_toast("请先确认至少一个套价方案", "error")
                return
            path = filedialog.asksaveasfilename(parent=self, title="导出套价方案", defaultextension=".csv", initialdir=str(default_dir), initialfile="已确认套价方案.csv", filetypes=(("CSV 表格", "*.csv"),))
            if not path:
                return
            try:
                with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.writer(handle)
                    for row in rows:
                        writer.writerow(row)
                self._show_toast(f"表格已导出：{Path(path).name}", "info")
            except OSError:
                self._show_toast("导出失败，请检查目录权限", "error")
            return
        if fmt == "json":
            payload = confirmed_proposal_payload(result)
            if not payload["proposals"]:
                self._show_toast("请先确认至少一个套价方案", "error")
                return
            path = filedialog.asksaveasfilename(parent=self, title="导出套价方案", defaultextension=".json", initialdir=str(default_dir), initialfile="已确认套价方案.json", filetypes=(("JSON", "*.json"),))
            if not path:
                return
            try:
                Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                self._show_toast(f"方案已导出：{Path(path).name}", "info")
            except OSError:
                self._show_toast("导出失败，请检查目录权限", "error")
            return
        path = filedialog.asksaveasfilename(parent=self, title="导出分析记录", defaultextension=".md", initialdir=str(default_dir), initialfile="定额分析记录.md", filetypes=(("Markdown", "*.md"), ("纯文本", "*.txt")))
        if not path:
            return
        try:
            content = result_markdown(result, selections, self._last_ai_text)
            Path(path).write_text(content, encoding="utf-8")
            self._show_toast(f"记录已导出：{Path(path).name}", "info")
        except OSError:
            self._show_toast("导出失败，请检查目录权限", "error")

    # ------------------------------------------------------------------ dialogs

    def _open_settings(self) -> None:
        SettingsDialog(self, tokens=self.tokens, settings=dict(self.settings), on_save=self._save_settings)

    def _save_settings(self, updates: dict) -> None:
        self.settings = sanitize_settings({**self.settings, **updates})
        save_settings(self.settings)
        self.edition.set(str(self.settings.get("quota_edition") or "2025"))
        self.standard_edition.set(str(self.settings.get("standard_edition") or "2024"))
        self.discipline.set(str(self.settings.get("discipline") or "建筑"))
        self.composer.set_enter_send(bool(self.settings.get("enter_send")))
        self._refresh_ai_presentation()
        self._show_toast("AI 设置已保存", "info")

    def _open_about(self) -> None:
        try:
            db_path = str(database_path())
        except FileNotFoundError:
            db_path = "未找到资料库"
        manifest = {}
        manifest_path = catalog_manifest_path()
        if manifest_path:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = {}
        build_id = manifest.get("catalog_build_id") or "未知构建"
        schema_version = manifest.get("catalog_schema_version") or "-"
        distribution_authorized = bool((manifest.get("database") or {}).get("distribution_authorized"))
        info = {
            "app_version": APP_VERSION,
            "database": db_path,
            "library": f"山东 2016 / 2025 定额 · 2013 / 2024 清单 · {build_id} · schema {schema_version}",
            "data_note": "资料库分发授权已登记" if distribution_authorized else "当前资料库未登记分发授权，仅限受控内部评估；不得对外复制或发布。",
            "search_backend": "fts（可用 LIKE 回退）",
            "logs": str(logs_dir()),
        }
        AboutDialog(self, tokens=self.tokens, info=info, on_export_diagnostics=self._export_diagnostics)

    def _export_diagnostics(self) -> None:
        target = exports_dir() / f"诊断包_{time.strftime('%Y%m%d_%H%M%S')}.zip"
        try:
            try:
                db_text = str(database_path())
            except FileNotFoundError:
                db_text = "未找到资料库"
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
                log_file = logs_dir() / "app.log"
                if log_file.exists():
                    bundle.write(log_file, "app.log")
                bundle.writestr("version.txt", f"app_version={APP_VERSION}\ndatabase={db_text}\n")
                recent = session_store.list_sessions()[:10]
                lines = [f"{item['id']}\t{item['title']}\t{time.strftime('%Y-%m-%d %H:%M', time.localtime(item['updated_at']))}" for item in recent]
                bundle.writestr("recent_sessions.txt", "\n".join(lines))
            self._show_toast(f"诊断包已导出：{target.name}", "info")
        except (OSError, FileNotFoundError):
            self._show_toast("诊断包导出失败", "error")

    # ------------------------------------------------------------------ events

    def _event_session(self, session_id: str) -> tuple[dict | None, bool]:
        is_current = bool(self.session and self.session.get("id") == session_id)
        return (self.session if is_current else session_store.load_session(session_id), is_current)

    def _save_event_session(self, session: dict, *, is_current: bool) -> bool:
        try:
            session_store.save_session(session)
        except session_store.SessionDeletedError:
            self.tasks.close_session(str(session.get("id") or ""))
            return False
        except (OSError, ValueError):
            self.tasks.close_session(str(session.get("id") or ""))
            log_exception("event session save failed")
            if is_current:
                self._set_status("记录未保存", "error")
                self._show_toast("结果未能写入本地记录，请检查磁盘空间和目录权限", "error")
                self.feed.add_warning("本轮结果因本地存储失败未被接纳；修复存储问题后请重新分析。")
            return False
        if is_current:
            self._refresh_session_list()
        return True

    def _clear_turn_thinking(self, turn_id: str) -> None:
        thinking = self._turn_thinking.pop(str(turn_id), None)
        if thinking is not None:
            self.feed.remove_entry(thinking)

    def _poll_events(self) -> None:
        if self._closing:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "library_stats":
                    if not self._closing:
                        self.sidebar.set_library_stats(payload)
                    continue
                request_id, cancel, value = payload
                if not isinstance(value, dict):
                    continue
                session_id = str(value.get("session_id") or "")
                turn_id = str(value.get("turn_id") or "")
                token = TaskToken(session_id, turn_id, int(request_id), int(value.get("revision") or -1))
                task = self.tasks.accepts(token)
                if task is None or cancel.is_set():
                    continue
                event_session, is_current = self._event_session(session_id)
                if event_session is None or session_store.find_turn(event_session, turn_id) is None:
                    self.tasks.finish(request_id, TaskPhase.CLOSED)
                    continue
                is_foreground_turn = bool(is_current and self._active_turn_id == turn_id)
                if kind == "local":
                    ai_enabled = bool(value.get("ai_enabled", False))
                    result = value["result"]
                    if result.get("discipline_auto_switched"):
                        turn = session_store.find_turn(event_session, turn_id)
                        if turn is not None:
                            turn["requested_discipline"] = result.get("requested_discipline")
                            turn["discipline"] = result.get("discipline")
                        if is_current:
                            label = DISCIPLINE_CODE_TO_LABEL.get(str(result.get("discipline") or ""), "")
                            if label:
                                self.discipline.set(label)
                                self.settings["discipline"] = label
                                try:
                                    save_settings(self.settings)
                                except OSError:
                                    log_exception("auto discipline setting save failed")
                                self._show_toast(f"已自动切换到{label}专业", "info")
                    session_store.set_turn_local_result(
                        event_session,
                        turn_id,
                        result,
                        ai_enabled=ai_enabled,
                    )
                    if ai_enabled:
                        session_store.start_ai_attempt(
                            event_session,
                            turn_id,
                            request_id=request_id,
                            model=str(value.get("ai_model") or ""),
                        )
                        self.tasks.transition(request_id, TaskPhase.AI_RUNNING)
                    else:
                        self.tasks.finish(request_id, TaskPhase.LOCAL_READY)
                    if not self._save_event_session(event_session, is_current=is_current):
                        continue
                    if is_current:
                        self._last_local = (
                            value["description"],
                            value["edition"],
                            value["standard_edition"],
                            result.get("discipline") or value["discipline"],
                            result,
                        )
                        status = "本地套价草案已返回 · AI 分析中，可能需要几十秒" if ai_enabled else "本地套价草案已返回"
                        self._set_status(status, "busy" if ai_enabled else "neutral")
                        panel = self.feed.add_result(
                            result,
                            on_primary_changed=lambda selected_kind, item, tid=turn_id: self._primary_changed(tid, selected_kind, item),
                            on_export=self._export_result,
                            on_clarify=self._clarification_selected,
                            collapsed=ai_enabled,
                        )
                        self._turn_panels[turn_id] = panel
                        self._last_panel = panel
                        self._active_turn_id = turn_id
                        if ai_enabled:
                            self._clear_turn_thinking(turn_id)
                            self._turn_thinking[turn_id] = self.feed.add_ai_thinking(before=panel)
                    self._refresh_task_controls()
                    continue
                if kind == "ai_error":
                    self._clear_turn_thinking(turn_id)
                    session_store.finish_ai_attempt(event_session, turn_id, request_id=request_id, status="error")
                    self.tasks.finish(request_id, TaskPhase.ERROR)
                    if self._save_event_session(event_session, is_current=is_current) and is_current:
                        if is_foreground_turn:
                            self._set_status("本地套价草案已返回 · AI 未连接", "error")
                            self._show_toast("AI 暂不可用，已保留本地方案与依据", "info")
                        self.feed.add_warning(
                            str(value.get("message") or "AI 请求失败"),
                            action_text="重试 AI",
                            command=lambda tid=turn_id: self._retry_ai(tid),
                            before=self._turn_panels.get(turn_id),
                        )
                elif kind == "ai_skipped":
                    self._clear_turn_thinking(turn_id)
                    session_store.set_turn_status(event_session, turn_id, "local_ready")
                    self.tasks.finish(request_id, TaskPhase.LOCAL_READY)
                    if self._save_event_session(event_session, is_current=is_current) and is_foreground_turn:
                        self._set_status("分析完成 · 仅本地结果（AI 已在设置中关闭）")
                elif kind == "error":
                    self._clear_turn_thinking(turn_id)
                    session_store.set_turn_status(event_session, turn_id, "error")
                    self.tasks.finish(request_id, TaskPhase.ERROR)
                    if self._save_event_session(event_session, is_current=is_current) and is_current:
                        self._set_status("检索失败", "error")
                        self._show_toast(str(value.get("message") or "本地检索失败"), "error")
                        self.feed.add_warning(str(value.get("message") or "本地检索失败"))
                else:
                    self._clear_turn_thinking(turn_id)
                    ai_text = str(value.get("text") or "")
                    validation = value.get("validation") or {}
                    session_store.finish_ai_attempt(
                        event_session,
                        turn_id,
                        request_id=request_id,
                        status="completed",
                        response=ai_text,
                        validation=validation,
                    )
                    self.tasks.finish(request_id, TaskPhase.LOCAL_READY)
                    if self._save_event_session(event_session, is_current=is_current) and is_current:
                        if is_foreground_turn:
                            self._set_status("AI 分析完成 · 原书证据已校验")
                        self._last_ai_text = ai_text
                        panel = self._turn_panels.get(turn_id)
                        if panel is not None and validation.get("structured_valid"):
                            panel.apply_ai_proposals(validation.get("structured"))
                        self.feed.add_ai_answer(
                            ai_text,
                            validation,
                            on_copy=self._copy_text,
                            before=panel,
                        )
                self._refresh_task_controls()
        except queue.Empty:
            pass
        if not self._closing:
            try:
                self._poll_job = self.after(120, self._poll_events)
            except tk.TclError:
                self._poll_job = None

    def _schedule_layout_update(self, event=None) -> None:
        if self._closing or (event is not None and event.widget is not self):
            return
        size = (event.width, event.height) if event is not None else (self.winfo_width(), self.winfo_height())
        if size == self._last_layout_size:
            return
        self._last_layout_size = size
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._apply_responsive_layout)

    def _apply_responsive_layout(self) -> None:
        self._resize_job = None
        padding = 22 if self.winfo_width() < 1120 else 30
        if padding == self._content_padding:
            return
        self._content_padding = padding
        self.header.grid_configure(padx=padding)
        self.divider.grid_configure(padx=padding)
        self.feed.grid_configure(padx=padding)
        self.composer.grid_configure(padx=padding, pady=(5, 19 if padding == 22 else 23))

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.tasks.close_all()
        try:
            self._save_current_session()
        except Exception:
            pass
        if self._ai_hint_job:
            try:
                self.after_cancel(self._ai_hint_job)
            except tk.TclError:
                pass
            self._ai_hint_job = None
        for job in (self._poll_job, self._resize_job):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self.log.info("app closed")
        self.destroy()


def main() -> int:
    guard = SingleInstanceGuard(r"Local\ShandongQuotaAssistant.SessionWriter.v2")
    if not guard.acquire():
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, "山东定额助手已在运行。", "山东定额助手", 0x40)
        except (AttributeError, OSError):
            pass
        return 0
    try:
        app = QuotaApp()
        app.mainloop()
        return 0
    finally:
        guard.release()


if __name__ == "__main__":
    raise SystemExit(main())
