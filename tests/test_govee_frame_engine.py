"""Pure tests for the Govee frame engine host + client (AWR-146, Part D 1-14).

No real strip sockets, no real subprocess, no real sleeps: the host is driven
through a duplex os.pipe-backed fake and injected fake runners/transports; the
client is driven tick-by-tick with a fake clock, fake conn, and fake child.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_engine import (  # noqa: E402
    ANCHOR_STALE_S,
    FrameEngineHost,
    decode_buffer,
    encode_msg,
)
from rb_ss_bridge_v2.govee_frame_engine_client import GoveeFrameEngineClient  # noqa: E402
from rb_ss_bridge_v2.govee_frame_renderer import GoveeFrameRenderer  # noqa: E402
from rb_ss_bridge_v2.govee_realtime_runner import EffectSpec, GoveeRealtimeRunner  # noqa: E402
from rb_ss_bridge_v2.led_models import BeatAnchor  # noqa: E402


def _init(**over) -> dict:
    base = {
        "t": "init", "dry_run": True, "ip": "10.0.0.9", "port": 4003,
        "segments": 4, "fps": 60, "grace_s": 0.25,
        "header_bytes": [0xBB, 0x00, 0xFA, 0xB0, 0x00], "stretch": False,
        "activate_pt": "uwABsQEK", "deactivate_pt": "uwABsQAL",
    }
    base.update(over)
    return base


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def activate(self) -> bool:
        self.calls.append("activate"); return True

    def deactivate(self) -> bool:
        self.calls.append("deactivate"); return True

    def set_brightness(self, value: int) -> bool:
        self.calls.append(f"brightness:{value}"); return True

    def send_frame(self, frame) -> bool:
        self.calls.append("send_frame"); return True

    def blackout(self) -> bool:
        self.calls.append("blackout"); return True

    def close(self) -> None:
        self.calls.append("close")

    def status(self) -> dict:
        return {}


class RecordingRunner:
    """Fake runner that records the host's duck-typed calls."""

    def __init__(self, *a, **k) -> None:
        self.calls: list[str] = []
        self.set_desired_specs: list = []
        self.started = False
        self.stopped = False
        self.status_dict: dict = {"frame_index": 0, "active": False}

    def set_beat_provider(self, provider) -> None:
        self.calls.append("set_beat_provider")

    def start(self) -> None:
        self.started = True

    def stop(self, timeout_s: float = 1.0) -> bool:
        self.stopped = True; return True

    def set_desired(self, spec) -> None:
        self.set_desired_specs.append(spec)
        self.calls.append("set_desired" if spec is not None else "set_desired:None")

    def fire_trigger(self) -> None:
        self.calls.append("fire_trigger")

    def request_activate_assert(self) -> None:
        self.calls.append("request_activate_assert")

    def request_brightness(self, value: int) -> None:
        self.calls.append(f"request_brightness:{value}")

    def emergency_stop(self) -> None:
        self.calls.append("emergency_stop")

    def force_deactivate(self) -> None:
        self.calls.append("force_deactivate")

    def status(self) -> dict:
        return dict(self.status_dict)


class HostFakeConn:
    """Duplex fake: recv() reads bytes fed via feed(); send() records. Backed by
    an os.pipe so select() sees readability (kernel pipe, not a socket)."""

    def __init__(self) -> None:
        self._r, self._w = os.pipe()
        self.sent = bytearray()

    def feed(self, data: bytes) -> None:
        os.write(self._w, data)

    def eof(self) -> None:
        os.close(self._w)

    def recv(self, n: int) -> bytes:
        return os.read(self._r, n)

    def send(self, data: bytes) -> int:
        self.sent += data
        return len(data)

    def fileno(self) -> int:
        return self._r

    def close(self) -> None:
        try:
            os.close(self._r)
        except OSError:
            pass

    def messages(self) -> list[dict]:
        msgs, _ = decode_buffer(bytes(self.sent))
        return msgs


def _anchor_wire(now: float, *, playing=True, permitted=True) -> dict:
    return {"deck": 1, "abs_beat_pos": 64.0, "bpm": 128.0,
            "captured_monotonic": now, "playing": playing, "permitted": permitted}


# ── Host tests (Part D 1-8) ─────────────────────────────────────────────────────

class FrameEngineHostTests(unittest.TestCase):
    def test_1_init_deactivates_once_before_runner_start(self) -> None:
        seen = {}

        def tf(init):
            seen["init"] = init
            return RecordingTransport()

        runner = RecordingRunner()
        host = FrameEngineHost(
            HostFakeConn(), transport_factory=tf,
            runner_factory=lambda *a, **k: runner)
        init = _init(dry_run=False)
        host._setup(init)
        self.assertEqual(seen["init"], init)
        self.assertEqual(host._transport.calls, ["deactivate"])  # exactly one
        self.assertFalse(runner.started)  # runner not started by _setup

    def test_1b_dry_run_does_not_deactivate(self) -> None:
        host = FrameEngineHost(
            HostFakeConn(), transport_factory=lambda i: RecordingTransport(),
            runner_factory=lambda *a, **k: RecordingRunner())
        host._setup(_init(dry_run=True))
        self.assertEqual(host._transport.calls, [])

    def test_2_anchor_provider_null_and_stale(self) -> None:
        clk = [100.0]
        host = FrameEngineHost(
            HostFakeConn(), transport_factory=lambda i: None,
            time_fn=lambda: clk[0])
        host.handle_message({"t": "anchor", "a": _anchor_wire(100.0)})
        self.assertEqual(
            host.beat_provider(),
            BeatAnchor(1, 64.0, 128.0, 100.0, True, True))
        host.handle_message({"t": "anchor", "a": None})
        self.assertIsNone(host.beat_provider())
        host.handle_message({"t": "anchor", "a": _anchor_wire(100.0)})
        clk[0] = 100.0 + ANCHOR_STALE_S + 0.01
        self.assertIsNone(host.beat_provider())

    def test_3_params_list_roundtrip_renders_equal(self) -> None:
        renderer = GoveeFrameRenderer()
        as_tuple = renderer.render(
            "solid", beat_pos=0.0, local_t=0.0, frame_index=0,
            params={"color": (10, 20, 30)}, segments=4, seed=1)
        as_list = renderer.render(
            "solid", beat_pos=0.0, local_t=0.0, frame_index=0,
            params={"color": [10, 20, 30]}, segments=4, seed=1)
        self.assertEqual(as_tuple, as_list)
        # And the host builds an EffectSpec (list params survive the JSON boundary).
        runner = RecordingRunner()
        host = FrameEngineHost(HostFakeConn(), transport_factory=lambda i: None)
        host._runner = runner
        wire = encode_msg({"t": "set_desired", "spec": {
            "effect_name": "solid", "params": {"color": [10, 20, 30]},
            "seed": 1, "applied_monotonic": 100.0, "sync_mode": "",
            "beat_division": 0.0}})
        msgs, _ = decode_buffer(wire)
        host.handle_message(msgs[0])
        spec = runner.set_desired_specs[-1]
        self.assertIsInstance(spec, EffectSpec)
        self.assertEqual(spec.params["color"], [10, 20, 30])

    def test_4_command_fanout(self) -> None:
        runner = RecordingRunner()
        host = FrameEngineHost(HostFakeConn(), transport_factory=lambda i: None)
        host._runner = runner
        for msg in ({"t": "fire_trigger"}, {"t": "activate_assert"},
                    {"t": "brightness", "value": 0}, {"t": "emergency_stop"},
                    {"t": "force_deactivate"}):
            host.handle_message(msg)
        self.assertEqual(runner.calls, [
            "fire_trigger", "request_activate_assert", "request_brightness:0",
            "emergency_stop", "force_deactivate"])
        # set_desired null → runner.set_desired(None)
        host.handle_message({"t": "set_desired", "spec": None})
        self.assertEqual(runner.calls[-1], "set_desired:None")
        # unknown type is a no-op (WARNING), not a crash
        self.assertTrue(host.handle_message({"t": "bogus"}))
        # shutdown returns False
        self.assertFalse(host.handle_message({"t": "shutdown"}))

    def _real_runner_host(self, transport, clk):
        def rf(tr, rnd, *, segments, fps, grace_s, on_thread_start):
            return GoveeRealtimeRunner(
                tr, rnd, segments=segments, fps=fps, grace_s=grace_s,
                time_fn=lambda: clk[0], on_thread_start=on_thread_start)
        host = FrameEngineHost(
            HostFakeConn(), transport_factory=lambda i: transport,
            runner_factory=rf, time_fn=lambda: clk[0])
        host._setup(_init(dry_run=True))
        return host

    def test_5_brightness0_through_boundary_while_inactive(self) -> None:
        # Task 6 / test 19 addendum: a NEVER-active runner still darkens via the
        # IPC brightness message — set_brightness(0) on 2 consecutive ticks.
        clk = [100.0]
        transport = RecordingTransport()
        host = self._real_runner_host(transport, clk)
        runner = host._runner
        host.handle_message({"t": "brightness", "value": 0})
        runner._tick_once(None, clk[0]); clk[0] += 0.02
        runner._tick_once(None, clk[0])
        self.assertEqual(transport.calls.count("brightness:0"), 2)
        self.assertNotIn("send_frame", transport.calls)  # never activated

    def test_5b_activate_assert_through_boundary(self) -> None:
        clk = [100.0]
        transport = RecordingTransport()
        host = self._real_runner_host(transport, clk)
        host.handle_message({"t": "activate_assert"})
        host._runner._tick_once(None, clk[0])
        self.assertIn("activate", transport.calls)

    def test_5c_keepalive_through_boundary(self) -> None:
        clk = [100.0]
        transport = RecordingTransport()
        host = self._real_runner_host(transport, clk)
        runner = host._runner
        host.handle_message({"t": "set_desired", "spec": {
            "effect_name": "solid", "params": {"color": [1, 2, 3]}, "seed": 1,
            "applied_monotonic": 100.0, "sync_mode": "", "beat_division": 0.0}})
        runner._tick_once(BeatAnchor(1, 64.0, 128.0, clk[0], True, True), clk[0])
        self.assertIn("activate", transport.calls)  # edge activate
        transport.calls.clear()
        clk[0] += 2.0  # RAZER_KEEPALIVE_S
        runner._tick_once(BeatAnchor(1, 64.0, 128.0, clk[0], True, True), clk[0])
        self.assertIn("activate", transport.calls)  # keepalive re-activate

    def test_6_eof_and_shutdown_teardown(self) -> None:
        for kind in ("eof", "shutdown"):
            conn = HostFakeConn()
            transport = RecordingTransport()
            host = FrameEngineHost(conn, transport_factory=lambda i: transport)
            thread = threading.Thread(target=host.run)
            thread.start()
            conn.feed(encode_msg(_init(dry_run=True)))
            if kind == "eof":
                conn.eof()
            else:
                conn.feed(encode_msg({"t": "shutdown"}))
            thread.join(timeout=3.0)
            self.assertFalse(thread.is_alive(), kind)
            self.assertEqual(transport.calls[-3:], ["blackout", "deactivate", "close"], kind)
            self.assertNotIn("brightness:0", transport.calls)  # cloud look survives
            conn.close()

    def test_7_heartbeat_fps_and_degraded(self) -> None:
        clk = [100.0]
        conn = HostFakeConn()
        runner = RecordingRunner()
        host = FrameEngineHost(conn, transport_factory=lambda i: None, time_fn=lambda: clk[0])
        host._runner = runner
        host._fps = 60
        # prime (first hb dt is 0 → achieved 0)
        runner.status_dict = {"frame_index": 0, "active": True}
        host._send_heartbeat(clk[0])
        clk[0] += 1.0
        runner.status_dict = {"frame_index": 60, "active": True}
        host._send_heartbeat(clk[0])
        hb = conn.messages()[-1]
        self.assertAlmostEqual(hb["achieved_fps"], 60.0, delta=0.5)
        self.assertFalse(hb["fps_degraded"])
        # 3 consecutive low-fps (20/s < 48) heartbeats while streaming → degraded
        degraded_flags = []
        for _ in range(3):
            clk[0] += 1.0
            runner.status_dict["frame_index"] += 20
            host._send_heartbeat(clk[0])
            degraded_flags.append(conn.messages()[-1]["fps_degraded"])
        self.assertEqual(degraded_flags, [False, False, True])
        # not streaming resets the counter (no longer degraded)
        clk[0] += 1.0
        runner.status_dict = {"frame_index": runner.status_dict["frame_index"], "active": False}
        host._send_heartbeat(clk[0])
        self.assertFalse(conn.messages()[-1]["fps_degraded"])

    def test_8_decode_buffer(self) -> None:
        buf = encode_msg({"t": "a"}) + b"not-json\n" + encode_msg({"t": "b"}) + b'{"t":"par'
        msgs, remainder = decode_buffer(buf)
        self.assertEqual([m["t"] for m in msgs], ["a", "b"])  # malformed skipped
        self.assertEqual(remainder, b'{"t":"par')  # partial line retained

    def test_7b_heartbeat_blockingio_is_skipped(self) -> None:
        """REQUIRED-4c: a send that raises BlockingIOError skips that heartbeat and
        does not propagate (the parent is slow to drain; the next hb is in 1 s)."""
        class _BlockConn(HostFakeConn):
            def send(self, data: bytes) -> int:
                raise BlockingIOError()

        conn = _BlockConn()
        runner = RecordingRunner()
        host = FrameEngineHost(conn, transport_factory=lambda i: None, time_fn=lambda: 100.0)
        host._runner = runner
        host._fps = 60
        host._send_heartbeat(100.0)  # must not raise
        self.assertEqual(bytes(conn.sent), b"")
        conn.close()

    def test_qos_missing_symbol_is_safe(self) -> None:
        """REQUIRED-3: a missing pthread_set_qos_class_self_np is a warn-and-return,
        not an exception that would silently kill the runner thread."""
        import rb_ss_bridge_v2.govee_frame_engine as eng

        class _Lib:  # no pthread_set_qos_class_self_np attribute
            pass

        orig = eng.ctypes.CDLL
        eng.ctypes.CDLL = lambda *a, **k: _Lib()
        try:
            eng._qos_user_interactive()  # must not raise
        finally:
            eng.ctypes.CDLL = orig


# ── Client fakes ────────────────────────────────────────────────────────────────

class FakeClientConn:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self._inbox = bytearray()
        self._eof = False
        self.block = False

    def push(self, data: bytes) -> None:
        self._inbox += data

    def eof(self) -> None:
        self._eof = True

    def send(self, data: bytes) -> int:
        if self.block:
            raise BlockingIOError()
        self.sent.append(bytes(data))
        return len(data)

    def recv(self, n: int) -> bytes:
        if self._inbox:
            out = bytes(self._inbox[:n]); del self._inbox[:n]; return out
        if self._eof:
            return b""
        raise BlockingIOError()

    def close(self) -> None:
        pass

    def messages(self) -> list[dict]:
        msgs, _ = decode_buffer(b"".join(self.sent))
        return msgs

    def types(self, *, drop_anchor=True) -> list[str]:
        return [m["t"] for m in self.messages()
                if not (drop_anchor and m["t"] == "anchor")]


class FakeProc:
    def __init__(self, honor_terminate: bool = True) -> None:
        self.rc = None
        self.honor_terminate = honor_terminate

    def poll(self):
        return self.rc

    def wait(self, timeout=None):
        if self.rc is None:
            raise subprocess.TimeoutExpired("govee_frame_engine", timeout)
        return self.rc

    def terminate(self) -> None:
        if self.honor_terminate:
            self.rc = -15

    def kill(self) -> None:
        self.rc = -9


class Spawner:
    def __init__(self, honor_terminate: bool = True) -> None:
        self.procs: list[FakeProc] = []
        self.conns: list[FakeClientConn] = []
        self._honor = honor_terminate

    def __call__(self, engine_init):
        proc = FakeProc(honor_terminate=self._honor)
        conn = FakeClientConn()
        self.procs.append(proc)
        self.conns.append(conn)
        return proc, conn


def _spec(name="solid"):
    return EffectSpec(name, {"color": (1, 2, 3)}, 7, 100.0)


def _make_client(spawner, clk):
    return GoveeFrameEngineClient(
        _init(), spawn_fn=spawner, time_fn=lambda: clk[0])


# ── Client tests (Part D 9-14) ──────────────────────────────────────────────────

class GoveeFrameEngineClientTests(unittest.TestCase):
    def test_9_no_caller_io_and_wire_order(self) -> None:
        clk = [100.0]
        sp = Spawner()
        c = _make_client(sp, clk)
        c._tick(clk[0])  # spawn child #0
        conn = sp.conns[0]
        conn.sent.clear()
        # Coordinator-facing methods must do ZERO I/O on the caller thread.
        c.set_desired(_spec())
        c.fire_trigger()
        c.request_activate_assert()
        self.assertEqual(conn.sent, [])
        # Draining on the client tick preserves command order on the wire.
        c._tick(clk[0])
        self.assertEqual(conn.types(), ["set_desired", "fire_trigger", "activate_assert"])

    def test_10_respawn_replays_intent(self) -> None:
        def scenario(setup):
            clk = [100.0]
            sp = Spawner()
            c = _make_client(sp, clk)
            c._tick(clk[0])          # spawn #0
            setup(c)                 # establish mirror intent
            c._tick(clk[0])          # drain onto #0
            sp.conns[0].eof()
            c._tick(clk[0])          # detect EOF
            clk[0] += 1.0
            c._tick(clk[0])          # kill + schedule respawn (backoff)
            clk[0] += 1.0
            c._tick(clk[0])          # respawn #1 + replay
            return c, sp

        # mid-look → set_desired + activate_assert
        c, sp = scenario(lambda c: c.set_desired(_spec()))
        self.assertEqual(sp.conns[1].types(), ["init", "set_desired", "activate_assert"])
        self.assertEqual(c._respawn_count, 1)

        # mid-emergency → emergency_stop + unconditional brightness 0
        c, sp = scenario(lambda c: c.emergency_stop())
        self.assertEqual(sp.conns[1].types(), ["init", "emergency_stop", "brightness"])
        bright = [m for m in sp.conns[1].messages() if m["t"] == "brightness"][0]
        self.assertEqual(bright["value"], 0)

        # force_deactivate (handoff) → force_deactivate only
        c, sp = scenario(lambda c: c.force_deactivate())
        self.assertEqual(sp.conns[1].types(), ["init", "force_deactivate"])

        # set_desired AFTER force_deactivate → replays as the look (handoff cleared)
        def fd_then_look(c):
            c.force_deactivate()
            c.set_desired(_spec())
        c, sp = scenario(fd_then_look)
        self.assertEqual(sp.conns[1].types(), ["init", "set_desired", "activate_assert"])

    def test_11_hung_and_stuck_respawn(self) -> None:
        # No heartbeat for >5 s → hung → kill + respawn.
        clk = [100.0]
        sp = Spawner()
        c = _make_client(sp, clk)
        c._tick(clk[0])  # spawn #0
        clk[0] += 6.0    # HEARTBEAT_STALE_S exceeded, no hb ever arrived
        c._tick(clk[0])  # detect hung → kill + schedule respawn
        self.assertIsNotNone(sp.procs[0].poll())  # killed
        clk[0] += 1.0
        c._tick(clk[0])  # respawn
        self.assertEqual(c._respawn_count, 1)
        self.assertEqual(len(sp.procs), 2)

        # A command stuck unsent >2 s → kill + respawn.
        clk = [100.0]
        sp = Spawner()
        c = _make_client(sp, clk)
        c._tick(clk[0])          # spawn #0
        sp.conns[0].block = True  # child stops draining
        c.set_desired(_spec())    # enqueue at t0
        c._tick(clk[0])          # drain blocked → command sticks
        clk[0] += 2.1            # COMMAND_STUCK_S exceeded
        c._tick(clk[0])          # detect stuck → kill
        self.assertIsNotNone(sp.procs[0].poll())
        clk[0] += 1.0
        c._tick(clk[0])          # backoff elapsed → a NEW child is spawned
        self.assertEqual(len(sp.procs), 2)
        self.assertEqual(c._respawn_count, 1)

    def test_12b_emergency_preserves_queued_brightness(self) -> None:
        """BLOCKING-1 regression: a blackout brightness-0 enqueued microseconds
        before emergency_stop() must survive promotion and follow emergency_stop
        on the wire (both delivered) — dropping it left the room lit."""
        clk = [100.0]
        sp = Spawner()
        c = _make_client(sp, clk)
        c._tick(clk[0])  # spawn #0
        sp.conns[0].sent.clear()
        c.request_brightness(0)  # operator-blackout LAN backstop
        c.emergency_stop()       # promotes; must NOT drop the brightness
        c._tick(clk[0])
        cmds = [t for t in sp.conns[0].types() if t in ("emergency_stop", "brightness")]
        self.assertEqual(cmds, ["emergency_stop", "brightness"])  # both, in order
        bright = [m for m in sp.conns[0].messages() if m["t"] == "brightness"][0]
        self.assertEqual(bright["value"], 0)

    def test_10b_respawn_replays_pending_brightness_only(self) -> None:
        """REQUIRED-2: when ONLY `_brightness_pending` is set (no desired/emergency/
        handoff), respawn replays exactly that brightness message — the trailing
        still-pending brightness resend in _replay_intent."""
        clk = [100.0]
        sp = Spawner()
        c = _make_client(sp, clk)
        c._tick(clk[0])          # spawn #0
        c.request_brightness(0)  # pending brightness, nothing else in intent
        sp.procs[0].rc = 1       # child crashes before the brightness drains
        c._tick(clk[0])          # detect dead → kill + schedule respawn
        clk[0] += 1.0
        c._tick(clk[0])          # respawn #1 + replay
        self.assertEqual(sp.conns[1].types(), ["init", "brightness"])
        bright = [m for m in sp.conns[1].messages() if m["t"] == "brightness"][0]
        self.assertEqual(bright["value"], 0)

    def test_12_emergency_jumps_queue(self) -> None:
        clk = [100.0]
        sp = Spawner()
        c = _make_client(sp, clk)
        c._tick(clk[0])  # spawn #0
        sp.conns[0].sent.clear()
        c.set_desired(_spec())   # queued look
        c.emergency_stop()       # promotes ahead + clears the queued look
        c._tick(clk[0])
        types = sp.conns[0].types()
        self.assertIn("emergency_stop", types)
        self.assertNotIn("set_desired", types)

    def test_13_status_merge_and_defaults(self) -> None:
        clk = [100.0]
        sp = Spawner()
        c = _make_client(sp, clk)
        # Before any heartbeat: safe defaults, engine_alive False.
        s0 = c.status()
        self.assertEqual(s0["engine_alive"], False)
        self.assertEqual(s0["achieved_fps"], 0.0)
        self.assertEqual(s0["active"], False)
        c._tick(clk[0])  # spawn #0
        sp.conns[0].push(encode_msg({
            "t": "hb", "pid": 1, "achieved_fps": 59.5, "streaming": True,
            "fps_degraded": False,
            "status": {"active": True, "provider_bound": True,
                       "desired_effect": "solid", "frame_index": 100,
                       "last_error": "", "razer_assert_count": 2}}))
        c._tick(clk[0])  # read heartbeat
        s = c.status()
        self.assertTrue(s["engine_alive"])
        self.assertEqual(s["achieved_fps"], 59.5)
        self.assertEqual(s["desired_effect"], "solid")
        self.assertEqual(s["razer_assert_count"], 2)
        self.assertEqual(s["frame_index"], 100)

    def test_14_stop_graceful_and_escalation(self) -> None:
        # Graceful: child already exited on shutdown → True.
        clk = [100.0]
        sp = Spawner()
        c = _make_client(sp, clk)
        c._tick(clk[0])  # spawn #0
        sp.procs[0].rc = 0  # child exits when shutdown lands
        self.assertTrue(c.stop())
        self.assertIn("shutdown", sp.conns[0].types())

        # Escalation: child ignores SIGTERM → kill() required → False.
        clk = [100.0]
        sp = Spawner(honor_terminate=False)
        c = _make_client(sp, clk)
        c._tick(clk[0])
        self.assertFalse(c.stop())
        self.assertEqual(sp.procs[0].poll(), -9)  # killed

    def test_14b_stop_terminate_middle_path_returns_true(self) -> None:
        """REQUIRED-4a: child ignores `shutdown` (never exits on the message) but
        honors terminate() → stop() returns True (exited before kill was needed)."""
        clk = [100.0]
        sp = Spawner(honor_terminate=True)
        c = _make_client(sp, clk)
        c._tick(clk[0])
        self.assertTrue(c.stop())
        self.assertEqual(sp.procs[0].poll(), -15)  # SIGTERM, not SIGKILL


if __name__ == "__main__":
    unittest.main()
