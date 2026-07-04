from __future__ import annotations

import queue
import time
from types import MappingProxyType
import unittest
from unittest.mock import Mock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_color_engine import (  # noqa: E402
    LaserColorEngine,
    LaserColorMap,
    LaserColorSnapshot,
    load_laser_color_map,
)
from rb_ss_bridge_v2.led_color_engine import LedColorEngine  # noqa: E402
from rb_ss_bridge_v2.led_models import ColorEngineConfig, LEDLookDecision, Palette  # noqa: E402
from rb_ss_bridge_v2.laser_models import LaserResolvedScene  # noqa: E402
from rb_ss_bridge_v2.models import PositionSnapshot  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402
from rb_ss_bridge_v2.soundswitch_laser_player import (  # noqa: E402
    ZERO_FRAME,
    LaserPackPlayer,
    render_autoloop_frame,
)
from rb_ss_bridge_v2.soundswitch_midi_input import LayerEntry  # noqa: E402
from rb_ss_bridge_v2.soundswitch_pack_loader import (  # noqa: E402
    LoadedAttribute,
    LoadedAutoloopBinding,
    LoadedDocument,
    LoadedPack,
    LoadedScalarValue,
    LoadedStaticLook,
    LoadedTimelineEvent,
)
from rb_ss_bridge_v2.soundswitch_pack_runtime import PackRuntime  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


SSID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _event(time: int, order: int, patch: tuple[tuple[int, int], ...]) -> LoadedTimelineEvent:
    return LoadedTimelineEvent(
        time=time,
        source_order=order,
        source_offset=100 + order,
        reference_kind="cue",
        raw_reference=order + 1,
        patch=tuple(LoadedAttribute(0x493, channel, channel, value) for channel, value in patch),
    )


def _document(*events: LoadedTimelineEvent, path: str) -> LoadedDocument:
    return LoadedDocument(path, "shared_441_dictionary_timeline", tuple(events), (), 19_200)


def _look(slot: int, values: tuple[int, ...]) -> LoadedStaticLook:
    return LoadedStaticLook(
        slot_index=slot,
        record_version=5,
        name=f"slot-{slot}",
        generic_attributes=tuple(
            LoadedAttribute(0x493, index, index, value)
            for index, value in enumerate(values, 1)
        ),
        intensity_values=(LoadedScalarValue(1, 1, 0.5),),
        strobe_values=(),
        colour_values=(),
        position_values=(),
    )


def _layer(slot: int) -> LayerEntry:
    return LayerEntry(slot, "toggle", 1)


def _pack() -> LoadedPack:
    scripted = _document(
        _event(0, 0, ((1, 11), (8, 81), (9, 91), (11, 111))),
        path="script.ssfile",
    )
    loop = _document(
        _event(-1, 0, ((1, 22), (8, 82), (9, 92), (11, 112))),
        path="SSAutoLoop8.ssfile",
    )
    return LoadedPack(
        schema_version="1.0.0",
        manifest_sha256="0" * 64,
        has_intensity_channel=False,
        scripted=MappingProxyType({SSID: scripted}),
        autoloops=MappingProxyType({"SSAutoLoop8.ssfile": loop}),
        static_looks=MappingProxyType({8: _look(8, (8,) * 19)}),
        autoloop_bindings=MappingProxyType({
            (0, 96): LoadedAutoloopBinding(0, 96, "SSAutoLoop8.ssfile", "House Drop"),
        }),
    )


def _color_map(**overrides) -> LaserColorMap:
    data = {
        "enabled": True,
        "fixed": {
            "red": 10,
            "green": 20,
            "blue": 30,
            "cyan": 40,
            "yellow": 50,
            "purple": 60,
            "white": 70,
        },
        "fixed_ch9": 0,
        "effects": {"rainbow_family": {"ch8": 80, "ch9": 100}},
        "settle": {"ease_beats": 8},
    }
    data.update(overrides)
    return LaserColorMap.from_dict(data)


class _FakeBackend:
    def __init__(self) -> None:
        self.frames: list[tuple[int, ...]] = []

    def submit_frame(self, frame) -> None:
        self.frames.append(tuple(frame))


class _FakeLaserExecutor:
    def current_autoloop_scene(self) -> LaserResolvedScene:
        return LaserResolvedScene("drop", "test", "house_drop", 1, 96, "static")

    def mask_owners_active(self) -> bool:
        return False

    def smart_drop_blackout_enabled(self) -> bool:
        return False

    def release_blackout_mask(self, _owner: str) -> None:
        pass


class _FakeLEDDirector:
    def tick(self, context) -> LEDLookDecision:
        return LEDLookDecision(
            look="rt_drop_blue",
            target="room_perimeter",
            action="realtime",
            scene_ref="drop_chase_blue",
            reason="role_preview:drop",
            source="automation",
            priority=2,
            role=str(context.role),
            backend="realtime_razer",
            params={},
        )

    def post_drop_cycle_beats(self) -> float:
        return 32.0


class _FakeLEDAdapter:
    def __init__(self) -> None:
        self.trigger_calls: list[LEDLookDecision] = []

    def trigger(self, decision: LEDLookDecision) -> bool:
        self.trigger_calls.append(decision)
        return True

    def last_white_moment(self) -> bool:
        return False


class _FakeLEDColorEngine:
    enabled = True
    diy_eligible = staticmethod(lambda _scene_ref: True)

    def advance_fade(self, _abs_beat: float) -> None:
        pass

    def begin_dispatch(self, **_kwargs) -> None:
        pass

    def resolve_color(self, **_kwargs) -> dict:
        return {}

    def snapshot(self) -> dict:
        return {"current_palette": "blue_cyan"}

    def color_state(self) -> dict:
        return {
            "rgb": (255, 0, 0),
            "palette": "blue_cyan",
            "white_sand_active": False,
            "rainbow_active": False,
        }

    def reset_fade_memory(self) -> None:
        pass


class LaserColorPassThroughTests(unittest.TestCase):
    def _run(self, scenario, snapshot=None):
        player = LaserPackPlayer(_pack())
        player.set_color_snapshot(snapshot)
        return scenario(player)

    def test_disabled_all_null_and_missing_snapshot_are_byte_identical(self) -> None:
        disabled = LaserColorEngine(LaserColorMap.from_dict({"enabled": False}))
        disabled.update({"rgb": (255, 0, 0)}, white_moment=False, drop_phase=None, post_drop_progress=None)
        all_null = LaserColorEngine(LaserColorMap.from_dict({
            "enabled": True,
            "fixed": {name: None for name in ("red", "green", "blue", "cyan", "yellow", "purple", "white")},
            "effects": {"rainbow_family": {"ch8": None, "ch9": None}},
        }))
        all_null.update({"rgb": (255, 0, 0)}, white_moment=False, drop_phase=None, post_drop_progress=None)
        snapshots = (None, disabled.snapshot(), all_null.snapshot())

        def autoloop(player):
            return player.select_autoloop("SSAutoLoop8.ssfile", 0)

        def scripted(player):
            return player.select_scripted(SSID, 0)

        def masked(player):
            player.set_masks(blackout=True, emergency=False)
            return player.select_autoloop("SSAutoLoop8.ssfile", 0)

        def static_layered(player):
            player.set_static_layers((_layer(8),))
            return player.select_autoloop("SSAutoLoop8.ssfile", 0)

        def diagnostic(player):
            return player.select_autoloop("SSAutoLoop8.ssfile", None)

        for scenario in (autoloop, scripted, masked, static_layered, diagnostic):
            control = self._run(scenario)
            for snapshot in snapshots:
                with self.subTest(scenario=scenario.__name__, snapshot=snapshot):
                    candidate = self._run(scenario, snapshot)
                    self.assertEqual(candidate.frame, control.frame)
                    self.assertEqual(
                        candidate.diagnostic.code if candidate.diagnostic else "",
                        control.diagnostic.code if control.diagnostic else "",
                    )


class LaserColorMapperTests(unittest.TestCase):
    def _snapshot(self, state, *, white_moment=False, drop_phase=None, post_drop_progress=None):
        engine = LaserColorEngine(_color_map())
        engine.update(
            state,
            white_moment=white_moment,
            drop_phase=drop_phase,
            post_drop_progress=post_drop_progress,
        )
        return engine.snapshot()

    def test_quantizer_known_colors_white_reserved_and_tie_break(self) -> None:
        self.assertEqual(self._snapshot({"rgb": (250, 0, 0)}).ch8, 10)
        self.assertEqual(self._snapshot({"rgb": (0, 250, 0)}).ch8, 20)
        self.assertEqual(self._snapshot({"rgb": (0, 0, 250)}).ch8, 30)
        self.assertEqual(self._snapshot({"rgb": (0, 250, 250)}).ch8, 40)
        self.assertEqual(self._snapshot({"rgb": (250, 250, 0)}).ch8, 50)
        self.assertEqual(self._snapshot({"rgb": (160, 0, 250)}).ch8, 60)
        self.assertEqual(self._snapshot({"rgb": (255, 255, 255)}).ch8, 40)
        self.assertEqual(self._snapshot({"rgb": (0, 0, 0)}).ch8, 10)

    def test_white_moment_and_white_sand_force_white(self) -> None:
        self.assertEqual(self._snapshot({"rgb": (255, 0, 0)}, white_moment=True).ch8, 70)
        self.assertEqual(self._snapshot({"rgb": (255, 0, 0)}, white_moment=False).ch8, 10)
        self.assertEqual(self._snapshot({"rgb": (255, 0, 0), "white_sand_active": True}).ch8, 70)

    def test_rainbow_family_and_post_drop_settle(self) -> None:
        values = []
        for progress in (0.0, 0.5, 1.0):
            snap = self._snapshot(
                {"rgb": (255, 0, 0), "rainbow_active": True},
                drop_phase="post_drop",
                post_drop_progress=progress,
            )
            values.append(snap.ch9)
            self.assertEqual(snap.ch8, 80)
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual(values[-1], 0)

    def test_loader_ships_disabled_with_calibrated_fixed_band_values(self) -> None:
        # The shipped chart carries the operator-calibrated FIXED half
        # (2026-07-04: virtuallasernode camera calibration — CH8 4-31 in
        # 4-value bands, order W,R,Y,G,C,B,M) but stays DISABLED: flipping
        # `enabled` is the operator's call. CH9 and the effect families are
        # still pending operator data and must remain null.
        loaded = load_laser_color_map("config/laser_color_map.json")
        self.assertFalse(loaded.enabled)
        fixed = loaded.fixed or {}
        for name, value in fixed.items():
            self.assertIsInstance(value, int, name)
            # Every fixed color must sit inside the calibrated fixed band —
            # never in the effect-family range (>= 32) or the 0-3 reserve.
            self.assertTrue(4 <= value <= 31, f"{name}={value}")
        self.assertEqual(fixed.get("red"), 10)     # pack-proven in-band values
        self.assertEqual(fixed.get("purple"), 28)  # fixture magenta band
        self.assertIsNone(loaded.fixed_ch9)
        rainbow = (loaded.effects or {}).get("rainbow_family", {})
        self.assertIsNone(rainbow.get("ch8"))
        self.assertIsNone(rainbow.get("ch9"))

    def test_white_path_ch9_always_none_preserves_authored_speed(self) -> None:
        # White (moment or white_sand) takes CH8 only; CH9 is left for whatever
        # speed the pack already authored, regardless of fixed_ch9 configuration.
        snap = self._snapshot({"rgb": (255, 0, 0)}, white_moment=True)
        self.assertEqual(snap.ch8, 70)
        self.assertIsNone(snap.ch9)
        snap = self._snapshot({"rgb": (255, 0, 0), "white_sand_active": True})
        self.assertIsNone(snap.ch9)

    def test_quantized_path_ch9_null_fixed_ch9_leaves_channel_unset(self) -> None:
        engine = LaserColorEngine(_color_map(fixed_ch9=None))
        engine.update({"rgb": (250, 0, 0)}, white_moment=False, drop_phase=None, post_drop_progress=None)
        snap = engine.snapshot()
        self.assertEqual(snap.ch8, 10)
        self.assertIsNone(snap.ch9)

    def test_quantized_path_ch9_eases_configured_fixed_ch9_post_drop(self) -> None:
        engine = LaserColorEngine(_color_map(fixed_ch9=200))
        values = []
        for progress in (0.0, 0.5, 1.0):
            engine.update(
                {"rgb": (250, 0, 0)},
                white_moment=False,
                drop_phase="post_drop",
                post_drop_progress=progress,
            )
            values.append(engine.snapshot().ch9)
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual(values[0], 200)
        self.assertEqual(values[-1], 0)


class LaserColorPackMergeTests(unittest.TestCase):
    def test_injection_scope_blackout_static_scripted_diagnostic_and_ch11(self) -> None:
        snap = LaserColorSnapshot(ch8=201, ch9=202, seq=1)
        control = render_autoloop_frame(_pack().autoloops["SSAutoLoop8.ssfile"], 0)
        player = LaserPackPlayer(_pack())
        player.set_color_snapshot(snap)

        injected = player.select_autoloop("SSAutoLoop8.ssfile", 0).frame
        self.assertEqual((injected[7], injected[8]), (201, 202))
        self.assertEqual(injected[10], control[10])

        scripted = player.select_scripted(SSID, 0).frame
        self.assertEqual((scripted[7], scripted[8], scripted[10]), (81, 91, 111))

        diagnostic = player.select_autoloop("SSAutoLoop8.ssfile", None)
        self.assertEqual(diagnostic.frame, ZERO_FRAME)
        self.assertEqual(diagnostic.diagnostic.code, "missing_phase")

        player = LaserPackPlayer(_pack())
        player.set_color_snapshot(snap)
        player.set_masks(blackout=True, emergency=False)
        self.assertEqual(player.select_autoloop("SSAutoLoop8.ssfile", 0).frame, ZERO_FRAME)

        player = LaserPackPlayer(_pack())
        player.set_color_snapshot(snap)
        player.set_static_layers((_layer(8),))
        static = player.select_autoloop("SSAutoLoop8.ssfile", 0).frame
        self.assertEqual((static[7], static[8]), (8, 8))

    def test_merge_writes_ch8_and_ch9_independently(self) -> None:
        # ch9=None (e.g. white moments, or a null fixed_ch9) leaves CH9 authored
        # while CH8 is still injected — and vice versa. Neither channel's
        # validity gates the other; all-null still injects nothing anywhere.
        player = LaserPackPlayer(_pack())
        player.set_color_snapshot(LaserColorSnapshot(ch8=201, ch9=None, seq=1))
        frame = player.select_autoloop("SSAutoLoop8.ssfile", 0).frame
        self.assertEqual((frame[7], frame[8]), (201, 92))

        player.set_color_snapshot(LaserColorSnapshot(ch8=None, ch9=202, seq=2))  # type: ignore[arg-type]
        frame = player.select_autoloop("SSAutoLoop8.ssfile", 0).frame
        self.assertEqual((frame[7], frame[8]), (82, 202))

        player.set_color_snapshot(LaserColorSnapshot(ch8=None, ch9=None, seq=3))  # type: ignore[arg-type]
        frame = player.select_autoloop("SSAutoLoop8.ssfile", 0).frame
        self.assertEqual((frame[7], frame[8]), (82, 92))

    def test_missing_snapshot_clears_stale_injection_and_resuming_reinjects(self) -> None:
        player = LaserPackPlayer(_pack())
        snap = LaserColorSnapshot(ch8=201, ch9=202, seq=1)
        player.set_color_snapshot(snap)
        self.assertEqual(player.select_autoloop("SSAutoLoop8.ssfile", 0).frame[7:9], (201, 202))

        player.set_color_snapshot(None)
        pass_through = player.select_autoloop("SSAutoLoop8.ssfile", 0).frame
        self.assertEqual(pass_through[7:9], (82, 92))

        player.set_color_snapshot(snap)
        self.assertEqual(player.select_autoloop("SSAutoLoop8.ssfile", 0).frame[7:9], (201, 202))


class LaserColorStateManagerStalenessTests(unittest.TestCase):
    def _make_state_manager(self) -> tuple[StateManager, _FakeBackend]:
        backend = _FakeBackend()
        runtime = PackRuntime(
            enabled=True,
            reason="test",
            player=LaserPackPlayer(_pack()),
            backend=backend,
            pack_sha12="0" * 12,
        )
        sm = StateManager(
            queue.Queue(maxsize=64),
            PositionCache(),
            Mock(),
            laser_executor=_FakeLaserExecutor(),
            led_look_director=_FakeLEDDirector(),
            led_scene_adapter=_FakeLEDAdapter(),
            led_color_engine=_FakeLEDColorEngine(),
            os2l_connected_provider=lambda: False,
            soundswitch_pack_runtime=runtime,
        )
        sm._led_palette_control = None
        sm._laser_color_engine = LaserColorEngine(_color_map())
        sm._rerun_active_deck_resolver = lambda *_args, **_kwargs: None
        sm._check_pending_arm = lambda: None
        sm._update_lighting = lambda *_args, **_kwargs: None
        sm._led_enabled_latch = True
        sm._led_automation_enabled_latch = True
        sm._led_scripted_mode_automation_latch = False

        deck = sm._deck[1]
        deck.playing = True
        deck.scripted_id = 0
        deck.load_gen = 11
        deck.meta.filepath = "/tracks/current.wav"
        deck.meta.content_id = "cid-1"
        deck.meta.bpm = 120.0
        sm._deck[2].playing = False
        sm._os.active_deck = 1
        sm._os.was_playing = True
        sm._os.lighting_mode = "autoloop"
        sm._os.last_armed_filepath = deck.meta.filepath
        sm._cache.update(PositionSnapshot(
            deck=1,
            elapsed_ms=32_000,
            playing=True,
            updated_at=time.monotonic(),
        ))
        return sm, backend

    def test_manual_override_tick_clears_stale_snapshot_and_resume_reinjects(self) -> None:
        sm, backend = self._make_state_manager()
        sp_states = [
            SmartPhrasingState(
                abs_beat=64.0,
                current_phrase_label="chorus",
                previous_phrase_label="up",
                current_phrase_is_chorus=True,
                phrase_start_crossing=True,
                current_phrase_start_beat=64.0,
                active_drop_beat=64.0,
            ),
            SmartPhrasingState(
                abs_beat=64.0,
                current_phrase_label="chorus",
                previous_phrase_label="up",
                current_phrase_is_chorus=True,
                phrase_start_crossing=True,
                current_phrase_start_beat=64.0,
                active_drop_beat=64.0,
            ),
            SmartPhrasingState(
                abs_beat=96.0,
                current_phrase_label="chorus",
                previous_phrase_label="up",
                current_phrase_is_chorus=True,
                phrase_start_crossing=True,
                current_phrase_start_beat=96.0,
                active_drop_beat=96.0,
            ),
        ]
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: sp_states.pop(0)

        sm._push_tick()
        self.assertEqual(backend.frames[-1][7:9], (10, 0))

        sm._led_manual_override = "room_manual"
        sm._push_tick()
        self.assertEqual(backend.frames[-1][7:9], (82, 92))

        sm._led_manual_override = ""
        sm._push_tick()
        self.assertEqual(backend.frames[-1][7:9], (10, 0))


class LedColorStateAccessorTests(unittest.TestCase):
    def test_color_state_mutates_no_led_engine_state(self) -> None:
        engine = LedColorEngine(
            ColorEngineConfig(
                palettes={
                    "blue_cyan": Palette(range=("cyan", "blue"), weight=1.0),
                    "white_sand": Palette(type="fixed_rgb", weight=0.0, rgb=(255, 235, 200)),
                    "rainbow": Palette(type="rainbow", weight=0.0),
                },
                set_seed_mode="fixed:9",
            ),
            set_seed=9,
        )
        before = (engine.snapshot(), engine._journey_rng.getstate(), dict(engine._prev_color))
        state = engine.color_state()
        after = (engine.snapshot(), engine._journey_rng.getstate(), dict(engine._prev_color))

        self.assertEqual(after, before)
        self.assertIn("rgb", state)
        self.assertFalse(state["rainbow_active"])


if __name__ == "__main__":
    unittest.main()
