from __future__ import annotations

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


class _FakeMidiOutput:
    def __init__(self, *, dry_run: bool, degraded: bool = False, running: bool = True) -> None:
        self._dry_run = dry_run
        self._degraded = degraded
        self._running = running
        self.calls: list[tuple[LaserMidiMessage, str]] = []
        self.trigger_result = True

    def trigger(self, msg: LaserMidiMessage, priority: str = "normal") -> bool:
        self.calls.append((msg, priority))
        return self.trigger_result

    def status(self) -> dict:
        return {
            "available": True,
            "running": self._running,
            "dry_run": self._dry_run,
            "degraded": self._degraded,
            "degraded_reason": "send_error" if self._degraded else "",
            "port_name": "IAC Driver Bus 1",
            "queue_size": 0,
            "queue_max": 64,
            "trigger_count": len(self.calls),
            "drop_count": 0,
            "rejected_count": 0,
            "send_error_count": 0,
            "sent_count": len(self.calls),
            "panic_count": 0,
            "last_error": "",
        }


def _scene(name: str, *, safety_class: str = "safe", note: int = 36) -> LaserScene:
    return LaserScene(
        name=name,
        scene_type="autoloop",
        safety_class=safety_class,
        midi=LaserMidiMessage(kind="note_pulse", channel=1, note=note, velocity=127, duration_ms=80),
    )


def _ctx(
    *,
    playing: bool = True,
    active_track_loaded: bool = True,
    position_stale: bool = False,
    lighting_mode: str = "autoloop",
    scripted_id: int = 0,
    autoloop_ready: bool = True,
    autoloop_tick_just_fired: bool = False,
) -> LaserContext:
    return LaserContext(
        active_deck=1,
        playing=playing,
        elapsed_ms=1000,
        bpm=128.0,
        beatpos=0.0,
        abs_beat=64.0,
        position_stale=position_stale,
        lighting_mode=lighting_mode,
        os2l_connected=True,
        active_track_loaded=active_track_loaded,
        autoloop_ready=autoloop_ready,
        autoloop_tick_just_fired=autoloop_tick_just_fired,
        scripted_id=scripted_id,
    )


def _decision(scene: str, reason: str, role: str) -> LaserSceneDecision:
    return LaserSceneDecision(scene=scene, reason=reason, priority=10, source="policy", role=role)


def _personality(*, allow_high_impact: bool = True) -> LaserPersonality:
    return LaserPersonality(
        name="house",
        safe_scene="safe",
        default_scene="phrase_a",
        phrase_scene="phrase_a",
        buildup_scene="buildup_a",
        pre_drop_scene="",
        drop_scene="drop_a",
        post_drop_scene="post_a",
        breakdown_scene="break_a",
        transition_scene="safe",
        phrase_bank=("phrase_a", "phrase_b"),
        buildup_bank=("buildup_a", "buildup_b"),
        drop_bank=("drop_a", "drop_b"),
        post_drop_bank=("post_a",),
        breakdown_bank=("break_a",),
        allow_high_impact=allow_high_impact,
    )


def _config(*, dry_run: bool = True) -> LaserConfig:
    scenes = {
        "safe": _scene("safe", note=36),
        "phrase_a": _scene("phrase_a", note=37),
        "phrase_b": _scene("phrase_b", note=38),
        "buildup_a": _scene("buildup_a", note=39),
        "buildup_b": _scene("buildup_b", note=40),
        "drop_a": _scene("drop_a", safety_class="high_impact", note=41),
        "drop_b": _scene("drop_b", note=42),
        "post_a": _scene("post_a", note=43),
        "break_a": _scene("break_a", note=44),
    }
    personality = _personality()
    return LaserConfig(
        enabled=True,
        dry_run=dry_run,
        midi_output_port="IAC Driver Bus 1",
        scenes=scenes,
        personalities={"house": personality},
        default_personality="house",
        startup_scene="safe",
        stop_scene="safe",
        stale_scene="safe",
        emergency_scene="safe",
        fallback_scene="safe",
    )


class LaserSceneExecutorTests(unittest.TestCase):
    def test_scene_empty_never_triggers(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        ex.on_decision(_decision("", "not_playing", "idle"), _ctx())
        self.assertEqual(midi.calls, [])

    def test_dry_run_false_triggers_once_on_valid_transition(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        ex.on_decision(_decision("phrase_a", "phrase_hold", "phrase"), _ctx())
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(midi.calls[0][1], "normal")

    def test_automatic_gates_block_stopped_no_track_stale_scripted_not_ready(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        decision = _decision("phrase_a", "default_init", "phrase")
        ex.on_decision(decision, _ctx(playing=False))
        ex.on_decision(decision, _ctx(active_track_loaded=False))
        ex.on_decision(decision, _ctx(position_stale=True))
        ex.on_decision(decision, _ctx(scripted_id=7))
        ex.on_decision(decision, _ctx(autoloop_ready=False))
        self.assertEqual(midi.calls, [])

    def test_missing_scene_mapping_safe_noop_records_error(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        ex.on_decision(
            LaserSceneDecision(
                scene="missing_scene",
                reason="manual_override",
                priority=2,
                source="manual",
                role="manual",
            ),
            _ctx(),
        )
        status = ex.status()
        self.assertEqual(len(midi.calls), 0)
        self.assertEqual(status["missing_scene_count"], 1)
        self.assertIn("missing_scene_mapping", status["last_error"])

    def test_trigger_false_is_handled_safely(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        midi.trigger_result = False
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(ex.status()["last_error"], "midi_trigger_rejected")

    def test_same_scene_reason_only_update_does_not_retrigger(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        ex.on_decision(_decision("phrase_a", "phrase_hold", "phrase"), _ctx())
        self.assertEqual(len(midi.calls), 1)

    def test_buildup_bank_holds_through_countdown(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        for _ in range(20):
            ex.on_decision(_decision("buildup_a", "buildup_to_drop_window", "buildup"), _ctx())
        self.assertEqual(len(midi.calls), 1)

    def test_drop_bank_rotates_each_crossing(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        self.assertEqual(len(midi.calls), 3)
        first_note = midi.calls[0][0].note
        second_note = midi.calls[2][0].note
        self.assertNotEqual(first_note, second_note)
        self.assertEqual(midi.calls[0][1], "high")
        self.assertEqual(midi.calls[2][1], "high")

    def test_post_drop_triggers_once(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx())
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx())
        self.assertEqual(len(midi.calls), 1)

    def test_phrase_waits_for_boundary_not_immediate_after_post_drop(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx())
        ex.on_decision(_decision("phrase_a", "default", "phrase"), _ctx(autoloop_tick_just_fired=False))
        self.assertEqual(len(midi.calls), 2)
        ex.on_decision(_decision("phrase_a", "phrase_boundary", "phrase"), _ctx(autoloop_tick_just_fired=True))
        self.assertEqual(len(midi.calls), 3)
        self.assertEqual(midi.calls[-1][1], "normal")

    def test_high_impact_blocked_when_personality_disallows(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        personality = _personality(allow_high_impact=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=personality)
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        self.assertEqual(len(midi.calls), 0)
        self.assertEqual(ex.status()["last_error"], "high_impact_blocked")

    def test_emergency_bypasses_high_impact_block(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        personality = _personality(allow_high_impact=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=personality)
        ex.on_decision(
            LaserSceneDecision(
                scene="drop_a",
                reason="emergency",
                priority=1,
                source="emergency",
                role="emergency",
            ),
            _ctx(playing=False, autoloop_ready=False),
        )
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(midi.calls[0][1], "high")

    def test_personality_reset_clears_bank_state(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), midi_output=midi, personality=_personality())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        ex.set_personality(_personality())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        self.assertEqual(len(midi.calls), 2)
        # After reset, first bank value is chosen again.
        self.assertEqual(midi.calls[0][0].note, midi.calls[1][0].note)


if __name__ == "__main__":
    unittest.main()
