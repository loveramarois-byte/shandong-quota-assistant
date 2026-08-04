"""Repeat the primary Qt workflow without touching the user's profile/window."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SHANDONG_DEMO_MODE", "0")
os.environ["APPDATA"] = str(Path(__file__).resolve().parents[1] / "build" / "qt-50-profile")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from app.qt_main import QuotaQtApp


QUERIES = (
    "地下室外墙4mm厚SBS防水卷材",
    "现浇C30混凝土柱，泵送施工",
    "室内给水管道安装DN25 PPR管",
    "挖沟槽土方，三类土，机械夯实",
    "外墙水泥砂浆抹灰20mm厚",
)


def wait_until(window: QuotaQtApp, predicate, timeout_ms: int = 30000) -> bool:
    loop = QEventLoop()
    started = time.perf_counter()

    def poll() -> None:
        if predicate() or (time.perf_counter() - started) * 1000 >= timeout_ms:
            loop.quit()
        else:
            QTimer.singleShot(20, poll)

    poll()
    loop.exec()
    return bool(predicate())


def main() -> int:
    app = QApplication([])
    window = QuotaQtApp()
    window.show()
    app.processEvents()
    failures: list[dict] = []
    durations: list[float] = []
    proposal_counts: list[int] = []
    for index in range(50):
        started = time.perf_counter()
        try:
            window._new_session()
            window.composer.set_text(QUERIES[index % len(QUERIES)])
            window._send()
            done = wait_until(window, lambda: window._cancel is None)
            app.processEvents()
            if not done:
                raise TimeoutError("workflow did not finish within 30 seconds")
            turn = ((window._session or {}).get("turns") or [{}])[-1]
            snapshot = turn.get("retrieval_snapshot") or {}
            proposal_counts.append(len(snapshot.get("proposals") or []))
            if not snapshot:
                raise AssertionError("local result snapshot is empty")
            if index % 5 == 0:
                window._toggle_theme()
            if index % 3 == 0:
                window._refresh_sessions()
            window.scroll.verticalScrollBar().setValue(window.scroll.verticalScrollBar().maximum())
            app.processEvents()
        except Exception as exc:  # noqa: BLE001 - this is a diagnostic harness
            failures.append({"iteration": index + 1, "error": repr(exc)})
            if window._cancel:
                window._cancel.set()
                window._finish_job()
        durations.append(round(time.perf_counter() - started, 3))
    window.close()
    report = {
        "iterations": 50,
        "failures": failures,
        "failure_count": len(failures),
        "duration_seconds": durations,
        "max_duration_seconds": max(durations) if durations else 0,
        "mean_duration_seconds": round(sum(durations) / len(durations), 3) if durations else 0,
        "proposal_counts": proposal_counts,
        "themes_exercised": ["light", "dark"],
        "workflow": ["new_session", "input", "local_search", "result_render", "theme_toggle", "session_refresh", "scroll"],
    }
    output = Path(__file__).resolve().parents[1] / "build" / "qt-real-machine-50.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
