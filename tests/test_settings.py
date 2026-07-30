from __future__ import annotations

import os
import tempfile
import unittest

from tests.support import requires_authorized_catalog
from pathlib import Path
from unittest import mock

from utils import paths
from utils import settings as settings_module
from utils.paths import PROJECT_ROOT


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._settings_file = Path(self._tmp.name) / "settings.json"
        patcher = mock.patch.object(settings_module, "settings_path", lambda: self._settings_file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_defaults_are_sane(self):
        cleaned = settings_module.sanitize_settings({})
        self.assertEqual(cleaned["quota_edition"], "2025")
        self.assertEqual(cleaned["standard_edition"], "2024")
        self.assertEqual(cleaned["discipline"], "建筑")
        self.assertEqual(settings_module.DISCIPLINE_OPTIONS, ("建筑", "安装", "市政", "园林"))
        self.assertNotIn("全部专业", settings_module.DISCIPLINE_OPTIONS)
        self.assertEqual(cleaned["ai_provider"], "ccswitch")
        self.assertFalse(cleaned["ai_enabled"])

    def test_legacy_ccswitch_fields_migrate_to_generic_ai_fields(self):
        cleaned = settings_module.sanitize_settings({
            "ccswitch_base_url": "http://127.0.0.1:19999",
            "ccswitch_model": "legacy-model",
            "ccswitch_timeout": 45,
        })
        self.assertEqual(cleaned["ai_provider"], "ccswitch")
        self.assertEqual(cleaned["ai_base_url"], "http://127.0.0.1:19999")
        self.assertEqual(cleaned["ai_model"], "legacy-model")
        self.assertEqual(cleaned["ai_timeout"], 45)

    def test_invalid_values_fall_back(self):
        cleaned = settings_module.sanitize_settings({"quota_edition": "2099", "discipline": "外星", "ccswitch_timeout": 9999, "theme": "neon"})
        self.assertEqual(cleaned["quota_edition"], "2025")
        self.assertEqual(cleaned["discipline"], "建筑")
        self.assertEqual(cleaned["ccswitch_timeout"], 0)
        self.assertEqual(cleaned["theme"], "light")

    def test_save_and_load_roundtrip(self):
        saved = {"quota_edition": "2016", "discipline": "安装", "ai_enabled": False, "enter_send": True, "ccswitch_model": "test-model"}
        settings_module.save_settings(saved)
        loaded = settings_module.load_settings()
        self.assertEqual(loaded["quota_edition"], "2016")
        self.assertEqual(loaded["discipline"], "安装")
        self.assertFalse(loaded["ai_enabled"])
        self.assertTrue(loaded["enter_send"])
        self.assertEqual(loaded["ccswitch_model"], "test-model")

    def test_legacy_all_disciplines_setting_migrates_to_building(self):
        cleaned = settings_module.sanitize_settings({"discipline": "全部专业"})
        self.assertEqual(cleaned["discipline"], "建筑")
        self.assertEqual(
            settings_module.DISCIPLINE_LABEL_TO_CODE[cleaned["discipline"]],
            "building",
        )

    def test_corrupt_settings_file_falls_back_to_defaults(self):
        self._settings_file.write_text("{not json", encoding="utf-8")
        loaded = settings_module.load_settings()
        self.assertEqual(loaded["quota_edition"], "2025")

    def test_apply_overrides_sets_environment(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CCSWITCH_MODEL", None)
            settings_module.apply_ccswitch_overrides({"ccswitch_model": "override-model", "ccswitch_base_url": "", "ccswitch_timeout": 45})
            self.assertEqual(os.environ.get("CCSWITCH_MODEL"), "override-model")
            self.assertEqual(os.environ.get("CCSWITCH_TIMEOUT"), "45")

    def test_deepseek_overrides_use_default_endpoint_and_encrypted_key_loader(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(settings_module, "load_api_key", return_value="sk-encrypted"):
            settings_module.apply_ccswitch_overrides({"ai_provider": "deepseek", "ai_model": "deepseek-chat"})
            self.assertEqual(os.environ["AI_PROVIDER"], "deepseek")
            self.assertEqual(os.environ["AI_BASE_URL"], "https://api.deepseek.com")
            self.assertEqual(os.environ["AI_MODEL"], "deepseek-chat")
            self.assertEqual(os.environ["AI_API_KEY"], "sk-encrypted")
            self.assertNotIn("CCSWITCH_BASE_URL", os.environ)
            self.assertNotIn("CCSWITCH_MODEL", os.environ)
            self.assertNotIn("CCSWITCH_API_KEY", os.environ)

    def test_api_key_is_not_persisted_in_settings_json(self):
        settings_module.save_settings({"ai_provider": "deepseek", "ai_api_key": "sk-plain-secret"})
        raw = self._settings_file.read_text(encoding="utf-8")
        self.assertNotIn("sk-plain-secret", raw)
        self.assertNotIn("ai_api_key", raw)

    def test_remote_http_ai_endpoint_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            settings_module.validate_ai_endpoint("http://api.example.com/v1")

    def test_endpoint_rejects_embedded_credentials_and_query_tokens(self):
        with self.assertRaises(ValueError):
            settings_module.validate_ai_endpoint("https://user:secret@api.example.com/v1")
        with self.assertRaises(ValueError):
            settings_module.validate_ai_endpoint("https://api.example.com/v1?token=secret")

    def test_ai_requires_separate_description_and_catalog_consents(self):
        description_only = settings_module.sanitize_settings({"ai_enabled": True, "ai_consent_version": 1})
        self.assertFalse(description_only["ai_enabled"])
        fully_consented = settings_module.sanitize_settings({"ai_enabled": True, "ai_consent_version": 1, "ai_catalog_consent_version": 1})
        self.assertTrue(fully_consented["ai_enabled"])


class PathSafetyTests(unittest.TestCase):
    def test_no_hardcoded_dev_machine_fallback(self):
        source = (PROJECT_ROOT / "utils" / "paths.py").read_text(encoding="utf-8")
        self.assertNotIn("D:\\Desktop\\", source)

    def test_app_data_dir_is_writable_location(self):
        data_dir = paths.app_data_dir()
        self.assertTrue(data_dir.exists())
        self.assertIn("ShandongQuotaAssistant", str(data_dir))

    @requires_authorized_catalog
    def test_database_path_resolves(self):
        self.assertTrue(paths.database_path().exists())


if __name__ == "__main__":
    unittest.main()
