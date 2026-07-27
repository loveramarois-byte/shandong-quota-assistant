from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils import secrets


class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "credentials.json"
        self.path_patch = mock.patch.object(secrets, "credentials_path", lambda: self.path)
        self.protect_patch = mock.patch.object(secrets, "_protect", lambda value: value[::-1])
        self.unprotect_patch = mock.patch.object(secrets, "_unprotect", lambda value: value[::-1])
        self.path_patch.start()
        self.protect_patch.start()
        self.unprotect_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.addCleanup(self.protect_patch.stop)
        self.addCleanup(self.unprotect_patch.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_roundtrip_never_writes_plaintext(self):
        secrets.save_api_key("deepseek", "sk-plain-secret")
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn("sk-plain-secret", raw)
        self.assertIn("dpapi:", raw)
        self.assertEqual(secrets.load_api_key("deepseek"), "sk-plain-secret")

    def test_keys_are_isolated_by_provider_and_can_be_deleted(self):
        secrets.save_api_key("deepseek", "deepseek-key")
        secrets.save_api_key("zhipu", "zhipu-key")
        secrets.delete_api_key("deepseek")
        self.assertEqual(secrets.load_api_key("deepseek"), "")
        self.assertEqual(secrets.load_api_key("zhipu"), "zhipu-key")


if __name__ == "__main__":
    unittest.main()
