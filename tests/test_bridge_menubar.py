from __future__ import annotations

import importlib
import json
import sys
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

    def test_export_handler_ignores_second_click(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu._export_in_progress = False
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
        self.assertEqual(menu._export_state, "reload_succeeded")
        menu._render_export_state.assert_called_once_with()

    def test_export_display_never_surfaces_paths_or_raw_errors(self) -> None:
        bridge_menubar = self._import_module()
        raw = "/private/project device UUID port raw failure"
        states = (
            "idle", "exporting", "published_not_live", "reload_succeeded", "reload_failed",
        )
        for state in states:
            for text in bridge_menubar.export_display(state, {}):
                self.assertNotIn("/", text)
                self.assertNotIn(raw, text)
        for text in bridge_menubar.export_display("export_failed", {"error_category": raw}):
            self.assertNotIn("/", text)
            self.assertNotIn(raw, text)
            self.assertIn("UnknownError", text)

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
