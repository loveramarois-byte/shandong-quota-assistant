from __future__ import annotations

import sys
import tkinter as tk
import time
import weakref

import customtkinter as ctk

from utils.motion import motion_enabled


def normalized_wheel_pixels(delta: int | float, step: int = 56) -> float:
    """Map a Windows 120-delta wheel notch to a stable pixel distance."""
    try:
        return -(float(delta) / 120.0) * step
    except (TypeError, ValueError):
        return 0.0


def pixel_scroll_fraction(view: tuple[float, float], pixels: int | float, viewport_pixels: int | float) -> float | None:
    """Translate a pixel delta into a bounded Tk canvas ``moveto`` fraction.

    ``Canvas.yview_scroll(..., "units")`` does not accept pixels: one unit is
    derived from Tk's scroll increment and therefore changes with the widget.
    Using the visible fraction lets every scrollable pane move by the same
    physical distance and keeps the thumb and content on the same view.
    """
    try:
        first, last = float(view[0]), float(view[1])
        delta = float(pixels)
        viewport = float(viewport_pixels)
    except (IndexError, TypeError, ValueError):
        return None
    span = last - first
    if not delta or viewport <= 0 or span <= 0 or span >= 1:
        return None
    total_pixels = viewport / span
    maximum = max(0.0, 1.0 - span)
    target = max(0.0, min(maximum, first + (delta / total_pixels)))
    return target if abs(target - first) > 1e-9 else None


def view_can_scroll(view: tuple[float, float], pixels: int | float) -> bool:
    """Return whether ``view`` can move in the requested pixel direction."""
    try:
        first, last = float(view[0]), float(view[1])
        delta = float(pixels)
    except (IndexError, TypeError, ValueError):
        return False
    if delta < 0:
        return first > 1e-9
    if delta > 0:
        return last < 1.0 - 1e-9
    return False


def ease_out_cubic(progress: float) -> float:
    value = max(0.0, min(1.0, float(progress)))
    return 1.0 - ((1.0 - value) ** 3)


class PointerScrollableFrame(ctk.CTkScrollableFrame):
    """Route and coalesce wheel input for the area under the pointer."""

    WHEEL_STEP = 56
    WHEEL_FLUSH_MS = 8
    _instances: weakref.WeakSet["PointerScrollableFrame"] = weakref.WeakSet()

    def __init__(self, *args, **kwargs):
        self._wheel_remainder = 0.0
        self._pending_vertical_pixels = 0
        self._pending_horizontal_pixels = 0
        self._wheel_job: str | None = None
        self._scroll_animation_job: str | None = None
        super().__init__(*args, **kwargs)
        try:
            self._scrollbar.configure(width=6)
            self._parent_canvas.configure(highlightthickness=0, yscrollincrement=1)
        except (AttributeError, tk.TclError):
            pass
        self._instances.add(self)

        # CTkScrollableFrame registers one bind_all callback per instance.
        # Keep one dispatcher for the whole Tk interpreter so sibling panes
        # cannot process the same event independently.
        if sys.platform.startswith("win"):
            self.unbind_all("<MouseWheel>")
            self.bind_all("<MouseWheel>", self._dispatch_windows_wheel, add="+")

    def apply_surface_color(self, color: str) -> None:
        """Update the CTk wrapper and its native canvas in one operation.

        CTkScrollableFrame is a composition of a CTkFrame, a native Tk canvas
        and this inner frame. Changing only ``fg_color`` can leave the canvas
        on the previous appearance mode for one or more idle frames, which is
        especially visible when switching to dark mode.
        """
        self.configure(fg_color=color)
        try:
            self._parent_canvas.configure(bg=color)
            tk.Frame.configure(self, bg=color)
        except (AttributeError, tk.TclError):
            pass

    def _pointer_belongs_here(self) -> bool:
        try:
            widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
            return widget is not None and self._check_if_valid_scroll(widget)
        except (AttributeError, RuntimeError, tk.TclError):
            return False

    @staticmethod
    def _dispatch_windows_wheel(event):
        candidates: list[PointerScrollableFrame] = []
        event_widget = getattr(event, "widget", None)
        for frame in tuple(PointerScrollableFrame._instances):
            try:
                if not frame.winfo_exists():
                    continue
                # Tk already tells us which child received the wheel. Walking
                # that widget tree avoids a winfo_containing call for every
                # scroll frame on every wheel tick, which is noticeable on a
                # large message feed.
                belongs = bool(event_widget is not None and frame._check_if_valid_scroll(event_widget))
                if not belongs:
                    belongs = frame._pointer_belongs_here()
                if belongs:
                    candidates.append(frame)
            except (RuntimeError, tk.TclError):
                continue
        if not candidates:
            return None

        # Prefer the deepest pane under the pointer, but hand the wheel to its
        # scrollable parent when the nested pane has reached an edge.
        candidates.sort(key=lambda frame: len(frame.winfo_pathname(frame.winfo_id())), reverse=True)
        pixels = normalized_wheel_pixels(getattr(event, "delta", 0), PointerScrollableFrame.WHEEL_STEP)
        shift_from_event = bool(int(getattr(event, "state", 0) or 0) & 0x1)
        for target in candidates:
            horizontal = shift_from_event or bool(getattr(target, "_shift_pressed", False))
            canvas = target._parent_canvas
            view = canvas.xview() if horizontal else canvas.yview()
            if view_can_scroll(view, pixels):
                target._queue_wheel(getattr(event, "delta", 0), horizontal=horizontal)
                break
        return "break"

    def _queue_wheel(self, delta: int | float, *, horizontal: bool) -> None:
        cancel_animation = getattr(self, "_cancel_smooth_scroll", None)
        if callable(cancel_animation):
            cancel_animation()
        self._wheel_remainder += normalized_wheel_pixels(delta, self.WHEEL_STEP)
        pixels = int(self._wheel_remainder)
        self._wheel_remainder -= pixels
        if not pixels:
            return
        if horizontal:
            self._pending_horizontal_pixels += pixels
        else:
            self._pending_vertical_pixels += pixels
        if self._wheel_job is None:
            self._wheel_job = self.after(self.WHEEL_FLUSH_MS, self._flush_wheel)

    def _flush_wheel(self) -> None:
        self._wheel_job = None
        horizontal = self._pending_horizontal_pixels
        vertical = self._pending_vertical_pixels
        self._pending_horizontal_pixels = 0
        self._pending_vertical_pixels = 0
        try:
            if horizontal:
                view = self._parent_canvas.xview()
                target = pixel_scroll_fraction(view, horizontal, self._parent_canvas.winfo_width())
                if target is not None:
                    self._parent_canvas.xview_moveto(target)
            if vertical:
                view = self._parent_canvas.yview()
                target = pixel_scroll_fraction(view, vertical, self._parent_canvas.winfo_height())
                if target is not None:
                    self._parent_canvas.yview_moveto(target)
        except tk.TclError:
            pass

    def smooth_moveto(self, fraction: float, duration_ms: int = 180) -> None:
        """Move the vertical canvas with a short, cancellable ease-out."""
        self._cancel_smooth_scroll()
        if not motion_enabled():
            duration_ms = 0
        try:
            start = float(self._parent_canvas.yview()[0])
        except (IndexError, TypeError, ValueError, tk.TclError):
            return
        target = max(0.0, min(1.0, float(fraction)))
        if abs(target - start) < 1e-6 or duration_ms <= 0:
            try:
                self._parent_canvas.yview_moveto(target)
            except tk.TclError:
                pass
            return
        started = time.perf_counter()

        def step() -> None:
            elapsed = (time.perf_counter() - started) * 1000
            progress = min(1.0, elapsed / max(1, duration_ms))
            value = start + ((target - start) * ease_out_cubic(progress))
            try:
                self._parent_canvas.yview_moveto(value)
            except tk.TclError:
                self._scroll_animation_job = None
                return
            if progress < 1.0:
                self._scroll_animation_job = self.after(16, step)
            else:
                self._scroll_animation_job = None

        self._scroll_animation_job = self.after(0, step)

    def _cancel_smooth_scroll(self) -> None:
        if self._scroll_animation_job is not None:
            try:
                self.after_cancel(self._scroll_animation_job)
            except tk.TclError:
                pass
            self._scroll_animation_job = None

    def cancel_scroll_motion(self) -> None:
        """Stop a programmatic scroll before a resize redraw starts."""
        self._cancel_smooth_scroll()

    def destroy(self):
        self._instances.discard(self)
        self._cancel_smooth_scroll()
        if self._wheel_job is not None:
            try:
                self.after_cancel(self._wheel_job)
            except tk.TclError:
                pass
            self._wheel_job = None
        super().destroy()
