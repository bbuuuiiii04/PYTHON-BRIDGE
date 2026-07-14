"""Layout tests for packaging/make_stick.sh (AWR-186 Task 1).

No PyInstaller, no hdiutil, no stick: the script's test seams
(RBSS_MAKE_STICK_APP / _STAGE_ONLY / _CONFIG_DIR + a throwaway $HOME) drive the
staging logic only — the piece that decides WHAT ships. The dangerous outcomes
under test: the payload layout the native installer consumes, existence-gating
(absent files skip, never abort), fail-closed on unreadable sources, and the
PIONEER/ target refusal.
"""

import json
import hashlib
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "packaging" / "make_stick.sh"
SPEC = SCRIPT.with_name("rbss_launcher.spec")
WHEEL_LOCK = SCRIPT.with_name("macos12_arm64_cp313.lock")
SOURCE_LOCK = SCRIPT.with_name("macos12_arm64_cp313_source.lock")

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
        self.pack = root / "soundswitch_pack"
        self.pack.mkdir()
        (self.pack / "manifest.json").write_text("{}")
        (self.config / "soundswitch_pack_player.json").write_text(
            json.dumps({"pack_path": str(self.pack)})
        )
        self.bindings = root / "bindings.json"
        self.bindings.write_text(json.dumps([{
            "channel": 0,
            "interaction": "press",
            "name": "BLACK OUT",
            "note": 0,
            "target_kind": "static_look",
        }]))
        self.exporter = root / "fake_sidecar_exporter.py"
        self.exporter.write_text(
            "import json, pathlib, sys\n"
            "root = pathlib.Path(sys.argv[sys.argv.index('--dest') + 1]) / 'lighting_sidecar'\n"
            "root.mkdir(parents=True, exist_ok=True)\n"
            "(root / 'index.json').write_text(json.dumps({"
            "'schema_version': 1, 'track_count': 1, 'tracks': [{'content_id': '1'}]}))\n"
        )
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
            "RBSS_MAKE_STICK_BINDINGS": str(self.bindings),
            "RBSS_MAKE_STICK_SIDECAR_EXPORTER": str(self.exporter),
            "RBSS_MAKE_STICK_SIDECAR_PYTHON": sys.executable,
            **(env_extra or {}),
        }
        return subprocess.run(
            ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env
        )

    def _source_and_run(self, command, env_extra=None):
        env = {
            **os.environ,
            "RBSS_MAKE_STICK_SOURCE_ONLY": "1",
            **(env_extra or {}),
        }
        return subprocess.run(
            ["bash", "-c", f"source {shlex.quote(str(SCRIPT))}; {command}"],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_product_floor_is_honest_macos_12_3(self):
        script = SCRIPT.read_text()
        self.assertIn('MACOSX_DEPLOYMENT_TARGET:-12.3', script)
        self.assertIn('BUILD_PYTHON_VERSION="3.13.14"', script)
        self.assertIn('"LSMinimumSystemVersion": "12.3"', SPEC.read_text())

    def test_cached_build_python_must_be_locked_version_and_universal2(self):
        fake_bin = Path(self.tmp.name) / "fake-bin"
        fake_bin.mkdir()
        python = fake_bin / "python"
        python.write_text('#!/bin/bash\nexit "${FAKE_PYTHON_CHECK_RC:-0}"\n')
        python.chmod(0o755)
        lipo = fake_bin / "lipo"
        lipo.write_text('#!/bin/bash\necho "${FAKE_LIPO_ARCHS:-x86_64 arm64}"\n')
        lipo.chmod(0o755)
        command = f"build_python_is_supported {shlex.quote(str(python))}"
        base_env = {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
        }

        supported = self._source_and_run(command, base_env)
        self.assertEqual(supported.returncode, 0, supported.stderr)
        wrong_python = self._source_and_run(
            command, {**base_env, "FAKE_PYTHON_CHECK_RC": "1"}
        )
        self.assertNotEqual(wrong_python.returncode, 0)
        wrong_arch = self._source_and_run(
            command, {**base_env, "FAKE_LIPO_ARCHS": "arm64"}
        )
        self.assertNotEqual(wrong_arch.returncode, 0)

    def test_locked_download_forces_macos_12_wheels_and_hashes(self):
        fake_python = Path(self.tmp.name) / "fake-python"
        capture = Path(self.tmp.name) / "pip-args"
        fake_python.write_text(
            '#!/bin/bash\nprintf "%s\\n" "$*" >> "$PIP_CAPTURE"\n'
        )
        fake_python.chmod(0o755)
        fake_bin = Path(self.tmp.name) / "fake-bin"
        fake_bin.mkdir()
        curl = fake_bin / "curl"
        curl.write_text('#!/bin/bash\nprintf "curl %s\\n" "$*" >> "$PIP_CAPTURE"\n')
        curl.chmod(0o755)
        wheelhouse = Path(self.tmp.name) / "wheelhouse"
        wheelhouse.mkdir()
        command = "download_locked_artifacts {} {} {} {}".format(
            *(shlex.quote(str(path)) for path in (
                fake_python, wheelhouse, WHEEL_LOCK, SOURCE_LOCK
            ))
        )
        result = self._source_and_run(
            command,
            {
                "PIP_CAPTURE": str(capture),
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = capture.read_text().splitlines()
        self.assertEqual(len(calls), 2)
        self.assertIn("--platform macosx_12_0_arm64", calls[0])
        self.assertIn("--python-version 3.13", calls[0])
        self.assertIn("--abi cp313 --abi abi3 --abi none", calls[0])
        self.assertIn("--only-binary=:all:", calls[0])
        self.assertIn("--require-hashes", calls[0])
        self.assertIn("files.pythonhosted.org", calls[1])
        self.assertIn("python_rtmidi-1.5.8.tar.gz", calls[1])

    def test_locked_artifact_hash_mismatch_is_fatal(self):
        wheelhouse = Path(self.tmp.name) / "wheelhouse"
        wheelhouse.mkdir()
        artifact = wheelhouse / "demo-1.0-py3-none-any.whl"
        artifact.write_bytes(b"locked")
        digest = hashlib.sha256(b"locked").hexdigest()
        lock = Path(self.tmp.name) / "test.lock"
        lock.write_text(
            f"demo==1.0 --hash=sha256:{digest}  # {artifact.name}\n"
        )
        command = "verify_locked_artifacts {} {}".format(
            shlex.quote(str(lock)), shlex.quote(str(wheelhouse))
        )
        valid = self._source_and_run(command)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        artifact.write_bytes(b"tampered")
        invalid = self._source_and_run(command)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("hash mismatch", invalid.stderr)

    def test_wheel_tags_refuse_newer_or_wrong_arch(self):
        for name in (
            "demo-1.0-py3-none-any.whl",
            "demo-1.0-cp313-cp313-macosx_11_0_arm64.whl",
            "demo-1.0-cp313-cp313-macosx_12_0_arm64.whl",
            "demo-1.0-cp313-cp313-macosx_10_13_universal2.whl",
        ):
            result = self._source_and_run(
                f"wheel_tag_is_supported {shlex.quote(name)}"
            )
            self.assertEqual(result.returncode, 0, (name, result.stderr))
        for name in (
            "demo-1.0-cp313-cp313-macosx_14_0_arm64.whl",
            "demo-1.0-cp313-cp313-macosx_12_0_x86_64.whl",
        ):
            result = self._source_and_run(
                f"wheel_tag_is_supported {shlex.quote(name)}"
            )
            self.assertNotEqual(result.returncode, 0, name)

    def test_wheel_macho_scan_accepts_12_3_and_refuses_newer(self):
        wheel = Path(self.tmp.name) / "demo-1.0-cp313-cp313-macosx_12_0_arm64.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("demo/native.so", b"native")
        fake_bin = Path(self.tmp.name) / "wheel-tools"
        fake_bin.mkdir()
        file_tool = fake_bin / "file"
        file_tool.write_text('#!/bin/bash\necho "Mach-O 64-bit bundle arm64"\n')
        file_tool.chmod(0o755)
        vtool = fake_bin / "vtool"
        vtool.write_text('#!/bin/bash\nprintf "    minos %s\\n" "${FAKE_MINOS:-12.3}"\n')
        vtool.chmod(0o755)
        command = f"validate_wheel_macos_target {shlex.quote(str(wheel))}"
        env = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}
        compatible = self._source_and_run(command, env)
        self.assertEqual(compatible.returncode, 0, compatible.stderr)
        incompatible = self._source_and_run(command, {**env, "FAKE_MINOS": "14.0"})
        self.assertNotEqual(incompatible.returncode, 0)
        self.assertIn("requires macOS 14.0", incompatible.stderr)

    def test_lock_pins_low_target_spectral_artifacts_and_rtmidi_source(self):
        lock = WHEEL_LOCK.read_text()
        for filename in (
            "numpy-2.4.6-cp313-cp313-macosx_11_0_arm64.whl",
            "scipy-1.18.0-cp313-cp313-macosx_12_0_arm64.whl",
            "numba-0.66.0-cp313-cp313-macosx_12_0_arm64.whl",
            "llvmlite-0.48.0-cp313-cp313-macosx_12_0_arm64.whl",
            "librosa-0.10.2.post1-py3-none-any.whl",
            "soundfile-0.14.0-py2.py3-none-macosx_11_0_arm64.whl",
            "pyinstaller-6.21.0-py3-none-macosx_10_13_universal2.whl",
            "pyobjc_framework_applicationservices-12.2.1-cp313-cp313-macosx_10_13_universal2.whl",
            "pyobjc_framework_quartz-12.2.1-cp313-cp313-macosx_10_13_universal2.whl",
            "pyobjc_framework_coretext-12.2.1-cp313-cp313-macosx_10_13_universal2.whl",
        ):
            self.assertIn(filename, lock)
        source = SOURCE_LOCK.read_text()
        self.assertIn("python-rtmidi==1.5.8", source)
        self.assertIn(
            "7f9ade68b068ae09000ecb562ae9521da3a234361ad5449e83fc734544d004fa",
            source,
        )

    def test_spec_and_make_stick_inject_generation_into_info_plist(self):
        spec = SPEC.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('os.environ.get("RBSS_GENERATION")', spec)
        self.assertIn('or "0.0.1"', spec)
        self.assertIn('CFBundleShortVersionString": _BUNDLE_VERSION', spec)
        self.assertIn('CFBundleVersion": _BUNDLE_VERSION', spec)
        self.assertIn('RBSS_GENERATION="$GENERATION"', script)
        self.assertIn("PlistBuddy", script)
        self.assertIn("Set :CFBundleShortVersionString $GENERATION", script)
        self.assertIn("Set :CFBundleVersion $GENERATION", script)
        # Sign still runs after the stamp.
        py_idx = script.index('RBSS_GENERATION="$GENERATION" "$VENV/bin/pyinstaller"')
        buddy_idx = script.index("Set :CFBundleShortVersionString $GENERATION")
        sign_idx = script.index('bash packaging/sign.sh "dist/RBSS Bridge.app"')
        self.assertLess(py_idx, buddy_idx)
        self.assertLess(buddy_idx, sign_idx)

    def test_bundle_native_files_must_not_exceed_deployment_target(self):
        fake_bin = Path(self.tmp.name) / "compat-tools"
        fake_bin.mkdir()
        file_tool = fake_bin / "file"
        file_tool.write_text('#!/bin/bash\necho "Mach-O 64-bit bundle arm64"\n')
        file_tool.chmod(0o755)
        vtool = fake_bin / "vtool"
        vtool.write_text(
            '#!/bin/bash\ncase "$*" in *too-new*) minos=14.0 ;; *) minos=12.3 ;; esac\n'
            'printf "    minos %s\\n" "$minos"\n'
        )
        vtool.chmod(0o755)
        app = Path(self.tmp.name) / "compat.app" / "Contents" / "Frameworks"
        app.mkdir(parents=True)
        (app / "good.so").write_text("x")
        command = f"validate_app_macos_target {shlex.quote(str(app.parents[1]))}"
        env = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        compatible = self._source_and_run(command, env)
        self.assertEqual(compatible.returncode, 0, compatible.stderr)
        (app / "too-new.so").write_text("x")
        incompatible = self._source_and_run(command, env)
        self.assertNotEqual(incompatible.returncode, 0)
        self.assertIn("requires macOS 14.0", incompatible.stderr)

    def test_sidecar_exporter_gets_exact_destination_and_failure_is_fatal(self):
        exporter = Path(self.tmp.name) / "fake_exporter.py"
        capture = Path(self.tmp.name) / "exporter_args.json"
        exporter.write_text(
            "import json, os, sys\n"
            "open(os.environ['SIDECAR_CAPTURE'], 'w').write(json.dumps(sys.argv[1:]))\n"
            "raise SystemExit(int(os.environ.get('SIDECAR_FAIL', '0')))\n"
        )
        dest = Path(self.tmp.name) / "RBSS BRIDGE USB"
        command = f"export_lighting_sidecar {shlex.quote(str(dest))}"
        env = {
            "RBSS_MAKE_STICK_SIDECAR_EXPORTER": str(exporter),
            "RBSS_MAKE_STICK_SIDECAR_PYTHON": sys.executable,
            "SIDECAR_CAPTURE": str(capture),
        }

        result = self._source_and_run(command, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(capture.read_text()), ["--dest", str(dest)])
        failed = self._source_and_run(command, {**env, "SIDECAR_FAIL": "1"})
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("stick update is incomplete", failed.stderr)

    def test_ship_logic_has_only_dmg_and_lighting_sidecar(self):
        ship_logic = (
            SCRIPT.read_text().split("# ── 4. ship", 1)[1].split("DMG_SIZE=", 1)[0]
        )
        self.assertNotIn("packaging/stick/install.command", ship_logic)
        self.assertNotIn("packaging/stick/purge.command", ship_logic)
        self.assertIn('publish_generation "$STICK" "$DMG"', ship_logic)
        publish = SCRIPT.read_text().split("publish_generation()", 1)[1].split(
            "# ── build interpreter", 1
        )[0]
        self.assertIn('"$stage/RBSS Bridge.dmg"', publish)
        self.assertIn('"$stage/lighting_sidecar"', publish)
        self.assertNotIn('"$stage/install.command"', publish)
        self.assertNotIn('"$stage/purge.command"', publish)
        self.assertNotIn('"$stage/RBSS_payload"', publish)

    def test_transactional_publish_replaces_complete_surface_and_cleans_legacy(self):
        stick = Path(self.tmp.name) / "stick"
        stick.mkdir()
        old = stick / "RBSS BRIDGE USB"
        old.mkdir()
        (old / "RBSS Bridge.dmg").write_text("old")
        (old / "install.command").write_text("legacy")
        (old / "purge.command").write_text("legacy")
        (old / "RBSS_payload").mkdir()
        dmg = Path(self.tmp.name) / "new.dmg"
        dmg.write_text("new")
        sidecar = Path(self.tmp.name) / "lighting_sidecar"
        sidecar.mkdir()
        (sidecar / "index.json").write_text("{}")

        command = "publish_generation {} {} {}".format(
            shlex.quote(str(stick)), shlex.quote(str(dmg)), shlex.quote(str(sidecar))
        )
        result = self._source_and_run(command)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual((old / "RBSS Bridge.dmg").read_text(), "new")
        self.assertTrue((old / "lighting_sidecar" / "index.json").is_file())
        manifest = json.loads(
            (old / "lighting_sidecar" / ".rbss_build_manifest.json").read_text()
        )
        self.assertEqual(
            {row["path"] for row in manifest["files"]},
            {"RBSS Bridge.dmg", "lighting_sidecar/index.json"},
        )
        self.assertFalse((old / "install.command").exists())
        self.assertFalse((old / "purge.command").exists())
        self.assertFalse((old / "RBSS_payload").exists())

    def test_transactional_publish_failure_keeps_prior_surface(self):
        stick = Path(self.tmp.name) / "stick-fail"
        stick.mkdir()
        old = stick / "RBSS BRIDGE USB"
        old.mkdir()
        (old / "RBSS Bridge.dmg").write_text("old")
        dmg = Path(self.tmp.name) / "new-fail.dmg"
        dmg.write_text("new")
        sidecar = Path(self.tmp.name) / "sidecar-fail"
        sidecar.mkdir()
        (sidecar / "index.json").write_text("{}")

        command = "publish_generation {} {} {}".format(
            shlex.quote(str(stick)), shlex.quote(str(dmg)), shlex.quote(str(sidecar))
        )
        result = self._source_and_run(
            command, {"RBSS_MAKE_STICK_FAIL_BEFORE_SWAP": "1"}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((old / "RBSS Bridge.dmg").read_text(), "old")
        self.assertFalse((old / "lighting_sidecar").exists())

    def test_transactional_publish_failure_after_hide_restores_prior_surface(self):
        stick = Path(self.tmp.name) / "stick-fail-after-hide"
        stick.mkdir()
        old = stick / "RBSS BRIDGE USB"
        old.mkdir()
        (old / "RBSS Bridge.dmg").write_text("old")
        dmg = Path(self.tmp.name) / "new-after-hide.dmg"
        dmg.write_text("new")
        sidecar = Path(self.tmp.name) / "sidecar-after-hide"
        sidecar.mkdir()
        (sidecar / "index.json").write_text("{}")

        command = "publish_generation {} {} {}".format(
            shlex.quote(str(stick)), shlex.quote(str(dmg)), shlex.quote(str(sidecar))
        )
        result = self._source_and_run(
            command, {"RBSS_MAKE_STICK_FAIL_AFTER_HIDE": "1"}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((old / "RBSS Bridge.dmg").read_text(), "old")
        self.assertFalse((stick / ".RBSS BRIDGE USB.previous").exists())
        self.assertFalse(any(stick.glob(".rbss-publish-new.*")))

    def test_interrupted_publish_recovers_hidden_previous_generation(self):
        stick = Path(self.tmp.name) / "stick-recover"
        stick.mkdir()
        previous = stick / ".RBSS BRIDGE USB.previous"
        previous.mkdir()
        (previous / "RBSS Bridge.dmg").write_text("old")
        dmg = Path(self.tmp.name) / "new-recover.dmg"
        dmg.write_text("new")
        sidecar = Path(self.tmp.name) / "sidecar-recover"
        sidecar.mkdir()
        (sidecar / "index.json").write_text("{}")

        command = "publish_generation {} {} {}".format(
            shlex.quote(str(stick)), shlex.quote(str(dmg)), shlex.quote(str(sidecar))
        )
        result = self._source_and_run(
            command, {"RBSS_MAKE_STICK_FAIL_BEFORE_SWAP": "1"}
        )

        self.assertNotEqual(result.returncode, 0)
        restored = stick / "RBSS BRIDGE USB" / "RBSS Bridge.dmg"
        self.assertEqual(restored.read_text(), "old")
        self.assertFalse(previous.exists())

    def test_space_preflight_uses_destination_allocation_units(self):
        stick = Path(self.tmp.name) / "allocation-stick"
        stick.mkdir()
        tiny = Path(self.tmp.name) / "tiny"
        tiny.write_bytes(b"x")
        result = self._source_and_run(
            "tree_allocated_bytes {} {}".format(
                shlex.quote(str(stick)), shlex.quote(str(tiny))
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        allocated = int(result.stdout.strip())
        unit = os.statvfs(stick).f_frsize or os.statvfs(stick).f_bsize
        self.assertEqual(allocated, unit)

    def test_stage_only_runs_sidecar_exporter_into_dmg_payload(self):
        marker = Path(self.tmp.name) / "exporter-ran"
        exporter = Path(self.tmp.name) / "marker_exporter.py"
        exporter.write_text(
            "import json, pathlib, sys\n"
            f"pathlib.Path({str(marker)!r}).write_text('ran')\n"
            "root = pathlib.Path(sys.argv[sys.argv.index('--dest') + 1]) / 'lighting_sidecar'\n"
            "root.mkdir(parents=True, exist_ok=True)\n"
            "(root / 'index.json').write_text(json.dumps({"
            "'schema_version': 1, 'track_count': 1, 'tracks': [{'content_id': '1'}]}))\n"
        )
        result = self._run(
            env_extra={"RBSS_MAKE_STICK_SIDECAR_EXPORTER": str(exporter)}
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(marker.exists())
        self.assertTrue(
            (self.staging / "RBSS_payload" / "lighting_sidecar" / "index.json").is_file()
        )

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
        self.assertEqual(
            stat.S_IMODE(
                (self.staging / "RBSS_payload" / "home" / "govee.env").stat().st_mode
            ),
            0o600,
        )
        self.assertTrue(
            (self.staging / "RBSS_payload" / "streamdeck_midi_bindings.json").is_file()
        )
        manifest = json.loads(
            (self.staging / "RBSS_payload" / "build_manifest.json").read_text()
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertRegex(manifest["git_head"], r"^[0-9a-f]{40}$")
        self.assertTrue(manifest["generation"])
        self.assertTrue(any(row["path"].endswith("govee.env") for row in manifest["files"]))
        self.assertNotIn("test-key-not-real", json.dumps(manifest))
        # cache + five managed home files + pack + bindings + sidecar + manifest
        self.assertIn("10 payload file(s)", result.stdout)

    def test_pack_dir_copied_into_payload(self):
        # AWR-186 Track A: pack_path from the live config is copied into the
        # payload so the guest Mac's native pack DMX renderer has the show.
        import json

        pack = Path(self.tmp.name) / "the_pack"
        (pack / "sub").mkdir(parents=True)
        (pack / "manifest.json").write_text("{}")
        (pack / "sub" / "cue.bin").write_text("x")
        (self.config / "soundswitch_pack_player.json").write_text(
            json.dumps({"pack_path": str(pack)})
        )
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        dest = self.staging / "RBSS_payload" / "soundswitch_pack"
        self.assertTrue((dest / "manifest.json").is_file())
        self.assertTrue((dest / "sub" / "cue.bin").is_file())
        # cache + five home + two pack + bindings + sidecar + build manifest
        self.assertIn("11 payload file(s)", result.stdout)

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

    def test_malformed_streamdeck_bindings_fail_closed(self):
        self.bindings.write_text("{}")
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("home-parity data", result.stderr)

    def test_empty_lighting_sidecar_fails_closed(self):
        self.exporter.write_text(
            "import json, pathlib, sys\n"
            "root = pathlib.Path(sys.argv[sys.argv.index('--dest') + 1]) / 'lighting_sidecar'\n"
            "root.mkdir(parents=True, exist_ok=True)\n"
            "(root / 'index.json').write_text(json.dumps({"
            "'schema_version': 1, 'track_count': 0, 'tracks': []}))\n"
        )
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("home-parity data", result.stderr)

    def test_empty_pack_path_fails_closed(self):
        import json

        (self.config / "soundswitch_pack_player.json").write_text(
            json.dumps({"pack_path": ""})
        )
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("pack_path is empty", result.stderr)
        self.assertFalse(
            (self.staging / "RBSS_payload" / "soundswitch_pack").exists()
        )

    def test_absent_managed_files_fail_closed(self):
        (self.support / "govee.env").unlink()
        (self.config / "laser_director.json").unlink()
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("required managed home file", result.stderr)

    def test_unreadable_source_fails_closed(self):
        target = self.config / "led_look_director.json"
        target.chmod(0o000)
        try:
            result = self._run()
        finally:
            target.chmod(0o644)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unreadable", result.stderr)

    def test_refuses_normal_folder_even_if_it_looks_like_a_stick(self):
        fake_stick = Path(self.tmp.name) / "not_a_stick"
        (fake_stick / "PIONEER").mkdir(parents=True)
        result = self._run(str(fake_stick), env_extra={"RBSS_MAKE_STICK_STAGE_ONLY": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not mounted under /Volumes", result.stderr)

    def test_payload_symlink_fails_closed(self):
        outside = Path(self.tmp.name) / "outside"
        outside.write_text("outside")
        (self.support / "spectral_cache" / "escape").symlink_to(outside)

        result = self._run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("payload contains a symbolic link", result.stderr)

    def test_real_build_requires_clean_stable_repository(self):
        script = SCRIPT.read_text()
        self.assertIn("status --porcelain --untracked-files=normal", script)
        self.assertIn("repository HEAD changed during the USB build", script)
        self.assertGreaterEqual(script.count("require_unchanged_clean_source"), 3)

    def test_refuses_missing_mount(self):
        result = self._run(
            str(Path(self.tmp.name) / "nope"), env_extra={"RBSS_MAKE_STICK_STAGE_ONLY": ""}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a mounted volume", result.stderr)


if __name__ == "__main__":
    unittest.main()
