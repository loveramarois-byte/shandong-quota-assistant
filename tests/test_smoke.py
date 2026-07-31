from __future__ import annotations

import importlib
import unittest

MODULES = [
    "app.main",
    "components.about_dialog",
    "components.button",
    "components.input",
    "components.message",
    "components.modal",
    "components.result",
    "components.settings_dialog",
    "components.sidebar",
    "components.toast",
    "themes.tokens",
    "utils.ai_validate",
    "utils.catalog",
    "utils.ccswitch",
    "utils.fonts",
    "utils.formatting",
    "utils.logging_setup",
    "utils.paths",
    "utils.query_parse",
    "utils.result_export",
    "utils.sessions",
    "utils.settings",
    "utils.single_instance",
    "utils.windows_theme",
]


class ImportSmokeTests(unittest.TestCase):
    def test_all_modules_import_cleanly(self):
        failures = []
        for name in MODULES:
            try:
                importlib.import_module(name)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: {exc}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_app_entrypoint_exists(self):
        from app.main import main
        self.assertTrue(callable(main))

    def test_version_is_set(self):
        from utils.paths import APP_VERSION
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
