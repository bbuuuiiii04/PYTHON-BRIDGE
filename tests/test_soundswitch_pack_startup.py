"""Focused T7b startup-selection tests; all output workers are fakes."""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import rb_ss_bridge_v2.__main__ as bridge_main
from rb_ss_bridge_v2.laser_config import LaserConfig, LaserConfigResult
from rb_ss_bridge_v2.laser_models import LaserMidiMessage
from rb_ss_bridge_v2.laser_output_backend import MidiOutputBackend, NoneBackend, PackOutputBackend
from rb_ss_bridge_v2.soundswitch_midi_input import (
    MidiInputSnapshot,
    SoundSwitchMidiInputGroup,
)
from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedPack, PackMidiBinding
from rb_ss_bridge_v2.soundswitch_pack_player_config import (
    SoundSwitchPackPlayerConfig,
    SoundSwitchPackPlayerConfigResult,
)


def _pack() -> LoadedPack:
    return LoadedPack(
        schema_version="1.0.0",
        manifest_sha256="a" * 64,
        has_intensity_channel=False,
        scripted=MappingProxyType({}),
        autoloops=MappingProxyType({}),
        static_looks=MappingProxyType({}),
        bridge_scene_crosswalk=MappingProxyType({"phrase": "SSAutoLoop1.ssfile"}),
        learned_midi_bindings=(PackMidiBinding(
            "DDJ", "note", 0, 7, "static_look", target_slot=8,
        ),),
    )


def _result(*, enabled=True, dry_run=False, output_backend="pack",
            enttec_port="fake-enttec", aliases=None):
    return SoundSwitchPackPlayerConfigResult(
        available=True,
        reason="ok",
        config=SoundSwitchPackPlayerConfig(
            enabled=enabled,
            dry_run=dry_run,
            output_backend=output_backend,
            pack_path="verified-pack",
            fixture_map=MappingProxyType({channel: 20 + channel for channel in range(1, 20)}),
            fixture_map_path="",
            midi_input_aliases=MappingProxyType(dict(aliases or {})),
            enttec_port=enttec_port,
            frame_stale_timeout_ms=250,
            controller_hold_timeout_ms=2000,
        ),
    )


class _LifecycleFake:
    def __init__(self, name, events, *, fail_start=False):
        self.name = name
        self.events = events
        self.fail_start = fail_start

    def start(self):
        self.events.append(f"{self.name}.start")
        if self.fail_start:
            raise RuntimeError("synthetic start failure")

    def stop(self):
        self.events.append(f"{self.name}.stop")


class StartupMatrixTests(unittest.TestCase):
    def _build(self, result, *, input_fail=False, sender_fail=False,
               pack_loader=lambda _path: _pack(), start=True):
        events = []
        controller = _LifecycleFake("input", events, fail_start=input_fail)
        sender = _LifecycleFake("sender", events, fail_start=sender_fail)
        captured = {}

        def input_factory(bindings, aliases, *, stale_timeout_ms):
            captured["bindings"] = bindings
            captured["aliases"] = aliases
            captured["hold"] = stale_timeout_ms
            return controller

        def sender_factory(port, *, fixture_map, idle_blackout_s):
            captured["port"] = port
            captured["fixture_map"] = fixture_map
            captured["idle"] = idle_blackout_s
            return sender

        bundle = bridge_main._build_soundswitch_pack_startup(
            result,
            pack_loader=pack_loader,
            player_factory=lambda pack: ("player", pack),
            frame_sender_factory=sender_factory,
            midi_input_factory=input_factory,
        )
        if start:
            bundle = bridge_main._start_soundswitch_pack_workers(bundle)
        return bundle, events, captured

    def test_absent_invalid_disabled_preserve_legacy_but_load_failure_is_no_output(self):
        cases = (
            SoundSwitchPackPlayerConfigResult(False, "not_configured"),
            SoundSwitchPackPlayerConfigResult(False, "invalid_config", errors=("bad",)),
            _result(enabled=False),
        )
        for result in cases:
            with self.subTest(reason=result.reason):
                bundle, events, _ = self._build(result)
                self.assertIsNone(bundle.laser_backend)
                self.assertEqual(events, [])
        bundle, events, _ = self._build(
            _result(), pack_loader=lambda _path: (_ for _ in ()).throw(ValueError("bad")),
        )
        self.assertIsInstance(bundle.laser_backend, NoneBackend)
        self.assertEqual(events, [])

    def test_midi_none_and_dry_run_matrix(self):
        midi, events, _ = self._build(_result(output_backend="midi"))
        self.assertIsNone(midi.laser_backend)
        self.assertEqual(events, [])
        for result in (_result(output_backend="none"), _result(dry_run=True)):
            with self.subTest(backend=result.config.output_backend,
                              dry_run=result.config.dry_run):
                bundle, events, _ = self._build(result)
                self.assertIsInstance(bundle.laser_backend, NoneBackend)
                self.assertEqual(events, [])

    def test_pack_starts_controller_then_sender_with_verified_inputs(self):
        bundle, events, captured = self._build(_result(aliases={"DDJ": "fake-midi"}))
        self.assertIsInstance(bundle.laser_backend, PackOutputBackend)
        self.assertEqual(events, ["input.start", "sender.start"])
        self.assertEqual(captured["bindings"], _pack().learned_midi_bindings)
        self.assertEqual(captured["aliases"], {"DDJ": "fake-midi"})
        self.assertEqual(captured["fixture_map"], {channel: 20 + channel for channel in range(1, 20)})
        self.assertEqual(captured["idle"], 0.25)

    def test_partial_start_failures_stop_both_and_never_fall_back_to_midi(self):
        for input_fail, sender_fail in ((True, False), (False, True)):
            with self.subTest(input_fail=input_fail, sender_fail=sender_fail):
                bundle, events, _ = self._build(
                    _result(), input_fail=input_fail, sender_fail=sender_fail,
                )
                self.assertIsInstance(bundle.laser_backend, NoneBackend)
                self.assertIsNone(bundle.frame_sender)
                self.assertIsNone(bundle.midi_input)
                self.assertIn("sender.stop", events)
                self.assertIn("input.stop", events)
                if input_fail:
                    self.assertNotIn("sender.start", events)

    def test_missing_enttec_is_no_output(self):
        bundle, events, _ = self._build(_result(enttec_port=""))
        self.assertIsInstance(bundle.laser_backend, NoneBackend)
        self.assertEqual(events, [])

    def test_legacy_builder_constructs_and_starts_midi_once_only_for_none_backend(self):
        cfg = LaserConfig(
            enabled=True, dry_run=False, smart_drop_mode="blackout_mask",
            midi_output_port="fake-midi", scenes={}, personalities={},
            default_personality="", startup_scene="safe", stop_scene="safe",
            stale_scene="safe", emergency_scene="safe", fallback_scene="safe",
        )
        created = []

        class FakeMidi:
            def __init__(self, *, port_name, dry_run):
                created.append((port_name, dry_run, "construct"))

            def start(self):
                created.append(("start",))

            def status(self):
                return {}

        result = LaserConfigResult(True, "ok", cfg)
        with mock.patch.object(bridge_main, "MidiOutput", FakeMidi):
            legacy = bridge_main._build_laser_startup_wiring(result)
            pack = bridge_main._build_laser_startup_wiring(result, backend=NoneBackend())
        self.assertIsInstance(legacy.laser_executor._backend, MidiOutputBackend)
        self.assertEqual(created, [("fake-midi", False, "construct"), ("start",)])
        self.assertIsNone(pack.midi_output)
        self.assertIsInstance(pack.laser_executor._backend, NoneBackend)

    def test_shutdown_zeros_pack_before_slow_bridge_joins(self):
        source = inspect.getsource(bridge_main.main)
        self.assertLess(source.index("signal.signal(signal.SIGTERM, _early_shutdown)"),
                        source.index("_start_soundswitch_pack_workers("))
        shutdown = source[source.index("def _shutdown(sig, frame):"):]
        self.assertLess(shutdown.index("_cleanup_pack_outputs()"),
                        shutdown.index("LOG.stop_control_watcher()"))
        self.assertLess(shutdown.index("_cleanup_pack_outputs()"),
                        shutdown.index("sm.stop()"))

    def test_shutdown_zeros_live_swapped_sender_not_just_startup(self):
        """After a runtime swap, shutdown must zero the LIVE sender; stopping the
        stale startup sender must be a harmless no-op."""
        calls = []

        class FakeSender:
            def __init__(self, name):
                self.name = name

            def stop(self):
                calls.append(f"{self.name}.stop")

        class FakeInput:
            def __init__(self, name):
                self.name = name

            def stop(self):
                calls.append(f"{self.name}.stop")

        class FakeRuntime:
            def __init__(self, sender, midi_input):
                self.frame_sender = sender
                self.midi_input = midi_input

        class FakeSM:
            def __init__(self, rt):
                self._rt = rt

            def get_pack_runtime(self):
                return self._rt

        startup_sender = FakeSender("startup_sender")
        startup_input = FakeInput("startup_input")
        live_sender = FakeSender("live_sender")  # installed by a runtime swap
        live_input = FakeInput("live_input")
        owners = {"sender": startup_sender, "midi_input": startup_input}
        sm = FakeSM(FakeRuntime(live_sender, live_input))

        bridge_main._shutdown_zero_pack_outputs(owners, sm)

        # The live swapped sender/input MUST be stopped (final zero frame + close).
        self.assertIn("live_sender.stop", calls)
        self.assertIn("live_input.stop", calls)
        # The stale startup sender is still stopped (harmless), proving no path is skipped.
        self.assertIn("startup_sender.stop", calls)
        self.assertIn("startup_input.stop", calls)
        # Startup-owner slots are drained so that branch is a no-op on repeat cleanup.
        self.assertNotIn("sender", owners)
        self.assertNotIn("midi_input", owners)

    def test_shutdown_pre_sm_window_only_touches_startup_owners(self):
        """Before StateManager exists (sm=None), only the startup slots are stopped
        and no live-runtime read is attempted."""
        calls = []

        class FakeSender:
            def stop(self):
                calls.append("startup.stop")

        owners = {"sender": FakeSender(), "midi_input": None}
        bridge_main._shutdown_zero_pack_outputs(owners, None)  # must not raise
        self.assertEqual(calls, ["startup.stop"])

    def test_shutdown_disabled_runtime_is_noop(self):
        """Default-off: a runtime with no sender/input must be a guarded no-op."""
        class FakeRuntime:
            frame_sender = None
            midi_input = None

        class FakeSM:
            def get_pack_runtime(self):
                return FakeRuntime()

        owners = {"sender": None, "midi_input": None}
        bridge_main._shutdown_zero_pack_outputs(owners, FakeSM())  # must not raise


class InputGroupTests(unittest.TestCase):
    binding = PackMidiBinding("DDJ", "note", 0, 7, "static_look", target_slot=8)

    def test_duplicate_port_and_unknown_device_rejected_before_construction(self):
        calls = []
        factory = lambda *args, **kwargs: calls.append((args, kwargs))
        with self.assertRaisesRegex(ValueError, "distinct ports"):
            SoundSwitchMidiInputGroup(
                (self.binding, PackMidiBinding("OTHER", "note", 0, 8,
                                               "static_look", target_slot=16)),
                {"DDJ": "same", "OTHER": "same"}, adapter_factory=factory,
            )
        with self.assertRaisesRegex(ValueError, "verified binding"):
            SoundSwitchMidiInputGroup((self.binding,), {"UNKNOWN": "port"},
                                      adapter_factory=factory)
        self.assertEqual(calls, [])

    def test_start_rollback_and_sanitized_status(self):
        events = []

        class Adapter:
            def __init__(self, bindings, *, stale_timeout_ms):
                self.device = bindings[0].device_name

            def start(self, port, *, device_name):
                events.append(("start", device_name))
                if device_name == "OTHER":
                    raise RuntimeError("fail")

            def stop(self):
                events.append(("stop", self.device))

            def snapshot(self):
                return MidiInputSnapshot(None, False, False, None, 0)

        bindings = (self.binding, PackMidiBinding(
            "OTHER", "note", 0, 8, "static_look", target_slot=16,
        ))
        group = SoundSwitchMidiInputGroup(
            bindings, {"DDJ": "secret-a", "OTHER": "secret-b"}, adapter_factory=Adapter,
        )
        with self.assertRaisesRegex(RuntimeError, "startup failed"):
            group.start()
        self.assertEqual(events[:2], [("start", "DDJ"), ("start", "OTHER")])
        status = group.status()
        self.assertNotIn("secret", repr(status))
        self.assertNotIn("DDJ", repr(status))


class PackBackendIdentityTests(unittest.TestCase):
    def test_identity_updates_only_on_accept_and_reset_clears(self):
        frames = []
        sender = mock.Mock()
        sender.submit.side_effect = frames.append
        backend = PackOutputBackend(
            scene_to_identity={"phrase": "SSAutoLoop1.ssfile"}, frame_sender=sender,
        )
        self.assertTrue(backend.trigger(LaserMidiMessage(scene_name="phrase")))
        self.assertEqual(backend.last_accepted_identity, "SSAutoLoop1.ssfile")
        self.assertFalse(backend.trigger(LaserMidiMessage(scene_name="unlearned")))
        self.assertEqual(backend.last_accepted_identity, "SSAutoLoop1.ssfile")
        backend.submit_frame((1,) * 19)
        self.assertEqual(frames, [(1,) * 19])
        backend.reset()
        self.assertIsNone(backend.last_accepted_identity)


if __name__ == "__main__":
    unittest.main()
