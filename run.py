from __future__ import annotations

import argparse
import os


def _prepare_runtime() -> None:
    parser = argparse.ArgumentParser(description="山东定额助手")
    parser.add_argument("--demo", action="store_true", help="使用无版权合成演示资料库")
    parser.add_argument("--legacy-tk", action="store_true", help="使用迁移前的 CustomTkinter 界面")
    args = parser.parse_args()
    if args.demo:
        from tools.build_demo_catalog import default_demo_path, build_demo_catalog

        path = default_demo_path()
        if not path.exists():
            build_demo_catalog(path)
        os.environ["SHANDONG_QUOTA_DB"] = str(path)
        os.environ["SHANDONG_DEMO_MODE"] = "1"
    if args.legacy_tk:
        os.environ["SHANDONG_LEGACY_TK"] = "1"


if __name__ == "__main__":
    _prepare_runtime()
    if os.environ.get("SHANDONG_LEGACY_TK") == "1":
        from app.main import main
    else:
        from app.qt_main import main

    raise SystemExit(main())
