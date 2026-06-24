from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class BridgeMenubarTests(unittest.TestCase):
    def _import_module(self):
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        try:
            return importlib.import_module("bridge_menubar")
        except ModuleNotFoundError as exc:
            if exc.name in {"objc", "AppKit", "Foundation"}:
                self.skipTest(f"PyObjC unavailable: {exc.name}")
            raise

    def test_map_lasers_opens_pad_url(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        bridge_menubar = self._import_module()

        handler = bridge_menubar.BridgeMenuBar.mapLasers_
        with patch.object(bridge_menubar, "open_browser_url") as open_browser:
            handler.callable(None, None)

        open_browser.assert_called_once_with(bridge_menubar.LASER_PAD_URL)
        self.assertEqual(bridge_menubar.LASER_PAD_URL, "http://127.0.0.1:8765")
        source = (scripts_dir / "bridge_menubar.py").read_text(encoding="utf-8")
        self.assertIn("Laser Pad…", source)

    def test_toggle_record_session_appends_runtime_command(self) -> None:
        bridge_menubar = self._import_module()

        handler = bridge_menubar.BridgeMenuBar.toggleRecordSession_
        with (
            patch.object(bridge_menubar, "read_status", return_value={}),
            patch.object(bridge_menubar, "default_recording_path", return_value="/tmp/session.jsonl"),
            patch.object(bridge_menubar, "append_command") as append_command,
        ):
            handler.callable(None, None)

        append_command.assert_called_once_with(
            {
                "cmd": "toggle_record_session",
                "path": "/tmp/session.jsonl",
                "dedup": False,
            }
        )

    def test_build_export_argv_uses_module_without_shell(self) -> None:
        bridge_menubar = self._import_module()
        self.assertEqual(bridge_menubar.build_export_argv("result.json"), [
            sys.executable,
            "-m",
            "rb_ss_bridge_v2.tools.export_soundswitch_pack",
            "--publish-canonical",
            "--result-json",
            "result.json",
        ])

    def test_parse_export_result_accepts_schema_and_rejects_malformed(self) -> None:
        bridge_menubar = self._import_module()
        expected = {
            "ok": True,
            "verdict": "published",
            "manifest_sha256": "a" * 64,
            "artifact_count": 95,
            "first_export": False,
            "error_category": "",
        }
        self.assertEqual(bridge_menubar.parse_export_result(json.dumps(expected)), expected)
        fallback = {"ok": False, "verdict": "unknown_error"}
        self.assertEqual(bridge_menubar.parse_export_result(""), fallback)
        self.assertEqual(bridge_menubar.parse_export_result("not-json"), fallback)
        self.assertEqual(bridge_menubar.parse_export_result("{}"), fallback)

    def test_evaluate_reload_ack_truth_table(self) -> None:
        bridge_menubar = self._import_module()
        expected = "a" * 12
        self.assertEqual(bridge_menubar.evaluate_reload_ack(
            {"soundswitch_pack": {"enabled": True, "pack_sha12": expected}}, expected,
        ), "succeeded")
        self.assertEqual(bridge_menubar.evaluate_reload_ack(
            {"soundswitch_pack": {"enabled": False, "pack_sha12": expected}}, expected,
        ), "not_live")
        self.assertEqual(bridge_menubar.evaluate_reload_ack({}, expected), "stale")
        self.assertEqual(bridge_menubar.evaluate_reload_ack({"written_at": 1}, expected), "not_live")
        self.assertEqual(bridge_menubar.evaluate_reload_ack(
            {"soundswitch_pack": {"enabled": True, "pack_sha12": "b" * 12}}, expected,
        ), "pending")
        self.assertEqual(bridge_menubar.evaluate_reload_ack(
            {"stale": True, "soundswitch_pack": {"enabled": True, "pack_sha12": expected}},
            expected,
        ), "stale")

    def _worker(self, bridge_menubar):
        worker = Mock()
        worker._marshal_export_result = Mock()
        worker._marshal_export_phase = Mock()
        return worker

    def _ok_subprocess(self, argv, **_kwargs):
        result = {
            "ok": True,
            "verdict": "published",
            "manifest_sha256": "a" * 64,
            "artifact_count": 95,
            "first_export": False,
            "error_category": "",
        }
        Path(argv[-1]).write_text(json.dumps(result), encoding="utf-8")
        return Mock(returncode=0)

    def test_export_worker_bridge_off_publishes_without_reload(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        with patch.object(bridge_menubar.subprocess, "run", side_effect=self._ok_subprocess) as run, \
             patch.object(bridge_menubar, "read_status", return_value={}), \
             patch.object(bridge_menubar, "bridge_pids", return_value=[]), \
             patch.object(bridge_menubar, "append_command") as append_command:
            handler(worker)
        append_command.assert_not_called()
        self.assertEqual(run.call_args.kwargs["cwd"], bridge_menubar.EXPORT_WORKING_DIRECTORY)
        state, result = worker._marshal_export_result.call_args.args
        self.assertEqual(state, "published_not_live")
        self.assertTrue(result["ok"])
        worker._marshal_export_phase.assert_called_once_with("reloading")

    def test_export_worker_bridge_on_reloads_and_confirms_matching_sha(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        statuses = [
            {"soundswitch_pack": {"enabled": True, "pack_sha12": "b" * 12}},
            {"soundswitch_pack": {"enabled": True, "pack_sha12": "a" * 12}},
        ]
        with patch.object(bridge_menubar.subprocess, "run", side_effect=self._ok_subprocess), \
             patch.object(bridge_menubar, "read_status", side_effect=statuses), \
             patch.object(bridge_menubar, "bridge_pids", return_value=["123"]), \
             patch.object(bridge_menubar, "append_command") as append_command, \
             patch.object(bridge_menubar.time, "sleep"):
            handler(worker)
        append_command.assert_called_once_with(
            {"cmd": "set_soundswitch_pack", "action": "reload"}
        )
        self.assertEqual(worker._marshal_export_result.call_args.args[0], "reload_succeeded")
        worker._marshal_export_phase.assert_called_once_with("reloading")

    def test_export_worker_bridge_on_but_stale_does_not_reload(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        stale = {"stale": True, "stale_age_s": 99,
                 "soundswitch_pack": {"enabled": True, "pack_sha12": "a" * 12}}
        with patch.object(bridge_menubar.subprocess, "run", side_effect=self._ok_subprocess), \
             patch.object(bridge_menubar, "read_status", return_value=stale), \
             patch.object(bridge_menubar, "bridge_pids", return_value=["123"]), \
             patch.object(bridge_menubar, "append_command") as append_command, \
             patch.object(bridge_menubar.time, "sleep"):
            handler(worker)
        append_command.assert_not_called()
        state, result = worker._marshal_export_result.call_args.args
        self.assertEqual(state, "reload_failed")
        self.assertTrue(result["ok"])

    def test_export_worker_bridge_on_pack_disabled_publishes_without_reload(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        disabled = {"soundswitch_pack": {"enabled": False}}
        with patch.object(bridge_menubar.subprocess, "run", side_effect=self._ok_subprocess), \
             patch.object(bridge_menubar, "read_status", return_value=disabled), \
             patch.object(bridge_menubar, "bridge_pids", return_value=["123"]), \
             patch.object(bridge_menubar, "append_command") as append_command, \
             patch.object(bridge_menubar.time, "sleep"):
            handler(worker)
        append_command.assert_not_called()
        self.assertEqual(
            worker._marshal_export_result.call_args.args[0], "published_not_live")

    def test_export_worker_identical_reexport_confirms_without_resending_reload(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        already = {"soundswitch_pack": {"enabled": True, "pack_sha12": "a" * 12}}
        with patch.object(bridge_menubar.subprocess, "run", side_effect=self._ok_subprocess), \
             patch.object(bridge_menubar, "read_status", return_value=already), \
             patch.object(bridge_menubar, "bridge_pids", return_value=["123"]), \
             patch.object(bridge_menubar, "append_command") as append_command, \
             patch.object(bridge_menubar.time, "sleep"):
            handler(worker)
        append_command.assert_not_called()
        self.assertEqual(
            worker._marshal_export_result.call_args.args[0], "reload_succeeded")

    def test_export_handler_ignores_second_click(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu._export_in_progress = False
        menu._detect_generation = 0
        menu._detect_in_progress = True
        menu._render_export_state = Mock()
        thread = Mock()
        with patch.object(bridge_menubar.threading, "Thread", return_value=thread) as thread_type:
            bridge_menubar.BridgeMenuBar.exportFromSS_.callable(menu, None)
            bridge_menubar.BridgeMenuBar.exportFromSS_.callable(menu, None)
        thread_type.assert_called_once_with(target=menu._run_export, daemon=True)
        thread.start.assert_called_once_with()

    def test_finish_export_clears_guard_and_renders(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu._export_in_progress = True
        menu._render_export_state = Mock()
        bridge_menubar.BridgeMenuBar.finishExport_.callable(menu, {
            "state": "reload_succeeded",
            "result": {"ok": True},
        })
        self.assertFalse(menu._export_in_progress)
        self.assertEqual(menu._export_phase, "idle")
        self.assertTrue(menu._export_up_to_date)
        self.assertEqual(menu._export_state, "reload_succeeded")
        menu._render_export_state.assert_called_once_with()

    def test_export_button_text_truth_table(self) -> None:
        bridge_menubar = self._import_module()
        self.assertEqual(bridge_menubar.export_button_text(True, False), "Exporting…")
        self.assertEqual(bridge_menubar.export_button_text(True, True), "Exporting…")
        self.assertEqual(bridge_menubar.export_button_text(False, True), "Exported")
        self.assertEqual(
            bridge_menubar.export_button_text(False, False), "Export from Soundswitch",
        )

    def test_export_result_line_truth_table_and_sanitization(self) -> None:
        bridge_menubar = self._import_module()
        self.assertEqual(bridge_menubar.export_result_line("idle"), "")
        self.assertEqual(bridge_menubar.export_result_line("exporting"), "")
        self.assertEqual(
            bridge_menubar.export_result_line("published_not_live"),
            "  saved (loads when pack enabled)",
        )
        self.assertEqual(bridge_menubar.export_result_line("reload_succeeded"), "  live now")
        self.assertEqual(
            bridge_menubar.export_result_line("reload_failed"),
            "  saved — live reload not confirmed",
        )
        raw = "/private/project device UUID port raw failure"
        text = bridge_menubar.export_result_line(
            "export_failed", {"error_category": raw},
        )
        self.assertNotIn("/", text)
        self.assertNotIn(raw, text)
        self.assertIn("UnknownError", text)

    def test_pack_export_status_line_truth_tables_and_bounds(self) -> None:
        bridge_menubar = self._import_module()
        states = {
            "disabled": "Disabled",
            "blackout": "Blackout",
            "input_degraded": "Input degraded",
            "static_held": "Static held",
            "scripted_active": "Scripted active",
            "autoloop_phase_blocked": "Autoloop blocked",
            "software_zero_frame": "Software zero",
            "bogus": "Unknown",
        }
        for state, label in states.items():
            with self.subTest(state=state):
                line = bridge_menubar.pack_export_status_line(
                    {"operational_state": state}, stale=False,
                    export_phase="idle", export_state="idle",
                    export_up_to_date=False,
                )
                self.assertEqual(line, f"Pack: {label} · Ready to export")

        exports = (
            ("exporting", "idle", False, {}, "Exporting…"),
            ("reloading", "idle", False, {}, "Reloading…"),
            ("idle", "idle", True, {}, "Exported"),
            ("idle", "published_not_live", True, {}, "Saved; pack disabled"),
            ("idle", "reload_succeeded", True, {}, "Live now"),
            ("idle", "reload_failed", True, {}, "Saved; reload unconfirmed"),
            ("idle", "export_failed", False, {"error_category": "TimeoutExpired"},
             "Export failed (TimeoutExpired)"),
        )
        for phase, state, current, result, label in exports:
            with self.subTest(phase=phase, state=state):
                line = bridge_menubar.pack_export_status_line(
                    {"operational_state": "disabled"}, stale=False,
                    export_phase=phase, export_state=state,
                    export_up_to_date=current, export_result=result,
                )
                self.assertEqual(line, f"Pack: Disabled · {label}")

        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "scripted_active"}, stale=True,
                export_phase="idle", export_state="reload_succeeded",
                export_up_to_date=True,
            ),
            "Pack: Unknown",
        )
        line = bridge_menubar.pack_export_status_line(
            {"operational_state": "scripted_active"}, stale=False,
            export_phase="idle", export_state="export_failed",
            export_up_to_date=False,
            export_result={"error_category": "A" * 200},
        )
        self.assertLessEqual(len(line), 80)
        self.assertNotIn("/private", bridge_menubar.pack_export_status_line(
            {"operational_state": "scripted_active"}, stale=False,
            export_phase="idle", export_state="export_failed",
            export_up_to_date=False,
            export_result={"error_category": "/private/device raw failure"},
        ))

    def test_stale_detect_and_phase_callbacks_cannot_overwrite_newer_state(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock(_detect_generation=2, _detect_in_progress=True,
                    _export_in_progress=False, _export_phase="idle")
        menu._render_export_state = Mock()

        bridge_menubar.BridgeMenuBar.finishDetect_.callable(menu, {
            "generation": 1, "verdict": "up_to_date", "sig": "old",
        })
        self.assertNotEqual(menu._export_up_to_date, True)
        menu._render_export_state.assert_not_called()

        bridge_menubar.BridgeMenuBar.setExportPhase_.callable(menu, "reloading")
        self.assertEqual(menu._export_phase, "idle")
        menu._render_export_state.assert_not_called()

    def test_reload_phase_is_marshaled_to_main_thread(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        bridge_menubar.BridgeMenuBar._marshal_export_phase(menu, "reloading")
        menu.performSelectorOnMainThread_withObject_waitUntilDone_.assert_called_once_with(
            "setExportPhase:", "reloading", False,
        )

    def test_detect_export_state_requires_positive_proof(self) -> None:
        bridge_menubar = self._import_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.ssproj"
            source.mkdir()
            source_file = source / "project.ssfile"
            source_file.write_bytes(b"one")
            pack = root / "pack"
            pack.mkdir()
            sidecar = bridge_menubar._sidecar_path(pack)
            sidecar.write_text(json.dumps({
                "source_fingerprint": bridge_menubar._source_content_fingerprint(source),
                "generator_commit": "a" * 40,
                "pack_manifest_sha256": "b" * 64,
            }), encoding="utf-8")

            with patch.object(bridge_menubar, "CANONICAL_SOURCE_PROJECT", str(source)), \
                 patch.object(bridge_menubar, "CANONICAL_PACK_DIR", pack), \
                 patch.object(bridge_menubar, "current_generator_commit", return_value="a" * 40):
                self.assertEqual(bridge_menubar.detect_export_state(), "up_to_date")
                source_file.write_bytes(b"two")
                self.assertEqual(bridge_menubar.detect_export_state(), "changes")
                source_file.write_bytes(b"one")
                sidecar.unlink()
                self.assertEqual(bridge_menubar.detect_export_state(), "changes")
                sidecar.write_text("not-json", encoding="utf-8")
                self.assertEqual(bridge_menubar.detect_export_state(), "changes")
                sidecar.write_text(json.dumps({
                    "source_fingerprint": bridge_menubar._source_content_fingerprint(source),
                    "generator_commit": "a" * 40,
                }), encoding="utf-8")
                pack.rmdir()
                self.assertEqual(bridge_menubar.detect_export_state(), "changes")
                pack.mkdir()

            with patch.object(bridge_menubar, "CANONICAL_SOURCE_PROJECT", str(source)), \
                 patch.object(bridge_menubar, "CANONICAL_PACK_DIR", pack), \
                 patch.object(bridge_menubar, "current_generator_commit", return_value="c" * 40):
                self.assertEqual(bridge_menubar.detect_export_state(), "changes")
            with patch.object(bridge_menubar, "CANONICAL_SOURCE_PROJECT", str(source)), \
                 patch.object(bridge_menubar, "CANONICAL_PACK_DIR", pack), \
                 patch.object(bridge_menubar, "current_generator_commit", return_value=None):
                self.assertEqual(bridge_menubar.detect_export_state(), "up_to_date")

            sidecar.write_text(json.dumps({
                "source_fingerprint": bridge_menubar._source_content_fingerprint(source),
            }), encoding="utf-8")
            with patch.object(bridge_menubar, "CANONICAL_SOURCE_PROJECT", str(source)), \
                 patch.object(bridge_menubar, "CANONICAL_PACK_DIR", pack), \
                 patch.object(bridge_menubar, "current_generator_commit", return_value=None):
                self.assertEqual(bridge_menubar.detect_export_state(), "changes")

    def test_finish_export_updates_freshness_verdict(self) -> None:
        bridge_menubar = self._import_module()
        for state in ("reload_succeeded", "published_not_live", "reload_failed"):
            with self.subTest(state=state):
                menu = Mock(_export_in_progress=True, _detect_sig="old")
                menu._render_export_state = Mock()
                bridge_menubar.BridgeMenuBar.finishExport_.callable(menu, {
                    "state": state, "result": {"ok": True},
                })
                self.assertTrue(menu._export_up_to_date)
                self.assertIsNone(menu._detect_sig)
        menu = Mock(_export_in_progress=True, _detect_sig="old")
        menu._render_export_state = Mock()
        bridge_menubar.BridgeMenuBar.finishExport_.callable(menu, {
            "state": "export_failed", "result": {"ok": False},
        })
        self.assertFalse(menu._export_up_to_date)
        self.assertIsNone(menu._detect_sig)

    def test_maybe_detect_skips_export_and_fresh_unchanged_signature(self) -> None:
        bridge_menubar = self._import_module()
        handler = bridge_menubar.BridgeMenuBar._maybe_detect_export_state
        menu = Mock(
            _export_in_progress=True,
            _detect_in_progress=False,
            _detect_sig=None,
            _detect_at=0.0,
        )
        with patch.object(bridge_menubar, "_source_stat_signature") as signature, \
             patch.object(bridge_menubar.threading, "Thread") as thread:
            handler(menu)
        signature.assert_not_called()
        thread.assert_not_called()

        menu._export_in_progress = False
        menu._detect_sig = "same"
        menu._detect_at = bridge_menubar.time.monotonic()
        with patch.object(bridge_menubar, "_source_stat_signature", return_value="same"), \
             patch.object(bridge_menubar.threading, "Thread") as thread:
            handler(menu)
        thread.assert_not_called()

    def test_worker_subprocess_failure_returns_sanitized_terminal_state(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        with patch.object(
            bridge_menubar.subprocess, "run",
            side_effect=bridge_menubar.subprocess.TimeoutExpired("/private/path", 1),
        ):
            handler(worker)
        state, result = worker._marshal_export_result.call_args.args
        self.assertEqual(state, "export_failed")
        self.assertEqual(result["error_category"], "TimeoutExpired")
        self.assertNotIn("/private/path", json.dumps(result))

    def test_post_publish_command_failure_remains_saved_not_export_failed(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        live = {"soundswitch_pack": {"enabled": True, "pack_sha12": "b" * 12}}
        with patch.object(bridge_menubar.subprocess, "run", side_effect=self._ok_subprocess), \
             patch.object(bridge_menubar, "read_status", return_value=live), \
             patch.object(bridge_menubar, "bridge_pids", return_value=["123"]), \
             patch.object(bridge_menubar, "append_command", side_effect=OSError("write failed")):
            handler(worker)
        state, result = worker._marshal_export_result.call_args.args
        self.assertEqual(state, "reload_failed")
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
