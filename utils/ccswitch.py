from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ai_providers import effective_base_url, endpoint_url, normalize_provider, provider_config
from .paths import APP_VERSION
from .secrets import load_api_key
from .settings import validate_ai_endpoint


CCSWITCH_BASE_URL = os.environ.get("CCSWITCH_BASE_URL", "http://127.0.0.1:15721").rstrip("/")
CCSWITCH_MODEL = os.environ.get("CCSWITCH_MODEL", "gpt-5.6-sol")
CCSWITCH_API_FORMAT = os.environ.get("CCSWITCH_API_FORMAT", "openai").strip().lower()
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class EmptyModelListError(RuntimeError):
    """The provider answered successfully but exposed no model IDs."""


class IncompleteAIResponseError(RuntimeError):
    """The provider exhausted its output budget before completing the answer."""


@dataclass(frozen=True)
class AIRequestConfig:
    provider: str
    base_url: str
    model: str
    timeout: int
    api_key: str
    api_format: str = "openai"


@dataclass(frozen=True)
class _AITextResponse:
    text: str
    finish_reason: str = ""


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
    try:
        base_url = validate_ai_endpoint(effective_base_url(provider, configured_base))
    except ValueError as exc:
        raise RuntimeError("AI 服务地址不符合安全要求") from exc
    return AIRequestConfig(
        provider=provider,
        base_url=base_url,
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
    try:
        return validate_ai_endpoint(effective_base_url(selected, override))
    except ValueError as exc:
        raise RuntimeError("AI 服务地址不符合安全要求") from exc


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
        try:
            base_url = validate_ai_endpoint(effective_base_url(provider, config.base_url))
        except ValueError as exc:
            raise RuntimeError("AI 服务地址不符合安全要求") from exc
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
    max_tokens = _read_max_tokens(provider, model)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "system": "你是一个严谨的山东工程造价定额助手。",
        "messages": [{"role": "user", "content": prompt}],
    }
    target = endpoint_url(_base_url(provider, base_url), "/v1/messages")
    label = provider_config(provider).label
    response = _send_completion(target, payload, protocol="Anthropic", provider=provider, api_key=api_key, timeout=timeout, provider_label=label)
    if not _response_is_incomplete(response):
        return response.text

    retry_payload = dict(payload)
    retry_payload["max_tokens"] = _retry_max_tokens(max_tokens)
    retry_payload["messages"] = _complete_retry_messages(payload["messages"], response.text)
    retry = _send_completion(target, retry_payload, protocol="Anthropic", provider=provider, api_key=api_key, timeout=timeout, provider_label=label)
    if _response_is_incomplete(retry):
        raise IncompleteAIResponseError(f"{label} 连续两次返回了不完整内容")
    return retry.text


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
    max_tokens = _read_max_tokens(selected_provider, model)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": "你是一个严谨的山东工程造价定额助手。"},
            {"role": "user", "content": prompt},
        ],
    }
    if selected_provider != "deepseek" and "reasoner" not in model.lower():
        payload["temperature"] = 0.1
    target = endpoint_url(_base_url(selected_provider, base_url), config.chat_path)
    response = _send_completion(target, payload, protocol="OpenAI", provider=selected_provider, api_key=api_key, timeout=timeout, provider_label=config.label)
    if not _response_is_incomplete(response):
        return response.text

    retry_payload = dict(payload)
    retry_payload["max_tokens"] = _retry_max_tokens(max_tokens)
    retry_payload["messages"] = _complete_retry_messages(payload["messages"], response.text)
    retry = _send_completion(target, retry_payload, protocol="OpenAI", provider=selected_provider, api_key=api_key, timeout=timeout, provider_label=config.label)
    if _response_is_incomplete(retry):
        raise IncompleteAIResponseError(f"{config.label} 连续两次返回了不完整内容")
    return retry.text


def _read_max_tokens(provider: str = "", model: str = "") -> int:
    selected_provider = _provider(provider)
    reasoning_model = selected_provider == "deepseek" or any(marker in str(model).lower() for marker in ("deepseek", "reasoner"))
    default = 3200 if reasoning_model else 2400
    try:
        configured = int(os.environ.get("AI_MAX_TOKENS") or os.environ.get("CCSWITCH_MAX_TOKENS") or default)
    except ValueError:
        configured = default
    return max(600, min(configured, 8192))


def _retry_max_tokens(initial: int) -> int:
    return min(8192, max(4096, int(initial) * 2))


def _complete_retry_messages(messages: list[dict[str, str]], partial: str) -> list[dict[str, str]]:
    return [
        *messages,
        {"role": "assistant", "content": partial},
        {
            "role": "user",
            "content": (
                "上一版回答在结尾处被截断。请重新输出一份完整答案，不要续写半句；"
                "严格保留原要求的标题和引用格式，压缩到 450 字以内，确保最后一节和最后一句完整结束。"
            ),
        },
    ]


def _looks_incomplete(text: str) -> bool:
    """Catch obvious cut-offs even when a compatible API omits finish_reason."""
    stripped = str(text or "").strip()
    if not stripped:
        return True
    if stripped.count("```") % 2:
        return True
    tail = re.sub(r"(?:\s*\[R\d+\])+\s*$", "", stripped, flags=re.IGNORECASE).rstrip()
    if not tail:
        return False
    if tail.endswith(("，", "、", "：", "；", "（", "(", "[", "【", "/")):
        return True
    last_line = tail.splitlines()[-1].strip()
    if re.fullmatch(r"#{1,6}\s*[^#]+", last_line):
        return True
    return bool(re.search(r"(?:与|和|及|或|但|且|而|因为|由于|如果|若|则|需|应|按|由|将|对|为)$", tail))


def is_complete_ai_text(text: str) -> bool:
    """Return whether saved/displayed model text has an obviously complete ending."""
    return not _looks_incomplete(text)


def _response_is_incomplete(response: _AITextResponse) -> bool:
    finish_reason = str(response.finish_reason or "").strip().lower()
    return finish_reason in {"length", "max_tokens", "max_output_tokens", "model_length"} or _looks_incomplete(response.text)


def _send_completion(
    target: str,
    payload: dict,
    *,
    protocol: str,
    provider: str,
    api_key: str,
    timeout: int | None,
    provider_label: str,
) -> _AITextResponse:
    request = Request(
        target,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(provider, api_key),
        method="POST",
    )
    return _request_completion(request, protocol=protocol, timeout=timeout, provider_label=provider_label)


def _request_json(request: Request, *, timeout: int, provider_label: str) -> dict:
    try:
        validate_ai_endpoint(request.full_url)
        with urlopen(request, timeout=timeout) as response:
            final_url = response.geturl() if hasattr(response, "geturl") else request.full_url
            validate_ai_endpoint(final_url)
            try:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            except TypeError:
                raw = response.read()
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError(f"{provider_label} 返回内容过大")
            body = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(f"{provider_label} 服务地址或返回格式无效") from exc
    except HTTPError as exc:
        raise RuntimeError(f"{provider_label} HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
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
    return _request_completion(
        request,
        protocol=protocol,
        timeout=timeout,
        provider_label=provider_label,
    ).text


def _request_completion(
    request: Request,
    *,
    protocol: str,
    timeout: int | None = None,
    provider_label: str = "AI 服务",
) -> _AITextResponse:
    body = _request_json(request, timeout=timeout or _read_timeout(), provider_label=provider_label)
    finish_reason = ""
    if protocol == "OpenAI":
        choices = body.get("choices") or []
        first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        finish_reason = str(first_choice.get("finish_reason") or body.get("finish_reason") or "")
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, list):
            text = "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
        else:
            text = str(content or body.get("output_text") or body.get("text") or "")
    else:
        finish_reason = str(body.get("stop_reason") or body.get("finish_reason") or "")
        content = body.get("content")
        if isinstance(content, list):
            text = "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
        else:
            text = str(body.get("output_text") or body.get("text") or "")
    if not text.strip():
        raise RuntimeError(f"{provider_label} 返回了空内容")
    return _AITextResponse(text.strip(), finish_reason)
