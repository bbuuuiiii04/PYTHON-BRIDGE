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

    def start(self):
        self._log.append(f"{self._name}.input_start")

    def stop(self):
        self._log.append(f"{self._name}.input_stop")


def _unstarted(log, name, sha="newsha"):
    return PackRuntime(
        enabled=False, reason="prepared", player=object(),
        midi_input=_Input(log, name), backend=object(),
        frame_sender=_Sender(log, name), pack_sha12=sha)


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
    def test_enable_from_disabled_builds_and_starts(self):
        log: list[str] = []
        h = _Harness(prepare=lambda: _unstarted(log, "new"))
        ok, detail = h.ctrl.handle("enable", enabled=True)
        self.assertEqual((ok, detail), (True, "pack"))
        self.assertTrue(h.current.active)
        self.assertEqual(log, ["new.input_start", "new.start"])  # input first, sender second

    def test_disable_zero_and_stops_old_sender(self):
        log: list[str] = []
        h = _Harness(prepare=lambda: _unstarted(log, "new"))
        h.current = PackRuntime(enabled=True, reason="pack", player=object(),
                                midi_input=_Input(log, "old"), backend=object(),
                                frame_sender=_Sender(log, "old"))
        ok, detail = h.ctrl.handle("enable", enabled=False)
        self.assertEqual((ok, detail), (True, "disabled"))
        self.assertFalse(h.current.active)
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

    def test_unknown_action_is_unsupported(self):
        h = _Harness(prepare=lambda: PackRuntime())
        self.assertEqual(h.ctrl.handle("bogus"), (False, "unsupported_action"))


if __name__ == "__main__":
    unittest.main()
