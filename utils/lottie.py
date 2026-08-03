from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path

from utils.motion import motion_enabled


def lottie_frame_delay(asset: Path, default: int = 120) -> int:
    """Read lightweight timing metadata from a standard Lottie JSON asset."""
    try:
        payload = json.loads(asset.read_text(encoding="utf-8"))
        frame_rate = float(payload.get("fr") or 0)
        if frame_rate > 0:
            return max(80, min(180, int(4000 / frame_rate)))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return int(default)


class LottiePulse(tk.Canvas):
    """A tiny Lottie-backed status indicator with a native Canvas fallback.

    The Lottie timing metadata is read off the UI path. Rendering three dots
    natively keeps the waiting state smooth without a browser runtime.
    """

    def __init__(self, master: tk.Misc, asset: Path, color: str, background: str) -> None:
        super().__init__(master, width=22, height=18, bg=background, highlightthickness=0, bd=0)
        self.color = color
        self.background = background
        self.frame_delay = 120
        self._job: str | None = None
        self._step = 0
        self._draw()
        threading.Thread(
            target=self._load_timing,
            args=(asset,),
            name="lottie-timing",
            daemon=True,
        ).start()

    def _load_timing(self, asset: Path) -> None:
        # This worker never touches Tk. The next animation tick simply picks
        # up the calculated delay, so the first result card remains instant.
        self.frame_delay = lottie_frame_delay(asset, self.frame_delay)

    def apply_theme(self, color: str, background: str) -> None:
        self.color = color
        self.background = background
        self.configure(bg=background)
        self._draw()

    def start(self) -> None:
        if not motion_enabled():
            self._step = 1
            self._draw()
            return
        if self._job is None:
            self._tick()

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self._step = 0
        self._draw()

    def _tick(self) -> None:
        self._step = (self._step + 1) % 3
        self._draw()
        self._job = self.after(self.frame_delay, self._tick)

    def _draw(self) -> None:
        self.delete("all")
        for index, x in enumerate((4, 11, 18)):
            radius = 3 if index == self._step else 2
            self.create_oval(x - radius, 9 - radius, x + radius, 9 + radius, fill=self.color, outline="")
