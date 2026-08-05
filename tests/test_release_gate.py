from __future__ import annotations

import json
import unittest

from utils.paths import APP_VERSION, PROJECT_ROOT


class ReleaseGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (PROJECT_ROOT / "build_release.ps1").read_text(encoding="utf-8-sig")
        manifest_path = PROJECT_ROOT / "manifests" / "catalog-baseline.json"
        if not manifest_path.exists():
            manifest_path = PROJECT_ROOT / "manifests" / "catalog-baseline.example.json"
        cls.catalog_manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

    def test_release_script_forbids_database_hardlinks(self):
        self.assertNotIn("ItemType HardLink", self.script)
        self.assertIn("Copy-Item -LiteralPath $database -Destination $stagedDatabase", self.script)

    def test_release_script_has_required_preflight_gates(self):
        for marker in (
            "unittest discover",
            "compileall",
            "PRAGMA quick_check",
            "PRAGMA user_version",
            "Get-FileSha256",
            "release-manifest.json",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.script)

    def test_release_compiles_every_first_party_python_package(self):
        self.assertIn('Join-Path $projectRoot "controllers"', self.script)
        self.assertIn('Join-Path $projectRoot "themes"', self.script)

    def test_staged_database_is_verified_as_an_independent_file(self):
        self.assertIn("Get-HardLinkCount $stagedDatabase", self.script)

    def test_release_version_is_consistent_across_runtime_and_packaging(self):
        self.assertEqual(APP_VERSION, "0.8.12")
        self.assertEqual(self.catalog_manifest["app_version"], APP_VERSION)
        installer = (PROJECT_ROOT / "packaging" / "ShandongQuotaAssistant.iss").read_text(encoding="utf-8-sig")
        version_info = (PROJECT_ROOT / "packaging" / "windows_version_info.txt").read_text(encoding="utf-8-sig")
        self.assertIn(f'#define MyAppVersion "{APP_VERSION}"', installer)
        self.assertIn(f"VersionInfoVersion={APP_VERSION}.0", installer)
        self.assertIn(f"StringStruct('FileVersion', '{APP_VERSION}')", version_info)
        self.assertIn(f"StringStruct('ProductVersion', '{APP_VERSION}')", version_info)

    def test_runtime_user_agent_comes_from_app_version(self):
        source = (PROJECT_ROOT / "utils" / "ccswitch.py").read_text(encoding="utf-8")
        self.assertIn('f"ShandongQuotaAssistant/{APP_VERSION}"', source)

    def test_public_example_manifest_does_not_grant_distribution_rights(self):
        example = json.loads(
            (PROJECT_ROOT / "manifests" / "catalog-baseline.example.json").read_text(encoding="utf-8")
        )
        self.assertFalse(example["database"]["distribution_authorized"])
        self.assertEqual(example["database"]["distribution_scope"], "local_only")
        self.assertIsNone(example["database"]["authorization_id"])

    def test_unsigned_authorized_mode_is_explicit_and_separate(self):
        for marker in (
            "[switch]$AuthorizedInternalDistribution",
            "build\\authorized-internal",
            "授权内部构建需要 DistributionAuthorizationId",
            "unsigned_user_accepted",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.script)
        self.assertIn('"v$appVersion"', self.script)
        self.assertIn("正式发布需要代码签名证书", self.script)

    def test_public_full_release_requires_explicit_authorization(self):
        for marker in (
            "[switch]$AuthorizedPublicDistribution",
            "[switch]$UnsignedReleaseAcknowledged",
            'distribution_scope -ne "public_release"',
            "DistributionAuthorizationId 与 catalog manifest 不一致",
            "authorized_public_distribution",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.script)

    def test_installer_is_one_self_contained_file(self):
        installer = (PROJECT_ROOT / "packaging" / "ShandongQuotaAssistant.iss").read_text(encoding="utf-8-sig")
        self.assertIn("Compression=lzma2/max", installer)
        self.assertIn("SolidCompression=yes", installer)
        self.assertIn("DiskSpanning=no", installer)
        self.assertNotIn("DiskSliceSize=", installer)

    def test_installer_is_one_click_for_regular_users(self):
        installer = (PROJECT_ROOT / "packaging" / "ShandongQuotaAssistant.iss").read_text(encoding="utf-8-sig")
        for directive in (
            "DisableWelcomePage=yes",
            "DisableDirPage=yes",
            "DisableProgramGroupPage=yes",
            "DisableReadyPage=no",
            "DisableFinishedPage=yes",
            "PrivilegesRequired=lowest",
            "ButtonInstall=一键安装(&I)",
        ):
            with self.subTest(directive=directive):
                self.assertIn(directive, installer)
        self.assertIn('Name: "{autodesktop}\\{#MyAppName}"', installer)
        self.assertIn('Flags: nowait postinstall skipifsilent', installer)

    def test_internal_build_is_separated_from_release_directory(self):
        self.assertIn("build\\internal-evaluation", self.script)
        self.assertIn("仅限内部评估", self.script)
        self.assertIn('$sourceRevision.Substring(0, 7)', self.script)

    def test_release_bundles_the_cjk_fallback_font(self):
        self.assertIn('"NotoSansSC-Regular.otf"', self.script)

    def test_release_bundles_the_cjk_display_font_and_license(self):
        self.assertIn('"SourceHanSerifSC-Regular.otf"', self.script)
        self.assertIn('"SourceHanSerifSC-SemiBold.otf"', self.script)
        self.assertIn('"SourceHanSerifSC-LICENSE.txt"', self.script)
        self.assertIn('"SourceHanSansSC-Regular.otf"', self.script)
        self.assertIn('"SourceHanSansSC-Medium.otf"', self.script)
        self.assertIn('"SourceHanSansSC-LICENSE.txt"', self.script)

    def test_installer_selection_is_exact_for_the_current_version(self):
        self.assertIn('$expectedInstaller = Join-Path $releaseRoot "山东定额助手-Setup-$appVersion.exe"', self.script)
        self.assertNotIn('Get-ChildItem -LiteralPath $releaseRoot -Filter "*-Setup-*.exe"', self.script)

    def test_release_manifest_only_collects_current_build_artifacts(self):
        self.assertIn("Get-ChildItem -LiteralPath $bundleRoot -Recurse -File", self.script)
        self.assertNotIn("Get-ChildItem -LiteralPath $releaseRoot -Recurse -File", self.script)

    def test_evidence_source_json_is_expanded_for_windows_powershell_5(self):
        self.assertIn("foreach ($item in $parsedSources)", self.script)
        self.assertIn("$registeredSources += [string]$item", self.script)
        self.assertNotIn("$registeredSources = @(Get-Content", self.script)


if __name__ == "__main__":
    unittest.main()
