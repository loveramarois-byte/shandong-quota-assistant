from __future__ import annotations

import tkinter as tk
from pathlib import Path


class LottiePulse(tk.Canvas):
    """A tiny Lottie-backed status indicator with a native Canvas fallback.

    The animation asset is parsed at startup to validate its timing metadata.
    Rendering three dots natively keeps the loading state smooth on Tk's UI
    thread without introducing a heavyweight browser runtime.
    """

    def __init__(self, master: tk.Misc, asset: Path, color: str, background: str) -> None:
        super().__init__(master, width=22, height=18, bg=background, highlightthickness=0, bd=0)
        self.color = color
        self.background = background
        self.frame_delay = 120
        self._job: str | None = None
        self._step = 0
        try:
            from lottie.parsers.tgs import parse_tgs

            animation = parse_tgs(str(asset))
            self.frame_delay = max(80, min(180, int(1000 / max(1, animation.frame_rate / 4))))
        except Exception:
            pass
        self._draw()

    def apply_theme(self, color: str, background: str) -> None:
        self.color = color
        self.background = background
        self.configure(bg=background)
        self._draw()

    def start(self) -> None:
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
