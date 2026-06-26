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
