from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
import threading

from .ai_providers import normalize_provider
from .paths import credentials_path


_LOCK = threading.RLock()
_PREFIX = "dpapi:"
_ENTROPY = b"ShandongQuotaAssistant.ai-credentials.v1"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[_DataBlob, object]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _crypt32():
    if os.name != "nt":
        raise RuntimeError("API Key 加密仅支持 Windows")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _protect(data: bytes) -> bytes:
    crypt32, kernel32 = _crypt32()
    source, source_buffer = _blob(data)
    entropy, entropy_buffer = _blob(_ENTROPY)
    result = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(source),
        "ShandongQuotaAssistant",
        ctypes.byref(entropy),
        None,
        None,
        0x1,
        ctypes.byref(result),
    )
    _ = source_buffer, entropy_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)


def _unprotect(data: bytes) -> bytes:
    crypt32, kernel32 = _crypt32()
    source, source_buffer = _blob(data)
    entropy, entropy_buffer = _blob(_ENTROPY)
    result = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        0x1,
        ctypes.byref(result),
    )
    _ = source_buffer, entropy_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)


def _read_store() -> dict[str, str]:
    try:
        raw = json.loads(credentials_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): str(value) for key, value in raw.items()} if isinstance(raw, dict) else {}


def _write_store(store: dict[str, str]) -> None:
    path = credentials_path()
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(store, handle, ensure_ascii=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def save_api_key(provider: str, api_key: str) -> None:
    provider = normalize_provider(provider)
    secret = str(api_key or "").strip()
    if not secret:
        return
    encrypted = _PREFIX + base64.b64encode(_protect(secret.encode("utf-8"))).decode("ascii")
    with _LOCK:
        store = _read_store()
        store[provider] = encrypted
        _write_store(store)


def load_api_key(provider: str) -> str:
    provider = normalize_provider(provider)
    with _LOCK:
        encoded = _read_store().get(provider, "")
    if not encoded.startswith(_PREFIX):
        return ""
    try:
        encrypted = base64.b64decode(encoded[len(_PREFIX):], validate=True)
        return _unprotect(encrypted).decode("utf-8")
    except (ValueError, UnicodeDecodeError, OSError):
        return ""


def delete_api_key(provider: str) -> None:
    provider = normalize_provider(provider)
    with _LOCK:
        store = _read_store()
        if provider not in store:
            return
        store.pop(provider, None)
        _write_store(store)
