from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GITHUB_LATEST_API = "https://api.github.com/repos/loveramarois-byte/shandong-quota-assistant/releases/latest"
GITEE_LATEST_API = "https://gitee.com/api/v5/repos/bbbbo-liu/shandong-quota-assistant/releases/latest"
GITHUB_RELEASES_URL = "https://github.com/loveramarois-byte/shandong-quota-assistant/releases/latest"
GITEE_RELEASES_URL = "https://gitee.com/bbbbo-liu/shandong-quota-assistant/releases"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    url: str
    source: str
    published_at: str = ""


def version_key(value: str | None) -> tuple[int, ...]:
    """Parse release versions without adding a packaging dependency."""
    raw = str(value or "").strip().lower()
    if raw.startswith("v"):
        raw = raw[1:]
    parts: list[int] = []
    for token in raw.split("."):
        digits = "".join(char for char in token if char.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts or [0])


def is_newer(candidate: str | None, current: str | None) -> bool:
    return version_key(candidate) > version_key(current)


def should_check(last_checked: float | int | None, *, now: float | None = None, interval: int = CHECK_INTERVAL_SECONDS) -> bool:
    try:
        previous = float(last_checked or 0)
        current = time.time() if now is None else float(now)
        return previous <= 0 or current - previous >= max(60, int(interval))
    except (TypeError, ValueError, OverflowError):
        return True


def _read_release(api_url: str, *, source: str, fallback_url: str, timeout: float, opener: Callable = urlopen) -> ReleaseInfo:
    request = Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ShandongQuotaAssistant-updater",
        },
    )
    with opener(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag = str(payload.get("tag_name") or payload.get("tag") or "").strip()
    version = tag[1:] if tag.lower().startswith("v") else tag
    if not version or version_key(version) == (0,):
        raise ValueError("release response has no usable version")
    return ReleaseInfo(
        version=version,
        tag=tag or f"v{version}",
        url=str(payload.get("html_url") or fallback_url),
        source=source,
        published_at=str(payload.get("published_at") or payload.get("created_at") or ""),
    )


def check_latest(*, current_version: str, timeout: float = 3.0, opener: Callable = urlopen) -> ReleaseInfo | None:
    """Return a newer public release, or ``None`` when current/upstream is unavailable."""
    sources = (
        (GITHUB_LATEST_API, "GitHub", GITHUB_RELEASES_URL),
        (GITEE_LATEST_API, "Gitee", GITEE_RELEASES_URL),
    )
    for api_url, source, fallback_url in sources:
        try:
            release = _read_release(api_url, source=source, fallback_url=fallback_url, timeout=timeout, opener=opener)
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError, TimeoutError):
            continue
        if is_newer(release.version, current_version):
            return release
        return None
    return None
