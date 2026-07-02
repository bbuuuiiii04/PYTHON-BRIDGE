"""Task 3 tests for the verified pack loader and pure CH1-CH19 player."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_laser_player import (
    ZERO_FRAME,
    LaserPackPlayer,
    apply_layers,
    parity_live_blocks_document,
    render_autoloop_frame,
    render_scripted_frame,
)
from rb_ss_bridge_v2.soundswitch_midi_input import LayerEntry
from rb_ss_bridge_v2.soundswitch_pack_loader import (
    LoadedAttribute,
    LoadedAutoloop,
    LoadedDocument,
    LoadedPack,
    LoadedScalarValue,
    LoadedStaticLook,
    LoadedTimelineEvent,
    SoundSwitchPackLoadError,
    _autoloop_bindings,
    _runtime_metadata,
    load_pack,
)
from rb_ss_bridge_v2.tools.export_soundswitch_pack import export_pack
from rb_ss_bridge_v2.soundswitch_pack import canonical_json_bytes


def _event(time: int, order: int, patch=(), *, clear=False,
           raw_reference: int | None = None) -> LoadedTimelineEvent:
    return LoadedTimelineEvent(
        time=time, source_order=order, source_offset=100 + order,
        reference_kind="clear_control" if clear else "cue",
        raw_reference=(0 if clear else order + 1) if raw_reference is None else raw_reference,
        patch=tuple(LoadedAttribute(0x493, channel, channel, value)
                    for channel, value in patch),
    )


def _document(*events: LoadedTimelineEvent, path="synthetic.ssfile") -> LoadedDocument:
    return LoadedDocument(path, "shared_441_dictionary_timeline", tuple(events), (), 19_200)


def _look(slot: int, values: tuple[int, ...]) -> LoadedStaticLook:
    return LoadedStaticLook(
        slot_index=slot, record_version=5, name=f"slot-{slot}",
        generic_attributes=tuple(LoadedAttribute(0x493, index, index, value)
                                 for index, value in enumerate(values, 1)),
        intensity_values=(LoadedScalarValue(1, 1, 0.5),),
        strobe_values=(), colour_values=(), position_values=(),
    )


def _sparse_look(slot: int, patch: tuple[tuple[int, int], ...],
                 *, fixture_group: int = 0x493) -> LoadedStaticLook:
    return LoadedStaticLook(
        slot_index=slot, record_version=5, name=f"slot-{slot}",
        generic_attributes=tuple(LoadedAttribute(fixture_group, channel, channel, value)
                                 for channel, value in patch),
        intensity_values=(LoadedScalarValue(1, 1, 0.5),),
        strobe_values=(), colour_values=(), position_values=(),
    )


def _layer(slot: int, seq: int = 1, kind: str = "toggle") -> LayerEntry:
    return LayerEntry(slot, kind, seq)  # type: ignore[arg-type]


def _pack(script=None, loop=None) -> LoadedPack:
    from types import MappingProxyType
    scripts = {} if script is None else {"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": script}
    loops = {} if loop is None else {loop.relative_path: loop}
    looks = {slot: _look(slot, (slot,) + (0,) * 18) for slot in (8, 16, 17, 24)}
    return LoadedPack(
        schema_version="1.0.0", manifest_sha256="0" * 64,
        has_intensity_channel=False,
        scripted=MappingProxyType(scripts), autoloops=MappingProxyType(loops),
        static_looks=MappingProxyType(looks),
    )


def _rewrite_pack_artifact(root: Path, relative: str, mutate) -> None:
    artifact_path = root / relative
    value = json.loads(artifact_path.read_text())
    mutate(value)
    data = canonical_json_bytes(value)
    artifact_path.write_bytes(data)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    row = next(item for item in manifest["artifact_hashes"] if item["path"] == relative)
    row["size"] = len(data)
    row["sha256"] = hashlib.sha256(data).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


class PureRendererTests(unittest.TestCase):
    def test_scripted_sparse_equal_time_clear_and_raw_extremes(self):
        track = _document(
            _event(0, 0, ((1, 0), (8, 1)), raw_reference=1),
            _event(10, 1, ((1, 255),), raw_reference=0xFFFFFFFF),
            _event(10, 2, ((3, 99),)),
            _event(20, 3, clear=True),
        )
        self.assertEqual(render_scripted_frame(track, 0)[0:8], (0, 0, 0, 0, 0, 0, 0, 1))
        at_tie = render_scripted_frame(track, 10)
        self.assertEqual((at_tie[0], at_tie[2], at_tie[7]), (255, 99, 1))
        cleared = render_scripted_frame(track, 20)
        self.assertEqual((cleared[0], cleared[2], cleared[7]), (0, 0, 1))

    def test_scripted_skips_non_primary_fixture_group(self):
        track = _document(LoadedTimelineEvent(
            time=0, source_order=0, source_offset=100,
            reference_kind="cue", raw_reference=1,
            patch=(
                LoadedAttribute(0x999, 2, 2, 99),
                LoadedAttribute(0x493, 3, 3, 7),
            ),
        ))
        self.assertEqual(render_scripted_frame(track, 0)[0:3], (0, 0, 7))

    def test_scripted_prefers_verified_boundary_frames_when_present(self):
        boundary = (9,) + (0,) * 18
        track = _document(LoadedTimelineEvent(
            time=10, source_order=0, source_offset=100,
            reference_kind="cue", raw_reference=1,
            patch=(LoadedAttribute(0x493, 1, 1, 1),),
            boundary_frame=boundary,
        ))
        self.assertEqual(render_scripted_frame(track, 9), ZERO_FRAME)
        self.assertEqual(render_scripted_frame(track, 10), boundary)

    def test_autoloop_signed_preroll_wrap_and_sparse_persistence(self):
        loop = _document(
            _event(-2, 0, ((1, 10),)),
            _event(0, 1, ((3, 20),)),
            _event(100, 2, ((1, 30),)),
            path="SSAutoLoop1.ssfile",
        )
        self.assertEqual(render_autoloop_frame(loop, 0)[0:3], (10, 0, 20))
        self.assertEqual(render_autoloop_frame(loop, 100)[0:3], (30, 0, 20))
        self.assertEqual(render_autoloop_frame(loop, 19_200),
                         render_autoloop_frame(loop, 0))
        self.assertEqual(render_autoloop_frame(loop, 38_500),
                         render_autoloop_frame(loop, 100))

    def test_autoloop_does_not_seed_from_prior_cycle_end(self):
        loop = _document(
            _event(-2, 0, ((1, 10),)),
            _event(100, 1, ((3, 20),)),
            path="SSAutoLoop1.ssfile",
        )
        self.assertEqual(render_autoloop_frame(loop, 0)[0:3], (10, 0, 0))

    def test_autoloop_equal_time_stored_order_and_raw_zero_control_persistence(self):
        loop = _document(
            _event(-1, 0, ((1, 4), (8, 77), (11, 255))),
            _event(5, 1, ((1, 8),)),
            _event(5, 2, ((1, 9),)),
            _event(6, 3, clear=True),
            path="SSAutoLoop13.ssfile",
        )
        self.assertEqual(render_autoloop_frame(loop, 5)[0], 9)
        frame = render_autoloop_frame(loop, 6)
        self.assertEqual(frame[0], 0)
        self.assertEqual((frame[7], frame[10]), (77, 255))

    def test_static_generic_attributes_and_retained_intensity_no_channel(self):
        look = _look(8, tuple(range(19)))
        rendered = apply_layers(ZERO_FRAME, (_layer(8),), {8: look}, False, False)
        self.assertEqual(rendered.frame, tuple(range(19)))
        self.assertEqual(look.intensity_values[0].value, 0.5)
        declared = LoadedStaticLook(
            slot_index=look.slot_index, record_version=look.record_version, name=look.name,
            generic_attributes=look.generic_attributes, intensity_values=look.intensity_values,
            strobe_values=look.strobe_values, colour_values=look.colour_values,
            position_values=look.position_values, profile_has_intensity_channel=True,
        )
        skipped = apply_layers(ZERO_FRAME, (_layer(8),), {8: declared}, False, False)
        self.assertEqual(skipped.frame, ZERO_FRAME)
        self.assertEqual(skipped.diagnostic.code, "static_layers_skipped")

    def test_apply_layers_precedence_and_frame_validation(self):
        base = (1,) * 19
        look = _sparse_look(8, ((1, 2),))
        self.assertEqual(apply_layers(base, (_layer(8),), {8: look}, False, False).frame[0], 2)
        self.assertEqual(apply_layers(base, (_layer(8),), {8: look}, True, False).frame,
                         ZERO_FRAME)
        self.assertEqual(apply_layers(base, (_layer(8),), {8: look}, False, True).frame,
                         ZERO_FRAME)
        with self.assertRaises(ValueError):
            apply_layers((1,) * 18, (), {}, False, False)

    def test_apply_layers_transparency_zero_and_topmost_wins(self):
        base = tuple(range(1, 20))
        looks = {
            1: _sparse_look(1, ((1, 100), (2, 0))),
            2: _sparse_look(2, ((1, 7), (3, 77))),
        }
        result = apply_layers(
            base,
            (_layer(1, 1, "toggle"), _layer(2, 2, "press")),
            looks,
            blackout=False,
            emergency=False,
        )
        self.assertIsNone(result.diagnostic)
        self.assertEqual(result.frame[0:4], (7, 0, 77, 4))

    def test_apply_layers_disjoint_press_release_and_masks(self):
        base = (9,) * 19
        looks = {
            1: _sparse_look(1, ((1, 10),)),
            2: _sparse_look(2, ((2, 20),)),
        }
        both = apply_layers(base, (_layer(1, 1), _layer(2, 2, "press")),
                            looks, False, False)
        reverted = apply_layers(base, (_layer(1, 1),), looks, False, False)
        self.assertEqual(both.frame[0:3], (10, 20, 9))
        self.assertEqual(reverted.frame[0:3], (10, 9, 9))
        self.assertEqual(apply_layers(base, (_layer(1),), looks, True, False).frame, ZERO_FRAME)
        self.assertEqual(apply_layers(base, (_layer(1),), looks, False, True).frame, ZERO_FRAME)

    def test_apply_layers_skips_malformed_without_zeroing_base(self):
        base = (3,) * 19
        looks = {
            1: _sparse_look(1, ((1, 10),)),
            2: _sparse_look(2, ((2, 20),), fixture_group=0x999),
            3: _sparse_look(3, ((20, 99),)),
        }
        result = apply_layers(
            base,
            (_layer(1, 1), _layer(2, 2), _layer(3, 3), _layer(99, 4)),
            looks,
            False,
            False,
        )
        self.assertEqual(result.frame[0:3], (10, 3, 3))
        self.assertEqual(result.diagnostic.code, "static_layers_skipped")


class PlayerStateTests(unittest.TestCase):
    def setUp(self):
        self.track = _document(_event(0, 0, ((1, 5),)), _event(50, 1, ((1, 9),)))
        self.loop = _document(_event(-1, 0, ((1, 4),)), _event(10, 1, ((1, 8),)),
                              path="SSAutoLoop8.ssfile")
        self.player = LaserPackPlayer(_pack(self.track, self.loop))

    def test_seek_backseek_pause_resume_refire_are_history_independent(self):
        ssid = "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}"
        forward = self.player.select_scripted(ssid, 50).frame
        backward = self.player.select_scripted(ssid.lower(), 0).frame
        paused = self.player.select_scripted(ssid, 50, transport="paused").frame
        resumed = self.player.select_scripted(ssid, 50, transport="playing").frame
        refired = self.player.select_scripted(ssid, 50, transport="playing").frame
        self.assertEqual((forward[0], backward[0]), (9, 5))
        self.assertEqual(forward, paused)
        self.assertEqual(forward, resumed)
        self.assertEqual(forward, refired)

    def test_clear_selection_lets_held_static_stand_alone(self):
        # SoundSwitch shows a manual Static Look even with no track playing: clearing
        # the automatic base must leave a held static visible (T7c idle behavior).
        self.player.set_static_layers((_layer(8),))
        result = self.player.clear_selection()
        self.assertIsNone(result.diagnostic)
        self.assertNotEqual(result.frame, ZERO_FRAME)
        self.assertEqual(tuple(layer.slot for layer in self.player.static_layers), (8,))

    def test_clear_selection_without_static_is_zero(self):
        result = self.player.clear_selection()
        self.assertEqual(result.frame, ZERO_FRAME)

    def test_parity_live_blocks_unverified_base_but_keeps_manual_static(self):
        ssid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        player = LaserPackPlayer(_pack(self.track, self.loop), parity_live=True)
        self.assertTrue(parity_live_blocks_document(self.track, True))

        scripted = player.select_scripted(ssid, 50)
        self.assertEqual(scripted.frame, ZERO_FRAME)
        self.assertEqual(scripted.diagnostic.code, "unverified_parity")

        player.set_static_layers((_layer(8),))
        with_static = player.select_scripted(ssid, 50)
        self.assertEqual(with_static.frame[0], 8)
        self.assertEqual(with_static.diagnostic.code, "unverified_parity")

        autoloop = LaserPackPlayer(_pack(self.track, self.loop), parity_live=True)
        loop_result = autoloop.select_autoloop("SSAutoLoop8.ssfile", 10)
        self.assertEqual(loop_result.frame, ZERO_FRAME)
        self.assertEqual(loop_result.diagnostic.code, "unverified_parity")

    def test_parity_live_allows_algorithm_generalized_document(self):
        ssid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        proven = LoadedDocument(
            self.track.relative_path,
            self.track.layout,
            self.track.events,
            self.track.intensity_nodes,
            self.track.cycle_ticks,
            parity_lane="algorithm_generalized",
        )
        player = LaserPackPlayer(_pack(proven, self.loop), parity_live=True)

        result = player.select_scripted(ssid, 50)

        self.assertEqual(result.frame[0], 9)
        self.assertIsNone(result.diagnostic)

    def test_clear_selection_held_static_still_loses_to_blackout(self):
        self.player.set_static_layers((_layer(8),))
        self.player.set_masks(blackout=True, emergency=False)
        self.assertEqual(self.player.clear_selection().frame, ZERO_FRAME)

    def test_clear_selection_zeros_a_prior_scripted_base(self):
        ssid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        self.assertNotEqual(self.player.select_scripted(ssid, 50).frame, ZERO_FRAME)
        self.assertEqual(self.player.clear_selection().frame, ZERO_FRAME)

    def test_stop_end_unload_and_fail_closed_authority_diagnostics(self):
        ssid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        for transport in ("stopped", "ended", "unloaded"):
            result = self.player.select_scripted(ssid, 10, transport=transport)
            self.assertEqual(result.frame, ZERO_FRAME)
            self.assertEqual(result.diagnostic.code, f"transport_{transport}")
        cases = (
            ({"soundswitch_id": None}, "missing_identity"),
            ({"soundswitch_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}, "scripted_not_found"),
            ({"soundswitch_id": ssid, "metadata_ready": False}, "metadata_not_ready"),
            ({"soundswitch_id": ssid, "source_errored": True}, "source_error"),
            ({"soundswitch_id": ssid, "authority": "stale"}, "stale_authority"),
            ({"soundswitch_id": ssid, "authority": "ambiguous"}, "ambiguous_authority"),
            ({"soundswitch_id": ssid, "elapsed_discontinuous": True}, "elapsed_discontinuity"),
            ({"soundswitch_id": ssid, "track_changed": True}, "track_change"),
        )
        for kwargs, code in cases:
            with self.subTest(code=code):
                result = self.player.select_scripted(elapsed_ms=10, **kwargs)
                self.assertEqual(result.frame, ZERO_FRAME)
                self.assertEqual(result.diagnostic.code, code)

    def test_player_error_diag_uses_class_name_not_str_exc(self):
        ssid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        result = self.player.select_scripted(ssid, -1)
        self.assertEqual(result.diagnostic.code, "player_error")
        self.assertEqual(result.diagnostic.message, "ValueError")

    def test_stop_stale_and_error_cannot_be_bypassed_by_static_override(self):
        ssid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        self.assertEqual(self.player.set_static_layers((_layer(8),)).frame[0], 8)
        for kwargs, code in (
                ({"transport": "stopped"}, "transport_stopped"),
                ({"authority": "stale"}, "stale_authority"),
                ({"source_errored": True}, "source_error")):
            with self.subTest(code=code):
                result = self.player.select_scripted(ssid, 0, **kwargs)
                self.assertEqual(result.frame, ZERO_FRAME)
                self.assertEqual(result.diagnostic.code, code)

    def test_override_replace_release_order_blackout_and_current_base(self):
        self.player.select_autoloop("SSAutoLoop8.ssfile", 0)
        self.assertEqual(self.player.set_static_layers((_layer(8, 1),)).frame[0], 8)
        self.assertEqual(self.player.set_static_layers((_layer(8, 1), _layer(17, 2))).frame[0], 17)
        self.assertEqual(self.player.set_static_layers((_layer(17, 2),)).frame[0], 17)
        self.assertEqual(self.player.set_blackout(True).frame, ZERO_FRAME)
        self.player.select_autoloop("SSAutoLoop8.ssfile", 10)
        self.assertEqual(self.player.set_blackout(False).frame[0], 17)
        self.assertEqual(self.player.set_static_layers((_layer(8, 1),)).frame[0], 8)

    def test_blackout_same_tick_wins_and_emergency_wins(self):
        self.player.select_scripted("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 0)
        self.player.set_static_layers((_layer(24),))
        self.assertEqual(self.player.set_masks(blackout=True, emergency=False).frame, ZERO_FRAME)
        self.assertEqual(self.player.set_masks(blackout=False, emergency=True).frame, ZERO_FRAME)

    def test_reload_clears_holds_masks_selection_until_fresh_authority(self):
        self.player.select_scripted("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 0)
        self.player.set_static_layers((_layer(16),))
        self.player.set_blackout(True)
        result = self.player.reload(_pack(self.track, self.loop))
        self.assertEqual(result.frame, ZERO_FRAME)
        self.assertEqual(result.diagnostic.code, "reload_waiting_authority")
        self.assertEqual(self.player.static_layers, ())
        self.assertFalse(self.player.blackout)
        self.assertEqual(self.player.render().frame, ZERO_FRAME)

    def test_unknown_loop_missing_phase_and_invalid_identity_zero(self):
        for identity, phase, code in (
                ("missing", 0, "autoloop_not_found"),
                ("SSAutoLoop8.ssfile", None, "missing_phase")):
            result = self.player.select_autoloop(identity, phase)
            self.assertEqual(result.frame, ZERO_FRAME)
            self.assertEqual(result.diagnostic.code, code)


class LoaderTests(unittest.TestCase):
    @staticmethod
    def _runtime_rows():
        manifest = {
            "project": {
                "container_version": 5,
                "project_uuid": "project",
                "soundswitch_version": "2.9",
                "venue_guid": "venue",
                "sensitive_path": "/private/project",
            },
            "supported_boundary": {
                "channel_span": "CH1-CH19",
                "fixture_profile_guid": "fixture",
                "project_uuid": "project",
                "soundswitch_version": "2.9",
                "universe": 1,
            },
            "source_inventory": [{
                "path": "safe/relative", "sha256": "a" * 64,
                "size": 10, "parse_status": "parsed",
            }],
            "active_cue_union": {"count": 2, "sha256": "b" * 64},
            "totals": {"active_autoloops": 1},
        }
        selection = {
            "bridge_scenes": [{
                "policy_name": "phrase", "resolution": "project_target",
                "control_classification": "pack_selection",
                "target_identity": "SSAutoLoop1.ssfile",
            }],
            "learned_controls": [{
                "active": True, "device_name": "DDJ", "message_type": "note",
                "channel_zero_based": 0, "data_byte": 7,
                "control_classification": "static_override",
                "target_kind": "static_look", "target_index": 8,
                "interaction_mode": "toggle",
            }],
        }
        return manifest, selection

    def test_runtime_metadata_is_sanitized_immutable_and_binding_owned_by_loader(self):
        manifest, selection = self._runtime_rows()
        crosswalk, bindings, project, boundary, source_hash, union, totals = (
            _runtime_metadata(manifest, selection)
        )
        self.assertEqual(crosswalk["phrase"], "SSAutoLoop1.ssfile")
        self.assertEqual(bindings[0].target_slot, 8)
        self.assertEqual(bindings[0].interaction, "toggle")
        self.assertNotIn("sensitive_path", project)
        self.assertEqual(len(source_hash), 64)
        self.assertEqual(union["count"], 2)
        self.assertEqual(totals["active_autoloops"], 1)
        with self.assertRaises(TypeError):
            crosswalk["phrase"] = "changed"

    def test_runtime_metadata_rejects_duplicate_policy_and_active_event(self):
        manifest, selection = self._runtime_rows()
        selection["bridge_scenes"].append(dict(selection["bridge_scenes"][0]))
        with self.assertRaisesRegex(SoundSwitchPackLoadError, "duplicate bridge"):
            _runtime_metadata(manifest, selection)
        manifest, selection = self._runtime_rows()
        selection["learned_controls"].append(dict(selection["learned_controls"][0]))
        with self.assertRaisesRegex(SoundSwitchPackLoadError, "duplicate active"):
            _runtime_metadata(manifest, selection)

    def test_runtime_metadata_rejects_missing_bad_and_duplicate_static_interaction(self):
        manifest, selection = self._runtime_rows()
        del selection["learned_controls"][0]["interaction_mode"]
        with self.assertRaisesRegex(SoundSwitchPackLoadError, "interaction mode"):
            _runtime_metadata(manifest, selection)

        manifest, selection = self._runtime_rows()
        selection["learned_controls"][0]["interaction_mode"] = "momentary"
        with self.assertRaisesRegex(SoundSwitchPackLoadError, "interaction mode"):
            _runtime_metadata(manifest, selection)

        manifest, selection = self._runtime_rows()
        duplicate = dict(selection["learned_controls"][0])
        duplicate["data_byte"] = 8
        selection["learned_controls"].append(duplicate)
        with self.assertRaisesRegex(SoundSwitchPackLoadError, "slot ownership"):
            _runtime_metadata(manifest, selection)

    def test_loader_autoloop_bindings_include_identity_and_display_name(self):
        loop = LoadedAutoloop("SSAutoLoop4.ssfile", True, _document(path="SSAutoLoop4.ssfile"))
        rows = [{
            "active": True,
            "device_name": "IAC Driver Bus 1",
            "message_type": "note",
            "channel_zero_based": 0,
            "data_byte": 96,
            "target_kind": "autoloop",
            "target_identity": "SSAutoLoop4.ssfile",
            "target_name": "House Drop",
        }]

        bindings = _autoloop_bindings(rows, {"SSAutoLoop4.ssfile": loop})

        self.assertEqual(bindings[(0, 96)].target_identity, "SSAutoLoop4.ssfile")
        self.assertEqual(bindings[(0, 96)].target_name, "House Drop")
        with self.assertRaises(TypeError):
            bindings[(0, 97)] = bindings[(0, 96)]

    def test_loader_autoloop_bindings_fail_closed_on_duplicate_missing_file_or_name(self):
        loop = LoadedAutoloop("SSAutoLoop4.ssfile", True, _document(path="SSAutoLoop4.ssfile"))
        row = {
            "active": True,
            "device_name": "IAC Driver Bus 1",
            "message_type": "note",
            "channel_zero_based": 0,
            "data_byte": 96,
            "target_kind": "autoloop",
            "target_identity": "SSAutoLoop4.ssfile",
            "target_name": "House Drop",
        }

        with self.assertRaisesRegex(SoundSwitchPackLoadError, "duplicate active Autoloop"):
            _autoloop_bindings((dict(row), dict(row)), {"SSAutoLoop4.ssfile": loop})
        missing_file = dict(row, target_identity="missing.ssfile")
        with self.assertRaisesRegex(SoundSwitchPackLoadError, "missing Autoloop"):
            _autoloop_bindings((missing_file,), {"SSAutoLoop4.ssfile": loop})
        missing_name = dict(row, target_name="")
        with self.assertRaisesRegex(SoundSwitchPackLoadError, "target_name"):
            _autoloop_bindings((missing_name,), {"SSAutoLoop4.ssfile": loop})

    def test_schema_is_mandatory_unknown_major_rejected_and_verifier_runs_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text(json.dumps({
                "schema_version": "2.0.0", "artifact_type": "manifest",
                "artifact_hashes": [],
            }))
            with mock.patch("rb_ss_bridge_v2.soundswitch_pack_loader.verify_pack",
                            return_value={"verified": True}) as verifier:
                with self.assertRaisesRegex(SoundSwitchPackLoadError, "major"):
                    load_pack(root)
                verifier.assert_called_once_with(root)

    def test_snapshot_change_after_verification_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extra = json.dumps({"schema_version": "1.0.0"}).encode()
            (root / "extra.json").write_bytes(extra)
            manifest_bytes = json.dumps({
                "schema_version": "1.0.0", "artifact_type": "manifest",
                "artifact_hashes": [{
                    "path": "extra.json", "size": len(extra), "sha256": "0" * 64,
                }],
            }).encode()
            (root / "manifest.json").write_bytes(manifest_bytes)
            verified = {
                "verified": True,
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            }
            with mock.patch("rb_ss_bridge_v2.soundswitch_pack_loader.verify_pack",
                            return_value=verified):
                with self.assertRaisesRegex(SoundSwitchPackLoadError, "changed after"):
                    load_pack(root)

    def test_loaded_models_are_immutable(self):
        look = _look(8, (1,) * 19)
        with self.assertRaises(FrozenInstanceError):
            look.slot_index = 9
        with self.assertRaises(TypeError):
            _pack().static_looks[8] = look


@unittest.skipUnless((Path.home() / "Music/SoundSwitch/default.ssproj/.ssproj").is_file(),
                     "canonical read-only SoundSwitch project is unavailable")
class CurrentPackGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.pack_path = Path(cls.workspace.name) / "pack"
        export_pack(Path.home() / "Music/SoundSwitch/default.ssproj", cls.pack_path)
        cls.pack = load_pack(cls.pack_path)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def test_ddj_slots_8_16_17_24_exact_ch1_ch19(self):
        expected = {
            8: "1800260000797c0000d6ff000000000000006e",
            16: "00000000000000000000000000000000000000",
            17: "26001d00006483ffffff00000000000000004f",
            24: "010015ff00288a00ff00ff00ff005d000000ff",
        }
        for slot, frame_hex in expected.items():
            with self.subTest(slot=slot):
                rendered = apply_layers(
                    ZERO_FRAME, (_layer(slot),), self.pack.static_looks, False, False,
                )
                self.assertEqual(bytes(rendered.frame).hex(),
                                 frame_hex)

    def test_current_pack_count_257_preroll_raw_zero_and_no_capture_state(self):
        loop13_row = self.pack.autoloops["SSAutoLoop13.ssfile"]
        self.assertTrue(loop13_row.supported_active)
        loop13 = loop13_row.document
        self.assertEqual(len(loop13.events), 257)
        self.assertLess(loop13.events[0].time, 0)
        self.assertEqual(bytes(render_autoloop_frame(loop13, 0)).hex(),
                         "3e00000000000089d600000000000000000000")
        self.assertEqual(bytes(render_autoloop_frame(loop13, 1)).hex(),
                         "3e003700005d8a89d600000000001400000000")
        self.assertEqual(render_autoloop_frame(loop13, 0),
                         render_autoloop_frame(loop13, 19_200))
        loop3 = self.pack.autoloops["SSAutoLoop3.ssfile"].document
        self.assertTrue(any(row.raw_reference == 0 for row in loop3.events))
        self.assertEqual(render_autoloop_frame(loop3, 1), ZERO_FRAME)
        self.assertNotIn("capture", repr(self.pack).lower())
        self.assertNotIn("oracle", repr(self.pack).lower())

    def test_only_active_inventory_is_selectable_but_inactive_rows_are_retained(self):
        self.assertEqual(sum(row.supported_active for row in self.pack.autoloops.values()),
                         self.pack.totals["iac_autoloop_bindings"])
        self.assertEqual(sum(row.supported_active for row in self.pack.scripted.values()),
                         self.pack.totals["active_existing_path_scripted"])
        inactive_loop = next(row for row in self.pack.autoloops.values()
                             if not row.supported_active)
        inactive_script = next(row for row in self.pack.scripted.values()
                               if row.status == "supported_mapped_primary"
                               and not row.supported_active)
        player = LaserPackPlayer(self.pack)
        loop_result = player.select_autoloop(inactive_loop.identity, 0)
        self.assertEqual(loop_result.frame, ZERO_FRAME)
        self.assertEqual(loop_result.diagnostic.code, "inactive_autoloop")
        script_result = player.select_scripted(inactive_script.soundswitch_id, 0)
        self.assertEqual(script_result.frame, ZERO_FRAME)
        self.assertEqual(script_result.diagnostic.code, "unsupported_scripted")

    def test_catalog_tail_is_retained_distinctly_and_never_enters_player_patches(self):
        self.assertGreater(len(self.pack.render_cue_guids), 0)
        self.assertGreater(len(self.pack.catalog_tail_guids), 0)
        self.assertTrue(self.pack.render_cue_guids.isdisjoint(self.pack.catalog_tail_guids))
        referenced = {
            event.resolved_cue_guid
            for row in self.pack.autoloops.values()
            for event in row.document.events
            if event.resolved_cue_guid is not None and event.patch
        }
        referenced.update(
            event.resolved_cue_guid
            for row in self.pack.scripted.values()
            if row.document is not None
            for event in row.document.events
            if event.resolved_cue_guid is not None and event.patch
        )
        self.assertTrue(referenced.isdisjoint(self.pack.catalog_tail_guids))

    def test_loader_rejects_catalog_tail_guid_collision_after_canonical_rehash(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / "pack"
            shutil.copytree(self.pack_path, mutated)

            def collide(value):
                render_guid = next(row["cue_guid"] for row in value["records"]
                                   if row["record_kind"] == "fixture_payload")
                tail = next(row for row in value["records"]
                            if row["record_kind"] == "minimal_default_catalog_tail")
                tail["cue_guid"] = render_guid

            _rewrite_pack_artifact(mutated, "venue_cues.json", collide)
            with self.assertRaisesRegex(SoundSwitchPackLoadError, "catalog-tail GUID"):
                load_pack(mutated)

    def test_loader_rejects_active_script_reclassified_unsupported_after_rehash(self):
        active = next(row for row in self.pack.scripted.values() if row.supported_active)
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / "pack"
            shutil.copytree(self.pack_path, mutated)

            def deactivate(value):
                value["classification"]["status"] = "unsupported_inactive_layout"

            relative = f"scripted/{active.soundswitch_id}.json"
            _rewrite_pack_artifact(mutated, relative, deactivate)
            with self.assertRaisesRegex(SoundSwitchPackLoadError,
                                        "active scripted inventory"):
                load_pack(mutated)

    def test_scripted_exported_boundary_golden_samples_and_stop_unload_zero(self):
        samples = {
            "025c1ddf-2cdc-4e54-bd8c-156b90dd8247": (
                83_839, "3e001530006e8b3ee000000000009400f10048"),
            "ae9e3c61-af40-4392-80b4-380d39c631b9": (
                14_738, "000000000000005a7300000000000000000000"),
        }
        for soundswitch_id, (elapsed_ms, frame_hex) in samples.items():
            with self.subTest(soundswitch_id=soundswitch_id):
                track = self.pack.scripted[soundswitch_id]
                self.assertEqual(bytes(render_scripted_frame(track, elapsed_ms)).hex(), frame_hex)
        player = LaserPackPlayer(self.pack)
        for transport in ("stopped", "unloaded"):
            self.assertEqual(player.select_scripted(next(iter(samples)), 83_839,
                                                    transport=transport).frame, ZERO_FRAME)

    def test_current_pack_override_and_blackout_release_full_frame_goldens(self):
        soundswitch_id = "025c1ddf-2cdc-4e54-bd8c-156b90dd8247"
        at_83839 = "3e001530006e8b3ee000000000009400f10048"
        at_84065 = "11001530006e8ba5ff00000000009400f10048"
        slot8 = "1800260000797c0000d6ff000000000000006e"
        player = LaserPackPlayer(self.pack)
        self.assertEqual(bytes(player.select_scripted(soundswitch_id, 83_839).frame).hex(),
                         at_83839)
        self.assertEqual(bytes(player.set_static_layers((_layer(8),)).frame).hex(), slot8)
        self.assertEqual(bytes(player.set_static_layers(()).frame).hex(), at_83839)
        self.assertEqual(player.set_blackout(True).frame, ZERO_FRAME)
        self.assertEqual(player.select_scripted(soundswitch_id, 84_065).frame, ZERO_FRAME)
        self.assertEqual(bytes(player.set_blackout(False).frame).hex(), at_84065)


if __name__ == "__main__":
    unittest.main()
