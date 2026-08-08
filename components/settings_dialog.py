from __future__ import annotations

import queue
import threading
import webbrowser

import customtkinter as ctk

from themes.tokens import ThemeTokens
from utils.ai_providers import (
    PROVIDER_LABELS,
    endpoint_after_provider_switch,
    effective_base_url,
    provider_config,
    provider_key_from_label,
)
from utils.ccswitch import EmptyModelListError, fetch_models, friendly_ai_error, probe_ccswitch
from utils.secrets import load_api_key, save_api_key
from utils.settings import DISCIPLINE_OPTIONS, validate_ai_endpoint
from .button import DSButton
from .scrollable import PointerScrollableFrame


AI_CONNECT_ACTION_LABEL = "连接并获取模型"


def is_current_connection_result(
    *,
    action: str,
    request_id: int,
    provider: str,
    current_provider: str,
    model_request_id: int,
    probe_request_id: int,
) -> bool:
    if provider != current_provider:
        return False
    expected_id = model_request_id if action in {"models", "models_fallback"} else probe_request_id
    return request_id == expected_id


def should_continue_connection_poll(*, closed: bool, pending_requests: int, queue_empty: bool) -> bool:
    return not closed and (pending_requests > 0 or not queue_empty)


class SettingsDialog(ctk.CTkToplevel):
    """Simple provider setup with model discovery and encrypted credentials."""

    def __init__(self, master, *, tokens: ThemeTokens, settings: dict, on_save, **kwargs):
        self.tokens = tokens
        self.on_save = on_save
        self._settings = settings
        self._connection_queue: queue.Queue[tuple[str, int, str, bool, object]] = queue.Queue()
        self._connection_poll_job: str | None = None
        self._model_request_id = 0
        self._probe_request_id = 0
        self._pending_requests = 0
        self._closed = False
        self._advanced_visible = False
        self._key_visible = False
        self._active_provider = provider_config(settings.get("ai_provider")).key
        super().__init__(master, fg_color=tokens.colors.background, **kwargs)
        self.title("设置")
        self.geometry("600x760")
        self.minsize(500, 560)
        self.transient(master)
        self.grab_set()
        self._build(settings)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())

    def _build(self, settings: dict) -> None:
        c = self.tokens.colors
        pad = {"padx": 28}
        body = PointerScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=c.border,
            scrollbar_button_hover_color=c.border_strong,
        )
        body.pack(fill="both", expand=True)
        ctk.CTkLabel(
            body,
            text="设置",
            text_color=c.text,
            font=self.tokens.font(self.tokens.typography.section, "semibold"),
            anchor="w",
        ).pack(anchor="w", pady=(22, 14), **pad)

        self._build_catalog_settings(body, settings, pad)
        self._build_ai_settings(body, settings, pad)

        self.error_label = ctk.CTkLabel(
            self,
            text="",
            text_color=c.danger,
            font=self.tokens.font(self.tokens.typography.caption),
            anchor="w",
            justify="left",
            wraplength=530,
            height=42,
        )
        self.error_label.pack(fill="x", padx=28, pady=(8, 0))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=28, pady=(8, 20))
        self.test_button = DSButton(buttons, tokens=self.tokens, text=AI_CONNECT_ACTION_LABEL, variant="secondary", width=132, command=self._connect_ai)
        self.test_button.pack(side="left")
        DSButton(buttons, tokens=self.tokens, text="保存", width=78, command=self._save).pack(side="right")
        DSButton(buttons, tokens=self.tokens, text="取消", variant="secondary", width=78, command=self._close).pack(side="right", padx=(0, 8))

    def _section_title(self, master, text: str, pad: dict) -> None:
        ctk.CTkLabel(
            master,
            text=text,
            text_color=self.tokens.colors.text_secondary,
            font=self.tokens.font(self.tokens.typography.meta, "semibold"),
            anchor="w",
        ).pack(anchor="w", pady=(12, 8), **pad)

    def _build_catalog_settings(self, body, settings: dict, pad: dict) -> None:
        c = self.tokens.colors
        self._section_title(body, "检索默认值", pad)
        frame = ctk.CTkFrame(body, fg_color="transparent")
        frame.pack(fill="x", **pad)
        frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="catalog")
        label_font = self.tokens.font(self.tokens.typography.caption)
        entry_font = self.tokens.font(self.tokens.typography.meta)
        for column, text in enumerate(("定额版本", "清单依据", "专业")):
            ctk.CTkLabel(frame, text=text, text_color=c.text_muted, font=label_font, anchor="w").grid(row=0, column=column, sticky="w", padx=(0, 8))
        self.edition = ctk.CTkOptionMenu(frame, values=["2025", "2016"], font=entry_font, fg_color=c.elevated, button_color=c.elevated, text_color=c.text)
        self.standard_edition = ctk.CTkOptionMenu(frame, values=["2024", "2013"], font=entry_font, fg_color=c.elevated, button_color=c.elevated, text_color=c.text)
        self.discipline = ctk.CTkOptionMenu(frame, values=list(DISCIPLINE_OPTIONS), font=entry_font, fg_color=c.elevated, button_color=c.elevated, text_color=c.text)
        self.edition.set(str(settings.get("quota_edition") or "2025"))
        self.standard_edition.set(str(settings.get("standard_edition") or "2024"))
        self.discipline.set(str(settings.get("discipline") or "建筑"))
        for column, control in enumerate((self.edition, self.standard_edition, self.discipline)):
            control.grid(row=1, column=column, sticky="ew", padx=(0, 8), pady=(4, 0))

    def _build_ai_settings(self, body, settings: dict, pad: dict) -> None:
        c = self.tokens.colors
        label_font = self.tokens.font(self.tokens.typography.meta)
        caption_font = self.tokens.font(self.tokens.typography.caption)
        self._section_title(body, "AI 连接", pad)
        ctk.CTkLabel(
            body,
            text="三步完成：选择服务商 → 粘贴 Key → 点击“连接并获取模型”",
            text_color=c.text_muted,
            font=caption_font,
            anchor="w",
        ).pack(fill="x", pady=(0, 8), **pad)
        form = ctk.CTkFrame(body, fg_color="transparent")
        form.pack(fill="x", **pad)
        form.grid_columnconfigure(1, weight=1)
        row = 0

        ctk.CTkLabel(form, text="服务商", text_color=c.text_secondary, font=label_font, anchor="w", width=86).grid(row=row, column=0, sticky="w", pady=7)
        initial_config = provider_config(settings.get("ai_provider"))
        self.provider = ctk.CTkOptionMenu(
            form,
            values=PROVIDER_LABELS,
            command=self._provider_changed,
            fg_color=c.elevated,
            button_color=c.elevated,
            text_color=c.text,
            font=label_font,
        )
        self.provider.set(initial_config.label)
        self.provider.grid(row=row, column=1, columnspan=2, sticky="ew", pady=7)
        row += 1

        self.provider_hint = ctk.CTkLabel(
            form,
            text=initial_config.novice_hint,
            text_color=c.text_muted,
            font=caption_font,
            anchor="w",
            justify="left",
            wraplength=430,
        )
        self.provider_hint.grid(row=row, column=1, columnspan=2, sticky="w", pady=(0, 3))
        row += 1

        ctk.CTkLabel(form, text="API Key", text_color=c.text_secondary, font=label_font, anchor="w", width=86).grid(row=row, column=0, sticky="w", pady=7)
        self.api_key = ctk.CTkEntry(form, show="•", placeholder_text=initial_config.key_hint, fg_color=c.elevated, border_color=c.border, text_color=c.text, font=label_font)
        self.api_key.grid(row=row, column=1, sticky="ew", pady=7)
        self.key_visibility_button = DSButton(form, tokens=self.tokens, text="显示", variant="ghost", width=54, height=30, command=self._toggle_key_visibility)
        self.key_visibility_button.grid(row=row, column=2, padx=(6, 0), pady=7)
        row += 1
        self.key_status = ctk.CTkLabel(form, text="", text_color=c.text_muted, font=caption_font, anchor="w")
        self.key_status.grid(row=row, column=1, sticky="w", pady=(0, 5))
        self.key_help_button = DSButton(form, tokens=self.tokens, text="获取 Key", variant="ghost", width=68, height=26, command=self._open_key_help)
        self.key_help_button.grid(row=row, column=2, padx=(6, 0), pady=(0, 5))
        self.key_help_button.set_enabled(bool(initial_config.key_url))
        row += 1

        ctk.CTkLabel(form, text="模型", text_color=c.text_secondary, font=label_font, anchor="w", width=86).grid(row=row, column=0, sticky="w", pady=7)
        current_model = str(settings.get("ai_model") or settings.get("ccswitch_model") or "")
        self.model = ctk.CTkComboBox(
            form,
            values=[current_model] if current_model else ["先点击右侧获取模型"],
            fg_color=c.elevated,
            border_color=c.border,
            button_color=c.elevated,
            text_color=c.text,
            font=label_font,
            state="readonly",
        )
        self.model.set(current_model or "先点击右侧获取模型")
        self.model.grid(row=row, column=1, sticky="ew", pady=7)
        self.models_button = DSButton(form, tokens=self.tokens, text="刷新", variant="secondary", width=58, height=32, command=self._fetch_models)
        self.models_button.grid(row=row, column=2, padx=(6, 0), pady=7)
        row += 1

        self.ai_enabled = ctk.CTkSwitch(form, text="启用 AI 定额分析", text_color=c.text, font=label_font, progress_color=c.accent)
        if settings.get("ai_enabled", False):
            self.ai_enabled.select()
        self.ai_enabled.grid(row=row, column=0, columnspan=3, sticky="w", pady=(12, 6))
        row += 1

        self.ai_consent = ctk.CTkCheckBox(form, text="允许发送施工描述", text_color=c.text_secondary, font=caption_font, fg_color=c.accent)
        if int(settings.get("ai_consent_version") or 0) >= 1:
            self.ai_consent.select()
        self.ai_consent.grid(row=row, column=0, columnspan=3, sticky="w", pady=4)
        row += 1
        self.catalog_consent = ctk.CTkCheckBox(form, text="允许发送本地候选摘要", text_color=c.text_secondary, font=caption_font, fg_color=c.accent)
        if int(settings.get("ai_catalog_consent_version") or 0) >= 1:
            self.catalog_consent.select()
        self.catalog_consent.grid(row=row, column=0, columnspan=3, sticky="w", pady=4)
        row += 1

        self.enter_send = ctk.CTkSwitch(form, text="Enter 发送（Shift+Enter 换行）", text_color=c.text, font=label_font, progress_color=c.accent)
        if settings.get("enter_send", False):
            self.enter_send.select()
        self.enter_send.grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 4))
        row += 1

        self.advanced_button = DSButton(form, tokens=self.tokens, text="高级设置", variant="ghost", width=84, height=28, command=self._toggle_advanced)
        self.advanced_button.grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 2))
        row += 1
        self.advanced_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.advanced_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.advanced_frame, text="服务地址", text_color=c.text_muted, font=caption_font, width=86, anchor="w").grid(row=0, column=0, sticky="w", pady=5)
        self.base_url = ctk.CTkEntry(self.advanced_frame, fg_color=c.elevated, border_color=c.border, text_color=c.text, font=label_font)
        self.base_url.insert(0, effective_base_url(initial_config.key, str(settings.get("ai_base_url") or settings.get("ccswitch_base_url") or "")))
        self.base_url.grid(row=0, column=1, sticky="ew", pady=5)
        ctk.CTkLabel(self.advanced_frame, text="超时（秒）", text_color=c.text_muted, font=caption_font, width=86, anchor="w").grid(row=1, column=0, sticky="w", pady=5)
        self.timeout = ctk.CTkEntry(self.advanced_frame, placeholder_text="默认 35", width=100, fg_color=c.elevated, border_color=c.border, text_color=c.text, font=label_font)
        timeout_value = settings.get("ai_timeout") or settings.get("ccswitch_timeout") or 0
        if timeout_value:
            self.timeout.insert(0, str(timeout_value))
        self.timeout.grid(row=1, column=1, sticky="w", pady=5)
        self._refresh_key_status()

    def _open_key_help(self) -> None:
        config = provider_config(self._provider_key())
        if config.key_url:
            try:
                webbrowser.open(config.key_url, new=2)
            except OSError:
                self._show_error(f"请在浏览器打开 {config.key_url}")
        else:
            self._show_error("ccSwitch 是本机服务：先启动 ccSwitch，再回到这里点击连接。")

    def _provider_key(self) -> str:
        return provider_key_from_label(self.provider.get())

    def _provider_changed(self, _label: str | None = None) -> None:
        provider = self._provider_key()
        config = provider_config(provider)
        current = self.base_url.get().strip()
        endpoint = endpoint_after_provider_switch(self._active_provider, provider, current)
        self._active_provider = provider
        self._model_request_id += 1
        self._probe_request_id += 1
        self.models_button.set_loading(False)
        self.test_button.set_loading(False)
        self.base_url.delete(0, "end")
        self.base_url.insert(0, endpoint)
        self.api_key.delete(0, "end")
        self.api_key.configure(placeholder_text=config.key_hint)
        self.provider_hint.configure(text=config.novice_hint)
        self.key_help_button.set_enabled(bool(config.key_url))
        self.model.configure(values=["先点击右侧获取模型"])
        self.model.set("先点击右侧获取模型")
        self._refresh_key_status()
        self.error_label.configure(text="")

    def _refresh_key_status(self) -> None:
        provider = self._provider_key()
        try:
            has_saved_key = bool(load_api_key(provider))
        except (OSError, RuntimeError):
            has_saved_key = False
        config = provider_config(provider)
        if has_saved_key:
            text = "已使用 Windows 加密保存在本机"
            color = self.tokens.colors.success
        elif config.requires_api_key:
            text = "尚未保存 API Key"
            color = self.tokens.colors.text_muted
        else:
            text = "本机 ccSwitch 通常不需要 API Key"
            color = self.tokens.colors.text_muted
        self.key_status.configure(text=text, text_color=color)

    def _toggle_key_visibility(self) -> None:
        self._key_visible = not self._key_visible
        self.api_key.configure(show="" if self._key_visible else "•")
        self.key_visibility_button.configure(text="隐藏" if self._key_visible else "显示")

    def _toggle_advanced(self) -> None:
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self.advanced_frame.grid(row=99, column=0, columnspan=3, sticky="ew", pady=(4, 8))
            self.advanced_button.configure(text="收起高级设置")
        else:
            self.advanced_frame.grid_remove()
            self.advanced_button.configure(text="高级设置")

    def _read_timeout(self) -> int | None:
        raw = self.timeout.get().strip()
        if not raw:
            return 0
        try:
            timeout = int(raw)
        except ValueError:
            self._show_error("超时必须是 8-180 之间的整数。", self.timeout)
            return None
        if not 8 <= timeout <= 180:
            self._show_error("超时必须在 8-180 秒之间。", self.timeout)
            return None
        return timeout

    def _endpoint(self) -> str | None:
        try:
            return validate_ai_endpoint(self.base_url.get())
        except ValueError as exc:
            self._show_error(str(exc), self.base_url)
            return None

    def _current_key(self) -> str:
        entered = self.api_key.get().strip()
        if entered:
            return entered
        try:
            return load_api_key(self._provider_key())
        except (OSError, RuntimeError):
            return ""

    def _show_error(self, text: str, widget=None) -> None:
        self.error_label.configure(text=text, text_color=self.tokens.colors.danger)
        if widget is not None:
            widget.focus_set()

    def _fetch_models(self) -> None:
        endpoint = self._endpoint()
        timeout = self._read_timeout()
        if endpoint is None or timeout is None:
            return
        provider = self._provider_key()
        key = self._current_key()
        config = provider_config(provider)
        if config.requires_api_key and not key:
            self._show_error(f"请先填写 {config.label} API Key。", self.api_key)
            return
        self.error_label.configure(text="正在读取模型列表…", text_color=self.tokens.colors.text_muted)
        self.models_button.set_loading(True, "获取中…")
        self._model_request_id += 1
        self._pending_requests += 1
        request_id = self._model_request_id

        def worker() -> None:
            try:
                models = fetch_models(provider=provider, base_url=endpoint, api_key=key, timeout=timeout or 12)
                self._connection_queue.put(("models", request_id, provider, True, models))
            except EmptyModelListError as exc:
                if provider == "ccswitch" and config.fallback_models:
                    configured = str(self._settings.get("ai_model") or self._settings.get("ccswitch_model") or "").strip()
                    models = list(dict.fromkeys(([configured] if configured else []) + list(config.fallback_models)))
                    self._connection_queue.put(("models_fallback", request_id, provider, True, models))
                else:
                    self._connection_queue.put(("models", request_id, provider, False, str(exc)))
            except Exception as exc:
                self._connection_queue.put(("models", request_id, provider, False, str(exc)))

        threading.Thread(target=worker, name=f"{provider}-models", daemon=True).start()
        self._ensure_connection_poll()

    def _selected_model(self) -> str:
        value = self.model.get().strip()
        return "" if value == "先点击右侧获取模型" else value

    def _connect_ai(self) -> None:
        """Discover a model and verify it in one novice-friendly action."""
        endpoint = self._endpoint()
        timeout = self._read_timeout()
        if endpoint is None or timeout is None:
            return
        provider = self._provider_key()
        key = self._current_key()
        config = provider_config(provider)
        if config.requires_api_key and not key:
            self._show_error(f"请先填写 {config.label} API Key，再点“连接并获取模型”。", self.api_key)
            return
        self.error_label.configure(text="正在连接并读取模型…", text_color=self.tokens.colors.text_muted)
        self.test_button.set_loading(True, "连接中…")
        self.models_button.set_enabled(False)
        self._probe_request_id += 1
        self._pending_requests += 1
        request_id = self._probe_request_id
        previous_model = self._selected_model()
        configured_model = str(self._settings.get("ai_model") or self._settings.get("ccswitch_model") or "").strip()

        def worker() -> None:
            used_fallback = False
            try:
                try:
                    models = fetch_models(provider=provider, base_url=endpoint, api_key=key, timeout=timeout or 12)
                except EmptyModelListError:
                    if provider != "ccswitch" or not config.fallback_models:
                        raise
                    used_fallback = True
                    models = list(dict.fromkeys(([configured_model] if configured_model else []) + list(config.fallback_models)))
                model = next((value for value in (previous_model, configured_model) if value in models), models[0])
                probe_ccswitch(endpoint, model=model, timeout=timeout or 12, provider=provider, api_key=key)
                self._connection_queue.put(("connect", request_id, provider, True, {
                    "models": models,
                    "model": model,
                    "fallback": used_fallback,
                }))
            except Exception as exc:
                self._connection_queue.put(("connect", request_id, provider, False, str(exc)))

        threading.Thread(target=worker, name=f"{provider}-connect", daemon=True).start()
        self._ensure_connection_poll()

    def _test_connection(self) -> None:
        endpoint = self._endpoint()
        timeout = self._read_timeout()
        if endpoint is None or timeout is None:
            return
        provider = self._provider_key()
        key = self._current_key()
        model = self._selected_model()
        config = provider_config(provider)
        if config.requires_api_key and not key:
            self._show_error(f"请先填写 {config.label} API Key。", self.api_key)
            return
        if not model:
            self._show_error("请先点击“获取模型”，再选择一个模型。", self.model)
            return
        self.error_label.configure(text="正在测试连接…", text_color=self.tokens.colors.text_muted)
        self.test_button.set_loading(True, "测试中…")
        self._probe_request_id += 1
        self._pending_requests += 1
        request_id = self._probe_request_id

        def worker() -> None:
            try:
                reply = probe_ccswitch(endpoint, model=model, timeout=timeout or 12, provider=provider, api_key=key)
                self._connection_queue.put(("probe", request_id, provider, True, reply[:80]))
            except Exception as exc:
                self._connection_queue.put(("probe", request_id, provider, False, str(exc)))

        threading.Thread(target=worker, name=f"{provider}-probe", daemon=True).start()
        self._ensure_connection_poll()

    def _ensure_connection_poll(self) -> None:
        if not self._closed and self._connection_poll_job is None:
            self._connection_poll_job = self.after(100, self._poll_connection)

    def _poll_connection(self) -> None:
        self._connection_poll_job = None
        if self._closed:
            return
        try:
            action, request_id, provider, ok, detail = self._connection_queue.get_nowait()
        except queue.Empty:
            if should_continue_connection_poll(
                closed=self._closed,
                pending_requests=self._pending_requests,
                queue_empty=True,
            ):
                self._ensure_connection_poll()
            return
        self._pending_requests = max(0, self._pending_requests - 1)
        if not is_current_connection_result(
            action=action,
            request_id=request_id,
            provider=provider,
            current_provider=self._provider_key(),
            model_request_id=self._model_request_id,
            probe_request_id=self._probe_request_id,
        ):
            if should_continue_connection_poll(
                closed=self._closed,
                pending_requests=self._pending_requests,
                queue_empty=self._connection_queue.empty(),
            ):
                self._ensure_connection_poll()
            return
        if action in {"models", "models_fallback"}:
            self.models_button.set_loading(False)
            if ok and isinstance(detail, list):
                models = [str(item) for item in detail]
                previous_model = self._selected_model()
                self.model.configure(values=models)
                self.model.set(previous_model if previous_model in models else models[0])
                if action == "models_fallback":
                    status = "ccSwitch 未提供模型清单，已载入本机验证可用模型，请选择后测试连接。"
                else:
                    status = f"已获取 {len(models)} 个模型，请选择后测试连接。"
                self.error_label.configure(text=status, text_color=self.tokens.colors.success)
            else:
                self._show_error(f"获取模型失败：{friendly_ai_error(detail, provider=provider)}")
        elif action == "connect":
            self.test_button.set_loading(False)
            self.models_button.set_enabled(True)
            if ok and isinstance(detail, dict):
                models = [str(item) for item in detail.get("models") or []]
                model = str(detail.get("model") or "")
                if models and model:
                    self.model.configure(values=models)
                    self.model.set(model)
                    note = " · 使用兼容模型" if detail.get("fallback") else ""
                    self.error_label.configure(
                        text=f"连接成功 · {self.provider.get()} · {model}{note}。勾选两项发送许可后保存即可启用 AI。",
                        text_color=self.tokens.colors.success,
                    )
                    self.ai_enabled.select()
                else:
                    self._show_error("连接未返回可用模型。请检查服务地址后重试。")
            else:
                self._show_error(f"连接失败：{friendly_ai_error(detail, provider=provider)}")
        else:
            self.test_button.set_loading(False)
            if ok:
                self.error_label.configure(text=f"连接成功 · {self.provider.get()} · {self._selected_model()}", text_color=self.tokens.colors.success)
            else:
                self._show_error(f"连接失败：{friendly_ai_error(detail, provider=provider)}")
        if should_continue_connection_poll(
            closed=self._closed,
            pending_requests=self._pending_requests,
            queue_empty=self._connection_queue.empty(),
        ):
            self._ensure_connection_poll()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._model_request_id += 1
        self._probe_request_id += 1
        if self._connection_poll_job is not None:
            try:
                self.after_cancel(self._connection_poll_job)
            except (ValueError, RuntimeError):
                pass
            self._connection_poll_job = None
        self.destroy()

    def _save(self) -> None:
        if self.ai_enabled.get() and (not self.ai_consent.get() or not self.catalog_consent.get()):
            self._show_error("启用 AI 前，请勾选两项发送许可。", self.ai_consent if not self.ai_consent.get() else self.catalog_consent)
            return
        endpoint = self._endpoint()
        timeout = self._read_timeout()
        if endpoint is None or timeout is None:
            return
        provider = self._provider_key()
        model = self._selected_model()
        key = self._current_key()
        config = provider_config(provider)
        if self.ai_enabled.get() and config.requires_api_key and not key:
            self._show_error(f"启用 {config.label} 前需填写 API Key。", self.api_key)
            return
        if self.ai_enabled.get() and not model:
            self._show_error("启用 AI 前，请先获取并选择模型。", self.model)
            return
        entered_key = self.api_key.get().strip()
        if entered_key:
            try:
                save_api_key(provider, entered_key)
            except (OSError, RuntimeError) as exc:
                self._show_error(f"API Key 保存失败：{exc}")
                return
        settings = {
            "quota_edition": self.edition.get(),
            "standard_edition": self.standard_edition.get(),
            "discipline": self.discipline.get(),
            "ai_enabled": bool(self.ai_enabled.get()),
            "ai_consent_version": 1 if self.ai_consent.get() else 0,
            "ai_catalog_consent_version": 1 if self.catalog_consent.get() else 0,
            "enter_send": bool(self.enter_send.get()),
            "ai_provider": provider,
            "ai_base_url": endpoint,
            "ai_model": model,
            "ai_timeout": timeout,
        }
        self.on_save(settings)
        self._close()
