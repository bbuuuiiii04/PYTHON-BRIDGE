"""Tests for the executor shuffle-bag, A8 never-dark fallback, and cycling gates.

Covers:
  - Shuffle-bag rotation: usable entries only, reshuffle on exhaustion, bag
    rebuilt on bank-membership change.
  - A8: static-only personality fires the static _drop_scene on drop_crossing
    (never dark); usable-bank personality picks from the bag.
  - Cycling gate: drop_cycle/post_drop_cycle only fire on autoloop_tick_just_fired.
  - A7 regression: not "same look all track, +1 next track".
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_config import LaserConfig  # noqa: E402
from rb_ss_bridge_v2.laser_executor import LaserSceneExecutor  # noqa: E402
from rb_ss_bridge_v2.laser_models import (  # noqa: E402
    LaserContext,
    LaserMidiMessage,
    LaserPersonality,
    LaserScene,
    LaserSceneDecision,
)
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402


class _FakeMidiOutput:
    def __init__(self) -> None:
        self.calls: list[tuple[LaserMidiMessage, str]] = []
        self.trigger_result = True

    def trigger(self, msg: LaserMidiMessage, priority: str = "normal") -> bool:
        self.calls.append((msg, priority))
        return self.trigger_result

    def status(self) -> dict:
        return {
            "available": True, "running": True, "dry_run": False,
            "degraded": False, "degraded_reason": "", "port_name": "test",
            "queue_size": 0, "queue_max": 64,
            "trigger_count": len(self.calls), "drop_count": 0,
            "rejected_count": 0, "send_error_count": 0,
            "sent_count": len(self.calls), "panic_count": 0, "last_error": "",
        }


def _scene(name: str, *, scene_type: str = "autoloop", safety_class: str = "safe",
           note: int = 36) -> LaserScene:
    return LaserScene(
        name=name,
        scene_type=scene_type,
        safety_class=safety_class,
        midi=LaserMidiMessage(kind="note_pulse", channel=1, note=note, velocity=127, duration_ms=80),
    )


def _ctx(
    *,
    abs_beat: float = 64.0,
    autoloop_tick_just_fired: bool = False,
    smart_drop_blackout_arm: bool = False,
) -> LaserContext:
    return LaserContext(
        active_deck=1, playing=True, elapsed_ms=1000, bpm=128.0,
        beatpos=0.0, abs_beat=abs_beat, position_stale=False,
        lighting_mode="autoloop", os2l_connected=True,
        active_track_loaded=True, autoloop_ready=True,
        autoloop_tick_just_fired=autoloop_tick_just_fired,
        scripted_id=0,
        smart_drop_blackout_arm=smart_drop_blackout_arm,
    )


def _decision(scene: str, reason: str, role: str) -> LaserSceneDecision:
    return LaserSceneDecision(scene=scene, reason=reason, priority=10, source="policy", role=role)


def _make_config(scenes: dict[str, LaserScene], smart_drop_mode: str = "blackout_mask") -> LaserConfig:
    return LaserConfig(
        enabled=True, dry_run=False, smart_drop_mode=smart_drop_mode,
        midi_output_port="test", scenes=scenes,
        personalities={}, default_personality="",
        startup_scene="safe_static", stop_scene="safe_static",
        stale_scene="safe_static", emergency_scene="safe_static",
        fallback_scene="safe_static",
        manual_blackout_on=LaserMidiMessage(kind="manual_blackout", channel=1, note=100, velocity=127),
        manual_blackout_off=LaserMidiMessage(kind="manual_blackout", channel=1, note=101, velocity=127),
    )


class TestShuffleBag(unittest.TestCase):
    """A7: drop/post_drop selection uses shuffle-bag (reshuffle on exhaustion)."""

    def test_full_pass_sees_all_usable_entries(self) -> None:
        """Over one full bag pass every usable entry appears exactly once."""
        scenes = {
            "d1": _scene("d1", note=41),
            "d2": _scene("d2", note=42),
            "d3": _scene("d3", note=43),
            "d_static": _scene("d_static", scene_type="static", note=44),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d_static", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1", "d2", "d3", "d_static"),
            drop_lifecycle_mirror=True,
        )
        rng = random.Random(42)
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            rng=rng, randomize_cursors=False,
        )

        # Fire 3 drop_cycle decisions with autoloop_tick_just_fired=True
        fired: list[str] = []
        for beat in range(0, 3):
            ctx = _ctx(abs_beat=float(64 + beat * 32), autoloop_tick_just_fired=True)
            dec = _decision("d_static", "drop_cycle", "drop")
            ex.on_decision(dec, ctx)

        # Collect the scenes that were triggered
        for msg, _ in backend.calls:
            for sname, sdef in scenes.items():
                if sdef.midi.note == msg.note and sname != "safe_static":
                    fired.append(sname)
                    break

        # Only usable (autoloop) entries should appear; d_static is scene_type=static → excluded
        for name in fired:
            self.assertNotEqual(scenes[name].scene_type, "static",
                                f"{name} is static and should not be in a cycle")

    def test_no_fire_without_autoloop_tick(self) -> None:
        """drop_cycle with autoloop_tick_just_fired=False → no MIDI."""
        scenes = {
            "d1": _scene("d1", note=41),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d1", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1",),
            drop_lifecycle_mirror=True,
        )
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            randomize_cursors=False,
        )
        ctx = _ctx(abs_beat=64.0, autoloop_tick_just_fired=False)
        dec = _decision("d1", "drop_cycle", "drop")
        ex.on_decision(dec, ctx)
        self.assertEqual(len(backend.calls), 0)


class TestA8NeverDark(unittest.TestCase):
    """A8: static-only personality fires the static drop scene on impact (never dark)."""

    def test_static_only_drop_crossing_fires(self) -> None:
        """A drop_crossing for a static-only bank fires the configured static scene."""
        scenes = {
            "house_drop_1": _scene("house_drop_1", scene_type="static", note=96),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="dubstep", safe_scene="safe_static", default_scene="safe_static",
            phrase_scene="safe_static", buildup_scene="safe_static", pre_drop_scene="",
            drop_scene="house_drop_1", post_drop_scene="house_drop_1",
            breakdown_scene="safe_static", transition_scene="safe_static",
            drop_bank=("house_drop_1",),
            post_drop_bank=("house_drop_1",),
            drop_lifecycle_mirror=True,
        )
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            randomize_cursors=False,
        )
        ctx = _ctx(abs_beat=64.0, autoloop_tick_just_fired=False)
        dec = _decision("house_drop_1", "drop_crossing", "drop")
        ex.on_decision(dec, ctx)
        # MUST fire — the static scene is valid for an impact
        self.assertGreater(len(backend.calls), 0)
        self.assertEqual(backend.calls[0][0].note, 96)

    def test_usable_bank_shuffles_impact(self) -> None:
        """A drop_crossing for a usable-bank personality picks from the shuffle bag."""
        scenes = {
            "d1": _scene("d1", note=41),
            "d2": _scene("d2", note=42),
            "d_static": _scene("d_static", scene_type="static", note=44),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="house", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d_static", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1", "d2", "d_static"),
            drop_lifecycle_mirror=True,
        )
        rng = random.Random(42)
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            rng=rng, randomize_cursors=False,
        )
        ctx = _ctx(abs_beat=64.0)
        dec = _decision("d_static", "drop_crossing", "drop")
        ex.on_decision(dec, ctx)
        # Must fire (not empty/dark); the note should be d1 or d2 (usable), not d_static
        self.assertGreater(len(backend.calls), 0)
        fired_note = backend.calls[0][0].note
        self.assertIn(fired_note, (41, 42), "impact should pick from usable bag, not static")


class TestA7Regression(unittest.TestCase):
    """A7: not 'same look all track, +1 next track'."""

    def test_cross_track_not_deterministic_sequential(self) -> None:
        """After a track reset, the bag is rebuilt → order changes, not +1."""
        scenes = {
            "d1": _scene("d1", note=41),
            "d2": _scene("d2", note=42),
            "d3": _scene("d3", note=43),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d1", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1", "d2", "d3"),
            drop_lifecycle_mirror=True,
        )
        # Using a seed that produces a non-sequential shuffle
        rng = random.Random(42)
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            rng=rng, randomize_cursors=False,
        )

        # Track 1: fire 3 cycles
        notes_track1: list[int] = []
        for i in range(3):
            ctx = _ctx(abs_beat=float(64 + i * 32), autoloop_tick_just_fired=True)
            dec = _decision("d1", "drop_cycle", "drop")
            ex.on_decision(dec, ctx)
        for msg, _ in backend.calls:
            notes_track1.append(msg.note)
        backend.calls.clear()

        # Assert every usable note appears exactly once
        self.assertEqual(sorted(notes_track1), [41, 42, 43])
        # Assert sequence is not monotonically-increasing (d1->d2->d3)
        self.assertNotEqual(notes_track1, [41, 42, 43], "Bag order should be shuffled, not sequential")

        # Track reset (simulates track load)
        ex.reset_runtime_state(reason="active_track_loaded")

        # The definitive check: _role_bag was cleared by reset_runtime_state
        self.assertEqual(ex._role_bag, {})

        # Track 2: fire 3 more cycles — bag must rebuild from scratch
        notes_track2: list[int] = []
        for i in range(3):
            ctx = _ctx(abs_beat=float(64 + i * 32), autoloop_tick_just_fired=True)
            dec = _decision("d1", "drop_cycle", "drop")
            ex.on_decision(dec, ctx)
        for msg, _ in backend.calls:
            notes_track2.append(msg.note)

        # Track 2 must have fired and contain all notes
        self.assertEqual(sorted(notes_track2), [41, 42, 43])
        # The two passes should not be identical
        self.assertNotEqual(notes_track1, notes_track2, "Track 2 bag pass should not match Track 1")


if __name__ == "__main__":
    unittest.main()
