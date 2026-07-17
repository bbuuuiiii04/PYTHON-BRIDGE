"""AWR-278: post-Accept lifecycle reconciliation + audit fixes (service layer).

Covers the Part A reconciliation (Reject/Delete/Rename/re-Accept keep the Lab
ledger and the pad show in sync), the Part B1 palette/live-tweak fix, and the
Part B3 cue-length clamp. All through LedPadService with a fake playback — no
bridge, no hardware.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


_GOOD_LAB = """
def spark(beat_pos, local_t, frame_index, params, segments, seed):
    return [(10, 20, 30)] * max(0, int(segments))

LAB_EFFECTS = {
    "spark": ("frame", spark),
}
"""


def _draft_entry(name: str, *, target_role: str = "drop", params: dict | None = None) -> dict:
    return {
        "name": name,
        "kind": "frame",
        "fn": name,
        "params": params if params is not None else {},
        "cue_beats": 16,
        "notes": "",
        "brief": "",
        "status": "iterating",
        "timing_mode": "beat",
        "target_role": target_role,
        "param_specs": {},
        "created": "2026-07-16T00:00:00+00:00",
        "updated": "2026-07-16T00:00:00+00:00",
    }


class _FakePlayback:
    def __init__(self) -> None:
        self._playing = False
        self._look = ""
        self.updates: list[dict] = []
        self.plays: list[dict] = []

    def ownership(self) -> dict:
        return {"state": "free"}

    def status(self) -> dict:
        return {"playing": self._playing, "playing_look": self._look}

    def set_bpm(self, *_a, **_k) -> None:
        return None

    def set_loop(self, *_a, **_k) -> None:
        return None

    def play(self, spec, *, cue_beats=16, loop=False) -> None:
        self._playing = True
        self._look = str(spec.get("look_name") or "")
        self.plays.append(copy.deepcopy(spec))

    def update(self, spec) -> None:
        self.updates.append(copy.deepcopy(spec))

    def stop(self) -> None:
        self._playing = False

    def emergency_stop(self) -> None:
        self._playing = False

    def request_takeover(self) -> None:
        return None

    def release(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


class _ServiceHarness(unittest.TestCase):
    def _service(self, drafts: list[dict]):
        from rb_ss_bridge_v2.tools.led_pad_web import LedPadService

        example = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"
        raw = json.loads(example.read_text(encoding="utf-8"))
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        config_path = root / "led_look_director.json"
        config_path.write_text(json.dumps(raw), encoding="utf-8")
        lab_dir = root / "led_lab"
        lab_dir.mkdir()
        (lab_dir / "effects_lab.py").write_text(_GOOD_LAB, encoding="utf-8")
        (lab_dir / "drafts.json").write_text(json.dumps({"entries": drafts}), encoding="utf-8")
        self._cmds: list[dict] = []
        self._playback = _FakePlayback()
        service = LedPadService(
            config_path, dry_run=True, playback=self._playback, lab_dir=lab_dir,
        )
        service._append_bridge_command = self._cmds.append  # type: ignore[method-assign]
        self._config_path = config_path
        return service

    def _live(self) -> dict:
        return json.loads(self._config_path.read_text(encoding="utf-8"))

    def _live_look_names_for_scene(self, scene_ref: str) -> list[str]:
        looks = (self._live().get("looks") or {})
        return sorted(n for n, l in looks.items() if isinstance(l, dict) and l.get("scene_ref") == scene_ref)


class LifecycleReconcileTests(_ServiceHarness):
    def test_accept_then_reject_removes_from_show(self) -> None:
        """A1: an untouched wired look is pulled out of the show on Reject."""
        service = self._service([_draft_entry("spark", target_role="drop")])
        accept = service.lab_accept({"name": "spark", "target_role": "drop", "params": {}, "overwrite": True})
        self.assertTrue(accept.get("wired"), accept)
        self.assertIn("spark", self._live().get("looks") or {})

        reject = service.lab_reject({"name": "spark", "params": {}, "status": "rejected", "overwrite": True})
        self.assertTrue(reject.get("unwired"), reject)
        self.assertEqual(reject.get("removed_look"), "spark")
        self.assertNotIn("spark", self._live().get("looks") or {})
        bank = ((self._live().get("banks") or {}).get("default") or {}).get("drop") or []
        self.assertNotIn("spark", bank)
        # The bridge is told to reload after both accept and reject.
        self.assertEqual(self._cmds, [{"cmd": "led_reload_looks"}, {"cmd": "led_reload_looks"}])
        # Ledger honesty: the draft is rejected, not still "accepted".
        self.assertEqual(service._lab.get("spark").get("status"), "rejected")

    def test_accept_padedit_then_reject_keeps_edited_look(self) -> None:
        """A1: a look changed on the Pad since accept is preserved, not destroyed."""
        service = self._service([_draft_entry("spark", target_role="drop", params={})])
        service.lab_accept({"name": "spark", "target_role": "drop", "params": {}, "overwrite": True})
        # Operator changes the wired look on the Pad.
        service.save_look({"name": "spark", "look": {"scene_ref": "lab:spark"}, "params": {"width": 7}})

        reject = service.lab_reject({"name": "spark", "params": {}, "status": "rejected", "overwrite": True})
        self.assertFalse(reject.get("unwired"), reject)
        self.assertEqual(reject.get("kept_look"), "spark")
        self.assertIn("kept", reject.get("message", "").lower())
        # The edited look stays in the show.
        self.assertIn("spark", self._live().get("looks") or {})

    def test_reject_plain_draft_no_wired_look(self) -> None:
        """A1: rejecting a draft that was never accepted just marks it rejected."""
        service = self._service([_draft_entry("spark", target_role="drop")])
        reject = service.lab_reject({"name": "spark", "params": {}, "status": "rejected", "overwrite": True})
        self.assertFalse(reject.get("unwired"))
        self.assertIn("stays out of the show", reject.get("message", ""))

    def test_delete_wired_look_flips_draft_back_to_iterating(self) -> None:
        """A2: deleting a wired look updates the Lab ledger away from Accepted."""
        service = self._service([_draft_entry("spark", target_role="drop")])
        service.lab_accept({"name": "spark", "target_role": "drop", "params": {}, "overwrite": True})
        self.assertEqual(service._lab.get("spark").get("status"), "accepted")

        service.delete_look({"name": "spark"})
        self.assertEqual(service._lab.get("spark").get("status"), "iterating")

    def test_accept_rename_reaccept_updates_in_place_no_duplicate(self) -> None:
        """A4: re-accepting a renamed wired look updates it, never duplicates."""
        service = self._service([_draft_entry("spark", target_role="drop")])
        service.lab_accept({"name": "spark", "target_role": "drop", "params": {}, "overwrite": True})
        # Rename the wired look on the Pad; scene_ref stays lab:spark.
        service.rename_look({"name": "spark", "new_name": "my_drop"})
        service.commit({})
        self.assertEqual(self._live_look_names_for_scene("lab:spark"), ["my_drop"])

        again = service.lab_accept({"name": "spark", "target_role": "drop", "params": {"width": 3}, "overwrite": True})
        self.assertTrue(again.get("updated"), again)
        self.assertEqual(again.get("look_name"), "my_drop")
        # Exactly one look carries the draft's scene_ref — no sibling created.
        self.assertEqual(self._live_look_names_for_scene("lab:spark"), ["my_drop"])
        self.assertNotIn("spark", self._live().get("looks") or {})
        self.assertEqual((self._live()["looks"]["my_drop"].get("params") or {}).get("width"), 3)


class PaletteLiveTweakTests(_ServiceHarness):
    def test_palette_change_keeps_live_tweak_and_snapshot(self) -> None:
        """B1: changing Test Palette mid lab-play must not revert live tweaks."""
        service = self._service([_draft_entry("spark", target_role="drop", params={})])
        service.lab_play({"name": "spark"})
        # Live tweak: dial a param up.
        service.lab_update({"name": "spark", "params": {"width": 5}})
        self.assertEqual(service._last_lab_applied.get("spark", {}).get("width"), 5)

        palettes = service.get_palettes()["palettes"]
        self.assertTrue(palettes, "example config must expose palettes")
        service.session({"test_palette": palettes[0]})

        last = self._playback.updates[-1]
        self.assertEqual((last.get("params") or {}).get("width"), 5, "palette change dropped the live tweak")
        self.assertEqual(service._last_lab_applied.get("spark", {}).get("width"), 5, "snapshot was clobbered")


class CueBeatsClampTests(_ServiceHarness):
    def test_save_look_clamps_zero_cue_to_at_least_one(self) -> None:
        """B3: a saved cue length of 0 is clamped to >=1 (stored truth)."""
        service = self._service([_draft_entry("spark", target_role="drop")])
        service.lab_accept({"name": "spark", "target_role": "drop", "params": {}, "overwrite": True})
        service.save_look({"name": "spark", "look": {"scene_ref": "lab:spark"}, "params": {}, "cue_beats": 0})
        cfg = service.get_config_payload()["config"]
        stored = (((cfg.get("_pad_meta") or {}).get("looks") or {}).get("spark") or {}).get("cue_beats")
        self.assertIsNotNone(stored)
        self.assertGreaterEqual(float(stored), 1.0)

    def test_cue_timer_zero_never_stops_but_one_does(self) -> None:
        """B3 root: CueTimer.start(0) is inactive (never auto-stops); >=1 stops."""
        from rb_ss_bridge_v2.tools.led_pad_playback import CueTimer

        clock = {"t": 0.0}
        timer = CueTimer(time_fn=lambda: clock["t"])
        timer.start(cue_beats=0, bpm=120.0, loop=False)
        self.assertFalse(timer.active)
        clock["t"] = 100.0
        self.assertFalse(timer.should_stop(), "cue_beats=0 loop-off never auto-stops")

        clock["t"] = 0.0
        timer.start(cue_beats=1, bpm=120.0, loop=False)
        self.assertTrue(timer.active)
        clock["t"] = 10.0  # far past 1 beat at 120 bpm (0.5s)
        self.assertTrue(timer.should_stop())


if __name__ == "__main__":
    unittest.main()
