from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_models import LaserResolvedScene
from rb_ss_bridge_v2.native_autoloop_resolver import (
    AUTOLOOP_TICKS_PER_BEAT,
    NativeAutoloopResolver,
    finalize_native_autoloop_render,
)
from rb_ss_bridge_v2.soundswitch_laser_player import PlayerDiagnostic, PlayerResult, ZERO_FRAME
from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedAutoloopBinding


def _oracle_ticks_per_beat() -> int:
    path = Path(__file__).resolve().parents[1] / "tools/ssfmt/re/autoloop_oracle/diff.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "TICKS_PER_BEAT"
                   for target in node.targets):
                value = ast.literal_eval(node.value)
                return int(value)
    raise AssertionError("oracle TICKS_PER_BEAT not found")


def _scene(
    note: int = 96,
    *,
    role: str = "drop",
    scene: str = "house_drop_1",
    reason: str = "drop_crossing",
    channel: int = 1,
) -> LaserResolvedScene:
    return LaserResolvedScene(
        role=role,
        reason=reason,
        scene=scene,
        channel=channel,
        note=note,
        scene_type="static",
    )


def _binding(identity: str = "SSAutoLoop4.ssfile", name: str = "Drop 1") -> LoadedAutoloopBinding:
    return LoadedAutoloopBinding(0, 96, identity, name)


def _binding_with_beats(
    beat_count: int,
    identity: str = "SSAutoLoop4.ssfile",
    name: str = "Drop 1",
) -> LoadedAutoloopBinding:
    return LoadedAutoloopBinding(0, 96, identity, name, beat_count, beat_count * 600)


class NativeAutoloopResolverTests(unittest.TestCase):
    def test_ticks_per_beat_matches_oracle(self) -> None:
        self.assertEqual(AUTOLOOP_TICKS_PER_BEAT, 600)
        self.assertEqual(AUTOLOOP_TICKS_PER_BEAT, _oracle_ticks_per_beat())

    def test_resolves_1_based_scene_channel_to_pack_binding_and_phase(self) -> None:
        resolver = NativeAutoloopResolver()

        decision = resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding(name="House Drop")},
            scene=_scene(channel=1, note=96),
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=64.0,
        )

        self.assertEqual(decision.status, "rendering_active")
        self.assertEqual(decision.target_identity, "SSAutoLoop4.ssfile")
        self.assertEqual(decision.soundswitch_name, "House Drop")
        self.assertEqual(decision.anchor_beat, 64.0)
        self.assertEqual(decision.window_start, 64.0)
        self.assertEqual(decision.phase_tick, 0)

    def test_latches_across_none_and_advances_phase(self) -> None:
        resolver = NativeAutoloopResolver()
        resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding()},
            scene=_scene(),
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=10.0,
        )

        decision = resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding()},
            scene=None,
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=11.5,
        )

        self.assertEqual(decision.status, "rendering_active")
        self.assertEqual(decision.target_identity, "SSAutoLoop4.ssfile")
        self.assertEqual(decision.phase_tick, 6900)

    def test_same_scene_refire_and_role_change_reanchor(self) -> None:
        resolver = NativeAutoloopResolver()
        kwargs = dict(
            pack_sha12="abc",
            bindings={
                (0, 96): _binding("SSAutoLoop4.ssfile", "Drop"),
                (0, 64): LoadedAutoloopBinding(0, 64, "SSAutoLoop18.ssfile", "Buildup"),
            },
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
        )
        resolver.resolve(scene=_scene(note=96), abs_beat_pos=32.0, **kwargs)
        refire = resolver.resolve(scene=_scene(note=96, reason="drop_cycle"), abs_beat_pos=64.0, **kwargs)
        buildup = resolver.resolve(
            scene=_scene(note=64, role="buildup", scene="house_buildup_1", reason="buildup"),
            abs_beat_pos=96.0,
            **kwargs,
        )

        self.assertEqual(refire.phase_tick, 0)
        self.assertEqual(refire.anchor_beat, 64.0)
        self.assertEqual(buildup.phase_tick, 0)
        self.assertEqual(buildup.target_identity, "SSAutoLoop18.ssfile")
        self.assertEqual(buildup.role, "buildup")

    def test_phase_offset_wraps_inside_32_beat_cycle(self) -> None:
        resolver = NativeAutoloopResolver()
        decision = resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding()},
            scene=_scene(),
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=64.0,
            phase_offset_beats=1.25,
        )

        self.assertEqual(decision.phase_tick, 750)

    def test_phase_uses_selected_non_32_beat_cycle_window(self) -> None:
        resolver = NativeAutoloopResolver()
        resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding_with_beats(16)},
            scene=_scene(),
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=34.0,
        )
        decision = resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding_with_beats(16)},
            scene=None,
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=47.5,
        )
        self.assertEqual(decision.window_start, 32.0)
        self.assertEqual(decision.beat_count, 16)
        self.assertEqual(decision.cycle_ticks, 9600)
        self.assertEqual(decision.phase_tick, 9300)

    def test_missing_binding_and_ineligible_clear_state(self) -> None:
        resolver = NativeAutoloopResolver()
        resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding()},
            scene=_scene(),
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=64.0,
        )

        missing = resolver.resolve(
            pack_sha12="abc",
            bindings={},
            scene=_scene(note=97),
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=65.0,
        )
        held = resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding()},
            scene=None,
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=66.0,
        )

        self.assertEqual(missing.status, "missing_binding")
        self.assertEqual(held.status, "software_zero_frame")
        self.assertEqual(held.reason, "waiting_for_edge")

    def test_stop_stale_seek_track_change_and_soundswitch_present_clear(self) -> None:
        for update, status in (
            ({"playing": False}, "software_zero_frame"),
            ({"fresh": False}, "software_zero_frame"),
            ({"track_changed": True}, "software_zero_frame"),
            ({"discontinuity": True}, "software_zero_frame"),
            ({"soundswitch_present": True}, "soundswitch_present_native_suppressed"),
        ):
            with self.subTest(update=update):
                resolver = NativeAutoloopResolver()
                base = dict(
                    pack_sha12="abc",
                    bindings={(0, 96): _binding()},
                    scene=_scene(),
                    lighting_mode="autoloop",
                    scripted_active=False,
                    playing=True,
                    fresh=True,
                    track_changed=False,
                    discontinuity=False,
                    soundswitch_present=False,
                    abs_beat_pos=64.0,
                )
                resolver.resolve(**base)
                base.update(update)
                decision = resolver.resolve(**base)
                self.assertEqual(decision.status, status)
                self.assertIsNone(resolver.state)

    def test_render_diagnostics_map_to_native_statuses(self) -> None:
        resolver = NativeAutoloopResolver()
        decision = resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding()},
            scene=_scene(),
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=64.0,
        )
        self.assertEqual(
            finalize_native_autoloop_render(
                decision,
                PlayerResult(ZERO_FRAME, PlayerDiagnostic("autoloop_not_found", "missing")),
            ).status,
            "missing_autoloop_file",
        )
        self.assertEqual(
            finalize_native_autoloop_render(
                decision,
                PlayerResult(ZERO_FRAME, PlayerDiagnostic("unsupported_layout", "layout")),
            ).status,
            "unsupported_layout",
        )
        self.assertEqual(
            finalize_native_autoloop_render(decision, PlayerResult(ZERO_FRAME)).status,
            "empty_dark_look",
        )

    def test_post_drop_fallback_and_mapped_post_drop_are_binding_driven(self) -> None:
        resolver = NativeAutoloopResolver()
        fallback = resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 96): _binding("SSAutoLoop4.ssfile", "Drop fallback")},
            scene=_scene(note=96, role="post_drop", scene="house_drop_1", reason="post_drop_cycle"),
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=128.0,
        )
        mapped = resolver.resolve(
            pack_sha12="abc",
            bindings={(0, 41): LoadedAutoloopBinding(0, 41, "SSAutoLoop41.ssfile", "Post")},
            scene=_scene(note=41, role="post_drop", scene="house_post_drop_1", reason="post_drop_cycle"),
            lighting_mode="autoloop",
            scripted_active=False,
            playing=True,
            fresh=True,
            track_changed=False,
            discontinuity=False,
            soundswitch_present=False,
            abs_beat_pos=160.0,
        )

        self.assertEqual(fallback.target_identity, "SSAutoLoop4.ssfile")
        self.assertEqual(fallback.role, "post_drop")
        self.assertEqual(mapped.target_identity, "SSAutoLoop41.ssfile")
        self.assertEqual(mapped.scene, "house_post_drop_1")


if __name__ == "__main__":
    unittest.main()
