from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# The NativeInstallGateTests patch rb_ss_bridge_v2.install_controller.*, which
# only resolves with the repo's PARENT on sys.path — the same convention as
# test_usb_launcher/test_launch_profile/test_install_controller (M2 review fix:
# without this, running this module alone from the repo root errors with
# ModuleNotFoundError instead of testing anything).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


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

    def test_open_pad_opens_directly_when_already_up(self) -> None:
        bridge_menubar = self._import_module()
        with patch.object(bridge_menubar, "_port_open", return_value=True), \
             patch.object(bridge_menubar.subprocess, "Popen") as popen, \
             patch.object(bridge_menubar, "open_browser_url") as open_browser:
            bridge_menubar.open_pad(bridge_menubar.LASER_PAD_URL, 8765, ["x"])
        popen.assert_not_called()  # already listening -> don't stack a 2nd server
        open_browser.assert_called_once_with(bridge_menubar.LASER_PAD_URL)

    def test_open_pad_spawns_when_down_then_opens(self) -> None:
        bridge_menubar = self._import_module()
        argv = bridge_menubar.laser_pad_argv()
        # down at the first probe, then up (so the wait loop exits immediately)
        with patch.object(bridge_menubar, "_port_open", side_effect=[False, True]), \
             patch.object(bridge_menubar.subprocess, "Popen") as popen, \
             patch.object(bridge_menubar, "open_browser_url") as open_browser:
            bridge_menubar.open_pad(bridge_menubar.LASER_PAD_URL, 8765, argv)
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], argv)
        open_browser.assert_called_once_with(bridge_menubar.LASER_PAD_URL)

    def test_pad_handlers_dispatch_off_main_thread(self) -> None:
        # open_pad may block up to 3s spawning the server, so the AppKit handlers
        # must background it (menu stays responsive) — pin that they thread it.
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        source = (scripts_dir / "bridge_menubar.py").read_text(encoding="utf-8")
        self.assertIn("Laser Pad…", source)
        self.assertIn("LED Pad…", source)
        for handler in ("def mapLasers_", "def openLedPad_"):
            start = source.index(handler)
            body = source[start:start + 400]
            self.assertIn("threading.Thread", body, f"{handler} must not block the menu")
            self.assertIn("open_pad", body)

    def test_watcher_path_uses_repo_copy(self) -> None:
        bridge_menubar = self._import_module()
        repo_root = Path(__file__).resolve().parents[1]

        self.assertEqual(
            bridge_menubar.WATCHER,
            str(repo_root / "scripts" / "ss_bridge_watcher.sh"),
        )
        self.assertIn("/scripts/ss_bridge_watcher\\.sh", bridge_menubar.WATCHER_PATTERN)
        self.assertNotIn("/Users/bbui/ss_bridge_watcher", bridge_menubar.WATCHER_PATTERN)

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

    def test_led_engine_v2_command_tracks_snapshot_mode(self) -> None:
        bridge_menubar = self._import_module()

        # Real status shape: the engine snapshot is nested under state_manager.
        v1 = {"state_manager": {"led_color_engine": {"engine": "v1"}}}
        v2 = {"state_manager": {"led_color_engine": {"engine": "v2"}}}
        missing = {"state_manager": {"led_color_engine": {"available": True}}}
        unconfigured = {"state_manager": {}}

        self.assertTrue(bridge_menubar.led_engine_v2_available(v1))
        self.assertFalse(bridge_menubar.led_engine_v2_enabled(v1))
        self.assertEqual(bridge_menubar.led_engine_v2_command(v1), {"cmd": "led_engine", "mode": "v2"})
        self.assertTrue(bridge_menubar.led_engine_v2_enabled(v2))
        self.assertEqual(bridge_menubar.led_engine_v2_command(v2), {"cmd": "led_engine", "mode": "v1"})
        self.assertFalse(bridge_menubar.led_engine_v2_available(missing))
        self.assertFalse(bridge_menubar.led_engine_v2_available(unconfigured))
        # Legacy top-level shape still resolves (back-compat fallback).
        self.assertTrue(bridge_menubar.led_engine_v2_available({"led_color_engine": {"engine": "v2"}}))

    def test_toggle_led_engine_v2_appends_runtime_command(self) -> None:
        bridge_menubar = self._import_module()

        handler = bridge_menubar.BridgeMenuBar.toggleLedEngineV2_
        with (
            patch.object(bridge_menubar, "read_status", return_value={"state_manager": {"led_color_engine": {"engine": "v1"}}}),
            patch.object(bridge_menubar, "append_command") as append_command,
        ):
            handler.callable(None, None)

        append_command.assert_called_once_with({"cmd": "led_engine", "mode": "v2"})

    def test_pack_auto_command_follows_soundswitch_connection(self) -> None:
        bridge_menubar = self._import_module()
        self.assertEqual(
            bridge_menubar.pack_auto_command(
                {
                    "soundswitch": {"connected": False},
                    "soundswitch_pack": {"available": True, "enabled": False},
                },
                bridge_status="on",
            ),
            {"cmd": "set_soundswitch_pack", "action": "enable", "enabled": True},
        )
        self.assertEqual(
            bridge_menubar.pack_auto_command(
                {
                    "soundswitch": {"connected": True},
                    "soundswitch_pack": {"available": True, "enabled": True},
                },
                bridge_status="on",
            ),
            {"cmd": "set_soundswitch_pack", "action": "enable", "enabled": False},
        )
        self.assertIsNone(
            bridge_menubar.pack_auto_command(
                {
                    "soundswitch": {"connected": False},
                    "soundswitch_pack": {"available": True, "enabled": True},
                },
                bridge_status="on",
            )
        )

    def test_pack_auto_command_holds_pack_enabled_during_artnet_exam(self) -> None:
        bridge_menubar = self._import_module()
        exam_status = {
            "soundswitch": {"connected": True},
            "soundswitch_pack": {"available": True, "enabled": True},
            "laser_director": {"executor": {"midi": {"midi_link": {"degraded": False}}}},
        }
        self.assertIsNone(
            bridge_menubar.pack_auto_command(exam_status, bridge_status="on")
        )
        # Same snapshot minus the exam signal reverts to normal auto-disable.
        non_exam_status = {
            "soundswitch": {"connected": True},
            "soundswitch_pack": {"available": True, "enabled": True},
        }
        self.assertEqual(
            bridge_menubar.pack_auto_command(non_exam_status, bridge_status="on"),
            {"cmd": "set_soundswitch_pack", "action": "enable", "enabled": False},
        )

    def test_pack_auto_command_ignores_unknown_or_unconfigured_state(self) -> None:
        bridge_menubar = self._import_module()
        snapshots = (
            {},
            {"stale": True, "soundswitch_pack": {"available": True, "enabled": False}},
            {"soundswitch_pack": "bad"},
            {"soundswitch": {}, "soundswitch_pack": {"available": True, "enabled": False}},
            {"soundswitch": {"connected": False}, "soundswitch_pack": {"reason": "not_configured"}},
        )
        for snapshot in snapshots:
            with self.subTest(snapshot=snapshot):
                self.assertIsNone(bridge_menubar.pack_auto_command(snapshot, bridge_status="on"))
        self.assertIsNone(
            bridge_menubar.pack_auto_command(
                {
                    "soundswitch": {"connected": False},
                    "soundswitch_pack": {"available": True, "enabled": False},
                },
                bridge_status="off",
            )
        )

    def test_auto_set_soundswitch_pack_suppresses_duplicate_pending_command(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock(
            _snapshot={
                "soundswitch": {"connected": False},
                "soundswitch_pack": {"available": True, "enabled": False},
            },
            _status="on",
            _pack_auto_pending_enabled=None,
        )
        handler = bridge_menubar.BridgeMenuBar._auto_set_soundswitch_pack

        with patch.object(bridge_menubar, "append_command") as append_command:
            handler(menu)
            handler(menu)

        append_command.assert_called_once_with(
            {"cmd": "set_soundswitch_pack", "action": "enable", "enabled": True}
        )
        self.assertTrue(menu._pack_auto_pending_enabled)

    def test_auto_set_soundswitch_pack_recovers_after_failed_enable(self) -> None:
        # Regression: a failed enable (enabled never flips True, e.g. no Enttec port)
        # must not latch the debounce flag forever and kill auto enable/disable.
        bridge_menubar = self._import_module()
        menu = Mock(
            _snapshot={
                "soundswitch": {"connected": False},
                "soundswitch_pack": {"available": True, "enabled": False},
            },
            _status="on",
            _pack_auto_pending_enabled=None,
        )
        handler = bridge_menubar.BridgeMenuBar._auto_set_soundswitch_pack
        with patch.object(bridge_menubar, "append_command") as append_command:
            handler(menu)               # SS off -> enable=True sent
            handler(menu)               # still off + still disabled -> suppressed
            self.assertEqual(append_command.call_count, 1)
            # SS reconnects: no command needed, but the latch must clear on a fresh no-op.
            menu._snapshot = {
                "soundswitch": {"connected": True},
                "soundswitch_pack": {"available": True, "enabled": False},
            }
            handler(menu)
            self.assertIsNone(menu._pack_auto_pending_enabled)
            # Stale snapshot must NOT clear or spam (keeps the latch, sends nothing).
            menu._pack_auto_pending_enabled = True
            menu._snapshot = {"stale": True}
            handler(menu)
            self.assertTrue(menu._pack_auto_pending_enabled)
            self.assertEqual(append_command.call_count, 1)
            # SS disconnects again on a fresh snapshot: a real transition re-sends.
            menu._pack_auto_pending_enabled = None
            menu._snapshot = {
                "soundswitch": {"connected": False},
                "soundswitch_pack": {"available": True, "enabled": False},
            }
            handler(menu)
            self.assertEqual(append_command.call_count, 2)

    def test_auto_set_soundswitch_pack_retries_one_failed_auto_enable(self) -> None:
        # U2: SS can drop OS2L before releasing the FTDI port. One retry covers the
        # transient busy-port handoff without per-refresh command spam.
        bridge_menubar = self._import_module()
        menu = Mock(
            _snapshot={
                "soundswitch": {"connected": False},
                "soundswitch_pack": {"available": True, "enabled": False},
            },
            _status="on",
            _pack_auto_pending_enabled=None,
            _pack_auto_retried_enabled=None,
        )
        handler = bridge_menubar.BridgeMenuBar._auto_set_soundswitch_pack
        with patch.object(bridge_menubar, "append_command") as append_command:
            handler(menu)
            menu._snapshot = {
                "soundswitch": {"connected": False},
                "soundswitch_pack": {
                    "available": True,
                    "enabled": False,
                    "reason": "pack_start_failed",
                },
            }
            handler(menu)
            handler(menu)

        self.assertEqual(
            append_command.call_args_list,
            [
                unittest.mock.call(
                    {"cmd": "set_soundswitch_pack", "action": "enable", "enabled": True}
                ),
                unittest.mock.call(
                    {"cmd": "set_soundswitch_pack", "action": "enable", "enabled": True}
                ),
            ],
        )
        self.assertTrue(menu._pack_auto_pending_enabled)
        self.assertTrue(menu._pack_auto_retried_enabled)

    def test_pack_export_status_line_surfaces_failure_reason(self) -> None:
        bridge_menubar = self._import_module()
        common = dict(stale=False, export_phase="idle", export_state="idle",
                      export_up_to_date=False)
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "disabled", "reason": "pack_start_failed"}, **common),
            "Lighting: pack off · output didn't start (check Enttec)",
        )
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "disabled", "reason": "pack_load_failed"}, **common),
            "Lighting: pack off · pack unreadable — re-export",
        )
        # Benign SS-connected auto-off carries reason "disabled": no scary note.
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "disabled", "reason": "disabled"}, **common),
            "Lighting: pack off",
        )
        # A live export note still wins over the steady failure reason.
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "disabled", "reason": "pack_start_failed"},
                stale=False, export_phase="exporting", export_state="idle",
                export_up_to_date=False),
            "Lighting: pack off · exporting…",
        )

    def test_pack_export_status_line_ss_connected_is_benign_not_a_fault(self) -> None:
        # SoundSwitch holds the shared Enttec port while running, so a boot-time
        # pack_start_failed with SS CONNECTED is the expected handoff, not a fault.
        bridge_menubar = self._import_module()
        common = dict(stale=False, export_phase="idle", export_state="idle",
                      export_up_to_date=False)
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "disabled", "reason": "pack_start_failed"},
                soundswitch_connected=True, **common),
            "Lighting: pack off · SoundSwitch active",
        )
        # Same failure reason but SS DISCONNECTED = the bridge owned the port and
        # couldn't open it -> real "check Enttec".
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "disabled", "reason": "pack_start_failed"},
                soundswitch_connected=False, **common),
            "Lighting: pack off · output didn't start (check Enttec)",
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

    def test_parse_export_result_accepts_sidecar_failure(self) -> None:
        bridge_menubar = self._import_module()
        result = {
            "ok": False,
            "verdict": "sidecar_failed",
            "manifest_sha256": "",
            "artifact_count": 0,
            "first_export": False,
            "error_category": "BindingSidecarWriteError",
        }

        self.assertEqual(bridge_menubar.parse_export_result(json.dumps(result)), result)

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
            bridge_menubar.export_button_text(False, False), "Export",
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
            "disabled": "pack off",
            "blackout": "blackout",
            "input_degraded": "input degraded",
            "static_held": "holding static",
            "scripted_active": "scripted active",
            "rendering_active": "native autoloop",
            "empty_dark_look": "native dark",
            "base_suppressed": "native dark",
            "missing_binding": "autoloop missing binding",
            "missing_autoloop_file": "autoloop file missing",
            "unsupported_layout": "autoloop unsupported",
            "unverified_parity": "unverified parity",
            "soundswitch_present_native_suppressed": "SoundSwitch owns lights",
            "autoloop_phase_blocked": "autoloop blocked",
            "software_zero_frame": "zeroed",
            "bogus": "unknown",
        }
        for state, label in states.items():
            with self.subTest(state=state):
                # Steady "ready to export" adds no note: button already shows it.
                line = bridge_menubar.pack_export_status_line(
                    {"operational_state": state}, stale=False,
                    export_phase="idle", export_state="idle",
                    export_up_to_date=False,
                )
                self.assertEqual(line, f"Lighting: {label}")

        exports = (
            ("exporting", "idle", False, {}, "exporting…"),
            ("reloading", "idle", False, {}, "reloading…"),
            ("idle", "published_not_live", True, {}, "saved — enable pack to go live"),
            ("idle", "reload_succeeded", True, {}, "live now"),
            ("idle", "reload_failed", True, {}, "saved — reload unconfirmed"),
            ("idle", "export_failed", False, {"error_category": "TimeoutExpired"},
             "export failed (TimeoutExpired)"),
        )
        for phase, state, current, result, label in exports:
            with self.subTest(phase=phase, state=state):
                line = bridge_menubar.pack_export_status_line(
                    {"operational_state": "disabled"}, stale=False,
                    export_phase=phase, export_state=state,
                    export_up_to_date=current, export_result=result,
                )
                self.assertEqual(line, f"Lighting: pack off · {label}")

        # Steady up-to-date adds no note (button shows "Exported").
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "scripted_active"}, stale=False,
                export_phase="idle", export_state="idle",
                export_up_to_date=True,
            ),
            "Lighting: scripted active",
        )
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "scripted_active", "static_binding_gap": True},
                stale=False,
                export_phase="idle", export_state="idle",
                export_up_to_date=True,
            ),
            "Lighting: static binding gap",
        )

        # Bridge off wins over any stale snapshot content.
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "scripted_active"}, stale=True,
                export_phase="idle", export_state="reload_succeeded",
                export_up_to_date=True, bridge_status="off",
            ),
            "Lighting: bridge off",
        )
        self.assertEqual(
            bridge_menubar.pack_export_status_line(
                {"operational_state": "scripted_active"}, stale=True,
                export_phase="idle", export_state="reload_succeeded",
                export_up_to_date=True,
            ),
            "Lighting: no status yet",
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

            # The bridge git commit no longer affects the verdict: a matching
            # source fingerprint is up-to-date regardless of HEAD movement.
            with patch.object(bridge_menubar, "CANONICAL_SOURCE_PROJECT", str(source)), \
                 patch.object(bridge_menubar, "CANONICAL_PACK_DIR", pack), \
                 patch.object(bridge_menubar, "current_generator_commit", return_value="c" * 40):
                self.assertEqual(bridge_menubar.detect_export_state(), "up_to_date")

            # A sidecar with only the source fingerprint (no commit) is enough.
            sidecar.write_text(json.dumps({
                "source_fingerprint": bridge_menubar._source_content_fingerprint(source),
            }), encoding="utf-8")
            with patch.object(bridge_menubar, "CANONICAL_SOURCE_PROJECT", str(source)), \
                 patch.object(bridge_menubar, "CANONICAL_PACK_DIR", pack):
                self.assertEqual(bridge_menubar.detect_export_state(), "up_to_date")

    def test_detect_export_state_ignores_opaque_source_files(self) -> None:
        # SoundSwitch rewrites non-content files (backups, demo media, caches)
        # as a side effect of normal UI navigation (e.g. selecting PERFORM).
        # The decoder marks those `retained_opaque`; the exporter records them
        # in the sidecar `ignored_paths`. Detection must skip them so the button
        # does not falsely flip to EXPORT when nothing the bridge runs changed.
        bridge_menubar = self._import_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.ssproj"
            source.mkdir()
            content = source / "project.ssfile"
            content.write_bytes(b"real-lighting")
            backup = source / "SoundSwitchVenues.bin.backup"
            backup.write_bytes(b"backup-v1")
            pack = root / "pack"
            pack.mkdir()
            ignored = ["SoundSwitchVenues.bin.backup"]
            sidecar = bridge_menubar._sidecar_path(pack)
            sidecar.write_text(json.dumps({
                "source_fingerprint": bridge_menubar._source_content_fingerprint(
                    source, ignore=frozenset(ignored)),
                "ignored_paths": ignored,
            }), encoding="utf-8")

            with patch.object(bridge_menubar, "CANONICAL_SOURCE_PROJECT", str(source)), \
                 patch.object(bridge_menubar, "CANONICAL_PACK_DIR", pack):
                self.assertEqual(bridge_menubar.detect_export_state(), "up_to_date")
                # The reported bug: rewriting the opaque backup must NOT flip.
                backup.write_bytes(b"backup-v2-rewritten-by-perform")
                self.assertEqual(bridge_menubar.detect_export_state(), "up_to_date")
                # A real lighting edit MUST still flip to changes.
                content.write_bytes(b"edited-lighting")
                self.assertEqual(bridge_menubar.detect_export_state(), "changes")

    def test_detect_export_state_keeps_recordable_dat_visible(self) -> None:
        bridge_menubar = self._import_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.ssproj"
            source.mkdir()
            (source / "project.ssfile").write_bytes(b"real-lighting")
            backup = source / "SoundSwitchVenues.bin.backup"
            backup.write_bytes(b"backup-v1")
            recordable = source / "recordable" / "01bede4d8ea57b3b58574d71826dc1f5.dat"
            recordable.parent.mkdir()
            recordable.write_bytes(b"opaque-today")
            pack = root / "pack"
            pack.mkdir()
            ignored = [
                "SoundSwitchVenues.bin.backup",
                "recordable/01bede4d8ea57b3b58574d71826dc1f5.dat",
            ]
            sidecar = bridge_menubar._sidecar_path(pack)
            sidecar.write_text(json.dumps({
                "source_fingerprint": bridge_menubar._source_content_fingerprint(
                    source, ignore=frozenset(ignored)),
                "ignored_paths": ignored,
            }), encoding="utf-8")

            with patch.object(bridge_menubar, "CANONICAL_SOURCE_PROJECT", str(source)), \
                 patch.object(bridge_menubar, "CANONICAL_PACK_DIR", pack):
                # Old sidecars that ignored recordable/*.dat must fail open.
                self.assertEqual(bridge_menubar.detect_export_state(), "changes")

                sidecar.write_text(json.dumps({
                    "source_fingerprint": bridge_menubar._source_content_fingerprint(
                        source, ignore=frozenset({"SoundSwitchVenues.bin.backup"})),
                    "ignored_paths": ignored,
                }), encoding="utf-8")
                self.assertEqual(bridge_menubar.detect_export_state(), "up_to_date")
                backup.write_bytes(b"backup-v2-rewritten-by-perform")
                self.assertEqual(bridge_menubar.detect_export_state(), "up_to_date")
                recordable.write_bytes(b"learned-midi-or-control-state")
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


    def test_led_row_fields_truth_table(self) -> None:
        bridge_menubar = self._import_module()
        fields = bridge_menubar.led_row_fields

        # Empty snapshot → unknown, all-safe defaults.
        self.assertEqual(
            fields({}),
            {"state": "unknown", "fps": None, "effect": "", "palette": "",
             "degraded_reason": ""},
        )

        # Director present but disabled → off.
        self.assertEqual(
            fields({"led_look_director": {"enabled": False}})["state"], "off"
        )

        # Fully live: enabled + realtime active + fps + effect + palette.
        status = {
            "led_look_director": {
                "enabled": True,
                "adapter": {
                    "degraded": False,
                    "degraded_reason": "",
                    "realtime": {
                        "active": True,
                        "achieved_fps": 59.63,
                        "active_effect": "razer_pulse",
                    },
                },
            },
            "state_manager": {
                "led_color_engine": {"engine": "v2", "current_palette": "ember"}
            },
        }
        self.assertEqual(
            fields(status),
            {"state": "on", "fps": 59.63, "effect": "razer_pulse",
             "palette": "ember", "degraded_reason": ""},
        )

        # Degraded adapter surfaces the reason.
        degraded = {
            "led_look_director": {
                "enabled": True,
                "adapter": {"degraded": True, "degraded_reason": "circuit_open"},
            }
        }
        self.assertEqual(fields(degraded)["degraded_reason"], "circuit_open")
        # degraded False → reason suppressed even if the string is present.
        not_degraded = {
            "led_look_director": {
                "enabled": True,
                "adapter": {"degraded": False, "degraded_reason": "circuit_open"},
            }
        }
        self.assertEqual(fields(not_degraded)["degraded_reason"], "")

    def test_led_row_fields_malformed_never_raises(self) -> None:
        bridge_menubar = self._import_module()
        fields = bridge_menubar.led_row_fields

        # led_look_director not a dict → unknown + defaults.
        self.assertEqual(
            fields({"led_look_director": "x"}),
            {"state": "unknown", "fps": None, "effect": "", "palette": "",
             "degraded_reason": ""},
        )
        # adapter not a dict → state still resolves, adapter fields default.
        got = fields({"led_look_director": {"enabled": True, "adapter": "nope"}})
        self.assertEqual(
            got,
            {"state": "on", "fps": None, "effect": "", "palette": "",
             "degraded_reason": ""},
        )
        # fps a string / a bool → None (never a crash, never a lie).
        for bad_fps in ("59", True):
            got = fields({
                "led_look_director": {
                    "enabled": True,
                    "adapter": {
                        "realtime": {"active": True, "achieved_fps": bad_fps}
                    },
                }
            })
            self.assertIsNone(got["fps"])
        # realtime not a dict, degraded_reason not a string → defaults.
        got = fields({
            "led_look_director": {
                "enabled": True,
                "adapter": {"realtime": 7, "degraded": True, "degraded_reason": 3},
            }
        })
        self.assertEqual(got["fps"], None)
        self.assertEqual(got["degraded_reason"], "")

    def _flatten_blueprint(self, blueprint) -> list:
        entries = []
        for entry in blueprint:
            entries.append(entry)
            if entry[0] == "submenu":
                entries.extend(entry[4])
        return entries

    def test_menu_blueprint_selector_inventory_exact(self) -> None:
        # The regroup adds/removes NO commands: the selector multiset is the
        # pre-refactor 14 plus M2's purge plus the get-task-allow "Enable
        # Rekordbox Reads" action — each exactly once. The install offer is
        # deliberately NOT a blueprint entry: per the M2 spec it is
        # primary-positioned (insertItem_atIndex_ 0 after the walk), and its
        # source/gating is pinned by NativeInstallGateTests.
        bridge_menubar = self._import_module()
        flat = self._flatten_blueprint(bridge_menubar.MENU_BLUEPRINT)
        selectors = sorted(e[3] for e in flat if e[3])
        self.assertEqual(
            selectors,
            sorted([
                "toggleBridge:", "exportFromSS:", "toggleSmartDrop:",
                "toggleSmartBreakdown:", "toggleLaserDirector:",
                "laserBlackout:", "laserClearBlackout:", "runValidation:",
                "toggleRecordSession:", "testLights:", "mapLasers:",
                "openLedPad:", "toggleLedEngineV2:", "quit:",
                "purgeBridge:", "enableRekordboxReads:",
            ]),
        )
        self.assertNotIn("installOnMac:", selectors)

    def test_menu_blueprint_blackout_promoted_to_top_level(self) -> None:
        bridge_menubar = self._import_module()
        top_selectors = [
            e[3] for e in bridge_menubar.MENU_BLUEPRINT if e[0] == "action"
        ]
        self.assertIn("laserBlackout:", top_selectors)
        self.assertIn("laserClearBlackout:", top_selectors)
        laser_sub = next(
            e for e in bridge_menubar.MENU_BLUEPRINT
            if e[0] == "submenu" and e[1] == "laser_item"
        )
        sub_selectors = [s[3] for s in laser_sub[4] if s[3]]
        self.assertNotIn("laserBlackout:", sub_selectors)
        self.assertNotIn("laserClearBlackout:", sub_selectors)

    def test_menu_blueprint_maintenance_block_order(self) -> None:
        # Purge sits after the last separator and before quit; quit is last.
        # (Install is not a blueprint entry — see the selector-inventory test.)
        bridge_menubar = self._import_module()
        blueprint = bridge_menubar.MENU_BLUEPRINT
        self.assertEqual(blueprint[-1][1], "quit_item")
        attrs = [e[1] for e in blueprint]
        last_sep = max(i for i, e in enumerate(blueprint) if e[0] == "sep")
        purge_i = attrs.index("purge_item")
        quit_i = attrs.index("quit_item")
        self.assertLess(last_sep, purge_i)
        self.assertLess(purge_i, quit_i)

    def test_menu_blueprint_attrs_unique(self) -> None:
        bridge_menubar = self._import_module()
        flat = self._flatten_blueprint(bridge_menubar.MENU_BLUEPRINT)
        attrs = [e[1] for e in flat if e[1]]
        self.assertEqual(len(attrs), len(set(attrs)))

    def test_compact_status_lines_returns_ten_rows_both_branches(self) -> None:
        # Pins the zip contract in refresh_: a row-count mismatch silently
        # drops rows, so both branches must agree with the range(10) allocation.
        bridge_menubar = self._import_module()
        self.assertEqual(len(bridge_menubar.compact_status_lines({})), 10)
        self.assertEqual(
            len(bridge_menubar.compact_status_lines({"stale": True, "stale_age_s": 4})),
            10,
        )
        self.assertEqual(len(bridge_menubar.compact_status_lines({"schema": 1})), 10)

    def test_compact_status_lines_surfaces_rekordbox_reason(self) -> None:
        # P1: the make-or-break (reads blocked) shows on the BRIDGE row (still 10 rows).
        bridge_menubar = self._import_module()
        rows = bridge_menubar.compact_status_lines(
            {"schema": 1, "rekordbox": {"reason": "reads_blocked"}}, ["123"])
        self.assertEqual(len(rows), 10)
        self.assertIn("RB reads blocked", rows[0].string())
        # We do NOT warn on unsupported_version (ObjC reads are version-robust) or on a
        # transient attach_failed — those would false-alarm the maintainer.
        for benign in ("unsupported_version", "attach_failed", ""):
            rows = bridge_menubar.compact_status_lines(
                {"schema": 1, "rekordbox": {"reason": benign}}, ["123"])
            self.assertNotIn("⚠ RB", rows[0].string(), benign)


class FrozenDefectHelperTests(BridgeMenubarTests):
    """Pure seams added for the frozen-app defect fixes (DEFECT 2/4/5/6)."""

    def test_acquire_menubar_lock_blocks_second_holder(self) -> None:
        import fcntl
        import os as _os
        import tempfile as _tf
        bridge_menubar = self._import_module()
        lock_path = str(Path(_tf.gettempdir()) / "rbss_menubar_locktest.lock")
        holder = open(lock_path, "w")
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            # Another process holds it -> the guard refuses (frozen or source).
            self.assertFalse(bridge_menubar.acquire_menubar_lock(lock_path))
        finally:
            fcntl.flock(holder, fcntl.LOCK_UN)
            holder.close()
        # Released -> now acquirable; clean up the module-global fd we opened.
        self.assertTrue(bridge_menubar.acquire_menubar_lock(lock_path))
        if bridge_menubar._MENUBAR_LOCK_FD is not None:
            _os.close(bridge_menubar._MENUBAR_LOCK_FD)
            bridge_menubar._MENUBAR_LOCK_FD = None

    def test_export_button_enabled_rules(self) -> None:
        bridge_menubar = self._import_module()
        f = bridge_menubar.export_button_enabled
        self.assertTrue(f(False, False, False))   # source + real changes -> actionable
        self.assertFalse(f(True, False, False))   # export already running
        self.assertFalse(f(False, True, False))   # already up to date
        self.assertFalse(f(False, False, True))   # frozen guest -> never actionable

    def test_pad_argv_source_and_frozen(self) -> None:
        bridge_menubar = self._import_module()
        self.assertEqual(
            bridge_menubar.laser_pad_argv()[-1],
            str(bridge_menubar.REPO_ROOT / "scripts" / "laser_pad.py"),
        )
        self.assertEqual(
            bridge_menubar.led_pad_argv()[-1],
            str(bridge_menubar.REPO_ROOT / "scripts" / "led_pad.py"),
        )
        with patch.object(bridge_menubar.sys, "frozen", True, create=True):
            self.assertEqual(
                bridge_menubar.laser_pad_argv(),
                [bridge_menubar.sys.executable, "--run-laser-pad"],
            )
            self.assertEqual(
                bridge_menubar.led_pad_argv(),
                [bridge_menubar.sys.executable, "--run-led-pad"],
            )

    def test_running_bridge_pid_readopts_only_a_live_bridge(self) -> None:
        import os as _os
        import tempfile
        from unittest.mock import Mock
        bridge_menubar = self._import_module()
        with tempfile.TemporaryDirectory() as d:
            lock = str(Path(d) / "bridge.lock")
            # absent lockfile -> None (nothing to adopt)
            self.assertIsNone(bridge_menubar._running_bridge_pid(lock))
            # our own (live) pid, adopted ONLY when ps shows a bridge argv
            Path(lock).write_text(f"{_os.getpid()}\n", encoding="utf-8")
            with patch.object(bridge_menubar.subprocess, "run",
                              return_value=Mock(stdout="/x/rb_ss_bridge_v2 --run-bridge")):
                self.assertEqual(bridge_menubar._running_bridge_pid(lock), _os.getpid())
            # live pid but NOT a bridge command -> reject (never SIGTERM a foreign pid)
            with patch.object(bridge_menubar.subprocess, "run",
                              return_value=Mock(stdout="/usr/bin/some_other_app")):
                self.assertIsNone(bridge_menubar._running_bridge_pid(lock))
            # dead/unknown pid -> None (os.kill probe fails)
            Path(lock).write_text("999999\n", encoding="utf-8")
            self.assertIsNone(bridge_menubar._running_bridge_pid(lock))

    def test_format_child_failure_names_code_and_tail(self) -> None:
        bridge_menubar = self._import_module()
        msg = bridge_menubar._format_child_failure(
            "frozen_bridge_start", 3, "Traceback:\nImportError: boom",
        )
        self.assertIn("bridge couldn't start", msg.lower())
        self.assertIn("code 3", msg)
        self.assertIn("ImportError: boom", msg)
        # unknown label -> a generic-but-honest message, still with the code
        generic = bridge_menubar._format_child_failure("weird", 1, "")
        self.assertIn("helper process", generic.lower())
        self.assertIn("code 1", generic)


class NativeInstallGateTests(BridgeMenubarTests):
    """AWR-186 M2: the install offer must be frozen-gated so source-run menubars
    never import install_controller (source behavior byte-identical)."""

    def test_install_offer_is_frozen_gated_in_init(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        source = (scripts_dir / "bridge_menubar.py").read_text(encoding="utf-8")
        # The install block sits behind the same frozen gate the bridge toggle
        # uses, and install_controller is imported nowhere at module level.
        self.assertIn("Install on this Mac…", source)
        self.assertIn('if getattr(sys, "frozen", False):', source)
        for line in source.splitlines():
            stripped = line.lstrip()
            if stripped.startswith(("from ", "import ")) and "install_controller" in line:
                self.assertNotEqual(
                    line, stripped,
                    f"install_controller import must never be module-level: {line!r}",
                )

    def test_purge_item_frozen_gated_and_worker_marshals_failure(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        source = (scripts_dir / "bridge_menubar.py").read_text(encoding="utf-8")
        self.assertIn("Purge RBSS Bridge…", source)
        bridge_menubar = self._import_module()
        worker = Mock()
        handler = bridge_menubar.BridgeMenuBar._run_purge
        with patch(
            "rb_ss_bridge_v2.install_controller.perform_purge",
            side_effect=OSError("disk gone"),
        ), patch(
            "rb_ss_bridge_v2.install_controller.bundle_root",
            return_value=Path("/Users/x/Applications/RBSS Bridge.app"),
        ):
            handler(worker)
        args = worker.performSelectorOnMainThread_withObject_waitUntilDone_.call_args.args
        self.assertEqual(args[0], "finishPurge:")
        self.assertTrue(args[1]["failures"])

    def test_install_worker_marshals_failure_to_dialog(self) -> None:
        bridge_menubar = self._import_module()
        worker = Mock()
        with patch.object(
            bridge_menubar.BridgeMenuBar, "_run_install",
            bridge_menubar.BridgeMenuBar._run_install,
        ):
            handler = bridge_menubar.BridgeMenuBar._run_install
            with patch(
                "rb_ss_bridge_v2.install_controller.perform_install",
                side_effect=OSError("disk gone"),
            ), patch(
                "rb_ss_bridge_v2.install_controller.bundle_root",
                return_value=Path("/Volumes/RBSS Bridge/RBSS Bridge.app"),
            ):
                handler(worker)
        args = worker.performSelectorOnMainThread_withObject_waitUntilDone_.call_args.args
        self.assertEqual(args[0], "finishInstall:")
        self.assertFalse(args[1]["ok"])
        self.assertIn("OSError", args[1]["failed_step"])


if __name__ == "__main__":
    unittest.main()
