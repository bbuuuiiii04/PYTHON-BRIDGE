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
        bridge_menubar = self._import_module()
        flat = self._flatten_blueprint(bridge_menubar.MENU_BLUEPRINT)
        selectors = sorted(e[3] for e in flat if e[3])
        self.assertEqual(
            selectors,
            sorted([
                "toggleBridge:", "openLiveLog:", "laserBlackout:",
                "laserClearBlackout:", "mapLasers:", "openLedPad:",
                "enableRekordboxReads:", "exportFromSS:", "updateUsbBridge:",
                "purgeBridge:", "restartMenubar:",
            ]),
        )
        self.assertNotIn("installOnMac:", selectors)

    def test_menu_blueprint_source_and_frozen_inventory_exact(self) -> None:
        bridge_menubar = self._import_module()
        flat = self._flatten_blueprint(bridge_menubar.MENU_BLUEPRINT)

        def visible_selectors(*, frozen, purge):
            gates = bridge_menubar._menu_visibility(frozen=frozen, purge=purge)
            hidden_submenus = {
                e[1] for e in bridge_menubar.MENU_BLUEPRINT
                if e[0] == "submenu" and gates.get(e[1]) is False
            }
            hidden_children = {
                child[1]
                for entry in bridge_menubar.MENU_BLUEPRINT
                if entry[0] == "submenu" and entry[1] in hidden_submenus
                for child in entry[4]
            }
            return sorted(
                e[3] for e in flat
                if e[3] and gates.get(e[1], True) and e[1] not in hidden_children
            )

        common = sorted([
            "toggleBridge:", "openLiveLog:", "laserBlackout:",
            "laserClearBlackout:", "enableRekordboxReads:", "restartMenubar:",
        ])
        self.assertEqual(
            visible_selectors(frozen=False, purge=False),
            sorted(common + ["mapLasers:", "openLedPad:", "exportFromSS:", "updateUsbBridge:"]),
        )
        self.assertEqual(visible_selectors(frozen=True, purge=False), common)
        self.assertEqual(
            visible_selectors(frozen=True, purge=True),
            sorted(common + ["purgeBridge:"]),
        )

    def test_menu_blueprint_maintenance_block_order(self) -> None:
        bridge_menubar = self._import_module()
        blueprint = bridge_menubar.MENU_BLUEPRINT
        self.assertEqual(blueprint[-1][1], "restart_item")
        attrs = [e[1] for e in blueprint]
        # Exact maintenance block order (separator immediately before Export).
        expected_tail = [
            "maintenance_sep",
            "export_item",
            "update_usb_item",
            "patch_rekordbox_item",
            "purge_item",
            "restart_item",
        ]
        self.assertEqual(attrs[-len(expected_tail):], expected_tail)
        last_sep = max(i for i, e in enumerate(blueprint) if e[0] == "sep")
        export_i = attrs.index("export_item")
        rebuild_i = attrs.index("update_usb_item")
        patch_i = attrs.index("patch_rekordbox_item")
        purge_i = attrs.index("purge_item")
        restart_i = attrs.index("restart_item")
        self.assertEqual(last_sep, export_i - 1)
        self.assertLess(export_i, rebuild_i)
        self.assertLess(rebuild_i, patch_i)
        self.assertLess(patch_i, purge_i)
        self.assertLess(purge_i, restart_i)
        self.assertNotIn("quit_item", attrs)
        # Patch must stay below the maintenance separator (never drift above).
        self.assertLess(attrs.index("maintenance_sep"), patch_i)

    def test_menu_maintenance_sep_visible_in_source_and_frozen(self) -> None:
        bridge_menubar = self._import_module()
        for frozen, purge in ((False, False), (True, False), (True, True)):
            gates = bridge_menubar._menu_visibility(frozen=frozen, purge=purge)
            self.assertTrue(
                gates["maintenance_sep"],
                f"maintenance_sep must stay visible frozen={frozen} purge={purge}",
            )
            # Patch is never gated — always present.
            self.assertNotIn("patch_rekordbox_item", gates)
            self.assertEqual(gates["export_item"], not frozen)
            self.assertEqual(gates["update_usb_item"], not frozen)
            self.assertEqual(gates["purge_item"], frozen and purge)

    def test_menu_blueprint_has_only_essential_status_and_no_dead_controls(self) -> None:
        # Locked inventory: Status submenu holds exactly four disabled rows
        # (Bridge / Rekordbox / Lasers / LEDs). No top-level status_item, and
        # the removed everyday controls stay absent from MENU_BLUEPRINT.
        bridge_menubar = self._import_module()
        status = next(
            e for e in bridge_menubar.MENU_BLUEPRINT if e[1] == "status_submenu_item"
        )
        self.assertEqual(status[0], "submenu")
        self.assertEqual(status[2], "Status")
        self.assertEqual(status[4], (("status_rows", "status_rows", 4, None),))
        flat = self._flatten_blueprint(bridge_menubar.MENU_BLUEPRINT)
        attrs = [e[1] for e in flat if e[1]]
        self.assertNotIn("status_item", attrs)
        self.assertEqual(
            [e for e in flat if e[0] == "status_rows"],
            [("status_rows", "status_rows", 4, None)],
        )
        text = repr(bridge_menubar.MENU_BLUEPRINT)
        for forbidden in (
            "Smart Phrasing", "Laser Director", "LED Engine v2", "Rekordbox Target Patch",
            "Record Session", "Test the Lights", "Run Health Check", "Quit Menubar",
        ):
            self.assertNotIn(forbidden, text)

    def test_menu_blueprint_attrs_unique(self) -> None:
        bridge_menubar = self._import_module()
        flat = self._flatten_blueprint(bridge_menubar.MENU_BLUEPRINT)
        attrs = [e[1] for e in flat if e[1]]
        self.assertEqual(len(attrs), len(set(attrs)))

    def test_compact_status_lines_returns_four_rows_both_branches(self) -> None:
        bridge_menubar = self._import_module()
        self.assertEqual(len(bridge_menubar.compact_status_lines({})), 4)
        self.assertEqual(
            len(bridge_menubar.compact_status_lines({"stale": True, "stale_age_s": 4})),
            4,
        )
        self.assertEqual(len(bridge_menubar.compact_status_lines({"schema": 1})), 4)

    def test_compact_status_lines_surfaces_rekordbox_reason(self) -> None:
        bridge_menubar = self._import_module()
        rows = bridge_menubar.compact_status_lines(
            {"schema": 1, "rekordbox": {"reason": "reads_blocked"}}, ["123"])
        self.assertEqual(len(rows), 4)

    def test_compact_status_uses_process_truth_and_never_shows_deck_status(self) -> None:
        bridge_menubar = self._import_module()
        stale_live_snapshot = {
            "schema": 1,
            "state_manager": {"active_deck": 2},
            "rekordbox": {"reads_ok": True},
            "laser_director": {"available": True, "enabled": True},
            "led_look_director": {"enabled": True},
        }
        rows = bridge_menubar.compact_status_lines(
            stale_live_snapshot, ["123"], bridge_state="off"
        )
        text = "\n".join(row.string() for row in rows)
        self.assertIn("BRIDGE  Off", text)
        self.assertNotIn("D2", text)
        self.assertNotIn("Reading", text)
        self.assertNotIn("Lasers  On", text)

        live = bridge_menubar.compact_status_lines(
            stale_live_snapshot, ["123"], bridge_state="on"
        )
        live_text = "\n".join(row.string() for row in live)
        self.assertIn("BRIDGE  On", live_text)
        self.assertNotIn("D2", live_text)
        self.assertIn("Rekordbox", live[1].string())
        self.assertIn("Reading", live[1].string())


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

    def test_running_streamdeck_pid_accepts_only_the_locked_helper(self) -> None:
        import os as _os

        bridge_menubar = self._import_module()
        with tempfile.TemporaryDirectory() as d:
            lock = str(Path(d) / "streamdeck.lock")
            Path(lock).write_text(f"{_os.getpid()}\n", encoding="utf-8")
            with patch.object(
                bridge_menubar.subprocess,
                "run",
                return_value=Mock(stdout="/Applications/RBSS Bridge --run-streamdeck"),
            ):
                self.assertEqual(
                    bridge_menubar._running_streamdeck_pid(lock), _os.getpid()
                )
            with patch.object(
                bridge_menubar.subprocess,
                "run",
                return_value=Mock(stdout="/usr/bin/unrelated"),
            ):
                self.assertIsNone(bridge_menubar._running_streamdeck_pid(lock))

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

    def test_is_user_cancel_matches_admin_prompt_dismissal(self) -> None:
        bridge_menubar = self._import_module()
        self.assertTrue(
            bridge_menubar._is_user_cancel(
                "0:101: execution error: User canceled. (-128)"
            )
        )
        self.assertFalse(bridge_menubar._is_user_cancel("codesign: not permitted"))
        self.assertFalse(bridge_menubar._is_user_cancel(""))

    def test_spawn_watched_busy_sets_title_and_disables_at_spawn(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu.patch_rekordbox_item = Mock()
        menu.patch_rekordbox_item.title.return_value = "Patch Rekordbox"
        proc = Mock()
        with patch.object(bridge_menubar.subprocess, "Popen", return_value=proc), \
             patch.object(bridge_menubar, "_child_error_log_dir", return_value=Path("/tmp")), \
             patch.object(bridge_menubar.threading, "Thread") as thread_type, \
             patch("builtins.open", side_effect=OSError("no log")):
            bridge_menubar.BridgeMenuBar._spawn_watched(
                menu,
                ["x"],
                label="patch_rekordbox",
                busy_item_attr="patch_rekordbox_item",
                busy_title="Patching Rekordbox…",
            )
        menu.patch_rekordbox_item.setEnabled_.assert_called_once_with(False)
        menu.patch_rekordbox_item.setTitle_.assert_called_once_with(
            "Patching Rekordbox…"
        )
        self.assertNotEqual(
            thread_type.call_args.kwargs["target"],
            bridge_menubar.BridgeMenuBar._watch_child,
        )

    def test_spawn_watched_popen_failure_restores_busy_and_surfaces(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu.patch_rekordbox_item = Mock()
        menu.patch_rekordbox_item.title.return_value = "Patch Rekordbox"
        menu._patch_rb_in_progress = True
        menu._rb_reads_state = "not_enabled"
        menu.finishWatchedChild_ = lambda payload: (
            bridge_menubar.BridgeMenuBar.finishWatchedChild_.callable(menu, payload)
        )
        err_fh = Mock()
        alert = Mock()
        nsalert = Mock()
        nsalert.alloc.return_value.init.return_value = alert
        with patch.object(
            bridge_menubar.subprocess, "Popen",
            side_effect=OSError("spawn failed"),
        ), patch.object(
            bridge_menubar, "_child_error_log_dir", return_value=Path("/tmp"),
        ), patch("builtins.open", return_value=err_fh), patch.object(
            bridge_menubar, "NSAlert", nsalert,
        ):
            bridge_menubar.BridgeMenuBar._spawn_watched(
                menu,
                ["x"],
                label="patch_rekordbox",
                busy_item_attr="patch_rekordbox_item",
                busy_title="Patching Rekordbox…",
                failure_title="Rekordbox target patch failed",
            )
        err_fh.close.assert_called_once()
        self.assertFalse(menu._patch_rb_in_progress)
        menu.patch_rekordbox_item.setTitle_.assert_any_call("Patch Rekordbox")
        menu.patch_rekordbox_item.setEnabled_.assert_any_call(True)
        alert.setMessageText_.assert_called_once_with("Rekordbox target patch failed")
        info = alert.setInformativeText_.call_args.args[0]
        self.assertIn("spawn failed", info)

    def test_notify_uses_timeout_and_swallows_timeout_expired(self) -> None:
        bridge_menubar = self._import_module()
        with patch.object(
            bridge_menubar.subprocess, "run",
            side_effect=bridge_menubar.subprocess.TimeoutExpired("osascript", 5),
        ) as run:
            bridge_menubar._notify("hello")
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs.get("timeout"), 5)

    def test_finish_watched_child_success_notifies_and_restores_item(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu.patch_rekordbox_item = Mock()
        menu._patch_rb_in_progress = True
        menu._rb_reads_state = "not_enabled"
        with patch.object(bridge_menubar, "_notify") as notify:
            bridge_menubar.BridgeMenuBar.finishWatchedChild_.callable(menu, {
                "returncode": 0,
                "tail": "",
                "busy_item_attr": "patch_rekordbox_item",
                "saved_title": "Patch Rekordbox",
                "success_message": "Rekordbox reads step finished",
            })
        notify.assert_called_once_with("Rekordbox reads step finished")
        self.assertFalse(menu._patch_rb_in_progress)
        menu.patch_rekordbox_item.setTitle_.assert_any_call("Patch Rekordbox")
        menu.patch_rekordbox_item.setEnabled_.assert_any_call(True)

    def test_finish_watched_child_empty_stderr_failure_marshals_alert(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu.patch_rekordbox_item = Mock()
        menu._patch_rb_in_progress = True
        menu._rb_reads_state = "not_enabled"
        alert = Mock()
        nsalert = Mock()
        nsalert.alloc.return_value.init.return_value = alert
        with patch.object(bridge_menubar, "NSAlert", nsalert):
            bridge_menubar.BridgeMenuBar.finishWatchedChild_.callable(menu, {
                "returncode": 2,
                "tail": "",
                "busy_item_attr": "patch_rekordbox_item",
                "saved_title": "Patch Rekordbox",
                "failure_title": "Rekordbox target patch failed",
                "err_path": "/tmp/patch_rekordbox.err.log",
            })
        self.assertFalse(menu._patch_rb_in_progress)
        menu.patch_rekordbox_item.setEnabled_.assert_any_call(True)
        alert.setMessageText_.assert_called_once_with("Rekordbox target patch failed")
        info = alert.setInformativeText_.call_args.args[0]
        self.assertIn("code 2", info)
        self.assertIn("/tmp/patch_rekordbox.err.log", info)
        self.assertIn("If you cancelled the prompts", info)
        alert.runModal.assert_called_once_with()

    def test_finish_watched_child_user_cancel_restores_without_alert(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu.patch_rekordbox_item = Mock()
        menu._patch_rb_in_progress = True
        menu._rb_reads_state = "not_enabled"
        nsalert = Mock()
        with patch.object(bridge_menubar, "NSAlert", nsalert), \
             patch.object(bridge_menubar, "_notify") as notify:
            bridge_menubar.BridgeMenuBar.finishWatchedChild_.callable(menu, {
                "returncode": 1,
                "tail": "execution error: User canceled. (-128)",
                "busy_item_attr": "patch_rekordbox_item",
                "saved_title": "Patch Rekordbox",
                "failure_title": "Rekordbox target patch failed",
            })
        self.assertFalse(menu._patch_rb_in_progress)
        menu.patch_rekordbox_item.setTitle_.assert_any_call("Patch Rekordbox")
        menu.patch_rekordbox_item.setEnabled_.assert_any_call(True)
        nsalert.alloc.assert_not_called()
        notify.assert_not_called()

    def test_finish_watched_child_signal_death_restores_without_alert(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu.patch_rekordbox_item = Mock()
        menu._patch_rb_in_progress = True
        menu._rb_reads_state = "not_enabled"
        nsalert = Mock()
        with patch.object(bridge_menubar, "NSAlert", nsalert), \
             patch.object(bridge_menubar, "_notify") as notify:
            bridge_menubar.BridgeMenuBar.finishWatchedChild_.callable(menu, {
                "returncode": -15,
                "tail": "killed",
                "busy_item_attr": "patch_rekordbox_item",
                "saved_title": "Patch Rekordbox",
                "failure_title": "Rekordbox target patch failed",
            })
        self.assertFalse(menu._patch_rb_in_progress)
        menu.patch_rekordbox_item.setTitle_.assert_any_call("Patch Rekordbox")
        menu.patch_rekordbox_item.setEnabled_.assert_any_call(True)
        nsalert.alloc.assert_not_called()
        notify.assert_not_called()

    def test_watch_child_full_marshals_completion_payload(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        proc = Mock()
        proc.wait.return_value = 0
        with patch.object(
            bridge_menubar.BridgeMenuBar,
            "_read_child_stderr_tail",
            return_value="",
        ):
            bridge_menubar.BridgeMenuBar._watch_child_full(
                menu,
                proc,
                Path("/tmp/patch_rekordbox.err.log"),
                "patch_rekordbox",
                "patch_rekordbox_item",
                "Patch Rekordbox",
                "done",
                "Rekordbox target patch failed",
            )
        args = menu.performSelectorOnMainThread_withObject_waitUntilDone_.call_args.args
        self.assertEqual(args[0], "finishWatchedChild:")
        self.assertEqual(args[1]["returncode"], 0)
        self.assertEqual(args[1]["success_message"], "done")
        self.assertFalse(args[2])

    def test_finish_watched_child_exit0_with_verify_uses_alert_not_notify(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu.patch_rekordbox_item = Mock()
        menu._patch_rb_in_progress = True
        menu._rb_reads_state = "not_enabled"
        verify = {"verdict": "enabled", "detail": "/Applications/rekordbox 7/rekordbox.app"}
        with patch.object(bridge_menubar, "_notify") as notify, \
             patch.object(bridge_menubar, "_rb_reads_verdict") as verdict_fn:
            bridge_menubar.BridgeMenuBar.finishWatchedChild_.callable(menu, {
                "returncode": 0,
                "tail": "",
                "busy_item_attr": "patch_rekordbox_item",
                "saved_title": "Patch Rekordbox",
                "success_message": "unused",
                "err_path": "/tmp/patch_rekordbox.err.log",
                "verify": verify,
            })
        self.assertFalse(menu._patch_rb_in_progress)
        menu._show_rb_reads_verdict.assert_called_once_with(
            verify, "/tmp/patch_rekordbox.err.log"
        )
        notify.assert_not_called()
        # The main-thread completion never re-runs codesign: the payload verdict
        # (computed on the watcher thread) is the only source.
        verdict_fn.assert_not_called()
        # Verify path defers render to _show_rb_reads_verdict / finishRbReadsCheck_
        # so exit 0 alone never paints "Rekordbox Patched".
        menu._render_patch_rb_state.assert_not_called()

    def test_show_rb_reads_verdict_enabled_says_target_only(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        alert = Mock()
        nsalert = Mock()
        nsalert.alloc.return_value.init.return_value = alert
        with patch.object(bridge_menubar, "NSAlert", nsalert):
            bridge_menubar.BridgeMenuBar._show_rb_reads_verdict(
                menu,
                {"verdict": "enabled", "detail": "/Applications/rekordbox 7/rekordbox.app"},
                "",
            )
        # Exit 0 may mean already-present; enabled dialog must verify, not claim install.
        alert.setMessageText_.assert_called_once_with("Rekordbox target patch verified")
        body = alert.setInformativeText_.call_args.args[0]
        self.assertIn("entitlement is present", body)
        self.assertNotIn("installed", alert.setMessageText_.call_args.args[0].lower())
        self.assertNotIn("installed", body.lower())
        self.assertIn("/Applications/rekordbox 7/rekordbox.app", body)
        self.assertIn("target patch only", body.lower())
        self.assertIn("live-unvalidated", body.lower())
        self.assertIn("RB reads blocked", body)
        alert.runModal.assert_called_once_with()
        # Positive entitlement verification still drives disabled "Rekordbox Patched".
        menu.finishRbReadsCheck_.assert_called_once_with("enabled")

    def test_show_rb_reads_verdict_absent_says_did_not_take_effect(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        alert = Mock()
        nsalert = Mock()
        nsalert.alloc.return_value.init.return_value = alert
        with patch.object(bridge_menubar, "NSAlert", nsalert):
            bridge_menubar.BridgeMenuBar._show_rb_reads_verdict(
                menu,
                {"verdict": "not_enabled", "detail": "/Applications/rekordbox 7/rekordbox.app"},
                "/tmp/patch_rekordbox.err.log",
            )
        body = alert.setInformativeText_.call_args.args[0]
        self.assertIn("did not take effect", body)
        self.assertIn("/tmp/patch_rekordbox.err.log", body)
        alert.runModal.assert_called_once_with()
        menu.finishRbReadsCheck_.assert_called_once_with("not_enabled")

    def test_show_rb_reads_verdict_error_says_could_not_verify(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        alert = Mock()
        nsalert = Mock()
        nsalert.alloc.return_value.init.return_value = alert
        with patch.object(bridge_menubar, "NSAlert", nsalert):
            bridge_menubar.BridgeMenuBar._show_rb_reads_verdict(
                menu,
                {"verdict": "unknown", "detail": "Rekordbox app not found in /Applications"},
                "",
            )
        body = alert.setInformativeText_.call_args.args[0]
        self.assertIn("could not be verified", body)
        self.assertIn("not found", body)
        alert.runModal.assert_called_once_with()
        menu.finishRbReadsCheck_.assert_called_once_with("unknown")

    def test_watch_child_full_verifies_on_watcher_thread(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        proc = Mock()
        proc.wait.return_value = 0
        with patch.object(
            bridge_menubar.BridgeMenuBar, "_read_child_stderr_tail", return_value="",
        ), patch.object(
            bridge_menubar, "_rb_reads_verdict",
            return_value=("enabled", "/Applications/rekordbox 7/rekordbox.app"),
        ) as verdict_fn:
            bridge_menubar.BridgeMenuBar._watch_child_full(
                menu,
                proc,
                None,
                "patch_rekordbox",
                "patch_rekordbox_item",
                "Patch Rekordbox",
                None,
                "Rekordbox target patch failed",
                True,
            )
        verdict_fn.assert_called_once_with()
        args = menu.performSelectorOnMainThread_withObject_waitUntilDone_.call_args.args
        self.assertEqual(args[1]["verify"], {
            "verdict": "enabled",
            "detail": "/Applications/rekordbox 7/rekordbox.app",
        })

    def test_watch_child_full_skips_verification_on_nonzero_exit(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        proc = Mock()
        proc.wait.return_value = 1
        with patch.object(
            bridge_menubar.BridgeMenuBar, "_read_child_stderr_tail", return_value="",
        ), patch.object(bridge_menubar, "_rb_reads_verdict") as verdict_fn:
            bridge_menubar.BridgeMenuBar._watch_child_full(
                menu, proc, None, "patch_rekordbox", "patch_rekordbox_item",
                "Patch Rekordbox", None, "failed", True,
            )
        verdict_fn.assert_not_called()
        args = menu.performSelectorOnMainThread_withObject_waitUntilDone_.call_args.args
        self.assertNotIn("verify", args[1])

    def test_rb_reads_status_title_truth_table(self) -> None:
        bridge_menubar = self._import_module()
        self.assertEqual(
            bridge_menubar.rb_reads_status_title("enabled"),
            "Rekordbox target patch: present",
        )
        self.assertEqual(
            bridge_menubar.rb_reads_status_title("not_enabled"),
            "Rekordbox target patch: not present",
        )
        for state in ("unknown", "", "bogus"):
            self.assertEqual(
                bridge_menubar.rb_reads_status_title(state),
                "Rekordbox target patch: unknown",
            )

    def test_maybe_check_rb_reads_uses_cache_and_background_thread(self) -> None:
        bridge_menubar = self._import_module()
        handler = bridge_menubar.BridgeMenuBar._maybe_check_rb_reads
        # Fresh cache: menu refresh renders the cached row, no thread spawned.
        menu = Mock(
            _rb_reads_in_progress=False,
            _rb_reads_at=bridge_menubar.time.monotonic(),
        )
        with patch.object(bridge_menubar.threading, "Thread") as thread:
            handler(menu)
        thread.assert_not_called()
        # Stale cache: a daemon thread refreshes it off the main thread.
        menu._rb_reads_at = 0.0
        with patch.object(bridge_menubar.threading, "Thread") as thread:
            handler(menu)
        thread.assert_called_once_with(target=menu._run_rb_reads_check, daemon=True)
        thread.return_value.start.assert_called_once_with()
        self.assertTrue(menu._rb_reads_in_progress)
        # Check already running: never stack a second one.
        with patch.object(bridge_menubar.threading, "Thread") as thread:
            handler(menu)
        thread.assert_not_called()

    def test_finish_rb_reads_check_updates_patch_action(self) -> None:
        bridge_menubar = self._import_module()
        handler = bridge_menubar.BridgeMenuBar.finishRbReadsCheck_.callable
        menu = Mock(patch_rekordbox_item=Mock(), rb_reads_status_item=None)
        menu._patch_rb_in_progress = False
        menu._render_patch_rb_state = (
            lambda: bridge_menubar.BridgeMenuBar._render_patch_rb_state(menu)
        )
        handler(menu, "enabled")
        self.assertEqual(menu._rb_reads_state, "enabled")
        self.assertFalse(menu._rb_reads_in_progress)
        menu.patch_rekordbox_item.setTitle_.assert_called_with("Rekordbox Patched")
        menu.patch_rekordbox_item.setEnabled_.assert_called_with(False)
        handler(menu, "not_enabled")
        menu.patch_rekordbox_item.setTitle_.assert_called_with("Patch Rekordbox")
        menu.patch_rekordbox_item.setEnabled_.assert_called_with(True)
        handler(menu, "unknown")
        menu.patch_rekordbox_item.setTitle_.assert_called_with("Patch Rekordbox")
        menu.patch_rekordbox_item.setEnabled_.assert_called_with(True)

    def test_run_rb_reads_check_marshals_verdict_to_main_thread(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        with patch.object(
            bridge_menubar, "_rb_reads_verdict", return_value=("not_enabled", "/app"),
        ):
            bridge_menubar.BridgeMenuBar._run_rb_reads_check(menu)
        menu.performSelectorOnMainThread_withObject_waitUntilDone_.assert_called_once_with(
            "finishRbReadsCheck:", "not_enabled", False,
        )

    def test_rb_reads_verdict_truth_table(self) -> None:
        bridge_menubar = self._import_module()
        patch_mod = Mock()
        # App missing -> unknown.
        patch_mod.find_rekordbox.return_value = None
        with patch.object(bridge_menubar, "_import_rekordbox_patch", return_value=patch_mod):
            self.assertEqual(bridge_menubar._rb_reads_verdict()[0], "unknown")
        # Valid target patch present / absent.
        patch_mod.find_rekordbox.return_value = Path("/Applications/rekordbox 7/rekordbox.app")
        patch_mod.has_valid_target_patch.return_value = True
        with patch.object(bridge_menubar, "_import_rekordbox_patch", return_value=patch_mod):
            self.assertEqual(
                bridge_menubar._rb_reads_verdict(),
                ("enabled", "/Applications/rekordbox 7/rekordbox.app"),
            )
        patch_mod.has_valid_target_patch.return_value = False
        with patch.object(bridge_menubar, "_import_rekordbox_patch", return_value=patch_mod):
            self.assertEqual(bridge_menubar._rb_reads_verdict()[0], "not_enabled")
        # Check itself blowing up -> unknown with the reason, never a raise.
        patch_mod.has_valid_target_patch.side_effect = OSError("codesign missing")
        with patch.object(bridge_menubar, "_import_rekordbox_patch", return_value=patch_mod):
            verdict, detail = bridge_menubar._rb_reads_verdict()
        self.assertEqual(verdict, "unknown")
        self.assertIn("codesign missing", detail)

    def test_menu_blueprint_restores_patch_action_without_status_row(self) -> None:
        # User override of the 39a2ffa slim-menu cut: the Patch Rekordbox action
        # is back in both editions; the old standing status row stays gone.
        bridge_menubar = self._import_module()
        flat = self._flatten_blueprint(bridge_menubar.MENU_BLUEPRINT)
        attrs = {e[1] for e in flat}
        self.assertIn("patch_rekordbox_item", attrs)
        self.assertNotIn("rb_reads_status_item", attrs)
        self.assertNotIn("enable_rb_reads_item", attrs)
        patch = next(e for e in flat if e[1] == "patch_rekordbox_item")
        self.assertEqual(patch[0], "action")
        self.assertEqual(patch[2], "Patch Rekordbox")
        self.assertEqual(patch[3], "enableRekordboxReads:")
        self.assertNotIn("Enable Rekordbox Reads", repr(bridge_menubar.MENU_BLUEPRINT))
        # Placement: inside the maintenance block after Export/Rebuild.
        top_attrs = [e[1] for e in bridge_menubar.MENU_BLUEPRINT]
        sep_i = top_attrs.index("maintenance_sep")
        self.assertEqual(
            top_attrs[sep_i:sep_i + 4],
            [
                "maintenance_sep",
                "export_item",
                "update_usb_item",
                "patch_rekordbox_item",
            ],
        )

    def test_patch_rb_button_text_and_enabled_table(self) -> None:
        bridge_menubar = self._import_module()
        text = bridge_menubar.patch_rb_button_text
        enabled = bridge_menubar.patch_rb_button_enabled
        for state in ("enabled", "not_enabled", "unknown", "", "garbage"):
            self.assertEqual(text(True, state), "Patching Rekordbox…")
            self.assertFalse(enabled(True, state))
        self.assertEqual(text(False, "enabled"), "Rekordbox Patched")
        self.assertFalse(enabled(False, "enabled"))
        for state in ("not_enabled", "unknown", "", "garbage"):
            self.assertEqual(text(False, state), "Patch Rekordbox")
            self.assertTrue(enabled(False, state))

    def test_render_patch_rb_keeps_busy_over_cached_enabled(self) -> None:
        # Periodic refresh / entitlement completion must not overwrite the busy
        # title while the patch child is still running.
        bridge_menubar = self._import_module()
        menu = Mock()
        menu.patch_rekordbox_item = Mock()
        menu._patch_rb_in_progress = True
        menu._rb_reads_state = "enabled"
        bridge_menubar.BridgeMenuBar._render_patch_rb_state(menu)
        menu.patch_rekordbox_item.setTitle_.assert_called_once_with(
            "Patching Rekordbox…"
        )
        menu.patch_rekordbox_item.setEnabled_.assert_called_once_with(False)

    def test_enable_rekordbox_reads_dispatches_source_and_frozen_argv(self) -> None:
        bridge_menubar = self._import_module()
        for frozen in (False, True):
            menu = Mock()
            menu._patch_rb_in_progress = False
            menu._rb_reads_state = "unknown"
            menu.patch_rekordbox_item = Mock()
            menu._render_patch_rb_state = (
                lambda m=menu: bridge_menubar.BridgeMenuBar._render_patch_rb_state(m)
            )
            with patch.object(bridge_menubar.sys, "frozen", frozen, create=True), \
                 patch.object(bridge_menubar.sys, "executable", "/fake/RBSS"):
                if frozen:
                    expected_argv = ["/fake/RBSS", "--patch-rekordbox"]
                else:
                    expected_argv = [
                        "/fake/RBSS",
                        str(bridge_menubar.REPO_ROOT / "usb_launcher.py"),
                        "--patch-rekordbox",
                    ]
                bridge_menubar.BridgeMenuBar.enableRekordboxReads_.callable(
                    menu, None
                )
            self.assertTrue(menu._patch_rb_in_progress)
            menu.patch_rekordbox_item.setTitle_.assert_called_with(
                "Patching Rekordbox…"
            )
            menu._spawn_watched.assert_called_once()
            self.assertEqual(menu._spawn_watched.call_args.args[0], expected_argv)
            kwargs = menu._spawn_watched.call_args.kwargs
            self.assertEqual(kwargs["busy_item_attr"], "patch_rekordbox_item")
            self.assertEqual(kwargs["busy_title"], "Patching Rekordbox…")
            self.assertTrue(kwargs["verify_rb_reads"])
            self.assertEqual(kwargs["label"], "patch_rekordbox")

    def test_enable_rekordbox_reads_ignores_duplicate_click(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu._patch_rb_in_progress = True
        bridge_menubar.BridgeMenuBar.enableRekordboxReads_.callable(menu, None)
        menu._spawn_watched.assert_not_called()

    def test_patch_rb_completion_resets_flag_on_every_path(self) -> None:
        bridge_menubar = self._import_module()
        for returncode, verify, expect_patched in (
            (0, {"verdict": "enabled", "detail": "/app"}, True),
            (0, {"verdict": "not_enabled", "detail": "/app"}, False),
            (1, None, False),
            (-15, None, False),
        ):
            menu = Mock()
            menu.patch_rekordbox_item = Mock()
            menu._patch_rb_in_progress = True
            menu._rb_reads_state = "unknown"
            menu.rb_reads_status_item = None
            menu._render_patch_rb_state = (
                lambda m=menu: bridge_menubar.BridgeMenuBar._render_patch_rb_state(m)
            )
            menu.finishRbReadsCheck_ = (
                lambda verdict, m=menu: bridge_menubar.BridgeMenuBar.finishRbReadsCheck_.callable(
                    m, verdict
                )
            )
            menu._show_rb_reads_verdict = (
                lambda v, err, m=menu: bridge_menubar.BridgeMenuBar._show_rb_reads_verdict(
                    m, v, err
                )
            )
            payload = {
                "busy_item_attr": "patch_rekordbox_item",
                "saved_title": "Patch Rekordbox",
                "returncode": returncode,
                "tail": "boom" if returncode and returncode > 0 else "",
                "err_path": "",
                "success_message": None,
                "failure_title": "Rekordbox target patch failed",
            }
            if verify is not None:
                payload["verify"] = verify
            alert = Mock()
            nsalert = Mock()
            nsalert.alloc.return_value.init.return_value = alert
            with patch.object(bridge_menubar, "NSAlert", nsalert), \
                 patch.object(bridge_menubar, "_notify"):
                bridge_menubar.BridgeMenuBar.finishWatchedChild_.callable(menu, payload)
            self.assertFalse(menu._patch_rb_in_progress)
            if expect_patched:
                self.assertEqual(menu._rb_reads_state, "enabled")
                menu.patch_rekordbox_item.setTitle_.assert_any_call("Rekordbox Patched")
                menu.patch_rekordbox_item.setEnabled_.assert_any_call(False)
            elif returncode == 0 and verify is not None:
                self.assertEqual(menu._rb_reads_state, "not_enabled")
                menu.patch_rekordbox_item.setTitle_.assert_any_call("Patch Rekordbox")
                menu.patch_rekordbox_item.setEnabled_.assert_any_call(True)

    def test_watch_child_full_exception_still_marshals_failure(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        proc = Mock()
        proc.wait.side_effect = RuntimeError("wait blew up")
        bridge_menubar.BridgeMenuBar._watch_child_full(
            menu,
            proc,
            None,
            "patch_rekordbox",
            "patch_rekordbox_item",
            "Patch Rekordbox",
            "done",
            "Rekordbox target patch failed",
        )
        args = menu.performSelectorOnMainThread_withObject_waitUntilDone_.call_args.args
        self.assertEqual(args[0], "finishWatchedChild:")
        self.assertEqual(args[1]["returncode"], 1)
        self.assertIn("wait blew up", args[1]["tail"])

    def test_spawn_watched_without_busy_keeps_early_window_watcher(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        proc = Mock()
        with patch.object(bridge_menubar.subprocess, "Popen", return_value=proc), \
             patch.object(bridge_menubar, "_child_error_log_dir", return_value=Path("/tmp")), \
             patch.object(bridge_menubar.threading, "Thread") as thread_type, \
             patch("builtins.open", side_effect=OSError("no log")):
            bridge_menubar.BridgeMenuBar._spawn_watched(
                menu, ["x"], label="frozen_bridge_start", early_window=4.0,
            )
        kwargs = thread_type.call_args.kwargs
        self.assertEqual(kwargs["args"][3], 4.0)
        self.assertNotEqual(
            kwargs["target"], bridge_menubar.BridgeMenuBar._watch_child_full,
        )

    def test_watch_child_early_crash_marshals_failure_dialog(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu._read_child_stderr_tail = Mock(return_value="ImportError: boom")
        proc = Mock()
        proc.wait.return_value = 3
        bridge_menubar.BridgeMenuBar._watch_child(
            menu, proc, Path("/tmp/frozen_bridge_start.err.log"),
            "frozen_bridge_start", 4.0,
        )
        args = menu.performSelectorOnMainThread_withObject_waitUntilDone_.call_args.args
        self.assertEqual(args[0], "showChildFailure:")
        self.assertIn("code 3", args[1])
        self.assertIn("ImportError: boom", args[1])

    def test_watch_child_survives_early_window_without_alert(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        proc = Mock()
        proc.wait.side_effect = bridge_menubar.subprocess.TimeoutExpired("cmd", 4.0)
        bridge_menubar.BridgeMenuBar._watch_child(
            menu, proc, None, "frozen_bridge_start", 4.0,
        )
        menu.performSelectorOnMainThread_withObject_waitUntilDone_.assert_not_called()

    def test_restart_argv_is_delayed_for_source_and_frozen(self) -> None:
        bridge_menubar = self._import_module()
        source = bridge_menubar.restart_menubar_argv()
        self.assertEqual(source[:2], ["/bin/sh", "-c"])
        self.assertIn("sleep 1", source[2])
        self.assertIn(bridge_menubar.sys.executable, source[2])
        self.assertIn("bridge_menubar.py", source[2])
        with patch.object(bridge_menubar.sys, "frozen", True, create=True), \
             patch.object(
                 bridge_menubar.sys, "executable",
                 "/Volumes/RBSS/RBSS Bridge.app/Contents/MacOS/RBSS Bridge",
             ):
            frozen = bridge_menubar.restart_menubar_argv()
        self.assertIn("sleep 1", frozen[2])
        self.assertIn("open -n", frozen[2])
        self.assertIn("RBSS Bridge.app", frozen[2])

    def test_restart_spawns_replacement_without_touching_bridge(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        app = Mock()
        nsapplication = Mock()
        nsapplication.sharedApplication.return_value = app
        with patch.object(bridge_menubar, "restart_menubar_argv", return_value=["sh", "-c", "sleep 1; x"]), \
             patch.object(bridge_menubar.subprocess, "Popen") as popen, \
             patch.object(bridge_menubar, "NSApplication", nsapplication), \
             patch.object(bridge_menubar, "_system_env", return_value={}), \
             patch.object(bridge_menubar, "bridge_status", side_effect=AssertionError("bridge touched")), \
             patch.object(bridge_menubar, "stop_manual_launchctl_job", side_effect=AssertionError("bridge stopped")):
            bridge_menubar.BridgeMenuBar.restartMenubar_.callable(menu, None)
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], ["sh", "-c", "sleep 1; x"])
        app.terminate_.assert_called_once_with(menu)


class NativeInstallGateTests(BridgeMenubarTests):
    """AWR-186 M2: the install offer must be frozen-gated so source-run menubars
    never import install_controller (source behavior byte-identical)."""

    def test_install_offer_is_frozen_gated_in_init(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        source = (scripts_dir / "bridge_menubar.py").read_text(encoding="utf-8")
        # The install block sits behind the same frozen gate the bridge toggle
        # uses, and install_controller is imported nowhere at module level.
        self.assertIn("Install on This Mac…", source)
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

    def test_adopted_or_owned_bridge_blocks_install_and_purge(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu._frozen_bridge_proc = None
        menu._frozen_streamdeck_proc = None
        with patch.object(bridge_menubar, "bridge_status", return_value="off"), \
             patch.object(bridge_menubar, "_running_bridge_pid", return_value=91), \
             patch.object(bridge_menubar, "_running_streamdeck_pid", return_value=None):
            self.assertFalse(bridge_menubar.BridgeMenuBar._bridge_fully_off(menu))
        proc = Mock()
        proc.poll.return_value = None
        menu._frozen_bridge_proc = proc
        with patch.object(bridge_menubar, "bridge_status", return_value="off"), \
             patch.object(bridge_menubar, "_running_bridge_pid", return_value=None), \
             patch.object(bridge_menubar, "_running_streamdeck_pid", return_value=None):
            self.assertFalse(bridge_menubar.BridgeMenuBar._bridge_fully_off(menu))

        proc.poll.return_value = 0
        menu._frozen_bridge_proc = None
        with patch.object(bridge_menubar, "bridge_status", return_value="off"), \
             patch.object(bridge_menubar, "_running_bridge_pid", return_value=None), \
             patch.object(bridge_menubar, "_running_streamdeck_pid", return_value=92):
            self.assertFalse(bridge_menubar.BridgeMenuBar._bridge_fully_off(menu))

        menu = Mock(_install_in_progress=False, _purge_in_progress=False)
        menu._require_bridge_off.return_value = False
        bridge_menubar.BridgeMenuBar.installOnMac_.callable(menu, None)
        bridge_menubar.BridgeMenuBar.purgeBridge_.callable(menu, None)
        menu._require_bridge_off.assert_any_call("installing or updating this Mac")
        menu._require_bridge_off.assert_any_call("purging this Mac")
        menu.install_item.setTitle_.assert_not_called()
        menu.purge_item.setTitle_.assert_not_called()

    def test_dmg_install_required_disables_bridge_start(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock(_install_required=True)
        with patch.object(bridge_menubar.sys, "frozen", True, create=True):
            bridge_menubar.BridgeMenuBar.toggleBridge_.callable(menu, None)
        menu._toggle_bridge_frozen.assert_not_called()

        menu = Mock(toggle_item=Mock(), _install_required=True)
        menu._snapshot = {}
        menu._status = None
        menu.status_rows = []
        menu._render_export_state = Mock()
        menu._auto_set_soundswitch_pack = Mock()
        menu._maybe_detect_export_state = Mock()
        menu.laser_blackout_item = Mock()
        menu.laser_clear_blackout_item = Mock()
        menu._adapt_timer = Mock()
        with patch.object(bridge_menubar, "read_status", return_value={}), \
             patch.object(bridge_menubar, "bridge_pids", return_value=[]), \
             patch.object(bridge_menubar, "watcher_running", return_value=False), \
             patch.object(bridge_menubar.sys, "frozen", True, create=True), \
             patch.object(bridge_menubar, "_running_bridge_pid", return_value=None):
            bridge_menubar.BridgeMenuBar.refresh_.callable(menu, None)
        menu.toggle_item.setTitle_.assert_called_with("Install or Update This Mac first")
        menu.toggle_item.setEnabled_.assert_called_with(False)

    def test_failed_install_restores_retry_title(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        alert = Mock()
        nsalert = Mock()
        nsalert.alloc.return_value.init.return_value = alert
        with patch.object(bridge_menubar, "NSAlert", nsalert), \
             patch("rb_ss_bridge_v2.install_controller.install_action_title",
                   return_value="Retry Installation…") as title:
            bridge_menubar.BridgeMenuBar.finishInstall_.callable(
                menu, {"ok": False, "failed_step": "create target folders (PermissionError)"}
            )
        title.assert_called_once()
        menu.install_item.setTitle_.assert_called_once_with("Retry Installation…")
        menu.install_item.setEnabled_.assert_called_once_with(True)
        text = alert.setInformativeText_.call_args.args[0]
        self.assertNotIn("PermissionError", text)
        self.assertNotIn("Failed step:", text)
        self.assertIn("What to do:", text)

class PortableLogAndUsbUpdateTests(BridgeMenubarTests):
    def test_log_argv_source_and_frozen_never_needs_host_python(self) -> None:
        bridge_menubar = self._import_module()
        source = bridge_menubar.log_viewer_argv()
        self.assertEqual(source[0], bridge_menubar.sys.executable)
        self.assertTrue(source[1].endswith("/bridge_view.py"))
        with patch.object(bridge_menubar.sys, "frozen", True, create=True):
            self.assertEqual(
                bridge_menubar.log_viewer_argv(),
                [bridge_menubar.sys.executable, "--run-log-viewer"],
            )

    def test_log_terminal_marker_title_and_one_viewer_guard(self) -> None:
        bridge_menubar = self._import_module()
        command = bridge_menubar.log_viewer_terminal_command(["/app", "--run-log-viewer"])
        self.assertIn("RBSS_BRIDGE_MONITOR", command)
        self.assertIn("--run-log-viewer", command)
        with patch.object(
            bridge_menubar.subprocess, "run", return_value=Mock(returncode=0)
        ) as run:
            self.assertTrue(
                bridge_menubar.open_terminal_command(command, "RBSS_BRIDGE_MONITOR")
            )
        apple_script = run.call_args.args[0][-1]
        self.assertIn('custom title of selected tab', apple_script)
        self.assertIn('RBSS_BRIDGE_MONITOR', apple_script)
        with patch.object(bridge_menubar, "monitor_open", return_value=True), \
             patch.object(bridge_menubar, "open_terminal_command") as terminal:
            self.assertTrue(bridge_menubar.open_live_log())
        terminal.assert_not_called()
        with patch.object(bridge_menubar, "monitor_open", return_value=False), \
             patch.object(bridge_menubar, "open_terminal_command", return_value=True) as terminal, \
             patch.object(bridge_menubar, "bridge_status", side_effect=AssertionError("bridge touched")):
            self.assertTrue(bridge_menubar.open_live_log())
        terminal.assert_called_once()
        self.assertEqual(terminal.call_args.args[1], "RBSS_BRIDGE_MONITOR")

        with patch.object(bridge_menubar, "monitor_open", return_value=False), \
             patch.object(bridge_menubar, "open_terminal_command", return_value=False):
            self.assertFalse(bridge_menubar.open_live_log())

    def test_open_live_log_failure_is_visible_and_does_not_touch_bridge(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        with patch.object(bridge_menubar, "open_live_log", return_value=False):
            bridge_menubar.BridgeMenuBar.openLiveLog_.callable(menu, None)
        menu.showLiveLogFailure_.assert_called_once_with(None)

        alert = Mock()
        nsalert = Mock()
        nsalert.alloc.return_value.init.return_value = alert
        with patch.object(bridge_menubar, "NSAlert", nsalert):
            bridge_menubar.BridgeMenuBar.showLiveLogFailure_.callable(menu, None)
        body = alert.setInformativeText_.call_args.args[0]
        self.assertIn("Privacy & Security", body)
        self.assertIn("Automation", body)
        self.assertIn("keeps running", body)

    def test_frozen_bridge_start_opens_log(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu._stop_frozen_bridge_child.return_value = False
        proc = Mock()
        menu._spawn_watched.return_value = proc
        with patch.object(bridge_menubar, "_running_bridge_pid", return_value=None), \
             patch.object(bridge_menubar, "open_live_log") as open_log:
            bridge_menubar.BridgeMenuBar._toggle_bridge_frozen(menu)
        self.assertIs(menu._frozen_bridge_proc, proc)
        menu._ensure_frozen_streamdeck.assert_called_once_with()
        open_log.assert_called_once_with()

    def test_frozen_streamdeck_supervisor_reuses_or_starts_one_helper(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock(_frozen_streamdeck_proc=None, _streamdeck_retry_at=0.0)
        helper = Mock()
        menu._spawn_watched.return_value = helper
        with patch.object(bridge_menubar, "_running_streamdeck_pid", return_value=77):
            bridge_menubar.BridgeMenuBar._ensure_frozen_streamdeck(menu)
        menu._spawn_watched.assert_not_called()

        with patch.object(bridge_menubar, "_running_streamdeck_pid", return_value=None), \
             patch.object(bridge_menubar.time, "monotonic", return_value=10.0):
            bridge_menubar.BridgeMenuBar._ensure_frozen_streamdeck(menu)
        menu._spawn_watched.assert_called_once_with(
            [bridge_menubar.sys.executable, "--run-streamdeck"],
            label="frozen_streamdeck_start",
            combined_log=True,
        )
        self.assertIs(menu._frozen_streamdeck_proc, helper)

    def test_frozen_refresh_stops_an_orphan_streamdeck_when_bridge_is_off(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock(
            _frozen_bridge_proc=None,
            _frozen_streamdeck_proc=None,
            _adopted_frozen_bridge=False,
            _install_required=False,
            _status="off",
            status_rows=[],
        )
        menu._snapshot = {}
        with patch.object(bridge_menubar, "read_status", return_value={}), \
             patch.object(bridge_menubar, "bridge_pids", return_value=[]), \
             patch.object(bridge_menubar, "watcher_running", return_value=False), \
             patch.object(bridge_menubar.sys, "frozen", True, create=True), \
             patch.object(bridge_menubar, "_running_bridge_pid", return_value=None), \
             patch.object(bridge_menubar, "_running_streamdeck_pid", return_value=92):
            bridge_menubar.BridgeMenuBar.refresh_.callable(menu, None)
        menu._stop_frozen_streamdeck.assert_called_once_with()

    def test_installed_relaunch_waits_for_dmg_menubar_lock_release(self) -> None:
        bridge_menubar = self._import_module()
        events = []
        alert = Mock()
        alert.runModal.side_effect = lambda: events.append("dialog") or 0
        nsalert = Mock()
        nsalert.alloc.return_value.init.return_value = alert
        application = Mock()
        nsapplication = Mock()
        nsapplication.sharedApplication.return_value = application
        menu = Mock(_install_in_progress=True)
        payload = {
            "ok": True,
            "app_dest": "/Users/guest/Applications/RBSS Bridge.app",
            "installed_files": 12,
        }
        with patch.object(bridge_menubar, "NSAlert", nsalert), \
             patch.object(bridge_menubar, "NSApplication", nsapplication), \
             patch("rb_ss_bridge_v2.install_controller.bundle_root",
                   return_value=Path("/tmp/RBSS Bridge.app")), \
             patch.object(
                 bridge_menubar.subprocess,
                 "Popen",
                 side_effect=lambda *args, **kwargs: events.append("spawn") or Mock(),
             ) as popen:
            bridge_menubar.BridgeMenuBar.finishInstall_.callable(menu, payload)
        self.assertEqual(events, ["dialog", "spawn"])
        argv = popen.call_args.args[0]
        self.assertEqual(argv[:2], ["/bin/sh", "-c"])
        self.assertIn("sleep 1; exec open -n", argv[2])
        self.assertIn("RBSS Bridge.app", argv[2])
        application.terminate_.assert_called_once_with(menu)

    def test_delayed_detach_keeps_mount_out_of_shell_source(self) -> None:
        bridge_menubar = self._import_module()
        mount = '/Volumes/odd"; touch /tmp/should-not-run; #'
        argv = bridge_menubar.delayed_detach_argv(mount)
        self.assertEqual(argv[:2], ["/bin/sh", "-c"])
        self.assertIn('detach "$1"', argv[2])
        self.assertNotIn(mount, argv[2])
        self.assertEqual(argv[-1], mount)

    def test_frozen_stop_orders_streamdeck_before_owned_or_adopted_bridge(self) -> None:
        bridge_menubar = self._import_module()
        events = []
        owned = Mock()
        owned.poll.return_value = None
        menu = Mock(_frozen_bridge_proc=owned)
        menu._stop_frozen_streamdeck.side_effect = lambda: events.append("streamdeck")
        menu._stop_frozen_bridge_child.side_effect = lambda: events.append("bridge") or True
        bridge_menubar.BridgeMenuBar._toggle_bridge_frozen(menu)
        self.assertEqual(events, ["streamdeck", "bridge"])

        events.clear()
        menu = Mock(_frozen_bridge_proc=None)
        menu._stop_frozen_bridge_child.return_value = False
        menu._stop_frozen_streamdeck.side_effect = lambda: events.append("streamdeck")
        with patch.object(bridge_menubar, "_running_bridge_pid", return_value=91), \
             patch.object(
                 bridge_menubar.os,
                 "kill",
                 side_effect=lambda pid, sig: events.append((pid, sig)),
             ):
            bridge_menubar.BridgeMenuBar._toggle_bridge_frozen(menu)
        self.assertEqual(events[0], "streamdeck")
        self.assertEqual(events[1], (91, bridge_menubar.signal.SIGTERM))

    def test_frozen_streamdeck_stop_handles_owned_and_adopted_helpers(self) -> None:
        bridge_menubar = self._import_module()
        owned = Mock()
        owned.poll.return_value = None
        menu = Mock(_frozen_streamdeck_proc=owned)
        self.assertTrue(bridge_menubar.BridgeMenuBar._stop_frozen_streamdeck(menu))
        owned.terminate.assert_called_once_with()
        owned.wait.assert_called_once_with(timeout=5)
        self.assertIsNone(menu._frozen_streamdeck_proc)

        menu = Mock(_frozen_streamdeck_proc=None)
        with patch.object(
            bridge_menubar,
            "_running_streamdeck_pid",
            side_effect=[91, None, None],
        ), patch.object(bridge_menubar.os, "kill") as kill:
            self.assertTrue(bridge_menubar.BridgeMenuBar._stop_frozen_streamdeck(menu))
        kill.assert_called_once_with(91, bridge_menubar.signal.SIGTERM)

    def test_pioneer_usb_mount_detection(self) -> None:
        bridge_menubar = self._import_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "B" / "PIONEER").mkdir(parents=True)
            (root / "a" / "PIONEER").mkdir(parents=True)
            (root / "not-rb").mkdir()
            self.assertEqual(
                [p.name for p in bridge_menubar.pioneer_usb_mounts(root)],
                ["a", "B"],
            )

    def test_update_usb_requires_exactly_one_mount_and_dispatches_build(self) -> None:
        bridge_menubar = self._import_module()
        menu = Mock()
        menu._require_bridge_off.return_value = True
        mount = Path("/Volumes/DJ USB")
        alert = Mock()
        alert.runModal.return_value = bridge_menubar.NSAlertFirstButtonReturn
        nsalert = Mock()
        nsalert.alloc.return_value.init.return_value = alert
        with patch.object(bridge_menubar, "pioneer_usb_mounts", return_value=[mount]), \
             patch.object(bridge_menubar, "NSAlert", nsalert):
            bridge_menubar.BridgeMenuBar.updateUsbBridge_.callable(menu, None)
        argv = menu._spawn_watched.call_args.args[0]
        self.assertEqual(argv, [
            "bash", str(bridge_menubar.REPO_ROOT / "packaging" / "make_stick.sh"),
            str(mount),
        ])
        self.assertEqual(menu._spawn_watched.call_args.kwargs["busy_item_attr"], "update_usb_item")

        for mounts, title in (([], "No Rekordbox USB found"),
                              ([Path("/Volumes/A"), Path("/Volumes/B")],
                               "More than one Rekordbox USB found")):
            menu = Mock()
            menu._require_bridge_off.return_value = True
            alert = Mock()
            nsalert = Mock()
            nsalert.alloc.return_value.init.return_value = alert
            with patch.object(bridge_menubar, "pioneer_usb_mounts", return_value=mounts), \
                 patch.object(bridge_menubar, "NSAlert", nsalert):
                bridge_menubar.BridgeMenuBar.updateUsbBridge_.callable(menu, None)
            alert.setMessageText_.assert_called_once_with(title)
            menu._spawn_watched.assert_not_called()

    # ── Rebuild-USB button state (usb_rebuild_button_state_spec_2026_07_12) ──

    def test_usb_button_text_table(self) -> None:
        bridge_menubar = self._import_module()
        text = bridge_menubar.usb_button_text
        # in_progress wins over every state, so the periodic repaint keeps it
        for state in ("no_usb", "up_to_date", "outdated", "garbage"):
            self.assertEqual(text(True, state), "Rebuilding USB Bridge…")
        self.assertEqual(text(False, "no_usb"), "No USB Found")
        self.assertEqual(text(False, "up_to_date"), "USB Bridge Rebuilt")
        self.assertEqual(text(False, "outdated"), "Rebuild USB Bridge…")
        self.assertEqual(text(False, "garbage"), "Rebuild USB Bridge…")

    def test_usb_button_enabled_table(self) -> None:
        bridge_menubar = self._import_module()
        enabled = bridge_menubar.usb_button_enabled
        self.assertTrue(enabled(False, "outdated", False))
        self.assertFalse(enabled(True, "outdated", False))   # building
        self.assertFalse(enabled(False, "outdated", True))   # frozen
        self.assertFalse(enabled(False, "up_to_date", False))
        self.assertFalse(enabled(False, "no_usb", False))

    def test_classify_usb_state_table(self) -> None:
        bridge_menubar = self._import_module()
        classify = bridge_menubar.classify_usb_state
        stamp = {"generation": "gen-1", "source_fingerprint": "fp-1"}
        self.assertEqual(classify(0, "gen-1", stamp, "fp-1"), "no_usb")
        self.assertEqual(classify(2, "gen-1", stamp, "fp-1"), "outdated")
        self.assertEqual(classify(1, None, stamp, "fp-1"), "outdated")
        self.assertEqual(classify(1, "gen-1", None, "fp-1"), "outdated")
        self.assertEqual(classify(1, "gen-2", stamp, "fp-1"), "outdated")
        self.assertEqual(classify(1, "gen-1", stamp, None), "outdated")
        self.assertEqual(classify(1, "gen-1", stamp, "fp-2"), "outdated")
        self.assertEqual(classify(1, "gen-1", stamp, "fp-1"), "up_to_date")

    def test_usb_source_signature_tracks_changes(self) -> None:
        bridge_menubar = self._import_module()
        import os as _os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = root / "cache"
            tree.mkdir()
            (tree / "a.json").write_text("{}")
            single = root / "config.json"
            single.write_text("{}")
            roots = [tree, single]
            first = bridge_menubar.usb_source_signature(roots)
            self.assertEqual(first, bridge_menubar.usb_source_signature(roots))
            # mtime bump = change (utime is explicit: same-second writes may not
            # move mtime_ns on coarse filesystems)
            _os.utime(single, ns=(1, 1))
            second = bridge_menubar.usb_source_signature(roots)
            self.assertNotEqual(first, second)
            # added file = change; removal returns to the prior signature
            (tree / "b.json").write_text("{}")
            third = bridge_menubar.usb_source_signature(roots)
            self.assertNotEqual(second, third)
            (tree / "b.json").unlink()
            self.assertEqual(second, bridge_menubar.usb_source_signature(roots))
            # absent root contributes nothing (stable, never flips the verdict)
            self.assertEqual(
                bridge_menubar.usb_source_signature(roots),
                bridge_menubar.usb_source_signature(roots + [root / "missing"]),
            )

    def test_usb_source_roots_pin_build_inputs(self) -> None:
        # Drift pin: if make_stick.sh's staged inputs change, this list must too.
        bridge_menubar = self._import_module()
        roots = {str(p) for p in bridge_menubar._usb_source_roots()}
        repo = bridge_menubar.REPO_ROOT
        for expected in (
            repo / "packaging" / "make_stick.sh",
            repo / "tools" / "lighting_sidecar_export.py",
            repo / "tools" / "laser_pad_assets",
            repo / "tools" / "led_pad_assets",
            repo / "config" / "laser_director.json",
            repo / "config" / "led_look_director.json",
            repo / "config" / "soundswitch_pack_player.json",
            repo / "config" / "laser_color_map.json",
        ):
            self.assertIn(str(expected), roots)
        self.assertTrue(
            any(p.endswith(".example.json") for p in roots),
            "config examples bundled by PyInstaller are missing from USB source roots",
        )
        self.assertTrue(
            any(p.endswith("spectral_cache") for p in roots),
            "spectral_cache missing from USB source roots",
        )

    def test_usb_stamp_round_trip(self) -> None:
        bridge_menubar = self._import_module()
        import os as _os
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(_os.environ, {"HOME": tmp}):
                self.assertIsNone(bridge_menubar.read_usb_stamp())  # missing
                bridge_menubar.write_usb_stamp("gen-1", "fp-1")
                self.assertEqual(
                    bridge_menubar.read_usb_stamp(),
                    {"generation": "gen-1", "source_fingerprint": "fp-1"},
                )
                bridge_menubar._usb_stamp_path().write_text("not json")
                self.assertIsNone(bridge_menubar.read_usb_stamp())  # corrupt

    def test_read_stick_generation(self) -> None:
        bridge_menubar = self._import_module()
        with tempfile.TemporaryDirectory() as tmp:
            mount = Path(tmp)
            self.assertIsNone(bridge_menubar.read_stick_generation(mount))
            sidecar = mount / "RBSS BRIDGE USB" / "lighting_sidecar"
            sidecar.mkdir(parents=True)
            manifest = sidecar / ".rbss_build_manifest.json"
            manifest.write_text(json.dumps({"generation": "abc-123"}))
            self.assertEqual(bridge_menubar.read_stick_generation(mount), "abc-123")
            manifest.write_text(json.dumps({"generation": ""}))
            self.assertIsNone(bridge_menubar.read_stick_generation(mount))
            manifest.write_text("corrupt")
            self.assertIsNone(bridge_menubar.read_stick_generation(mount))

    def test_usb_rebuild_completion_resets_flag_and_stamps_only_on_success(self) -> None:
        # Every completion path (success, failure, signal death) must reset the
        # busy flag; the stamp is written on exit 0 ONLY.
        bridge_menubar = self._import_module()
        for returncode, expect_stamp in ((0, True), (1, False), (-15, False)):
            menu = Mock()
            menu.update_usb_item = Mock()
            payload = {
                "busy_item_attr": "update_usb_item",
                "saved_title": "Rebuild USB Bridge…",
                "returncode": returncode,
                "tail": "boom" if returncode > 0 else "",
                "err_path": "",
                "success_message": None,
                "failure_title": "USB Bridge rebuild failed",
            }
            alert = Mock()
            nsalert = Mock()
            nsalert.alloc.return_value.init.return_value = alert
            with patch.object(bridge_menubar, "NSAlert", nsalert):
                bridge_menubar.BridgeMenuBar.finishWatchedChild_.callable(menu, payload)
            self.assertFalse(menu._usb_rebuild_in_progress)
            self.assertIsNone(menu._usb_pending_fingerprint)
            self.assertIsNone(menu._usb_mounts_key)
            self.assertEqual(menu._usb_detect_at, 0.0)
            menu._render_usb_state.assert_called_once()
            if expect_stamp:
                menu._record_usb_rebuild_stamp.assert_called_once()
            else:
                menu._record_usb_rebuild_stamp.assert_not_called()

    def test_record_usb_rebuild_stamp_uses_click_time_fingerprint(self) -> None:
        # The stamp must carry the fingerprint captured at CLICK time — never a
        # post-build recompute (an edit during the build must stay "outdated").
        bridge_menubar = self._import_module()
        menu = Mock()
        menu._usb_pending_fingerprint = "fp-click"
        with patch.object(bridge_menubar, "pioneer_usb_mounts",
                          return_value=[Path("/Volumes/MINK")]), \
             patch.object(bridge_menubar, "read_stick_generation",
                          return_value="gen-9"), \
             patch.object(bridge_menubar, "write_usb_stamp") as write_stamp:
            bridge_menubar.BridgeMenuBar._record_usb_rebuild_stamp(menu)
        write_stamp.assert_called_once_with("gen-9", "fp-click")
        # no pending fingerprint (e.g. spawn failed before capture) -> no stamp
        menu._usb_pending_fingerprint = None
        with patch.object(bridge_menubar, "write_usb_stamp") as write_stamp:
            bridge_menubar.BridgeMenuBar._record_usb_rebuild_stamp(menu)
        write_stamp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
