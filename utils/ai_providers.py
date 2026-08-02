from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    key: str
    label: str
    default_base_url: str
    chat_path: str
    models_path: str
    requires_api_key: bool
    key_hint: str
    fallback_models: tuple[str, ...] = ()
    novice_hint: str = ""
    key_url: str = ""


PROVIDERS: dict[str, ProviderConfig] = {
    "ccswitch": ProviderConfig(
        key="ccswitch",
        label="ccSwitch（本机）",
        default_base_url="http://127.0.0.1:15721",
        chat_path="/v1/chat/completions",
        models_path="/v1/models",
        requires_api_key=False,
        key_hint="通常不用填；ccSwitch 开启鉴权时再填写",
        fallback_models=("gpt-5.6-sol", "gpt-5.6-terra"),
        novice_hint="电脑上的 ccSwitch 已启动即可，通常不需要 API Key。",
    ),
    "deepseek": ProviderConfig(
        key="deepseek",
        label="DeepSeek",
        default_base_url="https://api.deepseek.com",
        chat_path="/chat/completions",
        models_path="/models",
        requires_api_key=True,
        key_hint="粘贴 DeepSeek 控制台创建的 API Key",
        novice_hint="在 DeepSeek 控制台创建 Key，粘贴到这里即可。",
        key_url="https://platform.deepseek.com/api_keys",
    ),
    "zhipu": ProviderConfig(
        key="zhipu",
        label="智谱 AI",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        chat_path="/chat/completions",
        models_path="/models",
        requires_api_key=True,
        key_hint="粘贴智谱开放平台创建的 API Key",
        novice_hint="在智谱开放平台创建 Key，粘贴到这里即可。",
        key_url="https://open.bigmodel.cn/usercenter/apikeys",
    ),
}

PROVIDER_LABELS = [config.label for config in PROVIDERS.values()]
_LABEL_TO_KEY = {config.label: key for key, config in PROVIDERS.items()}


def normalize_provider(value: str | None) -> str:
    provider = str(value or "").strip().lower()
    if provider in PROVIDERS:
        return provider
    return _LABEL_TO_KEY.get(str(value or "").strip(), "ccswitch")


def provider_config(value: str | None) -> ProviderConfig:
    return PROVIDERS[normalize_provider(value)]


def provider_key_from_label(label: str) -> str:
    return _LABEL_TO_KEY.get(str(label or "").strip(), normalize_provider(label))


def effective_base_url(provider: str, configured: str = "") -> str:
    return (str(configured or "").strip() or provider_config(provider).default_base_url).rstrip("/")


def endpoint_after_provider_switch(previous: str, selected: str, current: str = "") -> str:
    """Keep custom gateways only while the selected provider is unchanged."""
    previous_key = normalize_provider(previous)
    selected_key = normalize_provider(selected)
    if previous_key != selected_key:
        return provider_config(selected_key).default_base_url
    return effective_base_url(selected_key, current)


def endpoint_url(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    suffix = "/" + str(path or "").strip().lstrip("/")
    if base.lower().endswith(suffix.lower()):
        return base
    if base.lower().endswith("/v1") and suffix.lower().startswith("/v1/"):
        suffix = suffix[3:]
    return base + suffix
