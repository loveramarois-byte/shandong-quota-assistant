from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


ERROR_ALREADY_EXISTS = 183


class SingleInstanceGuard:
    """Process-wide Windows mutex that prevents concurrent session writers."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._handle: int | None = None

    def acquire(self) -> bool:
        if os.name != "nt":
            return True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, True, self.name)
        if not handle:
            return False
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self._handle = int(handle)
        return True

    def release(self) -> None:
        if os.name != "nt" or not self._handle:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReleaseMutex(wintypes.HANDLE(self._handle))
        kernel32.CloseHandle(wintypes.HANDLE(self._handle))
        self._handle = None

    def __enter__(self) -> "SingleInstanceGuard":
        if not self.acquire():
            raise RuntimeError("application instance already running")
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.release()
