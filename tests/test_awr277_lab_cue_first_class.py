"""AWR-277: accepted Template Lab cues are first-class in the pad + honest timing note.

Two operator-reported bugs:

* BUG 1 — accepted lab looks (scene_ref ``lab:<draft>``) were branded "cloud
  scene (not previewable)" and their Play tile was disabled. They are real,
  playable looks. This module proves the pad now names them "Lab cue", enables
  Play, and — the deeper bug — that pad tile Play actually renders frames for an
  accepted lab cue end-to-end (the AWR-260 adapter only lights inside the
  frame-engine child; the pad process renders through ``LabRenderer``).

* BUG 2 — the Template Lab "Timing" dropdown was presented as a functional
  playback control but nothing reads it for playback. It is demoted to a
  read-only design note; the stored field is preserved.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_ASSETS = Path(__file__).resolve().parents[1] / "tools" / "led_pad_assets"
_EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


_GOOD_LAB = """
def pulse(beat_pos, local_t, frame_index, params, segments, seed):
    return [(10, 20, 30)] * max(0, int(segments))

def sparkle(beat_pos, local_t, frame_index, params, segments, seed):
    # slot-kind field: each segment gets a slot index; colorizer fills it.
    return [i % 6 for i in range(max(0, int(segments)))]

LAB_EFFECTS = {
    "pulse": ("frame", pulse),
    "sparkle": ("slot", sparkle),
}
"""


def _draft_entry(name: str, *, kind: str = "frame", fn: str | None = None,
                 params: dict | None = None, target_role: str = "drop") -> dict:
    return {
        "name": name,
        "kind": kind,
        "fn": fn if fn is not None else name,
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
    def ownership(self):
        return {"state": "free"}

    def status(self):
        return {"playing": False}

    def set_bpm(self, *_a, **_k):
        return None

    def set_loop(self, *_a, **_k):
        return None

    def play(self, *_a, **_k):
        return None

    def update(self, *_a, **_k):
        return None

    def stop(self):
        return None

    def emergency_stop(self):
        return None

    def request_takeover(self):
        return None

    def release(self):
        return None

    def shutdown(self):
        return None


def _service(td: str, *, dry_run: bool = True, playback=None, entries=None):
    from rb_ss_bridge_v2.tools.led_pad_web import LedPadService

    root = Path(td)
    cfg = root / "led_look_director.json"
    cfg.write_text(_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    lab_dir = root / "led_lab"
    lab_dir.mkdir()
    (lab_dir / "effects_lab.py").write_text(_GOOD_LAB, encoding="utf-8")
    (lab_dir / "drafts.json").write_text(
        json.dumps({"entries": entries if entries is not None else [_draft_entry("pulse")]}),
        encoding="utf-8",
    )
    kwargs = {"dry_run": dry_run, "lab_dir": lab_dir}
    if playback is not None:
        kwargs["playback"] = playback
    service = LedPadService(cfg, **kwargs)
    service._append_bridge_command = lambda *_a, **_k: None  # type: ignore[method-assign]
    return service, cfg


class LabCuePadPlayTests(unittest.TestCase):
    """BUG 1 deeper fix: accepted lab cue plays by name and renders frames."""

    def test_play_spec_no_longer_raises_cloud_and_renders_lit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _cfg = _service(td, playback=_FakePlayback())
            res = service.lab_accept(
                {"name": "pulse", "updated": "2026-07-16T00:00:00+00:00", "target_role": "drop"}
            )
            self.assertTrue(res.get("ok"), res)
            self.assertEqual(res.get("scene_ref"), "lab:pulse")

            config = copy.deepcopy(service._draft)
            # Regression: this used to raise "cloud scene - not previewable in the pad".
            spec, cue = service._play_spec(config, "pulse", None)
            # The pad renderer lights lab_<draft>, not the stored lab:<draft>.
            self.assertEqual(spec["scene_ref"], "lab_pulse")
            self.assertEqual(cue, 16.0)

            # Render exactly as the runner does: renderer.render(spec.scene_ref, ...).
            service._lab_renderer.reload()
            frame = service._lab_renderer.render(
                spec["scene_ref"], beat_pos=0.0, local_t=0.0, frame_index=0,
                params=spec["params"], segments=4, seed=0,
            )
            self.assertNotEqual(frame, [(0, 0, 0)] * 4, "lab cue rendered blank")

    def test_slot_lab_cue_gets_slot_colors_injected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _cfg = _service(
                td, playback=_FakePlayback(),
                entries=[_draft_entry("sparkle", kind="slot")],
            )
            res = service.lab_accept(
                {"name": "sparkle", "updated": "2026-07-16T00:00:00+00:00", "target_role": "drop"}
            )
            self.assertTrue(res.get("ok"), res)
            config = copy.deepcopy(service._draft)
            spec, _cue = service._play_spec(config, "sparkle", None)
            self.assertEqual(spec["scene_ref"], "lab_sparkle")
            # Slot kind → engine injects a slot_colors palette (not a single color).
            self.assertIn("slot_colors", spec["params"])

    def test_end_to_end_runner_emits_nonblank_frames(self) -> None:
        """Real dry-run PadPlayback: play by name → runner tees a lit frame."""
        with tempfile.TemporaryDirectory() as td:
            service, _cfg = _service(td)  # real dry-run PadPlayback
            try:
                service.lab_accept(
                    {"name": "pulse", "updated": "2026-07-16T00:00:00+00:00", "target_role": "drop"}
                )
                res = service.play({"name": "pulse", "takeover": True})
                self.assertTrue(res.get("ok"), res)
                self.assertEqual(res["spec"]["scene_ref"], "lab_pulse")

                ring = service.mirror_ring()
                self.assertIsNotNone(ring)
                lit = None
                deadline = time.time() + 4.0
                while time.time() < deadline:
                    entry = ring.latest()
                    if entry is not None and any(px != (0, 0, 0) for px in entry[1]):
                        lit = entry[1]
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(lit, "runner never emitted a non-blank frame for the lab cue")
            finally:
                service.shutdown()


class LabCueFirstClassUiTests(unittest.TestCase):
    """BUG 1 labeling: pad UI treats lab: scene_refs as a Lab cue, not cloud."""

    def _pad(self) -> str:
        return (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")

    def test_lab_scene_helpers_present(self) -> None:
        src = self._pad()
        self.assertIn("function isLabScene(sceneRef)", src)
        self.assertIn("function labCueName(sceneRef)", src)
        self.assertIn('String(sceneRef || "").startsWith("lab:")', src)

    def test_lab_cue_card_is_playable_and_badged_not_cloud(self) -> None:
        src = self._pad()
        # Play enablement keys off `playable = realtime || labScene`, not realtime.
        self.assertIn("const playable = realtime || labScene;", src)
        self.assertIn("${!playable ?", src)
        # Lab cues get a "Lab cue" badge; cloud branding only for genuinely-unknown scenes.
        self.assertIn("<span class='badge'>Lab cue</span>", src)
        self.assertIn("const classBadge = labScene", src)

    def test_editor_renderer_select_labels_lab_cue_not_cloud(self) -> None:
        src = self._pad()
        self.assertIn("isLabScene(sceneRef)", src)
        self.assertIn("Lab cue — ${esc(labCueName(sceneRef))}", src)
        # Read-only lab param display + pointer to Lab view (no new edit pipeline).
        self.assertIn("function renderLabCueControls()", src)
        self.assertIn("Change this cue's motion and colors in the", src)


class TimingNoteDemotionTests(unittest.TestCase):
    """BUG 2: the Timing dropdown is demoted to a read-only design note."""

    def test_timing_select_removed_from_shell_markup(self) -> None:
        # lab.html is a symlink to the shared shell (index.html).
        html = (_ASSETS / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('id="timingModeSelect"', html)
        self.assertNotIn("Timing mode", html)  # the old aria-label of the control
        # The read-only note replaces it; the badge id survives (now visible).
        self.assertIn('class="lab-timing-note"', html)
        self.assertIn('id="timingText"', html)
        self.assertIn("doesn't change how the cue plays", html)

    def test_lab_js_no_longer_reads_the_select(self) -> None:
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        self.assertNotIn("timingModeSelect", lab)
        # Stored value is carried (not stranded) into save/stash payloads.
        self.assertIn('timing_mode: (state.current || {}).timing_mode || "unknown"', lab)
        # BPM-scope hint still reads the design note honestly.
        self.assertIn("function renderBpmScope()", lab)
        self.assertNotIn("Set timing (header) to enable BPM", lab)

    def test_timing_field_still_persists_through_save(self) -> None:
        """Keep-the-data: the demoted note's value round-trips through the registry."""
        from rb_ss_bridge_v2.tools.led_pad_web import LedPadService

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = root / "led_look_director.json"
            cfg.write_text(_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            lab_dir = root / "led_lab"
            lab_dir.mkdir()
            (lab_dir / "effects_lab.py").write_text(_GOOD_LAB, encoding="utf-8")
            service = LedPadService(cfg, dry_run=True, playback=_FakePlayback(), lab_dir=lab_dir)
            service.lab_save({
                "name": "pulse", "kind": "frame", "fn": "pulse", "params": {},
                "cue_beats": 8, "timing_mode": "mixed", "brief": "x",
            })
            # A later save that omits timing_mode must preserve the stored value.
            service.lab_save({
                "name": "pulse", "kind": "frame", "fn": "pulse", "params": {"a": 1},
                "cue_beats": 8, "brief": "y", "overwrite": True,
            })
            self.assertEqual(service._lab.get("pulse")["timing_mode"], "mixed")


if __name__ == "__main__":
    unittest.main()
