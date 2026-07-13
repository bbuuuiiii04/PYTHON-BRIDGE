"""Pure-seam tests for install_controller.py + the launch_profile config-override
map (AWR-186 M2 Task 2). No subprocess, no hdiutil, no AppKit — temp dirs only.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertTrue(
            ic.should_offer_install(
                dmg, manifest_exists=False, install_incomplete=False
            )
        )
        self.assertFalse(
            ic.should_offer_install(
                installed, manifest_exists=False, install_incomplete=False
            )
        )
        self.assertTrue(
            ic.should_offer_install(
                dmg, manifest_exists=True, install_incomplete=False
            )
        )
        self.assertTrue(
            ic.should_offer_install(
                dmg, manifest_exists=True, install_incomplete=True
            )
        )
        self.assertFalse(
            ic.should_offer_install(
                None, manifest_exists=False, install_incomplete=True
            )
        )

    def test_install_action_title_fresh_update_and_retry(self) -> None:
        self.assertEqual(
            ic.install_action_title(False, install_incomplete=False),
            "Install on This Mac…",
        )
        self.assertEqual(
            ic.install_action_title(True, install_incomplete=False),
            "Update This Mac…",
        )
        self.assertEqual(
            ic.install_action_title(True, install_incomplete=True),
            "Retry Installation…",
        )

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
        for name in (
            "laser_director.json",
            "led_look_director.json",
            "soundswitch_pack_player.json",
            "laser_color_map.json",
        ):
            (payload / "home" / name).write_text("{}")
        (payload / "soundswitch_pack").mkdir()
        (payload / "soundswitch_pack" / "manifest.json").write_text("{}")
        (payload / "lighting_sidecar").mkdir()
        (payload / "lighting_sidecar" / "index.json").write_text(
            json.dumps({"schema_version": 1, "track_count": 1, "tracks": [{}]})
        )
        (payload / "streamdeck_midi_bindings.json").write_text(json.dumps([{
            "channel": 0,
            "interaction": "press",
            "name": "BLACK OUT",
            "note": 0,
            "target_kind": "static_look",
        }]))
        self.apps = root / "Applications"
        self.support = root / "Application Support" / "RBSS Bridge"
        self._write_package_manifest()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _install(self) -> ic.InstallResult:
        return ic.perform_install(
            self.bundle, apps_dir=self.apps, app_support=self.support
        )

    def _write_package_manifest(self) -> None:
        payload = ic.payload_dir(self.bundle)
        manifest_path = payload / ic.BUILD_MANIFEST_NAME
        rows = []
        for tree in (self.bundle, payload):
            for path in sorted(p for p in tree.rglob("*") if p.is_file()):
                if path == manifest_path:
                    continue
                rows.append({
                    "path": str(path.relative_to(self.bundle.parent)),
                    "size": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                })
        manifest_path.write_text(json.dumps({
            "schema_version": 1,
            "generation": "test-generation",
            "built_at": "2026-07-12T00:00:00Z",
            "git_head": "a" * 40,
            "source_dirty": False,
            "files": rows,
        }))

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
        self.assertTrue((self.support / "lighting_sidecar" / "index.json").is_file())
        self.assertTrue((self.support / "streamdeck_midi_bindings.json").is_file())
        self.assertTrue((self.support / ic.BUILD_MANIFEST_NAME).is_file())
        lines = (self.support / "install_manifest.txt").read_text().splitlines()
        # Interim-format manifest: absolute paths, app first, one per line.
        self.assertEqual(lines[0], str(app_dest))
        self.assertIn(str(self.support / "spectral_cache" / "v4" / "a.json"), lines)
        self.assertIn(str(self.support / "govee.env"), lines)
        self.assertEqual(len(lines), 1 + result.installed_files)
        self.assertEqual(result.installed_files, 10)
        self.assertFalse((self.support / ic.INCOMPLETE_MARKER_NAME).exists())
        with mock.patch.object(ic, "APP_SUPPORT_DIR", self.support):
            self.assertTrue(
                ic.should_offer_install(
                    "/Volumes/RBSS Bridge/RBSS Bridge.app",
                    manifest_exists=True,
                )
            )

    def test_pack_payload_installs_and_is_manifest_recorded(self) -> None:
        # AWR-186 Track A: the exported SoundSwitch pack rides in the payload and
        # lands in App Support (file-level, manifest-recorded) like spectral_cache.
        payload = ic.payload_dir(self.bundle)
        (payload / "soundswitch_pack" / "sub").mkdir(parents=True)
        (payload / "soundswitch_pack" / "sub" / "cue.bin").write_text("x")
        self._write_package_manifest()
        result = self._install()
        self.assertTrue(result.ok, result.failed_step)
        self.assertTrue(
            (self.support / "soundswitch_pack" / "manifest.json").is_file()
        )
        self.assertTrue(
            (self.support / "soundswitch_pack" / "sub" / "cue.bin").is_file()
        )
        lines = (self.support / "install_manifest.txt").read_text().splitlines()
        self.assertIn(
            str(self.support / "soundswitch_pack" / "manifest.json"), lines
        )
        self.assertIn(
            str(self.support / "soundswitch_pack" / "sub" / "cue.bin"), lines
        )
        self.assertEqual(result.installed_files, 11)
        self.assertEqual(len(lines), 1 + result.installed_files)

    def test_missing_payload_fails_closed_and_marks_retry(self) -> None:
        bare = Path(self.tmp.name) / "bare" / "RBSS Bridge.app"
        (bare / "Contents").mkdir(parents=True)
        (bare / "Contents" / "bin").write_text("x")
        result = ic.perform_install(bare, apps_dir=self.apps, app_support=self.support)
        self.assertFalse(result.ok)
        self.assertIn("build manifest", result.failed_step)
        self.assertEqual(result.installed_files, 0)
        self.assertTrue((self.support / ic.INCOMPLETE_MARKER_NAME).is_file())
        self.assertFalse((self.apps / "RBSS Bridge.app").exists())

    def test_commit_failure_rolls_back_previous_app_and_payload(self) -> None:
        old_app = self.apps / "RBSS Bridge.app"
        (old_app / "Contents").mkdir(parents=True)
        (old_app / "Contents" / "old-bin").write_text("old")
        self.support.mkdir(parents=True)
        (self.support / "laser_director.json").write_text('{"old": true}')
        old_manifest = f"{old_app}\n{self.support / 'laser_director.json'}\n"
        (self.support / ic.MANIFEST_NAME).write_text(old_manifest)

        real_replace = ic._replace
        calls = 0

        def fail_new_support(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError("injected commit failure")
            real_replace(source, destination)

        with mock.patch.object(ic, "_replace", side_effect=fail_new_support):
            result = self._install()
        self.assertFalse(result.ok)
        self.assertIn("commit install", result.failed_step)
        self.assertTrue((old_app / "Contents" / "old-bin").is_file())
        self.assertEqual(
            (self.support / "laser_director.json").read_text(), '{"old": true}'
        )
        self.assertEqual((self.support / ic.MANIFEST_NAME).read_text(), old_manifest)
        self.assertTrue((self.support / ic.INCOMPLETE_MARKER_NAME).is_file())
        with mock.patch.object(ic, "APP_SUPPORT_DIR", self.support):
            self.assertTrue(
                ic.should_offer_install(
                    "/Volumes/RBSS Bridge/RBSS Bridge.app",
                    manifest_exists=True,
                )
            )

    def test_update_replaces_managed_data_prunes_stale_and_preserves_state(self) -> None:
        old_app = self.apps / "RBSS Bridge.app"
        (old_app / "Contents").mkdir(parents=True)
        (old_app / "Contents" / "old-bin").write_text("old")
        (self.support / "spectral_cache" / "stale").mkdir(parents=True)
        (self.support / "spectral_cache" / "stale" / "gone.json").write_text("old")
        (self.support / "soundswitch_pack" / "stale").mkdir(parents=True)
        (self.support / "soundswitch_pack" / "stale" / "gone.bin").write_text("old")
        (self.support / "lighting_sidecar" / "stale").mkdir(parents=True)
        (self.support / "lighting_sidecar" / "stale" / "gone.json").write_text("old")
        (self.support / "laser_director.json").write_text('{"old": true}')
        (self.support / "unmanaged-old.txt").write_text("prune")
        (self.support / "state").mkdir()
        (self.support / "state" / "learned.json").write_text("learned")

        result = self._install()
        self.assertTrue(result.ok, result.failed_step)
        self.assertFalse((old_app / "Contents" / "old-bin").exists())
        self.assertEqual((self.support / "laser_director.json").read_text(), "{}")
        self.assertFalse((self.support / "spectral_cache" / "stale").exists())
        self.assertFalse((self.support / "soundswitch_pack" / "stale").exists())
        self.assertFalse((self.support / "lighting_sidecar" / "stale").exists())
        self.assertFalse((self.support / "unmanaged-old.txt").exists())
        self.assertEqual((self.support / "state" / "learned.json").read_text(), "learned")

    def test_tampered_package_fails_before_replacing_previous_install(self) -> None:
        old_app = self.apps / "RBSS Bridge.app"
        (old_app / "Contents").mkdir(parents=True)
        (old_app / "Contents" / "old-bin").write_text("old")
        self.support.mkdir(parents=True)
        (self.support / ic.MANIFEST_NAME).write_text(f"{old_app}\n")
        (ic.payload_dir(self.bundle) / "home" / "laser_director.json").write_text(
            '{"tampered": true}'
        )

        result = self._install()
        self.assertFalse(result.ok)
        self.assertIn("integrity check", result.failed_step)
        self.assertTrue((old_app / "Contents" / "old-bin").is_file())
        self.assertTrue((self.support / ic.INCOMPLETE_MARKER_NAME).is_file())

    def test_hash_consistent_but_malformed_bindings_fail_closed(self) -> None:
        bindings = ic.payload_dir(self.bundle) / "streamdeck_midi_bindings.json"
        bindings.write_text("{}")
        self._write_package_manifest()

        result = self._install()

        self.assertFalse(result.ok)
        self.assertIn("MIDI bindings are malformed", result.failed_step)
        self.assertFalse((self.apps / "RBSS Bridge.app").exists())

    def test_legacy_manifest_without_marker_still_counts_as_complete(self) -> None:
        self.support.mkdir(parents=True)
        (self.support / ic.MANIFEST_NAME).write_text(
            f"{self.apps / 'RBSS Bridge.app'}\n"
        )
        self.assertFalse((self.support / ic.INCOMPLETE_MARKER_NAME).exists())
        with mock.patch.object(ic, "APP_SUPPORT_DIR", self.support):
            self.assertTrue(
                ic.should_offer_install(
                    "/Volumes/RBSS Bridge/RBSS Bridge.app",
                    manifest_exists=True,
                )
            )


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


class PerformPurgeTests(unittest.TestCase):
    """Native Purge allowlist, traversal refusal, manifest exactness, and
    three-root removal order against the pure helper."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.apps = root / "Applications"
        self.support = root / "Application Support" / "RBSS Bridge"
        self.logs = root / "Logs" / "rb_ss_bridge"
        self.app = self.apps / "RBSS Bridge.app"
        (self.app / "Contents").mkdir(parents=True)
        (self.app / "Contents" / "bin").write_text("x")
        cache = self.support / "spectral_cache" / "v4" / "a.json"
        cache.parent.mkdir(parents=True)
        cache.write_text("{}")
        (self.support / "govee.env").write_text("GOVEE_API_KEY=test-key-not-real\n")
        self.logs.mkdir(parents=True)
        (self.logs / "current.jsonl").write_text("")
        self.outside = root / "outside.txt"
        self.outside.write_text("never remove me")
        manifest = self.support / "install_manifest.txt"
        manifest.write_text(
            "\n".join(
                [
                    str(self.app),
                    str(cache),
                    str(self.support / "govee.env"),
                    str(self.outside),  # outside the roots -> must be skipped
                    str(self.apps / ".." / "escape.txt"),  # '..' -> must be skipped
                ]
            )
            + "\n"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _purge(self, own_app: Path | None = None) -> ic.PurgeResult:
        return ic.perform_purge(
            apps_dir=self.apps,
            app_support=self.support,
            logs_dir=self.logs,
            own_app=own_app,
        )

    def test_allowlist_dotdot_and_three_roots(self) -> None:
        result = self._purge()
        self.assertFalse(self.app.exists())          # manifest path, apps root
        self.assertFalse(self.support.exists())      # whole App Support dir
        self.assertFalse(self.logs.exists())         # logs root
        self.assertTrue(self.outside.exists())       # outside roots: untouched
        self.assertEqual(len(result.skipped), 2)     # outside + '..' entries
        self.assertEqual(result.failures, [])
        self.assertIn("System Settings", result.remains_note)

    def test_own_app_deferred_to_trash_step(self) -> None:
        result = self._purge(own_app=self.app)
        self.assertTrue(self.app.exists())  # menubar trashes it after purge
        self.assertFalse(self.support.exists())
        self.assertFalse(self.logs.exists())
        self.assertEqual(result.failures, [])

    def test_failure_records_and_continues(self) -> None:
        with mock.patch.object(ic.shutil, "rmtree", side_effect=OSError("locked")):
            result = self._purge()
        # Every dir-removal failed but the purge kept going and reported all
        # three (app bundle from the manifest + the two roots), never raised.
        self.assertEqual(len(result.failures), 3)
        self.assertTrue(any("RBSS Bridge.app" in f for f in result.failures))
        # File-level manifest entries still removed (unlink is not rmtree).
        self.assertFalse((self.support / "govee.env").exists())

    def test_missing_manifest_still_removes_roots(self) -> None:
        (self.support / "install_manifest.txt").unlink()
        result = self._purge()
        self.assertFalse(self.support.exists())
        self.assertFalse(self.logs.exists())
        self.assertTrue(any("manifest" in s for s in result.skipped))

    def test_legacy_rekordbox_backup_is_moved_outside_purge_root(self) -> None:
        legacy = self.support / "rekordbox_backups" / "original.app"
        legacy.mkdir(parents=True)
        (legacy / "bin").write_text("original")
        archive = self.support.parent / "RBSS Rekordbox Backups"

        result = ic.perform_purge(
            apps_dir=self.apps,
            app_support=self.support,
            logs_dir=self.logs,
            backup_archive=archive,
        )

        preserved = archive / "original.app" / "bin"
        self.assertEqual(preserved.read_text(), "original")
        self.assertFalse(self.support.exists())
        self.assertIn(str(archive / "original.app"), result.preserved)
        self.assertIn(str(archive), result.remains_note)
        self.assertEqual(result.failures, [])

    def test_backup_migration_failure_keeps_app_support(self) -> None:
        legacy = self.support / "rekordbox_backups" / "original.app"
        legacy.mkdir(parents=True)
        (legacy / "bin").write_text("original")
        with (self.support / ic.MANIFEST_NAME).open("a", encoding="utf-8") as fp:
            fp.write(f"{legacy / 'bin'}\n")
        archive = self.support.parent / "RBSS Rekordbox Backups"

        with mock.patch.object(ic.shutil, "move", side_effect=OSError("blocked")):
            result = ic.perform_purge(
                apps_dir=self.apps,
                app_support=self.support,
                logs_dir=self.logs,
                backup_archive=archive,
            )

        self.assertTrue((legacy / "bin").is_file())
        self.assertTrue(self.support.exists())
        self.assertFalse(self.logs.exists())
        self.assertTrue(any("preserve Rekordbox backup" in row for row in result.failures))
        self.assertTrue(any("kept" in row for row in result.skipped))


class FrozenStatePathTests(unittest.TestCase):
    """Task 3: local/state/* resolution — frozen runs move to App Support,
    source runs are byte-identical (the watcher's stores stay where they are)."""

    def test_source_run_returns_input_unchanged(self) -> None:
        for path in (
            "local/state/led_identity_v2.json",
            "local/state/laser_solo_learned.json",
            "/abs/elsewhere.json",
            "other/relative.json",
        ):
            self.assertEqual(launch_profile.resolve_state_path(path), path)

    def _frozen(self):
        return mock.patch.object(sys, "frozen", True, create=True)

    def test_frozen_maps_local_state_to_app_support(self) -> None:
        with self._frozen():
            resolved = launch_profile.resolve_state_path(
                "local/state/led_identity_v2.json"
            )
        self.assertEqual(
            resolved, str(launch_profile.FROZEN_STATE_DIR / "led_identity_v2.json")
        )

    def test_frozen_keeps_nested_layout(self) -> None:
        with self._frozen():
            resolved = launch_profile.resolve_state_path("local/state/sub/x.json")
        self.assertEqual(
            resolved, str(launch_profile.FROZEN_STATE_DIR / "sub" / "x.json")
        )

    def test_frozen_leaves_absolute_and_foreign_paths_alone(self) -> None:
        with self._frozen():
            self.assertEqual(
                launch_profile.resolve_state_path("/operator/store.json"),
                "/operator/store.json",
            )
            self.assertEqual(
                launch_profile.resolve_state_path("other/relative.json"),
                "other/relative.json",
            )

    def test_seam_wiring_led_config_and_learned_store(self) -> None:
        # Source-run import: both consumers must carry today's exact paths.
        from rb_ss_bridge_v2 import drop_presentation, led_config

        self.assertEqual(
            drop_presentation.LEARNED_STORE_PATH, "local/state/laser_solo_learned.json"
        )
        cfg = led_config._build_identity_v2_config({})
        self.assertEqual(cfg.store_path, "local/state/led_identity_v2.json")


class OperatorInstallFailureMessageTests(unittest.TestCase):
    def test_technical_failed_step_stays_out_of_operator_text(self) -> None:
        msg = ic.operator_install_failure_message(
            "create target folders (PermissionError)"
        )
        self.assertNotIn("PermissionError", msg)
        self.assertNotIn("create target folders", msg)
        self.assertIn("What to do:", msg)
        self.assertIn("Applications", msg)

    def test_unknown_step_still_gives_retry_guidance(self) -> None:
        msg = ic.operator_install_failure_message("weird internal token")
        self.assertIn("What to do:", msg)
        self.assertIn("Retry", msg)
        self.assertNotIn("Failed step:", msg)

    def test_insufficient_disk_maps_to_free_space(self) -> None:
        msg = ic.operator_install_failure_message(
            "insufficient free disk for a rollback-safe update"
        )
        self.assertIn("free disk", msg.casefold())
        self.assertIn("What to do:", msg)


if __name__ == "__main__":
    unittest.main()
