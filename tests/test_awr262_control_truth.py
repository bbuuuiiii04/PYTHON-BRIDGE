"""AWR-262: every pad-visible control must change rendered frames.

Regrowth barrier for the dim_beats / heads class of dead knobs. For each
effect × each key in EFFECT_VISIBLE_KEYS, render two frames with the key at
two distinct values (seeded, fixed beat grid) and assert the output differs.

Exempted keys need a one-line justification in VISIBLE_DRIFT_EXEMPTIONS.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.beat_sync_engine import BeatSyncEngine  # noqa: E402
from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    GoveeFrameRenderer,
    default_beat_division,
    default_sync_mode,
    is_comet_effect,
    _OVERLAP_EFFECTS,
)
from rb_ss_bridge_v2.led_pad_controls import (  # noqa: E402
    CONTROL_META,
    EFFECT_VISIBLE_KEYS,
    controls_for,
)


SEGMENTS = 24
SEED = 42
BPM = 128.0

# Fixed probe grid: early beats + post-intro (≥8) so chase travel/width engage,
# plus fine fractions so strobe duty/subdivision windows are visible.
_BEAT_GRID = (
    0.0, 0.05, 0.15, 0.35, 0.55, 0.75,
    1.0, 2.0, 4.0, 8.0, 10.0, 12.0, 16.0, 33.0, 40.0,
)
_LOCAL_T_GRID = (0.0, 0.02, 0.05, 0.08, 0.12, 0.2, 0.4)

# (effect, key) → why a fixed two-value probe cannot prove a frame delta.
VISIBLE_DRIFT_EXEMPTIONS: dict[tuple[str, str], str] = {
    **{
        (name, "spawn_on_wrap"): "requires a beat wrap event (TriggerClock.spawn_on_wrap)"
        for name in _OVERLAP_EFFECTS
    },
    **{
        (name, "max_pulses"): "only differs when multiple overlap instances are active"
        for name in _OVERLAP_EFFECTS
    },
}


def _probe_values(key: str, meta: dict[str, Any]) -> tuple[Any, Any]:
    kind = meta["kind"]
    if kind == "bool":
        return False, True
    if kind == "choice":
        choices = list(meta.get("choices") or [])
        if key == "sync_mode":
            # Prefer modes that change restart behavior on a forward grid.
            if "retrigger" in choices and "continuous" in choices:
                return "retrigger", "continuous"
            if "overlap" in choices and "continuous" in choices:
                return "overlap", "continuous"
        if len(choices) < 2:
            raise AssertionError(f"choice key needs ≥2 options: {key}")
        return choices[0], choices[1]
    if kind == "rgb":
        return [255, 0, 0], [0, 0, 255]
    # Key-specific pairs that actually move pixels inside the fixed grid.
    if key == "duration_beats":
        return 8.0, 32.0
    if key == "beat_division":
        return 0.5, 1.0
    if key == "duty":
        # _hz_strobe_on clamps duty to ≤0.5 — stay inside the live range.
        return 0.1, 0.5
    if key == "hz":
        return 2.0, 8.0
    if key == "travel_beats":
        return 2.0, 8.0
    if key == "width":
        return 0.5, 3.0
    if key == "ember_decay_beats":
        return 0.0, 4.0
    if key == "ember_hold_beats":
        return 4.0, 16.0
    lo = meta.get("min")
    hi = meta.get("max")
    default = meta.get("default")
    step = float(meta.get("step") or 1)
    if default is not None:
        a = float(default)
        b = a + step
        if hi is not None and b > float(hi):
            b = float(hi)
            a = max(float(lo) if lo is not None else b - step, b - step)
        if a != b:
            return a, b
    if lo is not None and hi is not None and float(lo) != float(hi):
        return float(lo), float(hi)
    return 1.0, 2.0


def _base_params(effect: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "color": [255, 80, 40],
        "bg": [10, 10, 20],
        "color_a": [255, 0, 0],
        "color_b": [0, 0, 255],
        "spark_a": [255, 200, 40],
        "spark_b": [255, 40, 40],
        "slot_colors": [
            (255, 40, 40),
            (40, 255, 40),
            (40, 40, 255),
            (255, 255, 40),
            (255, 40, 255),
        ],
        # Hold the Hz gate open enough that motion knobs are visible.
        "hz": 6.0,
        "duty": 0.5,
        "frame_period_s": 0.025,
    }
    for control in controls_for(effect):
        if control["default"] is not None and control["key"] not in params:
            params[control["key"]] = control["default"]
    params.setdefault("travel_beats", 2.0)
    params.setdefault("width", 1.2)
    params.setdefault("trail_beats", 0.5)
    params.setdefault("beat_division", 1.0)
    params.setdefault("sync_mode", default_sync_mode(effect))
    params.setdefault("duration_beats", 32.0)
    return params


def _compose_frames(effect: str, params: dict[str, Any]) -> list[tuple[tuple[int, int, int], ...]]:
    """Render a fixed beat × local_t grid.

    Comet-motion looks go through BeatSyncEngine (progress/direction). All other
    looks use direct ``GoveeFrameRenderer.render`` on a rich beat/local_t grid so
    strobe duty/hz and beat-phase knobs are observable.
    """
    renderer = GoveeFrameRenderer()
    frames: list[tuple[tuple[int, int, int], ...]] = []

    if is_comet_effect(effect):
        engine = BeatSyncEngine()
        mode = str(params.get("sync_mode") or default_sync_mode(effect))
        division = float(params.get("beat_division") or default_beat_division(effect))
        now0 = 1000.0
        engine.configure(
            effect_name=effect,
            sync_mode=mode,
            beat_division=division,
            params=params,
            seed=SEED,
            now=now0,
            abs_beat=0.0,
            bpm=BPM,
        )
        for abs_beat in _BEAT_GRID:
            now = now0 + abs_beat * (60.0 / BPM)
            instances = engine.on_tick(abs_beat, now, BPM)
            if not instances:
                frames.append(tuple(renderer.blank(SEGMENTS)))
                continue
            width = float(params.get("width", 0.8))
            direction = engine.direction
            parts = [
                renderer.render_comet(
                    effect,
                    progress=ir.progress,
                    segments=SEGMENTS,
                    width=width,
                    direction=direction,
                    params=params,
                )
                for ir in instances
            ]
            frame = renderer.fold_additive(parts, SEGMENTS)
            frames.append(tuple(tuple(px) for px in frame))
        return frames

    # Class B effects that need engine restart/bucket behavior.
    if effect in ("drop_burst", "sparkle"):
        engine = BeatSyncEngine()
        mode = str(params.get("sync_mode") or default_sync_mode(effect))
        division = float(params.get("beat_division") or default_beat_division(effect))
        now0 = 1000.0
        engine.configure(
            effect_name=effect,
            sync_mode=mode,
            beat_division=division,
            params=params,
            seed=SEED,
            now=now0,
            abs_beat=0.0,
            bpm=BPM,
        )
        for i, abs_beat in enumerate(_BEAT_GRID):
            now = now0 + abs_beat * (60.0 / BPM)
            instances = engine.on_tick(abs_beat, now, BPM)
            if not instances:
                frames.append(tuple(renderer.blank(SEGMENTS)))
                continue
            ir = instances[0]
            frame = renderer.render(
                effect,
                beat_pos=ir.local_beat,
                local_t=ir.local_t,
                frame_index=i,
                params=params,
                segments=SEGMENTS,
                seed=SEED ^ int(ir.bucket),
            )
            frames.append(tuple(tuple(px) for px in frame))
        return frames

    for i, beat in enumerate(_BEAT_GRID):
        for local_t in _LOCAL_T_GRID:
            frame = renderer.render(
                effect,
                beat_pos=float(beat),
                local_t=float(local_t),
                frame_index=i,
                params=params,
                segments=SEGMENTS,
                seed=SEED,
            )
            frames.append(tuple(tuple(px) for px in frame))
    return frames


class VisibleControlDriftTests(unittest.TestCase):
    def test_every_visible_key_changes_frames_or_is_exempt(self) -> None:
        failures: list[str] = []
        checked = 0
        for effect, keys in sorted(EFFECT_VISIBLE_KEYS.items()):
            if effect == "blackout":
                self.assertEqual(keys, ())
                continue
            meta_by_key = {item["key"]: item for item in controls_for(effect)}
            for key in keys:
                if (effect, key) in VISIBLE_DRIFT_EXEMPTIONS:
                    self.assertTrue(VISIBLE_DRIFT_EXEMPTIONS[(effect, key)].strip())
                    continue
                meta = meta_by_key[key]
                a, b = _probe_values(key, meta)
                base = _base_params(effect)
                frames_a = _compose_frames(effect, {**base, key: a})
                frames_b = _compose_frames(effect, {**base, key: b})
                checked += 1
                if frames_a == frames_b:
                    failures.append(f"{effect}.{key} values={a!r}/{b!r}")
        self.assertFalse(
            failures,
            "visible controls with identical frames (add exemption or fix map):\n  "
            + "\n  ".join(failures),
        )
        self.assertGreater(checked, 50)

    def test_exemptions_only_cover_visible_keys(self) -> None:
        for effect, key in VISIBLE_DRIFT_EXEMPTIONS:
            self.assertIn(key, EFFECT_VISIBLE_KEYS[effect], (effect, key))

    def test_heads_never_visible(self) -> None:
        for effect, keys in EFFECT_VISIBLE_KEYS.items():
            self.assertNotIn("heads", keys, effect)
        self.assertIn("heads", CONTROL_META)


if __name__ == "__main__":
    unittest.main()
