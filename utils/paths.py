from __future__ import annotations

import os
import sys
from pathlib import Path


APP_VERSION = "0.9.7"
APP_NAME = "山东定额助手"
APP_DIR_NAME = "ShandongQuotaAssistant"
CATALOG_SCHEMA_VERSION = 3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))


def resource_path(*parts: str) -> Path:
    return RUNTIME_ROOT.joinpath(*parts)


def writable_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.joinpath(*parts)
    return PROJECT_ROOT.joinpath(*parts)


def app_data_dir() -> Path:
    """Per-user writable data dir; never depends on a developer machine path."""
    base = None
    for env_name in ("APPDATA", "USERPROFILE"):
        value = os.environ.get(env_name)
        if value:
            candidate = Path(value) if env_name == "APPDATA" else Path(value) / "AppData" / "Roaming"
            base = candidate
            break
    if base is None:
        try:
            base = Path.home() / "AppData" / "Roaming"
        except RuntimeError:
            import tempfile

            base = Path(tempfile.gettempdir())
    target = base / APP_DIR_NAME
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        target = writable_path("userdata")
        target.mkdir(parents=True, exist_ok=True)
    return target


def logs_dir() -> Path:
    target = app_data_dir() / "logs"
    target.mkdir(parents=True, exist_ok=True)
    return target


def sessions_dir() -> Path:
    target = app_data_dir() / "sessions"
    target.mkdir(parents=True, exist_ok=True)
    return target


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def credentials_path() -> Path:
    return app_data_dir() / "credentials.json"


def exports_dir() -> Path:
    target = app_data_dir() / "exports"
    target.mkdir(parents=True, exist_ok=True)
    return target


def database_path() -> Path:
    override = os.environ.get("SHANDONG_QUOTA_DB")
    executable_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
    candidates = [
        Path(override) if override else None,
        writable_path("data", "shandong_quota.sqlite"),
        executable_root.parent.parent / "data" / "shandong_quota.sqlite" if executable_root else None,
        PROJECT_ROOT / "data" / "shandong_quota.sqlite",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    raise FileNotFoundError("未找到 shandong_quota.sqlite；请放到 data 目录或设置 SHANDONG_QUOTA_DB。")


def catalog_manifest_path() -> Path | None:
    candidates = (
        writable_path("manifests", "catalog-baseline.json"),
        PROJECT_ROOT / "manifests" / "catalog-baseline.json",
        resource_path("manifests", "catalog-baseline.json"),
    )
    return next((path for path in candidates if path.exists()), None)
