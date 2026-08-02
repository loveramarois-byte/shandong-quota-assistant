from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse

from .ai_providers import effective_base_url, normalize_provider
from .paths import settings_path
from .secrets import load_api_key

DISCIPLINE_LABEL_TO_CODE = {
    "建筑": "building",
    "安装": "installation",
    "市政": "municipal",
    "园林": "landscape",
}
DISCIPLINE_OPTIONS = tuple(DISCIPLINE_LABEL_TO_CODE)

DEFAULTS: dict[str, Any] = {
    "quota_edition": "2025",
    "standard_edition": "2024",
    "discipline": "建筑",
    "ai_enabled": False,
    "ai_consent_version": 0,
    "ai_catalog_consent_version": 0,
    "theme": "light",
    "enter_send": False,
    "ai_provider": "ccswitch",
    "ai_base_url": "",
    "ai_model": "",
    "ai_timeout": 0,
    "update_last_checked": 0.0,
    # Legacy keys remain readable so existing ccSwitch users migrate without
    # losing their endpoint and model.
    "ccswitch_base_url": "",
    "ccswitch_model": "",
    "ccswitch_timeout": 0,
}

_VALID_EDITIONS = {"2025", "2016"}
_VALID_STANDARD_EDITIONS = {"2024", "2013"}
_VALID_DISCIPLINES = set(DISCIPLINE_OPTIONS)
_AI_CONSENT_VERSION = 1


def validate_ai_endpoint(value: str | None) -> str:
    """Accept HTTPS endpoints and explicit loopback HTTP endpoints only."""
    endpoint = str(value or "").strip().rstrip("/")
    if not endpoint:
        return ""
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("AI 服务地址不得包含账号、密码、query 或 fragment；密钥请使用受控环境配置。")
    if parsed.scheme == "https" and host:
        return endpoint
    if parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}:
        return endpoint
    if parsed.scheme == "http" and host:
        raise ValueError("远程 AI 服务必须使用 HTTPS；仅本机 loopback 可使用 HTTP。")
    raise ValueError("AI 服务地址必须是完整的 HTTPS 地址或本机 loopback 地址。")


def load_settings() -> dict[str, Any]:
    settings = dict(DEFAULTS)
    try:
        raw = json.loads(settings_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            settings.update({key: value for key, value in raw.items() if key in DEFAULTS})
    except (OSError, json.JSONDecodeError):
        pass
    return sanitize_settings(settings)


def sanitize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(DEFAULTS)
    cleaned.update({key: value for key, value in settings.items() if key in DEFAULTS})
    if cleaned.get("quota_edition") not in _VALID_EDITIONS:
        cleaned["quota_edition"] = DEFAULTS["quota_edition"]
    if cleaned.get("standard_edition") not in _VALID_STANDARD_EDITIONS:
        cleaned["standard_edition"] = DEFAULTS["standard_edition"]
    # Old settings used this label for an unfiltered search. Migrate it to
    # the truthful explicit mode instead of implying a classifier exists.
    if cleaned.get("discipline") in {"自动判断", "全部专业"}:
        cleaned["discipline"] = DEFAULTS["discipline"]
    if cleaned.get("discipline") not in _VALID_DISCIPLINES:
        cleaned["discipline"] = DEFAULTS["discipline"]
    try:
        consent_version = int(cleaned.get("ai_consent_version") or 0)
    except (TypeError, ValueError):
        consent_version = 0
    cleaned["ai_consent_version"] = consent_version
    try:
        catalog_consent_version = int(cleaned.get("ai_catalog_consent_version") or 0)
    except (TypeError, ValueError):
        catalog_consent_version = 0
    cleaned["ai_catalog_consent_version"] = catalog_consent_version
    cleaned["ai_enabled"] = (
        bool(cleaned.get("ai_enabled", False))
        and consent_version >= _AI_CONSENT_VERSION
        and catalog_consent_version >= _AI_CONSENT_VERSION
    )
    cleaned["enter_send"] = bool(cleaned.get("enter_send", False))
    try:
        cleaned["update_last_checked"] = max(0.0, float(cleaned.get("update_last_checked") or 0.0))
    except (TypeError, ValueError, OverflowError):
        cleaned["update_last_checked"] = 0.0
    if cleaned.get("theme") not in {"light", "dark"}:
        cleaned["theme"] = "light"
    cleaned["ai_provider"] = normalize_provider(settings.get("ai_provider") or cleaned.get("ai_provider"))
    configured_base = str(settings.get("ai_base_url") or "").strip()
    configured_model = str(settings.get("ai_model") or "").strip()
    configured_timeout = settings.get("ai_timeout")
    if cleaned["ai_provider"] == "ccswitch":
        configured_base = configured_base or str(settings.get("ccswitch_base_url") or "").strip()
        configured_model = configured_model or str(settings.get("ccswitch_model") or "").strip()
        configured_timeout = configured_timeout or settings.get("ccswitch_timeout")
    cleaned["ai_base_url"] = configured_base[:300]
    cleaned["ai_model"] = configured_model[:200]
    try:
        cleaned["ai_base_url"] = validate_ai_endpoint(cleaned["ai_base_url"])
    except ValueError:
        cleaned["ai_base_url"] = ""
        cleaned["ai_enabled"] = False
    try:
        timeout = int(configured_timeout or 0)
    except (TypeError, ValueError):
        timeout = 0
    cleaned["ai_timeout"] = timeout if 8 <= timeout <= 180 else 0
    cleaned["ccswitch_base_url"] = cleaned["ai_base_url"] if cleaned["ai_provider"] == "ccswitch" else ""
    cleaned["ccswitch_model"] = cleaned["ai_model"] if cleaned["ai_provider"] == "ccswitch" else ""
    cleaned["ccswitch_timeout"] = cleaned["ai_timeout"] if cleaned["ai_provider"] == "ccswitch" else 0
    return cleaned


def save_settings(settings: dict[str, Any]) -> None:
    path = settings_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sanitize_settings(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def apply_ccswitch_overrides(settings: dict[str, Any]) -> None:
    """Apply the selected provider while keeping legacy env compatibility."""
    cleaned = sanitize_settings(settings)
    provider = cleaned["ai_provider"]
    base_url = effective_base_url(provider, cleaned.get("ai_base_url") or "")
    model = str(cleaned.get("ai_model") or "")
    timeout = int(cleaned.get("ai_timeout") or 0)
    try:
        api_key = load_api_key(provider)
    except (OSError, RuntimeError):
        api_key = ""
    os.environ["AI_PROVIDER"] = provider
    os.environ["AI_BASE_URL"] = base_url
    if model:
        os.environ["AI_MODEL"] = model
    else:
        os.environ.pop("AI_MODEL", None)
    if timeout:
        os.environ["AI_TIMEOUT"] = str(timeout)
    else:
        os.environ.pop("AI_TIMEOUT", None)
    if api_key:
        os.environ["AI_API_KEY"] = api_key
    else:
        os.environ.pop("AI_API_KEY", None)

    if provider == "ccswitch":
        os.environ["CCSWITCH_BASE_URL"] = base_url
        if model:
            os.environ["CCSWITCH_MODEL"] = model
        else:
            os.environ.pop("CCSWITCH_MODEL", None)
        if timeout:
            os.environ["CCSWITCH_TIMEOUT"] = str(timeout)
        else:
            os.environ.pop("CCSWITCH_TIMEOUT", None)
        if api_key:
            os.environ["CCSWITCH_API_KEY"] = api_key
        else:
            os.environ.pop("CCSWITCH_API_KEY", None)
    else:
        os.environ.pop("CCSWITCH_BASE_URL", None)
        os.environ.pop("CCSWITCH_MODEL", None)
        os.environ.pop("CCSWITCH_TIMEOUT", None)
        os.environ.pop("CCSWITCH_API_KEY", None)
