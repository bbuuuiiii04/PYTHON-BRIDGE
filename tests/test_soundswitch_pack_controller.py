"""T7e — SoundSwitchPackController validate-first / stop-before-start tests.

No real serial/MIDI. Fakes record lifecycle calls into a shared ordered log so
stop-before-start and physical zero/stop ordering can be asserted.
"""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_pack_controller import SoundSwitchPackController
from rb_ss_bridge_v2.soundswitch_pack_runtime import PackRuntime
from rb_ss_bridge_v2.soundswitch_midi_input import (
    MidiInputSnapshot,
    SoundSwitchMidiInputGroup,
)
from rb_ss_bridge_v2.soundswitch_pack_loader import PackMidiBinding


class _Sender:
    def __init__(self, log, name):
        self._log, self._name = log, name
        self.fail_start = False

    def start(self, **_k):
        self._log.append(f"{self._name}.start")
        if self.fail_start:
            raise RuntimeError("serial open failed")

    def zero_and_stop(self):
        self._log.append(f"{self._name}.zero_and_stop")

    def stop(self):
        self._log.append(f"{self._name}.stop")


class _Input:
    def __init__(self, log, name):
        self._log, self._name = log, name
        self.fail_start = False

    def start(self):
        self._log.append(f"{self._name}.input_start")
        if self.fail_start:
            raise OSError("controller open failed")

    def stop(self):
        self._log.append(f"{self._name}.input_stop")


def _unstarted(log, name, sha="newsha"):
    return PackRuntime(
        enabled=False, reason="prepared", player=object(),
        midi_input=_Input(log, name), backend=object(),
        frame_sender=_Sender(log, name), pack_sha12=sha,
        phase_offset_beats=1.25)


class _Harness:
    def __init__(self, prepare):
        self.published: list[PackRuntime] = []
        self.current = PackRuntime()  # start disabled
        self.ctrl = SoundSwitchPackController(
            publish=self._pub, snapshot=lambda: self.current, prepare=prepare)

    def _pub(self, rt):
        self.published.append(rt)
        self.current = rt


class ControllerTests(unittest.TestCase):
    def test_dead_build_started_helper_is_absent(self):
        self.assertFalse(hasattr(SoundSwitchPackController, "_build_started"))

    def test_enable_from_disabled_builds_and_starts(self):
        log: list[str] = []
        h = _Harness(prepare=lambda: _unstarted(log, "new"))
        ok, detail = h.ctrl.handle("enable", enabled=True)
        self.assertEqual((ok, detail), (True, "pack"))
        self.assertTrue(h.current.active)
        self.assertEqual(h.current.phase_offset_beats, 1.25)
        self.assertEqual(log, ["new.input_start", "new.start"])  # input first, sender second

    def test_disable_zero_and_stops_old_sender(self):
        log: list[str] = []
        h = _Harness(prepare=lambda: _unstarted(log, "new"))
        h.current = PackRuntime(enabled=True, reason="pack", player=object(),
                                midi_input=_Input(log, "old"), backend=object(),
                                frame_sender=_Sender(log, "old"),
                                phase_offset_beats=2.0)
        ok, detail = h.ctrl.handle("enable", enabled=False)
        self.assertEqual((ok, detail), (True, "disabled"))
        self.assertFalse(h.current.active)
        self.assertEqual(h.current.phase_offset_beats, 2.0)
        self.assertIn("old.zero_and_stop", log)  # physical zero, not just NoneBackend

    def test_stop_before_start_ordering_on_swap(self):
        log: list[str] = []
        h = _Harness(prepare=lambda: _unstarted(log, "new"))
        h.current = PackRuntime(enabled=True, reason="pack", player=object(),
                                midi_input=_Input(log, "old"), backend=object(),
                                frame_sender=_Sender(log, "old"))
        ok, _ = h.ctrl.handle("reload")
        self.assertTrue(ok)
        # old sender zero/stopped BEFORE the new sender starts (shared serial port).
        self.assertLess(log.index("old.zero_and_stop"), log.index("new.start"))
        # a disabled bundle is published before the new enabled one (driver stops first).
        self.assertFalse(h.published[0].active)
        self.assertTrue(h.published[-1].active)

    def test_reload_keeps_pack_enabled_when_controller_input_degrades(self):
        log: list[str] = []

        class MissingInputAdapter:
            def __init__(self, bindings, *, stale_timeout_ms):
                self._snap = MidiInputSnapshot((), False, True, None, 0)

            def start(self, port, *, device_name):
                log.append(f"{device_name}.input_start")
                raise OSError("synthetic missing controller")

            def stop(self):
                log.append("input.stop")

            def mark_unavailable(self):
                self._snap = MidiInputSnapshot((), False, False, "input_unavailable", 0)

            def snapshot(self):
                return self._snap

            def panic(self):
                pass

            def on_pack_reload(self):
                pass

        def prepared():
            group = SoundSwitchMidiInputGroup(
                (PackMidiBinding("DDJ", "note", 0, 7, "static_look", target_slot=8),),
                {},
                adapter_factory=MissingInputAdapter,
            )
            return PackRuntime(
                enabled=False, reason="prepared", player=object(),
                midi_input=group, backend=object(),
                frame_sender=_Sender(log, "new"), pack_sha12="newsha",
            )

        h = _Harness(prepare=prepared)
        h.current = PackRuntime(
            enabled=True, reason="pack", player=object(),
            midi_input=_Input(log, "old"), backend=object(),
            frame_sender=_Sender(log, "old"),
        )

        ok, detail = h.ctrl.handle("reload")

        self.assertEqual((ok, detail), (True, "pack"))
        self.assertTrue(h.current.active)
        # Missing controller is flagged via raw-health status() (snapshot().error is the
        # narrower overlay-trust verdict, None when nobody is holding an overlay).
        self.assertTrue(h.current.midi_input.status()["has_error"])
        self.assertIn("new.start", log)

    def test_validate_first_failure_retains_old_runtime(self):
        def boom():
            raise ValueError("verify failed: /Users/secret/pack.ssproj")
        old = PackRuntime(enabled=True, reason="pack", player=object(), backend=object())
        h = _Harness(prepare=boom)
        h.current = old
        ok, detail = h.ctrl.handle("reload")
        self.assertFalse(ok)
        self.assertEqual(detail, "ValueError")  # sanitized class only, no path
        self.assertIs(h.current, old)           # old retained; no publish
        self.assertEqual(h.published, [])

    def test_reload_while_disabled_does_not_enable(self):
        log: list[str] = []
        prepared = {"n": 0}
        def prep():
            prepared["n"] += 1
            return _unstarted(log, "new")
        h = _Harness(prepare=prep)  # current is disabled
        ok, detail = h.ctrl.handle("reload")
        self.assertEqual((ok, detail), (True, "reloaded_disabled"))
        self.assertFalse(h.current.active)       # no implicit hot-enable
        self.assertEqual(log, [])                # nothing started
        self.assertEqual(prepared["n"], 1)       # pack still validated

    def test_backend_none_disables_and_zero_stops(self):
        log: list[str] = []
        h = _Harness(prepare=lambda: _unstarted(log, "new"))
        h.current = PackRuntime(enabled=True, reason="pack", player=object(),
                                frame_sender=_Sender(log, "old"), backend=object())
        ok, detail = h.ctrl.handle("backend", backend="none")
        self.assertEqual((ok, detail), (True, "none"))
        self.assertFalse(h.current.active)
        self.assertIn("old.zero_and_stop", log)

    def test_backend_midi_is_unsupported_and_inert(self):
        log: list[str] = []
        h = _Harness(prepare=lambda: _unstarted(log, "new"))
        ok, detail = h.ctrl.handle("backend", backend="midi")
        self.assertEqual((ok, detail), (False, "unsupported_action"))
        self.assertEqual(h.published, [])   # no state change, no IAC/MIDI opened
        self.assertEqual(log, [])

    def test_backend_pack_start_failure_falls_back_to_disabled_not_midi(self):
        log: list[str] = []
        def prep():
            rt = _unstarted(log, "new")
            rt.frame_sender.fail_start = True
            return rt
        h = _Harness(prepare=prep)
        ok, detail = h.ctrl.handle("backend", backend="pack")
        self.assertFalse(ok)
        self.assertEqual(detail, "RuntimeError")
        self.assertFalse(h.current.active)            # safe no-output
        self.assertEqual(h.current.reason, "pack_start_failed")  # NOT midi

    def test_start_failure_preserves_pack_sha12_in_status(self):
        log: list[str] = []
        old_sha = "abc123def456"

        def prep():
            rt = _unstarted(log, "new", sha=old_sha)
            rt.frame_sender.fail_start = True
            return rt

        h = _Harness(prepare=prep)
        h.current = PackRuntime(enabled=True, reason="pack", pack_sha12=old_sha,
                                player=object(), backend=object())
        ok, detail = h.ctrl.handle("enable", enabled=True)
        self.assertEqual((ok, detail), (False, "RuntimeError"))
        self.assertEqual(h.published[-1].reason, "pack_start_failed")
        self.assertEqual(h.published[-1].pack_sha12, old_sha,
                         "pack_sha12 dropped on start-failure (drift vs other disabled publishes)")

    def test_output_start_failure_keeps_started_input_alive(self):
        # No Enttec attached: midi_input.start() succeeds, frame_sender.start()
        # raises. The pad input must survive — it is the ONLY thing driving
        # Stream Deck pads — mirroring the boot-path contract in
        # __main__._start_soundswitch_pack_workers.
        log: list[str] = []
        built = {}

        def prep():
            rt = _unstarted(log, "new")
            rt.frame_sender.fail_start = True
            built["rt"] = rt
            return rt

        h = _Harness(prepare=prep)
        ok, detail = h.ctrl.handle("enable", enabled=True)

        self.assertEqual((ok, detail), (False, "RuntimeError"))
        published = h.published[-1]
        self.assertFalse(published.active)
        self.assertEqual(published.reason, "pack_start_failed")
        # SAME midi_input object that was started — not stopped, not replaced.
        self.assertIs(published.midi_input, built["rt"].midi_input)
        self.assertNotIn("new.input_stop", log)
        # Output side was physically torn down.
        self.assertTrue(
            "new.zero_and_stop" in log or "new.stop" in log,
            f"frame sender was not stopped: {log}",
        )

    def test_input_start_failure_still_tears_down_input(self):
        # Pre-fix behavior preserved for the input-fails-first step: no started
        # workers to keep, so the safe no-output teardown applies as before.
        log: list[str] = []

        def prep():
            rt = _unstarted(log, "new")
            rt.midi_input.fail_start = True
            return rt

        h = _Harness(prepare=prep)
        ok, detail = h.ctrl.handle("enable", enabled=True)

        self.assertEqual((ok, detail), (False, "OSError"))
        published = h.published[-1]
        self.assertFalse(published.active)
        self.assertIsNone(published.midi_input)
        self.assertIn("new.input_stop", log)
        # Frame sender never started since input.start() raised first.
        self.assertNotIn("new.start", log)

    def test_retry_after_output_failure_converges_to_new_input(self):
        # The menubar auto-retries "enable" ~8s after boot. The first attempt
        # keeps a live input despite the missing Enttec (previous test); this
        # models the retry: the kept input from attempt 1 must be stopped by
        # the second swap, and the fresh input from attempt 2 is what ends up
        # published (proving the retry converges to a live input, not the
        # stale one from attempt 1).
        log: list[str] = []

        def prep_fail():
            rt = _unstarted(log, "new1")
            rt.frame_sender.fail_start = True
            return rt

        h = _Harness(prepare=prep_fail)
        ok, detail = h.ctrl.handle("enable", enabled=True)
        self.assertEqual((ok, detail), (False, "RuntimeError"))
        kept_input = h.current.midi_input
        self.assertIsNotNone(kept_input)
        self.assertNotIn("new1.input_stop", log)

        h.ctrl._prepare = lambda: _unstarted(log, "new2")
        ok, detail = h.ctrl.handle("enable", enabled=True)

        self.assertEqual((ok, detail), (True, "pack"))
        self.assertTrue(h.current.active)
        # The stale attempt-1 input was stopped by this swap ...
        self.assertIn("new1.input_stop", log)
        # ... and the published runtime carries the NEW input, not the old one.
        self.assertIsNot(h.current.midi_input, kept_input)
        self.assertEqual(h.current.midi_input._name, "new2")

    def test_unknown_action_is_unsupported(self):
        h = _Harness(prepare=lambda: PackRuntime())
        self.assertEqual(h.ctrl.handle("bogus"), (False, "unsupported_action"))


if __name__ == "__main__":
    unittest.main()
