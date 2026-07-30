from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

from PIL import ImageGrab

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import QuotaApp


DEFAULT_QUERY = "地下室外墙外侧做4mm SBS防水两道，20厚水泥砂浆保护层，外侧回填三七灰土，机械夯实。"
QUERY = os.environ.get("UI_SMOKE_QUERY", DEFAULT_QUERY).strip() or DEFAULT_QUERY
VIEW = os.environ.get("UI_SMOKE_VIEW", "default").strip().lower()
THEME = os.environ.get("UI_SMOKE_THEME", "").strip().lower()


def _capture(app: QuotaApp, path: Path) -> None:
    try:
        app.deiconify()
        app.lift()
        app.attributes("-topmost", True)
        app.update()
        time.sleep(0.15)
        left, top = app.winfo_rootx(), app.winfo_rooty()
        width, height = app.winfo_width(), app.winfo_height()
        ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True).save(path)
    finally:
        try:
            app.attributes("-topmost", False)
        except Exception:
            pass


def main() -> int:
    output = Path(os.environ.get("UI_SMOKE_OUTPUT", "build/ui-smoke")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QuotaApp()
    original_theme = app.theme_name
    if THEME in {"light", "dark"} and THEME != original_theme:
        app._toggle_theme()
    app._request_id = 1  # prevent deferred history restoration during the smoke run
    app._new_session()
    requested_discipline = os.environ.get("UI_SMOKE_DISCIPLINE", "").strip()
    if requested_discipline:
        app.discipline.set(requested_discipline)
    started = time.monotonic()
    local_saved = False
    final_saved = False
    finish_scheduled = False
    ai_expected = bool(app.settings.get("ai_enabled", False))

    def finish() -> None:
        nonlocal final_saved
        if final_saved:
            return
        final_saved = True
        if app._last_panel is not None:
            if VIEW in {"analysis", "expanded"} and not app._last_panel._analysis_visible:
                app._last_panel._toggle_analysis()
            if VIEW == "expanded" and not app._last_panel._details_visible:
                app._last_panel._toggle_details()
            app.feed.scroll_to_entry(app._last_panel)
            app.update_idletasks()
        _capture(app, output / "final.png")
        latest_turn = ((app.session or {}).get("turns") or [{}])[-1]
        latest_attempt = (latest_turn.get("ai_attempts") or [{}])[-1]
        report = {
            "query": QUERY,
            "ai_expected": ai_expected,
            "ai_status": latest_attempt.get("status"),
            "structured_valid": (latest_attempt.get("validation") or {}).get("structured_valid"),
            "decision_status": ((latest_turn.get("retrieval_snapshot") or {}).get("decision_status")),
            "proposal_count": len((latest_turn.get("retrieval_snapshot") or {}).get("proposals") or []),
            "result_discipline": (latest_turn.get("retrieval_snapshot") or {}).get("discipline"),
            "discipline_auto_switched": (latest_turn.get("retrieval_snapshot") or {}).get("discipline_auto_switched"),
            "active_ai_task": bool(app.tasks.latest_ai((app.session or {}).get("id"))),
            "cancel_button_manager": app.composer.cancel_button.winfo_manager(),
            "send_button_manager": app.composer.send_button.winfo_manager(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "view": VIEW,
            "theme": app.theme_name,
        }
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if app.theme_name != original_theme:
            app._toggle_theme()
        app.after(200, app._on_close)

    def poll() -> None:
        nonlocal local_saved, finish_scheduled
        elapsed = time.monotonic() - started
        if app._last_panel is not None and not local_saved:
            local_saved = True
            app.feed.scroll_to_entry(app._last_panel)
            app.after(500, lambda: _capture(app, output / "local-proposal.png"))
        active_ai = app.tasks.latest_ai((app.session or {}).get("id")) if app.session else None
        if local_saved and (app._last_ai_text or (not ai_expected and active_ai is None) or (elapsed > 8 and active_ai is None)):
            if not finish_scheduled:
                finish_scheduled = True
                app.after(600, finish)
            return
        if elapsed >= 120:
            finish()
            return
        app.after(250, poll)

    def send() -> None:
        app.composer.set_text(QUERY)
        app._send()
        poll()

    app.after(500, send)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
