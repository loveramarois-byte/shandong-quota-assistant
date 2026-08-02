from __future__ import annotations

import json
import unittest
from urllib.error import URLError

from utils.updater import check_latest, is_newer, should_check, version_key


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class UpdaterTests(unittest.TestCase):
    def test_version_comparison_handles_v_prefix(self):
        self.assertEqual(version_key("v0.8.7"), (0, 8, 7))
        self.assertTrue(is_newer("v0.9.0", "0.8.7"))
        self.assertFalse(is_newer("0.8.7", "0.8.7"))

    def test_daily_check_window(self):
        self.assertFalse(should_check(1000, now=1100, interval=3600))
        self.assertTrue(should_check(1000, now=5000, interval=3600))
        self.assertTrue(should_check("bad", now=5000, interval=3600))

    def test_github_newer_release_is_returned(self):
        def opener(_request, timeout):
            self.assertEqual(timeout, 2.5)
            return _Response({"tag_name": "v0.8.8", "html_url": "https://example.invalid/release"})

        release = check_latest(current_version="0.8.7", timeout=2.5, opener=opener)
        self.assertIsNotNone(release)
        self.assertEqual(release.version, "0.8.8")
        self.assertEqual(release.source, "GitHub")

    def test_gitee_is_used_when_github_is_unavailable(self):
        calls = 0

        def opener(_request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise URLError("offline")
            return _Response({"tag_name": "v0.8.9", "html_url": "https://example.invalid/gitee"})

        release = check_latest(current_version="0.8.7", opener=opener)
        self.assertIsNotNone(release)
        self.assertEqual(release.source, "Gitee")

    def test_current_release_returns_none(self):
        def opener(_request, timeout):
            return _Response({"tag_name": "v0.8.7"})

        self.assertIsNone(check_latest(current_version="0.8.7", opener=opener))


if __name__ == "__main__":
    unittest.main()
