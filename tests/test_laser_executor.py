from __future__ import annotations

from dataclasses import replace
import logging
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_config import LaserConfig  # noqa: E402
from rb_ss_bridge_v2.laser_executor import LaserSceneExecutor  # noqa: E402
from rb_ss_bridge_v2.laser_output_backend import (  # noqa: E402
    MidiOutputBackend,
    NoneBackend,
    PackOutputBackend,
)
from rb_ss_bridge_v2.laser_models import (  # noqa: E402
    LaserContext,
    LaserMidiMessage,
    LaserPersonality,
    LaserScene,
    LaserSceneDecision,
)
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402


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
    abs_beat: float = 64.0,
    smart_drop_blackout_active: bool = False,
    smart_drop_blackout_arm: bool = False,
    smart_phrasing_blackout_arm: bool = False,
    smart_phrasing: SmartPhrasingState | None = None,
) -> LaserContext:
    return LaserContext(
        active_deck=1,
        playing=playing,
        elapsed_ms=1000,
        bpm=128.0,
        beatpos=0.0,
        abs_beat=abs_beat,
        position_stale=position_stale,
        lighting_mode=lighting_mode,
        os2l_connected=True,
        active_track_loaded=active_track_loaded,
        autoloop_ready=autoloop_ready,
        autoloop_tick_just_fired=autoloop_tick_just_fired,
        scripted_id=scripted_id,
        smart_drop_blackout_active=smart_drop_blackout_active,
        smart_drop_blackout_arm=smart_drop_blackout_arm,
        smart_phrasing_blackout_arm=smart_phrasing_blackout_arm,
        smart_phrasing=smart_phrasing,
    )


def _smart_phrasing_state(*, transition_mask_should_clear: bool) -> SmartPhrasingState:
    return SmartPhrasingState(
        current_phrase_label="other",
        current_phrase_is_up=False,
        current_phrase_is_chorus=False,
        current_phrase_is_low=False,
        next_smart_drop_beat=None,
        beats_to_next_drop=None,
        smart_drop_window_active=False,
        smart_drop_crossing=False,
        smart_drop_preclear_requested=False,
        smart_drop_rearm_requested=False,
        smart_post_drop_active=False,
        active_drop_beat=None,
        smart_buildup_active=False,
        smart_breakdown_active=False,
        breakdown_start_crossing=False,
        breakdown_end_crossing=False,
        smart_breakdown_clear_requested=False,
        smart_breakdown_restore_requested=False,
        transition_mask_should_arm=False,
        transition_mask_should_clear=transition_mask_should_clear,
        transition_window_active=False,
        phrase_anchor_requested=False,
        phrase_anchor_preclear_requested=False,
        phrase_anchor_rearm_requested=False,
        phrase_anchor_target_beat=None,
        reason="test",
    )


def _decision(scene: str, reason: str, role: str) -> LaserSceneDecision:
    return LaserSceneDecision(scene=scene, reason=reason, priority=10, source="policy", role=role)


def _personality(*, allow_high_impact: bool = True, rotating_banks: bool = False) -> LaserPersonality:
    phrase_bank = ("phrase_a", "phrase_b") if rotating_banks else ("phrase_a",)
    buildup_bank = ("buildup_a", "buildup_b") if rotating_banks else ("buildup_a",)
    drop_bank = ("drop_a", "drop_b") if rotating_banks else ("drop_a",)
    return LaserPersonality(
        name="house",
        safe_scene="safe",
        default_scene="phrase_a",
        phrase_scene="phrase_a",
        buildup_scene="buildup_a",
        drop_scene="drop_a",
        post_drop_scene="post_a",
        breakdown_scene="break_a",
        transition_scene="safe",
        phrase_bank=phrase_bank,
        buildup_bank=buildup_bank,
        drop_bank=drop_bank,
        post_drop_bank=("post_a",),
        breakdown_bank=("break_a",),
        allow_high_impact=allow_high_impact,
        drop_lifecycle_mirror=False,
    )


def _drop_mode_personality(*, allow_high_impact: bool = True) -> LaserPersonality:
    return LaserPersonality(
        name="house",
        safe_scene="safe",
        default_scene="phrase_a",
        phrase_scene="phrase_a",
        buildup_scene="buildup_a",
        drop_scene="drop_a",
        post_drop_scene="drop_a",
        breakdown_scene="break_a",
        transition_scene="safe",
        phrase_bank=("phrase_a", "phrase_b"),
        buildup_bank=("buildup_a", "buildup_b"),
        drop_bank=("drop_a",),
        post_drop_bank=("drop_a",),
        breakdown_bank=("break_a",),
        allow_high_impact=allow_high_impact,
        drop_lifecycle_mirror=False,
    )


def _single_drop_scene_personality(*, allow_high_impact: bool = True) -> LaserPersonality:
    return LaserPersonality(
        name="house",
        safe_scene="safe",
        default_scene="phrase_a",
        phrase_scene="phrase_a",
        buildup_scene="buildup_a",
        drop_scene="drop_a",
        post_drop_scene="post_a",
        breakdown_scene="break_a",
        transition_scene="safe",
        phrase_bank=("phrase_a",),
        buildup_bank=("buildup_a",),
        drop_bank=("drop_a",),
        post_drop_bank=("post_a",),
        breakdown_bank=("break_a",),
        allow_high_impact=allow_high_impact,
        drop_lifecycle_mirror=False,
    )


def _config(
    *,
    dry_run: bool = True,
    smart_drop_mode: str = "blackout_mask",
    manual_blackout_on=None,
    manual_blackout_off=None,
) -> LaserConfig:
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
        smart_drop_mode=smart_drop_mode,
        midi_output_port="IAC Driver Bus 1",
        scenes=scenes,
        personalities={"house": personality},
        default_personality="house",
        startup_scene="safe",
        stop_scene="safe",
        stale_scene="safe",
        emergency_scene="safe",
        fallback_scene="safe",
        manual_blackout_on=manual_blackout_on,
        manual_blackout_off=manual_blackout_off,
    )


def _config_with_role_cooldowns(
    *,
    dry_run: bool = True,
    smart_drop_mode: str = "blackout_mask",
    manual_blackout_on=None,
    manual_blackout_off=None,
) -> LaserConfig:
    cfg = _config(
        dry_run=dry_run,
        smart_drop_mode=smart_drop_mode,
        manual_blackout_on=manual_blackout_on,
        manual_blackout_off=manual_blackout_off,
    )
    scenes = dict(cfg.scenes)
    scenes["phrase_a"] = LaserScene(
        name="phrase_a",
        scene_type="autoloop",
        safety_class="safe",
        midi=scenes["phrase_a"].midi,
        cooldown_beats=16.0,
    )
    scenes["phrase_b"] = LaserScene(
        name="phrase_b",
        scene_type="autoloop",
        safety_class="safe",
        midi=scenes["phrase_b"].midi,
        cooldown_beats=16.0,
    )
    scenes["buildup_a"] = LaserScene(
        name="buildup_a",
        scene_type="autoloop",
        safety_class="safe",
        midi=scenes["buildup_a"].midi,
        cooldown_beats=8.0,
    )
    scenes["drop_a"] = LaserScene(
        name="drop_a",
        scene_type="autoloop",
        safety_class="safe",
        midi=scenes["drop_a"].midi,
        cooldown_beats=32.0,
    )
    return replace(cfg, scenes=scenes)


def _five_drop_config() -> tuple[LaserConfig, LaserPersonality]:
    cfg = _config(dry_run=False)
    scenes = dict(cfg.scenes)
    scenes.update(
        {
            "drop_c": _scene("drop_c", note=45),
            "drop_d": _scene("drop_d", note=46),
            "drop_e": _scene("drop_e", note=47),
        }
    )
    personality = replace(
        _personality(),
        drop_bank=("drop_a", "drop_b", "drop_c", "drop_d", "drop_e"),
    )
    cfg = replace(cfg, scenes=scenes, personalities={"house": personality})
    return cfg, personality


class LaserSceneExecutorTests(unittest.TestCase):
    def test_smart_drop_mode_controls_blackout_algorithm(self) -> None:
        midi = _FakeMidiOutput(dry_run=True)
        ex_blackout_dry = LaserSceneExecutor(
            config=_config(dry_run=True, smart_drop_mode="blackout_mask"),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex_legacy_live = LaserSceneExecutor(
            config=_config(dry_run=False, smart_drop_mode="legacy_rearm"),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        self.assertTrue(ex_blackout_dry.smart_drop_blackout_enabled())
        self.assertFalse(ex_legacy_live.smart_drop_blackout_enabled())

    def test_scene_empty_never_triggers(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        ex.on_decision(_decision("", "not_playing", "idle"), _ctx())
        self.assertEqual(midi.calls, [])

    def test_dry_run_false_triggers_once_on_valid_transition(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        ex.on_decision(_decision("phrase_a", "phrase_hold", "phrase"), _ctx())
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(midi.calls[0][1], "normal")

    def test_automatic_gates_block_stopped_no_track_stale_scripted_not_ready(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        decision = _decision("phrase_a", "default_init", "phrase")
        ex.on_decision(decision, _ctx(playing=False))
        ex.on_decision(decision, _ctx(active_track_loaded=False))
        ex.on_decision(decision, _ctx(position_stale=True))
        ex.on_decision(decision, _ctx(scripted_id=7))
        ex.on_decision(decision, _ctx(autoloop_ready=False))
        self.assertEqual(midi.calls, [])

    def test_missing_scene_mapping_safe_noop_records_error(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
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
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        resolved = ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(ex.status()["last_error"], "midi_trigger_rejected")
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.scene, "phrase_a")
        self.assertEqual(resolved.channel, 1)
        self.assertEqual(resolved.note, 37)
        self.assertEqual(resolved.scene_type, "autoloop")

    def test_on_decision_returns_resolved_scene_on_success_only_after_selection_gates(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())

        first = ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        skipped = ex.on_decision(_decision("phrase_a", "phrase_hold", "phrase"), _ctx())
        blocked = ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx(playing=False))

        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.role, "phrase")
        self.assertEqual(first.reason, "default_init")
        self.assertEqual(first.scene, "phrase_a")
        self.assertEqual(skipped, None)
        self.assertEqual(blocked, None)

    def test_same_scene_reason_only_update_does_not_retrigger(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        ex.on_decision(_decision("phrase_a", "phrase_hold", "phrase"), _ctx())
        self.assertEqual(len(midi.calls), 1)

    def test_buildup_bank_holds_through_countdown(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        for _ in range(20):
            ex.on_decision(_decision("buildup_a", "buildup_to_drop_window", "buildup"), _ctx())
        self.assertEqual(len(midi.calls), 1)

    def test_drop_bank_rotates_each_crossing(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(rotating_banks=True),
            rng=random.Random(2),
        )
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
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx())
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx())
        self.assertEqual(len(midi.calls), 1)

    def test_phrase_waits_for_boundary_not_immediate_after_post_drop(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx())
        ex.on_decision(_decision("phrase_a", "default", "phrase"), _ctx(autoloop_tick_just_fired=False))
        self.assertEqual(len(midi.calls), 2)
        ex.on_decision(_decision("phrase_a", "phrase_boundary", "phrase"), _ctx(autoloop_tick_just_fired=True))
        self.assertEqual(len(midi.calls), 3)
        self.assertEqual(midi.calls[-1][1], "normal")

    def test_same_scene_phrase_refire_logs_skip_bypass(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx(abs_beat=64.0))

        with self.assertLogs("perf.laser.fired", level="INFO") as captured:
            ex.on_decision(
                _decision("phrase_a", "phrase_boundary", "phrase"),
                _ctx(abs_beat=96.0, autoloop_tick_just_fired=True),
            )

        output = "\n".join(captured.output)
        self.assertIn("same-scene-refire", output)
        self.assertIn("role=phrase", output)
        self.assertIn("scene=phrase_a", output)
        self.assertEqual(len(midi.calls), 2)

    def test_high_impact_blocked_when_personality_disallows(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        personality = _personality(allow_high_impact=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=personality)
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        self.assertEqual(len(midi.calls), 0)
        self.assertEqual(ex.status()["last_error"], "high_impact_blocked")

    def test_drop_bank_skips_high_impact_when_personality_disallows(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        personality = _personality(allow_high_impact=False, rotating_banks=True)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=personality,
            randomize_cursors=False,
        )

        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())

        self.assertEqual([call[0].note for call in midi.calls], [42])
        self.assertEqual(ex.status()["last_scene"], "drop_b")
        self.assertEqual(ex.status()["last_error"], "")

    def test_missing_bank_scene_restores_cursor_and_active_scene(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        personality = replace(_personality(), drop_bank=())
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=personality,
            randomize_cursors=False,
        )
        before = ex.status()

        ex.on_decision(_decision("missing_scene", "drop_crossing", "drop"), _ctx())
        after = ex.status()

        self.assertEqual(len(midi.calls), 0)
        self.assertIn("missing_scene_mapping", after["last_error"])
        self.assertEqual(after["role_cursors"]["drop"], before["role_cursors"]["drop"])
        self.assertEqual(after["role_active_scenes"]["drop"], before["role_active_scenes"]["drop"])

    def test_emergency_bypasses_high_impact_block(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        personality = _personality(allow_high_impact=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=personality)
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

    def test_runtime_reset_preserves_drop_cursor_across_track_lifecycle(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        cfg, personality = _five_drop_config()
        ex = LaserSceneExecutor(
            config=cfg,
            backend=MidiOutputBackend(midi),
            personality=personality,
            rng=random.Random(0),
        )
        notes = []
        for reset_reason in (
            "active_track_loaded",
            "master_changed",
            "stop",
            "active_track_loaded",
            "stop",
            "master_changed",
        ):
            ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
            notes.append(midi.calls[-1][0].note)
            cursor_after_drop = ex.status()["role_cursors"]["drop"]
            ex.reset_runtime_state(reason=reset_reason)
            status = ex.status()
            self.assertEqual(status["role_cursors"]["drop"], cursor_after_drop)
            self.assertEqual(status["role_active_scenes"]["drop"], "")
        self.assertEqual(notes, [41, 42, 45, 46, 47, 41])

    def test_personality_change_reseeds_bank_cursors(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        cfg, personality = _five_drop_config()
        ex = LaserSceneExecutor(
            config=cfg,
            backend=MidiOutputBackend(midi),
            personality=personality,
            rng=random.Random(0),
        )
        self.assertEqual(ex.status()["role_cursors"]["drop"], 0)
        ex.set_personality(replace(personality, name="techno"))
        status = ex.status()
        self.assertEqual(status["role_cursors"]["drop"], 3)
        self.assertEqual(status["role_active_scenes"]["drop"], "")
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        self.assertEqual(midi.calls[-1][0].note, 46)

    def test_single_entry_bank_is_stable_across_runtime_resets(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_single_drop_scene_personality(),
            rng=random.Random(5),
        )
        notes = []
        for reset_reason in ("active_track_loaded", "stop", "master_changed"):
            ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
            notes.append(midi.calls[-1][0].note)
            ex.reset_runtime_state(reason=reset_reason)
        self.assertEqual(notes, [41, 41, 41])

    def test_hold_beats_materializes_with_context_bpm(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        cfg = _config(dry_run=False)
        scenes = dict(cfg.scenes)
        scenes["drop_a"] = LaserScene(
            name="drop_a",
            scene_type="static",
            safety_class="high_impact",
            midi=LaserMidiMessage(
                kind="note_on",
                behavior="hold_beats",
                channel=1,
                note=41,
                velocity=127,
                hold_beats=4,
            ),
        )
        cfg = replace(cfg, scenes=scenes)
        ex = LaserSceneExecutor(config=cfg, backend=MidiOutputBackend(midi), personality=_personality())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx())
        self.assertEqual(len(midi.calls), 1)
        rendered = midi.calls[0][0]
        self.assertEqual(rendered.behavior, "hold_ms")
        self.assertEqual(rendered.hold_ms, 1875)

    def test_drop_crossing_enforces_minimum_pulse_duration(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(config=_config(dry_run=False), backend=MidiOutputBackend(midi), personality=_personality())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=250.0))
        self.assertEqual(len(midi.calls), 1)
        rendered = midi.calls[0][0]
        self.assertEqual(rendered.behavior, "pulse")
        self.assertGreaterEqual(rendered.duration_ms, 120)

    def test_drop_crossing_emits_drop_then_manual_unblack(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        unblack = LaserMidiMessage(
            kind="note_off",
            behavior="note_off",
            channel=1,
            note=90,
            velocity=0,
        )
        ex = LaserSceneExecutor(
            config=_config(
                dry_run=False,
                manual_blackout_on=blackout_on,
                manual_blackout_off=unblack,
            ),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.trigger_blackout_on(_ctx(abs_beat=319.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=320.0))
        self.assertEqual(len(midi.calls), 3)
        self.assertEqual(midi.calls[0][0].note, 89)
        self.assertEqual(midi.calls[1][0].note, 41)
        self.assertEqual(midi.calls[2][0].note, 90)
        self.assertEqual(midi.calls[0][1], "high")
        self.assertEqual(midi.calls[1][1], "high")
        self.assertEqual(midi.calls[2][1], "high")
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_trigger_blackout_on_sends_pulse_message_unaltered(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_pulse",
            behavior="pulse",
            channel=1,
            note=89,
            velocity=127,
            duration_ms=80,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )

        ex.trigger_blackout_on(_ctx(abs_beat=319.0))

        self.assertEqual(len(midi.calls), 1)
        sent, priority = midi.calls[0]
        self.assertEqual(priority, "high")
        self.assertEqual(sent.note, 89)
        self.assertEqual(sent.kind, "note_pulse")
        self.assertEqual(sent.behavior, "pulse")

    def test_blackout_mask_refcount_sends_on_first_and_final_owner(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=89)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=89)
        ex = LaserSceneExecutor(
            config=_config(
                dry_run=False,
                manual_blackout_on=blackout_on,
                manual_blackout_off=blackout_off,
            ),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )

        ex.hold_blackout_mask("breakdown")
        ex.hold_blackout_mask("master_switch")
        ex.release_blackout_mask("breakdown")
        ex.release_blackout_mask("master_switch")

        self.assertEqual([call[0].behavior for call in midi.calls], ["note_on", "note_off"])

    def test_blackout_mask_final_release_respects_pending_drop_window(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=89)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=89)
        ex = LaserSceneExecutor(
            config=_config(
                dry_run=False,
                manual_blackout_on=blackout_on,
                manual_blackout_off=blackout_off,
            ),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )

        ex.trigger_blackout_on(_ctx(abs_beat=319.0))
        ex.hold_blackout_mask("breakdown")
        ex.release_blackout_mask("breakdown")

        self.assertEqual([call[0].behavior for call in midi.calls], ["note_on"])
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])

    def test_resolve_pending_blackout_sends_pulse_message_unaltered(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        blackout_off = LaserMidiMessage(
            kind="note_pulse",
            behavior="pulse",
            channel=1,
            note=90,
            velocity=127,
            duration_ms=80,
        )
        ex = LaserSceneExecutor(
            config=_config(
                dry_run=False,
                manual_blackout_on=blackout_on,
                manual_blackout_off=blackout_off,
            ),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )

        ex.trigger_blackout_on(_ctx(abs_beat=319.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=320.0))

        self.assertEqual(len(midi.calls), 3)
        sent_off, priority = midi.calls[2]
        self.assertEqual(priority, "high")
        self.assertEqual(sent_off.note, 90)
        self.assertEqual(sent_off.kind, "note_pulse")
        self.assertEqual(sent_off.behavior, "pulse")

    def test_on_tick_clear_then_drop_crossing_sends_blackout_off_once_and_drop_scene(self) -> None:
        """Current ordering is on_tick cleanup before on_decision drop output."""
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        blackout_off = LaserMidiMessage(
            kind="note_off",
            behavior="note_off",
            channel=1,
            note=90,
            velocity=0,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.trigger_blackout_on(_ctx(abs_beat=319.0))
        ctx = _ctx(
            abs_beat=320.0,
            smart_phrasing=_smart_phrasing_state(transition_mask_should_clear=True),
        )
        ex.on_tick(ctx)
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), ctx)

        notes = [call[0].note for call in midi.calls]
        self.assertEqual(notes, [89, 90, 41])
        self.assertEqual(notes.count(90), 1)
        self.assertEqual(notes.count(41), 1)
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_on_tick_clears_blackout_when_transition_mask_should_clear(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.trigger_blackout_on(_ctx())
        ex.on_tick(_ctx(smart_phrasing=_smart_phrasing_state(transition_mask_should_clear=True)))
        self.assertEqual([call[0].note for call in midi.calls], [91, 90])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_on_tick_noop_when_transition_mask_should_clear_false(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.trigger_blackout_on(_ctx())
        ex.on_tick(_ctx(smart_phrasing=_smart_phrasing_state(transition_mask_should_clear=False)))
        self.assertEqual([call[0].note for call in midi.calls], [91])
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])

    def test_on_tick_handles_missing_smart_phrasing_safely(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_tick(_ctx(smart_phrasing=None))
        self.assertEqual(midi.calls, [])

    def test_blackout_off_clears_when_decision_is_none_via_on_tick(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ctx = _ctx(smart_phrasing=_smart_phrasing_state(transition_mask_should_clear=True))
        ex.trigger_blackout_on(_ctx())
        ex.on_tick(ctx)
        ex.on_decision(None, ctx)
        self.assertEqual([call[0].note for call in midi.calls], [91, 90])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_blackout_off_clears_when_decision_is_idle_non_drop_reason_via_on_tick(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ctx = _ctx(smart_phrasing=_smart_phrasing_state(transition_mask_should_clear=True))
        ex.trigger_blackout_on(_ctx())
        ex.on_tick(ctx)
        ex.on_decision(_decision("", "not_playing", "idle"), ctx)
        self.assertEqual([call[0].note for call in midi.calls], [91, 90])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_blackout_arm_fires_after_same_scene_already_triggered_in_window(self) -> None:
        """Regression: arm signal raised mid-buildup must still send blackout_on.

        Real-world sequence: buildup scene fires at window entry, then several
        seconds later the smart-drop arm signal is raised. The decision is the
        same buildup scene, so same_scene_skip would discard it. Blackout
        arming must not be gated by scene retriggering.
        """
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=127,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        # First tick: buildup scene fires (no arm yet, mid-window).
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=192.0, smart_drop_blackout_arm=False),
        )
        triggered_after_first = [call[0].note for call in midi.calls]
        self.assertEqual(triggered_after_first, [39])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

        # Later tick in the same window: arm raised, same scene already active.
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=252.0, smart_drop_blackout_arm=True),
        )
        notes = [call[0].note for call in midi.calls]
        # blackout_on (127) must have been sent on the second call.
        self.assertIn(127, notes)
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])

    def test_blackout_arm_fires_when_cooldown_blocks_scene(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=127,
            velocity=127,
        )
        cfg = _config(dry_run=False, manual_blackout_on=blackout_on)
        scenes = dict(cfg.scenes)
        scenes["buildup_a"] = LaserScene(
            name="buildup_a",
            scene_type="autoloop",
            safety_class="safe",
            midi=scenes["buildup_a"].midi,
            cooldown_beats=64.0,
        )
        ex = LaserSceneExecutor(
            config=replace(cfg, scenes=scenes),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=192.0, smart_drop_blackout_arm=False),
        )
        self.assertEqual([call[0].note for call in midi.calls], [39])
        gated_before = ex.status()["gated_count"]
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=240.0, smart_drop_blackout_arm=True),
        )
        notes = [call[0].note for call in midi.calls]
        self.assertEqual(notes, [39, 127])
        self.assertEqual(notes.count(39), 1)
        status = ex.status()
        self.assertTrue(status["blackout_pending_for_drop_window"])
        self.assertEqual(status["last_error"], "role_cooldown_blocked")
        self.assertEqual(status["gated_count"], gated_before + 1)

    def test_blackout_arm_fires_when_high_impact_blocks_scene(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=127,
            velocity=127,
        )
        cfg = _config(dry_run=False, manual_blackout_on=blackout_on)
        scenes = dict(cfg.scenes)
        scenes["buildup_a"] = LaserScene(
            name="buildup_a",
            scene_type="autoloop",
            safety_class="high_impact",
            midi=scenes["buildup_a"].midi,
        )
        ex = LaserSceneExecutor(
            config=replace(cfg, scenes=scenes),
            backend=MidiOutputBackend(midi),
            personality=_personality(allow_high_impact=False),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=240.0, smart_drop_blackout_arm=True),
        )
        notes = [call[0].note for call in midi.calls]
        self.assertEqual(notes, [127])
        status = ex.status()
        self.assertTrue(status["blackout_pending_for_drop_window"])
        self.assertEqual(status["last_error"], "high_impact_blocked")
        self.assertEqual(status["gated_count"], 1)

    def test_blackout_arm_does_not_fire_when_auto_gates_fail(self) -> None:
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=127,
            velocity=127,
        )
        # AWR-206: autoloop_ready=False is deliberately NOT here -- the pre-drop
        # blackout now arms on the relaxed gate while the autoloop is mid-re-arm
        # (covered by test_blackout_arms_under_autoloop_churn_*). These cases each
        # fail a relaxed-gate sub-condition, so they still must NOT arm.
        cases = (
            _ctx(playing=False, smart_drop_blackout_arm=True),
            _ctx(active_track_loaded=False, smart_drop_blackout_arm=True),
            _ctx(position_stale=True, smart_drop_blackout_arm=True),
            _ctx(lighting_mode="static", smart_drop_blackout_arm=True),
            _ctx(scripted_id=7, smart_drop_blackout_arm=True),
        )
        for case_ctx in cases:
            midi = _FakeMidiOutput(dry_run=False)
            ex = LaserSceneExecutor(
                config=_config(dry_run=False, manual_blackout_on=blackout_on),
                backend=MidiOutputBackend(midi),
                personality=_personality(),
            )
            ex.on_decision(_decision("buildup_a", "buildup_to_drop_window", "buildup"), case_ctx)
            self.assertEqual(midi.calls, [])
            self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_blackout_arms_under_autoloop_churn_smart_drop(self) -> None:
        """AWR-206: autoloop_ready=False (autoloop mid-re-arm at the pre-drop
        instant) must NOT block the pre-drop blackout note. The buildup scene
        MIDI still stays blocked by the strict gate, and the auto-gate block is
        still counted."""
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=90, velocity=127)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(autoloop_ready=False, smart_drop_blackout_arm=True),
        )
        # Blackout note (90) fired; buildup scene (note 39) did NOT.
        self.assertEqual([call[0].note for call in midi.calls], [90])
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])
        self.assertEqual(ex.status()["last_error"], "auto_gate_blocked")
        self.assertEqual(ex.status()["gated_count"], 1)

    def test_blackout_arms_under_autoloop_churn_smart_phrasing(self) -> None:
        """AWR-206: the smart-phrasing arm signal takes the same relaxed path as
        the smart-drop arm signal."""
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=90, velocity=127)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(autoloop_ready=False, smart_phrasing_blackout_arm=True),
        )
        self.assertEqual([call[0].note for call in midi.calls], [90])
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])

    def test_blackout_does_not_arm_under_churn_when_scene_unmapped(self) -> None:
        """AWR-206: even on the relaxed gate, an unmapped scene name must fail
        closed (no arm), same as the strict-gate path."""
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=90, velocity=127)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("no_such_scene", "buildup_to_drop_window", "buildup"),
            _ctx(autoloop_ready=False, smart_drop_blackout_arm=True),
        )
        self.assertEqual(midi.calls, [])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_drop_crossing_resolves_pending_blackout_when_auto_gate_blocked(self) -> None:
        """AWR-206: a blackout armed under churn must still release at the drop
        even if the auto gate is still blocked at the crossing tick."""
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=90, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(autoloop_ready=False, smart_drop_blackout_arm=True),
        )
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])
        ex.on_decision(
            _decision("drop_a", "drop_crossing", "drop"),
            _ctx(autoloop_ready=False, abs_beat=192.0),
        )
        self.assertEqual([call[0].note for call in midi.calls], [90, 90])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_blackout_skip_logs_failing_subconditions_at_info(self) -> None:
        """AWR-206: when the relaxed gate blocks the blackout, the skip is logged
        at INFO (visible at the bridge's live log level) with the failing
        sub-conditions -- the old DEBUG line was invisible."""
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=90, velocity=127)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        with self.assertLogs("laser_executor", level="INFO") as cm:
            ex.on_decision(
                _decision("buildup_a", "buildup_to_drop_window", "buildup"),
                _ctx(position_stale=True, autoloop_ready=False, smart_drop_blackout_arm=True),
            )
        self.assertTrue(
            any("blackout skipped: auto_gate_blocked" in m and "stale=True" in m for m in cm.output),
            cm.output,
        )
        self.assertEqual(midi.calls, [])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_blackout_arm_fires_for_phrase_role_mid_window_no_phrase_boundary(self) -> None:
        """Regression: mini-drop case.

        When two drops are <32 beats apart, the executor stays in role="phrase"
        between them. The arm signal arrives on a phrase tick whose decision
        reason is "default" (not "phrase_boundary"), so _select_scene returns
        "". Blackout arming must still fire on this tick because the upcoming
        drop will need transition masking.
        """
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=127,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("phrase_a", "default", "phrase"),
            _ctx(abs_beat=492.0, smart_drop_blackout_arm=True),
        )
        notes = [call[0].note for call in midi.calls]
        # Only blackout_on (127) should be sent; no scene MIDI because
        # _select_scene returns "" for phrase role outside a phrase_boundary.
        self.assertEqual(notes, [127])
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])

    def test_blackout_arm_does_not_fire_when_scene_def_missing(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=127,
            velocity=127,
        )
        # Decision.scene must not exist in config.scenes catalog. The
        # personality's buildup_bank also points at the missing scene so
        # _select_scene returns the missing name and the scene_def lookup also
        # fails. Blackout arming must be suppressed because the policy-supplied
        # decision.scene is absent from the configured scene catalog.
        personality = replace(
            _personality(),
            buildup_scene="missing_buildup_scene",
            buildup_bank=("missing_buildup_scene",),
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=personality,
        )
        ex.on_decision(
            _decision("missing_buildup_scene", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=240.0, smart_drop_blackout_arm=True),
        )
        self.assertEqual(midi.calls, [])
        status = ex.status()
        self.assertIn("missing_scene_mapping", status["last_error"])
        self.assertFalse(status["blackout_pending_for_drop_window"])

    def test_blackout_arm_signal_triggers_manual_blackout_on_for_valid_auto_decision(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=200.0, smart_drop_blackout_arm=True),
        )
        self.assertEqual([call[0].note for call in midi.calls], [89, 39])
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])

    def test_smart_phrasing_blackout_arm_triggers_blackout_on_for_valid_auto_decision(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=200.0, smart_drop_blackout_arm=False, smart_phrasing_blackout_arm=True),
        )
        self.assertEqual([call[0].note for call in midi.calls], [89, 39])
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])

    def test_both_arm_signals_true_sends_blackout_on_exactly_once(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=200.0, smart_drop_blackout_arm=True, smart_phrasing_blackout_arm=True),
        )
        notes = [call[0].note for call in midi.calls]
        self.assertEqual(notes.count(89), 1)
        self.assertIn(39, notes)

    def test_smart_phrasing_blackout_arm_suppressed_when_role_not_auto(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            LaserSceneDecision(scene="drop_a", reason="manual_override", priority=1, source="manual", role="manual"),
            _ctx(smart_drop_blackout_arm=False, smart_phrasing_blackout_arm=True),
        )
        ex.on_decision(
            LaserSceneDecision(scene="drop_a", reason="emergency", priority=1, source="emergency", role="emergency"),
            _ctx(smart_drop_blackout_arm=False, smart_phrasing_blackout_arm=True),
        )
        ex.on_decision(
            _decision("", "not_playing", "idle"),
            _ctx(smart_drop_blackout_arm=False, smart_phrasing_blackout_arm=True),
        )
        self.assertEqual([call[0].note for call in midi.calls], [41, 41])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_smart_phrasing_blackout_arm_false_no_blackout_on(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=200.0, smart_drop_blackout_arm=False, smart_phrasing_blackout_arm=False),
        )
        self.assertEqual([call[0].note for call in midi.calls], [39])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_smart_phrasing_blackout_arm_retry_across_ticks_idempotent(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        for beat in (200.0, 201.0, 202.0):
            ex.on_decision(
                _decision("buildup_a", "buildup_to_drop_window", "buildup"),
                _ctx(abs_beat=beat, smart_drop_blackout_arm=False, smart_phrasing_blackout_arm=True),
            )
        notes = [call[0].note for call in midi.calls]
        self.assertEqual(notes.count(89), 1)
        self.assertEqual(notes.count(39), 1)
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])

    def test_legacy_arm_still_triggers_when_smart_phrasing_arm_false(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=200.0, smart_drop_blackout_arm=True, smart_phrasing_blackout_arm=False),
        )
        self.assertEqual([call[0].note for call in midi.calls], [89, 39])
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])

    def test_neither_arm_signal_triggers_blackout_on(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=200.0, smart_drop_blackout_arm=False, smart_phrasing_blackout_arm=False),
        )
        self.assertEqual([call[0].note for call in midi.calls], [39])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_blackout_arm_signal_does_not_trigger_for_none_manual_emergency_or_gated(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=89,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(None, _ctx(smart_drop_blackout_arm=True))
        ex.on_decision(
            LaserSceneDecision(scene="drop_a", reason="manual_override", priority=1, source="manual", role="manual"),
            _ctx(smart_drop_blackout_arm=True),
        )
        ex.on_decision(
            LaserSceneDecision(scene="drop_a", reason="emergency", priority=1, source="emergency", role="emergency"),
            _ctx(smart_drop_blackout_arm=True),
        )
        ex.on_decision(
            _decision("", "not_playing", "idle"),
            _ctx(smart_drop_blackout_arm=True),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(smart_drop_blackout_arm=True, scripted_id=77),
        )
        # AWR-206: the autoloop_ready=False case that used to live here now ARMS
        # the blackout (relaxed gate) -- see test_blackout_arms_under_autoloop_churn_*.
        self.assertEqual([call[0].note for call in midi.calls], [41, 41])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_trigger_blackout_on_enqueues_manual_command(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=91,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.trigger_blackout_on(_ctx())
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(midi.calls[0][0].note, 91)
        self.assertEqual(midi.calls[0][1], "high")
        self.assertTrue(ex.status()["blackout_pending_for_drop_window"])
        self.assertFalse(ex.status()["manual_blackout_commands_configured"])

    def test_trigger_blackout_on_skips_in_legacy_mode(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(
            kind="note_on",
            behavior="note_on",
            channel=1,
            note=91,
            velocity=127,
        )
        ex = LaserSceneExecutor(
            config=_config(
                dry_run=False,
                smart_drop_mode="legacy_rearm",
                manual_blackout_on=blackout_on,
            ),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.trigger_blackout_on(_ctx())
        self.assertEqual(midi.calls, [])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_manual_blackout_commands_optional(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=None, manual_blackout_off=None),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.trigger_blackout_on(_ctx())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=251.0))
        self.assertEqual(len(midi.calls), 1)
        self.assertFalse(ex.status()["manual_blackout_commands_configured"])

    def test_drop_crossing_high_impact_block_clears_pending_blackout(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=_personality(allow_high_impact=False),
        )
        ex.trigger_blackout_on(_ctx())
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=320.0))
        self.assertEqual([call[0].note for call in midi.calls], [91, 90])
        self.assertEqual(ex.status()["last_error"], "high_impact_blocked")
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_drop_crossing_role_cooldown_block_clears_pending_blackout(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(
                dry_run=False,
                manual_blackout_on=blackout_on,
                manual_blackout_off=blackout_off,
            ),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=300.0))
        ex.trigger_blackout_on(_ctx(abs_beat=301.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=301.0))
        self.assertEqual([call[0].note for call in midi.calls], [41, 91, 90])
        self.assertEqual(ex.status()["last_error"], "role_cooldown_blocked")
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_drop_crossing_missing_scene_mapping_clears_pending_blackout(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=None,
        )
        ex.trigger_blackout_on(_ctx())
        ex.on_decision(_decision("missing_drop_scene", "drop_crossing", "drop"), _ctx(abs_beat=401.0))
        self.assertEqual([call[0].note for call in midi.calls], [91, 90])
        self.assertIn("missing_scene_mapping", ex.status()["last_error"])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_drop_crossing_midi_rejected_clears_pending_blackout(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.trigger_blackout_on(_ctx())
        midi.trigger_result = False
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=450.0))
        self.assertEqual([call[0].note for call in midi.calls], [91, 41, 90])
        self.assertIn(
            ex.status()["last_error"],
            {"midi_trigger_rejected", "manual_blackout_off_rejected"},
        )
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_pending_blackout_clear_is_idempotent(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=blackout_on, manual_blackout_off=blackout_off),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.trigger_blackout_on(_ctx())
        ex.clear_pending_blackout(reason="first")
        ex.clear_pending_blackout(reason="second")
        self.assertEqual([call[0].note for call in midi.calls], [91, 90])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_reset_runtime_state_clears_role_and_blackout_state(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(
                dry_run=False,
                manual_blackout_on=blackout_on,
                manual_blackout_off=blackout_off,
            ),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=300.0))
        ex.trigger_blackout_on(_ctx(abs_beat=301.0))
        ex.reset_runtime_state(reason="test_reset")
        status = ex.status()
        self.assertEqual(status["last_scene"], "")
        self.assertEqual(status["last_role"], "idle")
        self.assertFalse(status["blackout_pending_for_drop_window"])
        self.assertEqual([call[0].note for call in midi.calls], [41, 91, 90])

    def test_drop_crossing_same_scene_still_clears_pending_blackout(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        blackout_on = LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=91, velocity=127)
        blackout_off = LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)
        ex = LaserSceneExecutor(
            config=_config(
                dry_run=False,
                manual_blackout_on=blackout_on,
                manual_blackout_off=blackout_off,
            ),
            backend=MidiOutputBackend(midi),
            personality=_drop_mode_personality(),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=500.0))
        ex.trigger_blackout_on(_ctx(abs_beat=501.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=501.1))
        self.assertEqual([call[0].note for call in midi.calls], [41, 91, 41, 90])
        self.assertFalse(ex.status()["blackout_pending_for_drop_window"])

    def test_role_cooldown_blocks_then_allows_after_beats(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(rotating_banks=True),
            rng=random.Random(2),
        )
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx(abs_beat=100.0))
        ex.on_decision(_decision("phrase_a", "phrase_boundary", "phrase"), _ctx(abs_beat=108.0, autoloop_tick_just_fired=True))
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(ex.status()["last_error"], "role_cooldown_blocked")
        ex.on_decision(_decision("phrase_a", "phrase_boundary", "phrase"), _ctx(abs_beat=116.1, autoloop_tick_just_fired=True))
        self.assertEqual(len(midi.calls), 2)

    def test_buildup_and_drop_cooldown_block_retrigger(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("buildup_a", "buildup_to_drop_window", "buildup"), _ctx(abs_beat=200.0))
        ex.on_decision(_decision("buildup_a", "buildup_to_drop_window", "buildup"), _ctx(abs_beat=205.0))
        self.assertEqual(len(midi.calls), 1)
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=300.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=320.0))
        self.assertEqual(len(midi.calls), 2)
        self.assertEqual(ex.status()["last_error"], "role_cooldown_blocked")

    def test_same_scene_buildup_refire_bypasses_role_cooldown(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        cfg = _config_with_role_cooldowns(dry_run=False)
        scenes = dict(cfg.scenes)
        scenes["buildup_a"] = replace(scenes["buildup_a"], cooldown_beats=32.0)
        ex = LaserSceneExecutor(
            config=replace(cfg, scenes=scenes),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("buildup_a", "buildup_to_drop_window", "buildup"),
            _ctx(abs_beat=72.0),
        )

        with self.assertLogs("perf.laser.fired", level="INFO") as captured:
            ex.on_decision(
                _decision("buildup_a", "buildup_to_drop_window", "buildup"),
                _ctx(abs_beat=88.0, autoloop_tick_just_fired=True),
            )

        output = "\n".join(captured.output)
        self.assertIn("same-scene-refire", output)
        self.assertIn("role=buildup", output)
        self.assertEqual([call[0].note for call in midi.calls], [39, 39])
        self.assertNotEqual(ex.status()["last_error"], "role_cooldown_blocked")

    def test_drop_crossing_not_blocked_on_role_transition(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("buildup_a", "buildup_to_drop_window", "buildup"), _ctx(abs_beat=100.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=101.0))
        self.assertEqual(len(midi.calls), 2)
        self.assertEqual(midi.calls[0][0].note, 39)
        self.assertEqual(midi.calls[1][0].note, 41)
        self.assertEqual(ex.status()["last_scene"], "drop_a")
        self.assertEqual(ex.status()["last_error"], "")

    def test_later_drop_crossing_with_same_scene_is_not_same_scene_skipped(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        cfg = _config_with_role_cooldowns(dry_run=False)
        scenes = dict(cfg.scenes)
        scenes["drop_a"] = LaserScene(
            name="drop_a",
            scene_type="autoloop",
            safety_class="safe",
            midi=scenes["drop_a"].midi,
            cooldown_beats=8.0,
        )
        cfg = replace(cfg, scenes=scenes)
        ex = LaserSceneExecutor(
            config=cfg,
            backend=MidiOutputBackend(midi),
            personality=_single_drop_scene_personality(),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=64.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=65.0))
        self.assertEqual(ex.status()["last_error"], "role_cooldown_blocked")
        self.assertEqual(len(midi.calls), 1)
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=96.0))
        self.assertEqual(len(midi.calls), 2)
        self.assertEqual(midi.calls[0][0].note, 41)
        self.assertEqual(midi.calls[1][0].note, 41)

    def test_drop_retrigger_blocked_then_later_drop_can_fire(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(rotating_banks=True),
            rng=random.Random(2),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=300.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=301.0))
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(ex.status()["last_error"], "role_cooldown_blocked")
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx(abs_beat=302.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=333.0))
        self.assertEqual(len(midi.calls), 3)
        self.assertEqual(midi.calls[-1][0].note, 42)
        self.assertEqual(ex.status()["last_error"], "")

    def test_drop_retrigger_after_post_drop_within_cooldown_is_blocked(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_single_drop_scene_personality(),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=300.0))
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx(abs_beat=301.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=302.0))
        self.assertEqual(len(midi.calls), 2)
        self.assertEqual(midi.calls[0][0].note, 41)
        self.assertEqual(midi.calls[1][0].note, 43)
        self.assertEqual(ex.status()["last_error"], "role_cooldown_blocked")

    def test_drop_after_buildup_remains_allowed_within_cooldown(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(rotating_banks=True),
            rng=random.Random(2),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=300.0))
        ex.on_decision(_decision("buildup_a", "buildup_to_drop_window", "buildup"), _ctx(abs_beat=310.0))
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=312.0))
        self.assertEqual(len(midi.calls), 3)
        self.assertEqual(midi.calls[0][0].note, 41)
        self.assertEqual(midi.calls[1][0].note, 39)
        self.assertEqual(midi.calls[2][0].note, 42)
        self.assertEqual(ex.status()["last_error"], "")

    def test_drop_mode_post_drop_reuses_drop_note(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_drop_mode_personality(),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=400.0))
        ex.on_decision(_decision("drop_a", "post_drop_hold", "post_drop"), _ctx(abs_beat=401.0))
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(midi.calls[0][0].note, 41)
        self.assertEqual(ex.status()["last_scene"], "drop_a")

    def test_emphasized_drop_can_use_separate_post_drop_note(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=500.0))
        ex.on_decision(_decision("post_a", "post_drop_hold", "post_drop"), _ctx(abs_beat=501.0))
        self.assertEqual(len(midi.calls), 2)
        self.assertEqual(midi.calls[0][0].note, 41)
        self.assertEqual(midi.calls[1][0].note, 43)

    def test_drop_crossing_updates_last_scene_when_preceded_by_buildup(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("buildup_a", "buildup_to_drop_window", "buildup"), _ctx(abs_beat=600.0))
        self.assertEqual(ex.status()["last_scene"], "buildup_a")
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=601.0))
        status = ex.status()
        self.assertEqual(status["last_scene"], "drop_a")
        self.assertNotEqual(status["last_error"], "role_cooldown_blocked")

    def test_cooldown_block_does_not_advance_role_cursor(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=400.0))
        cursor_after_first = ex.status()["role_cursors"]["drop"]
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=401.0))
        cursor_after_block = ex.status()["role_cursors"]["drop"]
        self.assertEqual(cursor_after_block, cursor_after_first)

    def test_role_cooldown_uses_abs_beat_not_wall_clock(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx(abs_beat=700.0))
        ex.on_decision(_decision("phrase_a", "phrase_boundary", "phrase"), _ctx(abs_beat=700.0, autoloop_tick_just_fired=True))
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(ex.status()["last_error"], "role_cooldown_blocked")

    def test_emergency_and_manual_bypass_role_cooldown(self) -> None:
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("drop_a", "drop_crossing", "drop"), _ctx(abs_beat=500.0))
        ex.on_decision(
            LaserSceneDecision(scene="drop_a", reason="manual_override", priority=1, source="manual", role="manual"),
            _ctx(abs_beat=501.0),
        )
        ex.on_decision(
            LaserSceneDecision(scene="drop_a", reason="emergency", priority=1, source="emergency", role="emergency"),
            _ctx(abs_beat=502.0),
        )
        self.assertEqual(len(midi.calls), 3)

    def test_dry_run_blackout_arm_resolve_same_logic_as_live(self) -> None:
        """dry_run=True follows the same blackout arm/resolve logic as live;
        only MIDI output is suppressed at the transport layer."""
        blackout_on = LaserMidiMessage(
            kind="note_on", behavior="note_on", channel=1, note=89, velocity=127,
        )
        blackout_off = LaserMidiMessage(
            kind="note_off", behavior="note_off", channel=1, note=90, velocity=0,
        )
        # --- dry-run executor ---
        midi_dry = _FakeMidiOutput(dry_run=True)
        ex_dry = LaserSceneExecutor(
            config=_config(
                dry_run=True,
                smart_drop_mode="blackout_mask",
                manual_blackout_on=blackout_on,
                manual_blackout_off=blackout_off,
            ),
            backend=MidiOutputBackend(midi_dry),
            personality=_personality(),
        )
        # --- live executor ---
        midi_live = _FakeMidiOutput(dry_run=False)
        ex_live = LaserSceneExecutor(
            config=_config(
                dry_run=False,
                smart_drop_mode="blackout_mask",
                manual_blackout_on=blackout_on,
                manual_blackout_off=blackout_off,
            ),
            backend=MidiOutputBackend(midi_live),
            personality=_personality(),
        )
        # Arm blackout in both.
        ctx_arm = _ctx(abs_beat=319.0)
        ex_dry.trigger_blackout_on(ctx_arm)
        ex_live.trigger_blackout_on(ctx_arm)
        # Blackout pending must be identical in both modes.
        self.assertTrue(ex_dry.status()["blackout_pending_for_drop_window"])
        self.assertTrue(ex_live.status()["blackout_pending_for_drop_window"])
        # Drop crossing resolves blackout in both.
        ctx_drop = _ctx(abs_beat=320.0)
        ex_dry.on_decision(_decision("drop_a", "drop_crossing", "drop"), ctx_drop)
        ex_live.on_decision(_decision("drop_a", "drop_crossing", "drop"), ctx_drop)
        # Pending cleared in both.
        self.assertFalse(ex_dry.status()["blackout_pending_for_drop_window"])
        self.assertFalse(ex_live.status()["blackout_pending_for_drop_window"])
        # Both produced the same MIDI call sequence (blackout_on, drop, blackout_off).
        dry_notes = [call[0].note for call in midi_dry.calls]
        live_notes = [call[0].note for call in midi_live.calls]
        self.assertEqual(dry_notes, live_notes)
        self.assertEqual(dry_notes, [89, 41, 90])
        # dry_run does not change smart_drop_mode.
        self.assertTrue(ex_dry.smart_drop_blackout_enabled())
        self.assertEqual(
            ex_dry.status()["smart_drop_mode"],
            ex_live.status()["smart_drop_mode"],
        )

    def test_first_drop_at_beat_zero_is_not_cooldown_blocked(self) -> None:
        """The very first drop should trigger even if abs_beat is 0.0."""
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config_with_role_cooldowns(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(
            _decision("drop_a", "drop_crossing", "drop"),
            _ctx(abs_beat=0.0),
        )
        self.assertEqual(len(midi.calls), 1)
        self.assertEqual(midi.calls[0][0].note, 41)
        self.assertNotEqual(ex.status()["last_error"], "role_cooldown_blocked")
        self.assertEqual(ex.status()["last_error"], "")

    def test_materialize_midi_hold_beats_with_zero_bpm_uses_minimum(self) -> None:
        """hold_beats with BPM 0 should fall back to _MIN_HOLD_MS, not divide by zero."""
        midi = _FakeMidiOutput(dry_run=False)
        cfg = _config(dry_run=False)
        scenes = dict(cfg.scenes)
        scenes["drop_a"] = LaserScene(
            name="drop_a",
            scene_type="static",
            safety_class="high_impact",
            midi=LaserMidiMessage(
                kind="note_on",
                behavior="hold_beats",
                channel=1,
                note=41,
                velocity=127,
                hold_beats=4,
            ),
        )
        cfg = replace(cfg, scenes=scenes)
        ex = LaserSceneExecutor(config=cfg, backend=MidiOutputBackend(midi), personality=_personality())
        # BPM=0 — executor must not raise and must use safe minimum.
        ex.on_decision(
            _decision("drop_a", "drop_crossing", "drop"),
            _ctx(abs_beat=64.0),
        )
        # Force bpm=0 by building ctx directly.
        ex.reset_runtime_state(reason="test")
        zero_bpm_ctx = LaserContext(
            active_deck=1,
            playing=True,
            elapsed_ms=1000,
            bpm=0.0,
            beatpos=0.0,
            abs_beat=128.0,
            position_stale=False,
            lighting_mode="autoloop",
            os2l_connected=True,
            active_track_loaded=True,
            autoloop_ready=True,
            scripted_id=0,
        )
        ex.on_decision(
            _decision("drop_a", "drop_crossing", "drop"),
            zero_bpm_ctx,
        )
        self.assertGreaterEqual(len(midi.calls), 2)
        rendered = midi.calls[-1][0]
        self.assertEqual(rendered.behavior, "hold_ms")
        # _MIN_HOLD_MS is 10 in laser_executor.py.
        self.assertEqual(rendered.hold_ms, 10)
        self.assertGreater(rendered.hold_ms, 0)


class _SpyBackend:
    """Records every message handed to the backend; no physical output."""

    def __init__(self, *, trigger_result: bool = True) -> None:
        self.calls: list[tuple[LaserMidiMessage, str]] = []
        self.trigger_result = trigger_result

    def trigger(self, msg: LaserMidiMessage, priority: str = "normal") -> bool:
        self.calls.append((msg, priority))
        return self.trigger_result

    def submit_frame(self, frame: tuple[int, ...]) -> None:
        pass

    def status(self) -> dict:
        return {"backend": "spy", "available": True}

    def reset(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


class BackendInjectionTests(unittest.TestCase):
    def test_none_backend_emits_no_midi_to_underlying_output(self) -> None:
        # With a NoneBackend injected, the executor routes solely through that
        # single backend (there is no MIDI path). NoneBackend accepts the
        # trigger so selection advances, but it emits no physical output.
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=NoneBackend(),
            personality=_personality(),
        )
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        self.assertEqual(ex.status()["triggered_count"], 1)
        self.assertEqual(ex._backend.status()["backend"], "none")
        self.assertFalse(hasattr(ex, "_midi_output"))

    def test_scene_name_populated_on_fired_message(self) -> None:
        spy = _SpyBackend()
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=spy,
            personality=_personality(),
        )
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        self.assertEqual(len(spy.calls), 1)
        fired_msg, _priority = spy.calls[0]
        self.assertEqual(fired_msg.scene_name, "phrase_a")

    def test_pack_backend_learned_scene_advances_selection(self) -> None:
        backend = PackOutputBackend(scene_to_identity={"phrase_a": "ssid-7"})
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=backend,
            personality=_personality(),
        )
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        # Learned scene -> PackOutputBackend.trigger returns True -> executor
        # advances _last_triggered_scene and counts the trigger.
        self.assertEqual(ex.status()["triggered_count"], 1)
        self.assertEqual(ex._last_triggered_scene, "phrase_a")
        self.assertEqual(backend.status()["trigger_count"], 1)

    def test_pack_backend_unlearned_scene_does_not_advance_selection(self) -> None:
        backend = PackOutputBackend(scene_to_identity={})  # nothing learned
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=backend,
            personality=_personality(),
        )
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        # Unlearned scene -> PackOutputBackend.trigger returns False -> the
        # executor must NOT advance _last_triggered_scene (rejected scene).
        self.assertEqual(ex._last_triggered_scene, "")
        self.assertEqual(ex.status()["triggered_count"], 0)
        self.assertEqual(ex.status()["last_error"], "midi_trigger_rejected")
        self.assertEqual(backend.status()["no_op_count"], 1)

    def test_single_backend_slot_no_secondary_midi_path(self) -> None:
        # Mutual exclusivity at the object: constructing with one backend holds
        # exactly that backend in the single slot and wires no MIDI path.
        spy = _SpyBackend()
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=spy,
            personality=_personality(),
        )
        self.assertIs(ex._backend, spy)
        # No second backend / midi attribute exists to bypass the single slot.
        self.assertFalse(hasattr(ex, "_midi_output"))


class PerfEmitTests(unittest.TestCase):
    """Task W3a (AWR-125): fires emit perf.laser.fired records via bridge_log.

    Records are captured with a plain logging.Handler on the category logger
    (records propagate); bridge_log.init() is never called in tests.
    """

    def _capture(self, name: str) -> list[logging.LogRecord]:
        logger = logging.getLogger(name)
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _Capture()
        old_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        self.addCleanup(logger.setLevel, old_level)
        self.addCleanup(logger.removeHandler, handler)
        return records

    def test_fired_emits_one_perf_record_with_data_fields(self) -> None:
        records = self._capture("perf.laser.fired")
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx())
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.cat, "perf.laser.fired")
        self.assertEqual(rec.deck, 1)
        self.assertEqual(rec.beat, 64.0)
        self.assertEqual(rec.data["role"], "phrase")
        self.assertEqual(rec.data["scene"], "phrase_a")
        self.assertEqual(rec.data["note"], 37)
        self.assertEqual(rec.data["reason"], "default_init")
        self.assertEqual(rec.data["cursor"], 1)
        self.assertFalse(rec.data["refire"])
        self.assertIn("phrase_a", rec.getMessage())

    def test_gated_decision_emits_no_perf_record(self) -> None:
        records = self._capture("perf.laser.fired")
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx(playing=False))
        self.assertEqual(records, [])

    def test_same_scene_refire_records_carry_refire_flag(self) -> None:
        records = self._capture("perf.laser.fired")
        midi = _FakeMidiOutput(dry_run=False)
        ex = LaserSceneExecutor(
            config=_config(dry_run=False),
            backend=MidiOutputBackend(midi),
            personality=_personality(),
        )
        ex.on_decision(_decision("phrase_a", "default_init", "phrase"), _ctx(abs_beat=64.0))
        del records[:]
        ex.on_decision(
            _decision("phrase_a", "phrase_boundary", "phrase"),
            _ctx(abs_beat=96.0, autoloop_tick_just_fired=True),
        )
        # A same-scene refire produces the refire announcement plus the fired
        # record, mirroring today's two INFO lines; both carry refire=True.
        self.assertEqual(len(records), 2)
        self.assertIn("same-scene-refire", records[0].getMessage())
        self.assertTrue(records[0].data["refire"])
        self.assertEqual(records[0].data["role"], "phrase")
        self.assertEqual(records[0].data["scene"], "phrase_a")
        self.assertIn("fired", records[1].getMessage())
        self.assertTrue(records[1].data["refire"])
        self.assertEqual(len(midi.calls), 2)


if __name__ == "__main__":
    unittest.main()
