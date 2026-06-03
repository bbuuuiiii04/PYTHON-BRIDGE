from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_config import LaserConfig  # noqa: E402
from rb_ss_bridge_v2.laser_director import LaserDirector  # noqa: E402
from rb_ss_bridge_v2.laser_executor import LaserSceneExecutor  # noqa: E402
from rb_ss_bridge_v2.laser_models import (  # noqa: E402
    LaserContext,
    LaserMidiMessage,
    LaserPersonality,
    LaserScene,
)
from rb_ss_bridge_v2.smart_phrasing import (  # noqa: E402
    BeatSegment,
    PhraseSegment,
    SmartPhrasingEngine,
    SmartPhrasingSnapshot,
    SmartPhrasingState,
)
from rb_ss_bridge_v2.models import DeckState, OutputState  # noqa: E402
from rb_ss_bridge_v2.smart_rearm import (  # noqa: E402
    SmartRearmContext,
    SmartRearmCoordinator,
)

_SIGNAL_NONE = 0
_SIGNAL_BLACKOUT_ARMED = 1
_SIGNAL_CROSSING = 2


class _FakeMidiOutput:
    def __init__(self, *, dry_run: bool, degraded: bool = False, running: bool = True) -> None:
        self._dry_run = dry_run
        self._degraded = degraded
        self._running = running
        self.current_abs_beat: float = 0.0
        self.calls: list[tuple[float, LaserMidiMessage, str]] = []
        self.trigger_result = True

    def trigger(self, msg: LaserMidiMessage, priority: str = "normal") -> bool:
        self.calls.append((self.current_abs_beat, msg, priority))
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


def _personality() -> LaserPersonality:
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
        allow_high_impact=True,
        minimum_scene_hold_beats=8,
        # These scenarios exercise the separate post-drop hold; that is the
        # emphasized_drop behavior. (drop_mode holds the drop look instead.)
        drop_style="emphasized_drop",
    )


def _blackout_on_msg() -> LaserMidiMessage:
    return LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=89, velocity=127)


def _blackout_off_msg() -> LaserMidiMessage:
    return LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=90, velocity=0)


def _config(*, smart_drop_mode: str = "blackout_mask") -> LaserConfig:
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
        dry_run=True,
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
        manual_blackout_on=_blackout_on_msg(),
        manual_blackout_off=_blackout_off_msg(),
    )


@dataclass
class _DropArmState:
    drop_cut_armed: bool = False
    drop_rearm_beat: int = 0


def _smart_drop_state(arm: _DropArmState, sp: SmartPhrasingState, *, blackout_mode: bool) -> int:
    # Mirrors SmartRearmCoordinator._drop and
    # the smart_drop_blackout_arm derivation around state_manager.py:1641-1650.
    # Intentionally omitted production gates (none affect current scenarios):
    #   - os.autoloop_arm_pending / os.pending_autoloop_arm_meta short-circuit
    #   - os.breakdown_active short-circuit
    #   - legacy_rearm path's _send_direct_autoloop_rearm return-value handling
    #     and sm._sse.send_smart_transition_clear side effect (no laser MIDI).
    if arm.drop_cut_armed:
        if sp.smart_drop_crossing:
            # blackout-mode defers arm reset until after on_decision so the
            # same-tick LaserContext can still derive smart_drop_blackout_arm;
            # see _GoldenHarness.tick() cleanup at the post-on_decision block.
            if blackout_mode:
                return _SIGNAL_CROSSING
            arm.drop_cut_armed = False
            arm.drop_rearm_beat = 0
            return _SIGNAL_CROSSING
        return _SIGNAL_NONE

    if sp.transition_mask_should_arm and sp.next_smart_drop_beat is not None:
        arm.drop_cut_armed = True
        arm.drop_rearm_beat = int(sp.next_smart_drop_beat)
        return _SIGNAL_BLACKOUT_ARMED

    return _SIGNAL_NONE


class _GoldenHarness:
    def __init__(
        self,
        *,
        smart_drop_beats: tuple[float, ...] = (),
        phrase_segments: tuple[PhraseSegment, ...] = (),
        breakdown_segments: tuple[BeatSegment, ...] = (),
        smart_drop_mode: str = "blackout_mask",
        deck_id: str = "1",
        track_id: str = "track-A",
        bpm: float = 128.0,
        phrase_anchor_last_beat: int = -1,
        use_real_smart_rearm: bool = False,
    ) -> None:
        self._deck_id = deck_id
        self._track_id = track_id
        self._bpm = bpm
        self._phrase_anchor_last_beat = phrase_anchor_last_beat
        self._use_real_smart_rearm = use_real_smart_rearm
        self._playing = True
        self._smart_drop_beats = smart_drop_beats
        self._phrase_segments = phrase_segments
        self._breakdown_segments = breakdown_segments
        self._breakdown_active = False
        self._arm = _DropArmState()
        self._os = OutputState(lighting_mode="autoloop")
        self._os.phrase_anchor_last_beat = phrase_anchor_last_beat
        self._deck = {1: DeckState(number=1), 2: DeckState(number=2)}
        self._direct_rearm_calls: list[tuple[tuple, dict]] = []
        self._transition_clear_calls: list[int] = []
        self._now = 0.0
        self._last_abs_beat = 0.0

        cfg = _config(smart_drop_mode=smart_drop_mode)
        personality = _personality()
        self._note_to_scene = {scene.midi.note: name for name, scene in cfg.scenes.items()}
        self._note_to_scene[_blackout_on_msg().note] = "blackout_on"
        self._note_to_scene[_blackout_off_msg().note] = "blackout_off"

        self._engine = SmartPhrasingEngine()
        self._director = LaserDirector(
            dry_run=True,
            enabled=True,
            safe_scene=personality.safe_scene,
            default_scene=personality.default_scene,
            emergency_scene=personality.safe_scene,
        )
        self._director.set_personality_config(personality)
        self._midi = _FakeMidiOutput(dry_run=True)
        self._executor = LaserSceneExecutor(
            config=cfg,
            midi_output=self._midi,
            personality=personality,
            rng=random.Random(2),
        )
        self._smart_rearm = SmartRearmCoordinator(
            output_state_ref=lambda: self._os,
            deck_ref=lambda d: self._deck[d],
            send_direct_autoloop_rearm=self._send_direct_autoloop_rearm,
            send_smart_transition_clear=self._send_smart_transition_clear,
        )

    def _send_direct_autoloop_rearm(self, *args, **kwargs) -> bool:
        self._direct_rearm_calls.append((args, kwargs))
        return True

    def _send_smart_transition_clear(self, active: int) -> None:
        self._transition_clear_calls.append(active)

    def _smart_drop_signal(self, sp_state: SmartPhrasingState, smart_drop_blackout_mode: bool) -> int:
        if not self._use_real_smart_rearm:
            return _smart_drop_state(self._arm, sp_state, blackout_mode=smart_drop_blackout_mode)

        result = self._smart_rearm.tick(
            int(self._deck_id),
            sp_state,
            SmartRearmContext(
                mirror=2 if self._deck_id == "1" else 1,
                bpm=self._bpm,
                this_beat=int(self._last_abs_beat),
                elapsed_ms=int(round((self._last_abs_beat * 60_000.0) / self._bpm))
                if self._bpm > 0
                else 0,
                abs_beat_pos=self._last_abs_beat,
                blackout_mode=smart_drop_blackout_mode,
                smart_drop_enabled=True,
                smart_breakdown_enabled=False,
                phrase_anchor_enabled=False,
                lighting_mode_is_autoloop=True,
            ),
        )
        self._arm.drop_cut_armed = self._os.drop_cut_armed
        self._arm.drop_rearm_beat = self._os.drop_rearm_beat
        if result.drop.crossing:
            return _SIGNAL_CROSSING
        if result.drop.blackout_armed:
            return _SIGNAL_BLACKOUT_ARMED
        return _SIGNAL_NONE

    def tick(
        self,
        *,
        abs_beat: float,
        playing: bool | None = None,
        autoloop_ready: bool = True,
        active_track_loaded: bool = True,
        position_stale: bool = False,
        scripted_id: int = 0,
        autoloop_tick_just_fired: bool | None = None,
        breakdown_active: bool | None = None,
    ) -> LaserContext:
        self._last_abs_beat = abs_beat
        is_playing = self._playing if playing is None else playing
        # Whole-beat heuristic. Production sets autoloop_tick_just_fired in
        # state_manager._push_tick based on real autoloop arm/lock/beat-event
        # boundaries (state_manager.py:1574-1636); the harness mimics it
        # deterministically by firing on integer beats. Pass an explicit value
        # to override for scenarios that need different behavior.
        if autoloop_tick_just_fired is None:
            autoloop_tick_just_fired = abs(abs_beat - round(abs_beat)) < 1e-9

        snap = SmartPhrasingSnapshot(
            deck_id=self._deck_id,
            track_id=self._track_id,
            is_playing=is_playing,
            abs_beat=abs_beat if self._bpm > 0 else None,
            phrase_segments=self._phrase_segments,
            smart_drop_beats=self._smart_drop_beats,
            breakdown_segments=self._breakdown_segments,
            phrase_lookahead_beats=32.0,
            drop_window_beats=4.0,
            post_drop_beats=8.0,
            transition_window_beats=4.0,
            phrase_anchor_last_beat=self._phrase_anchor_last_beat,
            phrase_anchor_period_beats=64,
        )
        sp_state = self._engine.update(snap).state

        # Harness mirrors OutputState.breakdown_active for smart-phasing arm
        # gating. Default source is engine smart_breakdown_active, but callers
        # can override per tick to simulate production's deliberate divergence
        # between os.breakdown_active and engine breakdown segments.
        self._breakdown_active = (
            bool(sp_state.smart_breakdown_active)
            if breakdown_active is None
            else bool(breakdown_active)
        )

        smart_drop_blackout_mode = self._executor.smart_drop_blackout_enabled()
        signal = self._smart_drop_signal(sp_state, smart_drop_blackout_mode)

        smart_drop_blackout_arm = bool(
            (
                signal == _SIGNAL_BLACKOUT_ARMED
                or (self._arm.drop_cut_armed and signal != _SIGNAL_CROSSING)
            )
            and smart_drop_blackout_mode
        )
        smart_phrasing_blackout_arm = bool(
            smart_drop_blackout_mode
            and sp_state.transition_mask_arm_latched
            and not self._breakdown_active
            and signal != _SIGNAL_CROSSING
        )

        # Mirrors state_manager._build_laser_context (state_manager.py:1759-1829).
        # The harness diverges from production on the following LaserContext
        # fields, using constants or kwargs in place of StateManager-derived
        # values:
        #   - lighting_mode  (hardcoded "autoloop")
        #   - os2l_connected (hardcoded True)
        #   - active_track_loaded (kwarg, default True)
        #   - autoloop_ready (kwarg, default True)
        #   - autoloop_tick_just_fired (kwarg or whole-beat heuristic)
        #   - scripted_id (kwarg, default 0)
        #   - position_stale (kwarg, default False; production: snap.is_stale)
        #   - elapsed_ms (synthesized from abs_beat/bpm; production: real clock)
        ctx = LaserContext(
            active_deck=int(self._deck_id),
            playing=is_playing,
            elapsed_ms=int(round((abs_beat * 60_000.0) / self._bpm)) if self._bpm > 0 else 0,
            bpm=self._bpm,
            beatpos=abs_beat % 4.0,
            abs_beat=abs_beat,
            position_stale=position_stale,
            lighting_mode="autoloop",
            os2l_connected=True,
            active_track_loaded=active_track_loaded,
            autoloop_ready=autoloop_ready,
            autoloop_tick_just_fired=autoloop_tick_just_fired,
            scripted_id=scripted_id,
            smart_drop_blackout_active=self._arm.drop_cut_armed,
            smart_drop_blackout_arm=smart_drop_blackout_arm,
            smart_phrasing_blackout_arm=smart_phrasing_blackout_arm,
            smart_phrasing=sp_state,
        )

        self._midi.current_abs_beat = abs_beat
        decision = self._director.tick(ctx, now=self._now)
        self._executor.on_tick(ctx)
        self._executor.on_decision(decision, ctx)

        drop_crossing_decision_emitted = bool(decision is not None and decision.reason == "drop_crossing")
        # Mirrors state_manager._push_tick post-on_decision cleanup
        # (state_manager.py:1683-1697). The phrase_anchor_last_beat update
        # from production is intentionally skipped — irrelevant for laser MIDI.
        #
        # Dual-cleanup design: when the executor's own gating rejects the drop
        # decision (e.g., high_impact_blocked, role_cooldown_blocked), it calls
        # _resolve_pending_blackout itself with a specific reason
        # (laser_executor.py:115-208). When the decision was emitted but
        # something else suppressed it before reaching the executor, the
        # harness fires clear_pending_blackout here as a safety net so a
        # crossing tick never leaves a blackout window orphaned.
        if signal == _SIGNAL_CROSSING and smart_drop_blackout_mode:
            if not drop_crossing_decision_emitted:
                self._executor.clear_pending_blackout(reason="smart_drop_crossing_without_drop_decision")
            self._arm.drop_cut_armed = False
            self._arm.drop_rearm_beat = 0
            if self._use_real_smart_rearm:
                self._os.drop_cut_armed = False
                self._os.drop_rearm_beat = 0

        # Monotonic per-tick clock. LaserDirector only reads `now` for
        # _manual_override_expires_at (laser_director.py:250); none of the
        # current scenarios exercise manual override, so realism here is
        # unimportant — only monotonicity matters.
        self._now += (60.0 / self._bpm) / 4.0
        return ctx

    def master_change(
        self,
        *,
        track_id: str = "track-B",
        smart_drop_beats: tuple[float, ...] = (),
        phrase_segments: tuple[PhraseSegment, ...] = (),
        breakdown_segments: tuple[BeatSegment, ...] = (),
    ) -> None:
        """Simulate a deck master change between ticks.

        Production goes through state_manager._on_master_changed which calls
        _clear_smart_rearm_state (state_manager.py:2223-2232) BEFORE
        _laser_executor.reset_runtime_state(reason="master_changed"). Both
        paths each reach _resolve_pending_blackout (state_manager.py:2226 via
        clear_pending_blackout; laser_executor.py:82 directly via
        reset_runtime_state), which is
        deduped via _blackout_pending_for_drop_window, so exactly one
        blackout_off fires. The harness collapses to one reset_runtime_state
        call; the observable MIDI transcript is identical.
        """
        self._midi.current_abs_beat = self._last_abs_beat
        self._executor.reset_runtime_state(reason="master_changed")
        self._engine.reset("master_changed")
        self._arm.drop_cut_armed = False
        self._arm.drop_rearm_beat = 0
        self._os.drop_cut_armed = False
        self._os.drop_rearm_beat = 0
        self._os.breakdown_active = False
        self._os.breakdown_restore_beat = 0
        self._breakdown_active = False
        self._track_id = track_id
        self._smart_drop_beats = smart_drop_beats
        self._phrase_segments = phrase_segments
        self._breakdown_segments = breakdown_segments

    def stop(self) -> None:
        """Simulate a deck stop event.

        Mirrors state_manager._clear_smart_rearm_state (state_manager.py:2223-2232):
        clears the executor pending blackout, the SmartPhrasingEngine blackout
        latch, the harness-tracked _breakdown_active mirror, and the smart-drop
        arm. The observable MIDI transcript is identical for the current
        scenarios; the tightening prevents stale state from masking bugs in
        future scenarios.

        Intentionally omitted from this method's manual clears:
          - os.breakdown_active = False — harness instead keeps
            self._breakdown_active in sync each tick from
            sp_state.smart_breakdown_active (see tick() ~line 255), so the
            stop()-time `_breakdown_active = False` assignment is a defensive
            idempotent overwrite, not the source of truth.
          - os.phrase_anchor_last_beat = -1 — dormant; harness initializes
            self._phrase_anchor_last_beat to -1 and never updates it.
        """
        self._playing = False
        self._executor.reset_runtime_state(reason="stop")
        self._engine.clear_blackout_latch()
        self._breakdown_active = False
        self._arm.drop_cut_armed = False
        self._arm.drop_rearm_beat = 0
        self._os.drop_cut_armed = False
        self._os.drop_rearm_beat = 0
        self._os.breakdown_active = False
        self._os.breakdown_restore_beat = 0

    def resume(
        self,
        *,
        track_id: str,
        smart_drop_beats: tuple[float, ...] = (),
        phrase_segments: tuple[PhraseSegment, ...] = (),
        breakdown_segments: tuple[BeatSegment, ...] = (),
    ) -> None:
        """Simulate resume on a (possibly new) track.

        Today the engine auto-resets when track_id changes (smart_phrasing.py:
        161-163, 178). The explicit clears below make resume() correct even on
        same-track resume, matching production's _clear_smart_rearm_state
        semantics (state_manager.py:2223-2232).
        """
        self._playing = True
        self._engine.clear_blackout_latch()
        self._breakdown_active = False
        self._arm.drop_cut_armed = False
        self._arm.drop_rearm_beat = 0
        self._os.drop_cut_armed = False
        self._os.drop_rearm_beat = 0
        self._os.breakdown_active = False
        self._os.breakdown_restore_beat = 0
        self._track_id = track_id
        self._smart_drop_beats = smart_drop_beats
        self._phrase_segments = phrase_segments
        self._breakdown_segments = breakdown_segments

    def transcript(self) -> list[tuple[int, str, int, int, str]]:
        out: list[tuple[int, str, int, int, str]] = []
        for abs_beat, msg, priority in self._midi.calls:
            scene = self._note_to_scene.get(msg.note, f"note_{msg.note}")
            out.append((int(abs_beat), scene, msg.channel, msg.note, priority))
        return out


def _beats(start: float, end: float) -> Iterator[float]:
    """Yield quarter-beat ticks from `start` to `end` inclusive on both ends.

    Inclusive end is intentional: scenarios pin events that fire on the
    upper-bound beat (e.g., scenario 1's (64, "phrase_a", ...) row).
    """
    start_q = int(round(start * 4.0))
    end_q = int(round(end * 4.0))
    for q in range(start_q, end_q + 1):
        yield q / 4.0


def _run_scenario_1() -> list[tuple[int, str, int, int, str]]:
    h = _GoldenHarness(
        phrase_segments=(
            PhraseSegment(0.0, 32.0, "other"),
            PhraseSegment(32.0, 64.0, "other"),
            PhraseSegment(64.0, 96.0, "other"),
        )
    )
    for beat in _beats(0.0, 64.0):
        h.tick(abs_beat=beat)
    return h.transcript()


def _run_scenario_2() -> list[tuple[int, str, int, int, str]]:
    h = _GoldenHarness(
        smart_drop_beats=(64.0,),
        phrase_segments=(
            PhraseSegment(48.0, 64.0, "up"),
            PhraseSegment(64.0, 80.0, "chorus"),
        ),
        smart_drop_mode="blackout_mask",
    )
    for beat in _beats(50.0, 70.0):
        h.tick(abs_beat=beat)
    return h.transcript()


def _run_scenario_2_real_coordinator() -> list[tuple[int, str, int, int, str]]:
    h = _GoldenHarness(
        smart_drop_beats=(64.0,),
        phrase_segments=(
            PhraseSegment(48.0, 64.0, "up"),
            PhraseSegment(64.0, 80.0, "chorus"),
        ),
        smart_drop_mode="blackout_mask",
        use_real_smart_rearm=True,
    )
    for beat in _beats(50.0, 70.0):
        h.tick(abs_beat=beat)
    return h.transcript()


def _run_scenario_3() -> list[tuple[int, str, int, int, str]]:
    h = _GoldenHarness(
        smart_drop_beats=(64.0,),
        phrase_segments=(
            PhraseSegment(48.0, 64.0, "up"),
            PhraseSegment(64.0, 80.0, "chorus"),
        ),
        smart_drop_mode="legacy_rearm",
    )
    for beat in _beats(50.0, 70.0):
        h.tick(abs_beat=beat)
    return h.transcript()


def _run_scenario_4() -> list[tuple[int, str, int, int, str]]:
    h = _GoldenHarness(
        breakdown_segments=(BeatSegment(32.0, 64.0),),
        phrase_segments=(
            PhraseSegment(0.0, 96.0, "other"),
        ),
    )
    for beat in _beats(28.0, 68.0):
        h.tick(abs_beat=beat)
    return h.transcript()


def _run_scenario_5() -> list[tuple[int, str, int, int, str]]:
    h = _GoldenHarness(
        smart_drop_beats=(64.0,),
        phrase_segments=(
            PhraseSegment(48.0, 64.0, "up"),
            PhraseSegment(64.0, 80.0, "chorus"),
        ),
        smart_drop_mode="blackout_mask",
    )
    for beat in _beats(50.0, 70.0):
        h.tick(abs_beat=beat)
        if abs(beat - 60.0) < 1e-9:
            h.master_change(
                track_id="track-B",
                smart_drop_beats=(),
                phrase_segments=(PhraseSegment(0.0, 96.0, "other"),),
                breakdown_segments=(),
            )
    return h.transcript()


def _run_scenario_6() -> list[tuple[int, str, int, int, str]]:
    h = _GoldenHarness(
        smart_drop_beats=(20.0,),
        phrase_segments=(
            PhraseSegment(0.0, 20.0, "up"),
            PhraseSegment(20.0, 80.0, "chorus"),
        ),
        smart_drop_mode="blackout_mask",
    )
    for beat in _beats(0.0, 30.0):
        h.tick(abs_beat=beat)

    h.stop()
    for beat in _beats(30.25, 31.0):
        h.tick(abs_beat=beat)

    h.resume(
        track_id="track-B",
        smart_drop_beats=(),
        phrase_segments=(PhraseSegment(0.0, 96.0, "other"),),
        breakdown_segments=(),
    )
    # Post-resume ticks restart at beat 0 on the new track, so the final
    # transcript contains two rows with abs_beat=0 distinguished only by scene
    # name (pre-stop buildup_a vs post-resume phrase_a).
    for beat in _beats(0.0, 8.0):
        h.tick(abs_beat=beat)
    return h.transcript()


class GoldenTraceTests(unittest.TestCase):
    def test_normal_phrase_walk(self) -> None:
        self.assertEqual(
            _run_scenario_1(),
            [
                (0, "phrase_a", 1, 37, "normal"),
                (32, "phrase_b", 1, 38, "normal"),
                (64, "phrase_a", 1, 37, "normal"),
            ],
        )

    def test_smart_drop_blackout_window(self) -> None:
        self.assertEqual(
            _run_scenario_2(),
            [
                (50, "buildup_a", 1, 39, "normal"),
                (60, "blackout_on", 1, 89, "high"),
                (64, "blackout_off", 1, 90, "high"),
                (64, "drop_a", 1, 41, "high"),
                (64, "post_a", 1, 43, "normal"),
            ],
        )

    def test_smart_drop_blackout_window_real_coordinator(self) -> None:
        self.assertEqual(
            _run_scenario_2_real_coordinator(),
            [
                (50, "buildup_a", 1, 39, "normal"),
                (60, "blackout_on", 1, 89, "high"),
                (64, "blackout_off", 1, 90, "high"),
                (64, "drop_a", 1, 41, "high"),
                (64, "post_a", 1, 43, "normal"),
            ],
        )

    def test_smart_drop_legacy_rearm(self) -> None:
        self.assertEqual(
            _run_scenario_3(),
            [
                (50, "buildup_a", 1, 39, "normal"),
                (64, "drop_a", 1, 41, "high"),
                (64, "post_a", 1, 43, "normal"),
            ],
        )

    def test_breakdown_lifecycle(self) -> None:
        self.assertEqual(
            _run_scenario_4(),
            [
                (28, "phrase_a", 1, 37, "normal"),
                (32, "break_a", 1, 44, "normal"),
                (64, "phrase_b", 1, 38, "normal"),
            ],
        )

    def test_master_change_mid_drop(self) -> None:
        self.assertEqual(
            _run_scenario_5(),
            [
                (50, "buildup_a", 1, 39, "normal"),
                (60, "blackout_on", 1, 89, "high"),
                (60, "blackout_off", 1, 90, "high"),
                (64, "phrase_a", 1, 37, "normal"),
            ],
        )

    def test_stop_resume_clean_state(self) -> None:
        self.assertEqual(
            _run_scenario_6(),
            [
                (0, "buildup_a", 1, 39, "normal"),
                (16, "blackout_on", 1, 89, "high"),
                (20, "blackout_off", 1, 90, "high"),
                (20, "drop_a", 1, 41, "high"),
                (20, "post_a", 1, 43, "normal"),
                (0, "phrase_a", 1, 37, "normal"),
            ],
        )

    def test_breakdown_override_can_gate_sp_blackout_arm_mid_window(self) -> None:
        h = _GoldenHarness(
            smart_drop_beats=(64.0,),
            phrase_segments=(
                PhraseSegment(48.0, 64.0, "up"),
                PhraseSegment(64.0, 80.0, "chorus"),
            ),
            breakdown_segments=(),
            smart_drop_mode="blackout_mask",
        )

        h.tick(abs_beat=59.0)
        arm_ctx = h.tick(abs_beat=60.0)
        self.assertTrue(arm_ctx.smart_phrasing_blackout_arm)

        gated_ctx = h.tick(abs_beat=61.0, breakdown_active=True)
        self.assertFalse(gated_ctx.smart_phrasing_blackout_arm)
        self.assertTrue(gated_ctx.smart_phrasing.transition_mask_arm_latched)

        resumed_ctx = h.tick(abs_beat=62.0, breakdown_active=False)
        self.assertTrue(resumed_ctx.smart_phrasing_blackout_arm)
