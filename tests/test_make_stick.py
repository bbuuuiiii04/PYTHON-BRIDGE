"""Layout tests for packaging/make_stick.sh (AWR-186 Task 1).

No PyInstaller, no hdiutil, no stick: the script's test seams
(RBSS_MAKE_STICK_APP / _STAGE_ONLY / _CONFIG_DIR + a throwaway $HOME) drive the
staging logic only — the piece that decides WHAT ships. The dangerous outcomes
under test: the payload layout the native installer consumes, existence-gating
(absent files skip, never abort), fail-closed on unreadable sources, and the
PIONEER/ target refusal.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "packaging" / "make_stick.sh"

HOME_PARITY_NAMES = [
    "govee.env",
    "laser_director.json",
    "led_look_director.json",
    "soundswitch_pack_player.json",
    "laser_color_map.json",
]


class MakeStickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.support = self.home / "Library" / "Application Support" / "RBSS Bridge"
        (self.support / "spectral_cache" / "v4").mkdir(parents=True)
        (self.support / "spectral_cache" / "v4" / "a.json").write_text("{}")
        (self.support / "govee.env").write_text("GOVEE_API_KEY=test-key-not-real\n")
        self.config = root / "config"
        self.config.mkdir()
        for name in HOME_PARITY_NAMES[1:]:
            (self.config / name).write_text("{}")
        self.app = root / "RBSS Bridge.app"
        (self.app / "Contents" / "MacOS").mkdir(parents=True)
        (self.app / "Contents" / "MacOS" / "bin").write_text("x")
        self.staging = root / "staging"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, env_extra=None):
        env = {
            **os.environ,
            "HOME": str(self.home),
            "RBSS_MAKE_STICK_APP": str(self.app),
            "RBSS_MAKE_STICK_STAGE_ONLY": str(self.staging),
            "RBSS_MAKE_STICK_CONFIG_DIR": str(self.config),
            **(env_extra or {}),
        }
        return subprocess.run(
            ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env
        )

    def test_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_staging_layout(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue((self.staging / "RBSS Bridge.app" / "Contents" / "MacOS" / "bin").is_file())
        self.assertTrue(
            (self.staging / "RBSS_payload" / "spectral_cache" / "v4" / "a.json").is_file()
        )
        for name in HOME_PARITY_NAMES:
            self.assertTrue(
                (self.staging / "RBSS_payload" / "home" / name).is_file(), name
            )
        # 1 cache file + 5 home-parity files
        self.assertIn("6 payload file(s)", result.stdout)

    def test_pack_dir_copied_into_payload(self):
        # AWR-186 Track A: pack_path from the live config is copied into the
        # payload so the guest Mac's native pack DMX renderer has the show.
        import json

        pack = Path(self.tmp.name) / "the_pack"
        (pack / "sub").mkdir(parents=True)
        (pack / "pack_manifest.json").write_text("{}")
        (pack / "sub" / "cue.bin").write_text("x")
        (self.config / "soundswitch_pack_player.json").write_text(
            json.dumps({"pack_path": str(pack)})
        )
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        dest = self.staging / "RBSS_payload" / "soundswitch_pack"
        self.assertTrue((dest / "pack_manifest.json").is_file())
        self.assertTrue((dest / "sub" / "cue.bin").is_file())
        # 1 cache + 5 home-parity + 2 pack files
        self.assertIn("8 payload file(s)", result.stdout)

    def test_nonexistent_pack_path_fails_closed(self):
        # A non-empty pack_path that points nowhere is a broken config, NOT
        # "no pack": the builder must abort so a stick claiming success can never
        # ship without its show.
        import json

        gone = Path(self.tmp.name) / "not_there_pack"
        (self.config / "soundswitch_pack_player.json").write_text(
            json.dumps({"pack_path": str(gone)})
        )
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("not a readable directory", result.stderr)
        self.assertFalse(
            (self.staging / "RBSS_payload" / "soundswitch_pack").exists()
        )

    def test_malformed_pack_config_fails_closed(self):
        # A config that exists but can't be parsed must abort — the old
        # `2>/dev/null || true` swallowed this into a silent no-pack success.
        (self.config / "soundswitch_pack_player.json").write_text(
            "{ this is not valid json"
        )
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("pack config read", result.stderr)

    def test_empty_pack_path_succeeds_no_pack(self):
        # An intentionally empty pack_path stays backward-compatible: no pack,
        # clean success (proves the fail-closed change didn't over-tighten).
        import json

        (self.config / "soundswitch_pack_player.json").write_text(
            json.dumps({"pack_path": ""})
        )
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(
            (self.staging / "RBSS_payload" / "soundswitch_pack").exists()
        )

    def test_absent_files_skip_but_run_succeeds(self):
        (self.support / "govee.env").unlink()
        (self.config / "laser_director.json").unlink()
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        home_dir = self.staging / "RBSS_payload" / "home"
        self.assertFalse((home_dir / "govee.env").exists())
        self.assertFalse((home_dir / "laser_director.json").exists())
        self.assertTrue((home_dir / "led_look_director.json").is_file())
        self.assertIn("absent; skipped", result.stdout)

    def test_unreadable_source_fails_closed(self):
        target = self.config / "led_look_director.json"
        target.chmod(0o000)
        try:
            result = self._run()
        finally:
            target.chmod(0o644)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unreadable", result.stderr)

    def test_refuses_target_without_pioneer_dir(self):
        fake_stick = Path(self.tmp.name) / "not_a_stick"
        fake_stick.mkdir()
        result = self._run(str(fake_stick), env_extra={"RBSS_MAKE_STICK_STAGE_ONLY": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PIONEER", result.stderr)

    def test_refuses_missing_mount(self):
        result = self._run(
            str(Path(self.tmp.name) / "nope"), env_extra={"RBSS_MAKE_STICK_STAGE_ONLY": ""}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a mounted volume", result.stderr)


if __name__ == "__main__":
    unittest.main()
