"""Pure-seam tests for install_controller.py + the launch_profile config-override
map (AWR-186 M2 Task 2). No subprocess, no hdiutil, no AppKit — temp dirs only.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import install_controller as ic  # noqa: E402
from rb_ss_bridge_v2 import launch_profile  # noqa: E402


class DetectionTests(unittest.TestCase):
    def test_bundle_root_walks_up_to_the_app(self) -> None:
        exe = "/Volumes/RBSS Bridge/RBSS Bridge.app/Contents/MacOS/RBSS Bridge"
        self.assertEqual(
            ic.bundle_root(exe), Path("/Volumes/RBSS Bridge/RBSS Bridge.app")
        )

    def test_bundle_root_none_outside_an_app(self) -> None:
        self.assertIsNone(ic.bundle_root("/usr/local/bin/python3"))

    def test_read_only_locations(self) -> None:
        self.assertTrue(
            ic.running_from_read_only_location("/Volumes/RBSS Bridge/RBSS Bridge.app")
        )
        self.assertTrue(
            ic.running_from_read_only_location(
                "/private/var/folders/ab/T/AppTranslocation/1234/d/RBSS Bridge.app"
            )
        )
        self.assertFalse(
            ic.running_from_read_only_location(
                str(Path.home() / "Applications" / "RBSS Bridge.app")
            )
        )

    def test_should_offer_install_matrix(self) -> None:
        dmg = "/Volumes/RBSS Bridge/RBSS Bridge.app"
        installed = str(Path.home() / "Applications" / "RBSS Bridge.app")
        self.assertTrue(ic.should_offer_install(dmg, manifest_exists=False))
        self.assertFalse(ic.should_offer_install(dmg, manifest_exists=True))
        self.assertFalse(ic.should_offer_install(installed, manifest_exists=False))
        self.assertFalse(ic.should_offer_install(None, manifest_exists=False))

    def test_payload_is_sibling_of_the_app(self) -> None:
        self.assertEqual(
            ic.payload_dir("/Volumes/RBSS Bridge/RBSS Bridge.app"),
            Path("/Volumes/RBSS Bridge/RBSS_payload"),
        )


class PerformInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        # A fake mounted-DMG layout: app + sibling payload.
        self.bundle = root / "dmg" / "RBSS Bridge.app"
        (self.bundle / "Contents" / "MacOS").mkdir(parents=True)
        (self.bundle / "Contents" / "MacOS" / "bin").write_text("x")
        payload = root / "dmg" / "RBSS_payload"
        (payload / "spectral_cache" / "v4").mkdir(parents=True)
        (payload / "spectral_cache" / "v4" / "a.json").write_text("{}")
        (payload / "home").mkdir()
        (payload / "home" / "govee.env").write_text("GOVEE_API_KEY=test-key-not-real\n")
        (payload / "home" / "laser_director.json").write_text("{}")
        self.apps = root / "Applications"
        self.support = root / "Application Support" / "RBSS Bridge"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _install(self) -> ic.InstallResult:
        return ic.perform_install(
            self.bundle, apps_dir=self.apps, app_support=self.support
        )

    def test_full_install_layout_and_manifest(self) -> None:
        result = self._install()
        self.assertTrue(result.ok, result.failed_step)
        app_dest = self.apps / "RBSS Bridge.app"
        self.assertTrue((app_dest / "Contents" / "MacOS" / "bin").is_file())
        self.assertTrue(
            (self.support / "spectral_cache" / "v4" / "a.json").is_file()
        )
        self.assertTrue((self.support / "govee.env").is_file())
        self.assertTrue((self.support / "laser_director.json").is_file())
        lines = (self.support / "install_manifest.txt").read_text().splitlines()
        # Interim-format manifest: absolute paths, app first, one per line.
        self.assertEqual(lines[0], str(app_dest))
        self.assertIn(str(self.support / "spectral_cache" / "v4" / "a.json"), lines)
        self.assertIn(str(self.support / "govee.env"), lines)
        self.assertEqual(len(lines), 1 + result.installed_files)
        self.assertEqual(result.installed_files, 3)

    def test_missing_payload_still_installs_app(self) -> None:
        bare = Path(self.tmp.name) / "bare" / "RBSS Bridge.app"
        (bare / "Contents").mkdir(parents=True)
        (bare / "Contents" / "bin").write_text("x")
        result = ic.perform_install(bare, apps_dir=self.apps, app_support=self.support)
        self.assertTrue(result.ok, result.failed_step)
        self.assertEqual(result.installed_files, 0)
        self.assertEqual(len(result.notes), 2)
        lines = (self.support / "install_manifest.txt").read_text().splitlines()
        self.assertEqual(lines, [str(self.apps / "RBSS Bridge.app")])

    def test_partial_failure_names_step_and_keeps_manifest_accurate(self) -> None:
        blocked = self.support / "spectral_cache" / "v4"
        blocked.mkdir(parents=True)
        blocked.chmod(0o500)  # copyfile into it fails -> step must be reported
        try:
            result = self._install()
        finally:
            blocked.chmod(0o755)
        self.assertFalse(result.ok)
        self.assertIn("analysis cache file", result.failed_step)
        lines = (self.support / "install_manifest.txt").read_text().splitlines()
        # Manifest lists ONLY what actually landed: the app copy, nothing after.
        self.assertEqual(lines, [str(self.apps / "RBSS Bridge.app")])


class ConfigOverrideEnvTests(unittest.TestCase):
    def test_present_files_map_to_their_env_seams(self) -> None:
        env = launch_profile.app_support_config_env(
            "/tmp/sup", {"laser_director.json", "led_look_director.json", "govee.env"}
        )
        self.assertEqual(
            env,
            {
                "RBSS_LASER_CONFIG": "/tmp/sup/laser_director.json",
                "RBSS_LED_CONFIG": "/tmp/sup/led_look_director.json",
            },
        )

    def test_absent_files_yield_no_overrides(self) -> None:
        self.assertEqual(launch_profile.app_support_config_env("/tmp/sup", set()), {})

    def test_all_four_seams_covered(self) -> None:
        env = launch_profile.app_support_config_env(
            "/s", set(launch_profile.APP_SUPPORT_CONFIG_ENV)
        )
        self.assertEqual(
            set(env),
            {
                "RBSS_LASER_CONFIG",
                "RBSS_LED_CONFIG",
                "RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG",
                "RBSS_LASER_COLOR_MAP_CONFIG",
            },
        )


if __name__ == "__main__":
    unittest.main()
