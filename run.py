from __future__ import annotations

import argparse
import os


def _prepare_runtime() -> None:
    parser = argparse.ArgumentParser(description="山东定额助手")
    parser.add_argument("--demo", action="store_true", help="使用无版权合成演示资料库")
    args = parser.parse_args()
    if args.demo:
        from tools.build_demo_catalog import default_demo_path, build_demo_catalog

        path = default_demo_path()
        if not path.exists():
            build_demo_catalog(path)
        os.environ["SHANDONG_QUOTA_DB"] = str(path)
        os.environ["SHANDONG_DEMO_MODE"] = "1"


if __name__ == "__main__":
    _prepare_runtime()
    from app.main import main

    raise SystemExit(main())
