from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ai_providers import effective_base_url, endpoint_url, normalize_provider, provider_config
from .paths import APP_VERSION
from .secrets import load_api_key


CCSWITCH_BASE_URL = os.environ.get("CCSWITCH_BASE_URL", "http://127.0.0.1:15721").rstrip("/")
CCSWITCH_MODEL = os.environ.get("CCSWITCH_MODEL", "gpt-5.6-sol")
CCSWITCH_API_FORMAT = os.environ.get("CCSWITCH_API_FORMAT", "openai").strip().lower()


class EmptyModelListError(RuntimeError):
    """The provider answered successfully but exposed no model IDs."""


@dataclass(frozen=True)
class AIRequestConfig:
    provider: str
    base_url: str
    model: str
    timeout: int
    api_key: str
    api_format: str = "openai"


def build_ai_request_config(settings: Mapping[str, Any]) -> AIRequestConfig:
    """Freeze one request's routing and credentials without mutating process state."""
    provider = normalize_provider(settings.get("ai_provider") or os.environ.get("AI_PROVIDER") or "ccswitch")
    selected_env_provider = normalize_provider(os.environ.get("AI_PROVIDER") or provider)
    configured_base = str(settings.get("ai_base_url") or "").strip()
    configured_model = str(settings.get("ai_model") or "").strip()
    configured_timeout = settings.get("ai_timeout")
    if provider == "ccswitch":
        configured_base = configured_base or str(settings.get("ccswitch_base_url") or "").strip()
        configured_model = configured_model or str(settings.get("ccswitch_model") or "").strip()
        configured_timeout = configured_timeout or settings.get("ccswitch_timeout")
    if not configured_base and selected_env_provider == provider:
        configured_base = str(os.environ.get("AI_BASE_URL") or "").strip()
    if not configured_base and provider == "ccswitch":
        configured_base = str(os.environ.get("CCSWITCH_BASE_URL") or "").strip()
    if not configured_model and selected_env_provider == provider:
        configured_model = str(os.environ.get("AI_MODEL") or "").strip()
    if not configured_model and provider == "ccswitch":
        configured_model = str(os.environ.get("CCSWITCH_MODEL") or CCSWITCH_MODEL).strip()
    try:
        timeout = int(configured_timeout or 0)
    except (TypeError, ValueError):
        timeout = 0
    if not timeout and selected_env_provider == provider:
        try:
            timeout = int(os.environ.get("AI_TIMEOUT") or 0)
        except ValueError:
            timeout = 0
    if not timeout and provider == "ccswitch":
        try:
            timeout = int(os.environ.get("CCSWITCH_TIMEOUT") or 0)
        except ValueError:
            timeout = 0
    timeout = max(8, min(timeout or 35, 180))
    try:
        api_key = load_api_key(provider)
    except (OSError, RuntimeError):
        api_key = ""
    if not api_key and selected_env_provider == provider:
        api_key = str(os.environ.get("AI_API_KEY") or "").strip()
    if not api_key:
        provider_key_name = {"deepseek": "DEEPSEEK_API_KEY", "zhipu": "ZHIPU_API_KEY", "ccswitch": "CCSWITCH_API_KEY"}[provider]
        api_key = str(os.environ.get(provider_key_name) or "").strip()
    return AIRequestConfig(
        provider=provider,
        base_url=effective_base_url(provider, configured_base),
        model=configured_model,
        timeout=timeout,
        api_key=api_key,
        api_format=str(os.environ.get("CCSWITCH_API_FORMAT") or CCSWITCH_API_FORMAT).strip().lower(),
    )


def _read_timeout() -> int:
    raw = os.environ.get("AI_TIMEOUT") or os.environ.get("CCSWITCH_TIMEOUT") or "35"
    try:
        configured = int(raw)
    except ValueError:
        configured = 35
    return max(8, min(configured, 180))


def _provider(value: str = "") -> str:
    return normalize_provider(value or os.environ.get("AI_PROVIDER") or "ccswitch")


def _base_url(provider: str = "", configured: str = "") -> str:
    selected = _provider(provider)
    override = str(configured or "").strip()
    if not override and selected == _provider():
        override = os.environ.get("AI_BASE_URL", "")
    if not override and selected == "ccswitch":
        override = os.environ.get("CCSWITCH_BASE_URL", "")
    return effective_base_url(selected, override)


def _api_key(provider: str, explicit: str = "") -> str:
    if explicit:
        return explicit.strip()
    selected = _provider(provider)
    provider_env = {
        "deepseek": "DEEPSEEK_API_KEY",
        "zhipu": "ZHIPU_API_KEY",
        "ccswitch": "CCSWITCH_API_KEY",
    }
    key = ""
    if selected == _provider():
        # apply_ccswitch_overrides loads the encrypted key selected in the UI.
        # It must win over a stale machine-level provider variable.
        key = os.environ.get("AI_API_KEY", "")
    if not key:
        key = os.environ.get(provider_env[selected], "")
    if not key and selected == "ccswitch":
        key = os.environ.get("CCSWITCH_API_KEY", "")
    return str(key).strip()


def _headers(provider: str, api_key: str = "") -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"ShandongQuotaAssistant/{APP_VERSION}",
    }
    key = _api_key(provider, api_key)
    if key:
        headers["Authorization"] = f"Bearer {key}"
        if provider == "ccswitch":
            headers["x-api-key"] = key
    return headers


def _selected_model(provider: str, model: str = "") -> str:
    selected = str(model or "").strip()
    if not selected and provider == _provider():
        selected = str(os.environ.get("AI_MODEL") or "").strip()
    if not selected and provider == "ccswitch":
        selected = str(os.environ.get("CCSWITCH_MODEL") or CCSWITCH_MODEL).strip()
    if not selected:
        raise RuntimeError("尚未选择 AI 模型，请在设置中点击“获取模型”后选择。")
    return selected


def call_ccswitch(prompt: str, *, model: str | None = None, config: AIRequestConfig | None = None) -> str:
    """Call the configured ccSwitch, DeepSeek or Zhipu provider."""
    if config is None:
        provider = _provider()
        selected_model = _selected_model(provider, model or "")
        base_url = _base_url(provider)
        api_key = _api_key(provider)
        timeout = _read_timeout()
        api_format = os.environ.get("CCSWITCH_API_FORMAT", CCSWITCH_API_FORMAT).strip().lower()
    else:
        provider = normalize_provider(config.provider)
        selected_model = _selected_model(provider, model or config.model)
        base_url = effective_base_url(provider, config.base_url)
        api_key = str(config.api_key or "").strip()
        timeout = max(8, min(int(config.timeout), 180))
        api_format = str(config.api_format or "openai").strip().lower()
    provider_details = provider_config(provider)
    if provider_details.requires_api_key and not api_key:
        raise RuntimeError(f"{provider_details.label} 需要 API Key")
    if provider == "ccswitch" and api_format not in {"openai", "chat", "chat_completions"}:
        return _call_anthropic(prompt, selected_model, provider=provider, base_url=base_url, api_key=api_key, timeout=timeout)
    return _call_openai(prompt, selected_model, provider=provider, base_url=base_url, api_key=api_key, timeout=timeout)


def probe_ccswitch(
    base_url: str = "",
    *,
    model: str = "",
    timeout: int = 12,
    provider: str = "",
    api_key: str = "",
) -> str:
    """Send a fixed non-project probe without mutating saved settings."""
    selected_provider = _provider(provider)
    config = provider_config(selected_provider)
    key = _api_key(selected_provider, api_key)
    if config.requires_api_key and not key:
        raise RuntimeError(f"{config.label} 需要 API Key")
    selected_model = _selected_model(selected_provider, model)
    target = _base_url(selected_provider, base_url)
    payload = {
        "model": selected_model,
        # Current DeepSeek reasoning models may spend 20-40 tokens before
        # emitting the short probe answer.
        "max_tokens": 96 if selected_provider == "deepseek" else 32,
        "messages": [{"role": "user", "content": "Connection probe. Reply only OK."}],
    }
    if selected_provider != "deepseek" and "reasoner" not in selected_model.lower():
        payload["temperature"] = 0
    request = Request(
        endpoint_url(target, config.chat_path),
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(selected_provider, key),
        method="POST",
    )
    return _request_text(
        request,
        protocol="OpenAI",
        timeout=max(3, min(int(timeout), 30)),
        provider_label=config.label,
    )


def fetch_models(
    *,
    provider: str = "",
    base_url: str = "",
    api_key: str = "",
    timeout: int = 12,
) -> list[str]:
    """Return every model ID exposed by the provider's OpenAI-compatible API."""
    selected_provider = _provider(provider)
    config = provider_config(selected_provider)
    key = _api_key(selected_provider, api_key)
    if config.requires_api_key and not key:
        raise RuntimeError(f"{config.label} 需要 API Key")
    request = Request(
        endpoint_url(_base_url(selected_provider, base_url), config.models_path),
        headers=_headers(selected_provider, key),
        method="GET",
    )
    body = _request_json(request, timeout=max(3, min(int(timeout), 30)), provider_label=config.label)
    raw_items = body.get("data") or body.get("models") or []
    if isinstance(raw_items, dict):
        raw_items = raw_items.get("data") or raw_items.get("models") or []
    models: list[str] = []
    for item in raw_items if isinstance(raw_items, list) else []:
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("model") or item.get("name") or ""
        else:
            model_id = ""
        model_id = str(model_id).strip()
        if model_id and model_id not in models:
            models.append(model_id)
    if not models:
        raise EmptyModelListError(f"{config.label} 没有返回可用模型")
    return models


def _call_anthropic(
    prompt: str,
    model: str,
    *,
    provider: str = "ccswitch",
    base_url: str = "",
    api_key: str = "",
    timeout: int | None = None,
) -> str:
    payload = {
        "model": model,
        "max_tokens": _read_max_tokens(),
        "temperature": 0.1,
        "system": "你是一个严谨的山东工程造价定额助手。",
        "messages": [{"role": "user", "content": prompt}],
    }
    request = Request(
        endpoint_url(_base_url(provider, base_url), "/v1/messages"),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(provider, api_key),
        method="POST",
    )
    return _request_text(request, protocol="Anthropic", timeout=timeout, provider_label=provider_config(provider).label)


def _call_openai(
    prompt: str,
    model: str,
    *,
    provider: str = "",
    base_url: str = "",
    api_key: str = "",
    timeout: int | None = None,
) -> str:
    selected_provider = _provider(provider)
    config = provider_config(selected_provider)
    payload = {
        "model": model,
        "max_tokens": _read_max_tokens(),
        "messages": [
            {"role": "system", "content": "你是一个严谨的山东工程造价定额助手。"},
            {"role": "user", "content": prompt},
        ],
    }
    if selected_provider != "deepseek" and "reasoner" not in model.lower():
        payload["temperature"] = 0.1
    request = Request(
        endpoint_url(_base_url(selected_provider, base_url), config.chat_path),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(selected_provider, api_key),
        method="POST",
    )
    return _request_text(request, protocol="OpenAI", timeout=timeout, provider_label=config.label)


def _read_max_tokens() -> int:
    try:
        configured = int(os.environ.get("CCSWITCH_MAX_TOKENS", "900"))
    except ValueError:
        configured = 900
    return max(300, min(configured, 1600))


def _request_json(request: Request, *, timeout: int, provider_label: str) -> dict:
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
    except HTTPError as exc:
        raise RuntimeError(f"{provider_label} HTTP {exc.code}") from exc
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise RuntimeError(f"{provider_label} 请求失败") from exc
    if not isinstance(body, dict):
        raise RuntimeError(f"{provider_label} 返回格式无效")
    return body


def _request_text(
    request: Request,
    *,
    protocol: str,
    timeout: int | None = None,
    provider_label: str = "AI 服务",
) -> str:
    body = _request_json(request, timeout=timeout or _read_timeout(), provider_label=provider_label)
    if protocol == "OpenAI":
        choices = body.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, list):
            text = "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
        else:
            text = str(content or body.get("output_text") or body.get("text") or "")
    else:
        content = body.get("content")
        if isinstance(content, list):
            text = "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
        else:
            text = str(body.get("output_text") or body.get("text") or "")
    if not text.strip():
        raise RuntimeError(f"{provider_label} 返回了空内容")
    return text.strip()
