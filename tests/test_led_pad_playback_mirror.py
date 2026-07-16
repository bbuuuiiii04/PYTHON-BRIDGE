"""AWR-269: pad live-play mirror — tee transport + SSE gates."""

from __future__ import annotations

import http.client
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import GoveeFrameRenderer  # noqa: E402
from rb_ss_bridge_v2.govee_realtime_runner import EffectSpec, GoveeRealtimeRunner  # noqa: E402
from rb_ss_bridge_v2.govee_realtime_transport import GoveeRealtimeDryRunTransport  # noqa: E402
from rb_ss_bridge_v2.led_models import BeatAnchor  # noqa: E402
from rb_ss_bridge_v2.tools.led_pad_mirror import (  # noqa: E402
    FrameMirrorRing,
    TeeTransport,
)
from rb_ss_bridge_v2.tools.led_pad_web import LedPadService, build_handler  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE_PATH = _ROOT / "config" / "led_look_director.example.json"


class _RecordingTransport:
    def __init__(self, *, segments: int = 4) -> None:
        self.segments = segments
        self.frames: list[list[tuple[int, int, int]]] = []
        self.frames_sent = 0

    def activate(self) -> bool:
        return True

    def deactivate(self) -> bool:
        return True

    def set_brightness(self, value: int) -> bool:
        return True

    def send_frame(self, rgb_list) -> bool:  # type: ignore[no-untyped-def]
        self.frames.append([tuple(px) for px in rgb_list])
        self.frames_sent += 1
        return True

    def blackout(self) -> bool:
        return self.send_frame([(0, 0, 0)] * self.segments)

    def close(self) -> None:
        return None

    def status(self) -> dict:
        return {"frames_sent": self.frames_sent, "segments": self.segments}


class _FakePlayback:
    def __init__(self, ring: FrameMirrorRing | None = None) -> None:
        self.mirror = ring
        self._playing = False
        self._look = ""

    def status(self):
        return {
            "playing": self._playing,
            "playing_look": self._look,
            "bridge_owned": False,
        }

    def ownership(self):
        return {"state": "free", "warning": ""}

    def shutdown(self):
        return None


@contextmanager
def _pad_http(service: LedPadService):
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        service.shutdown()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def _anchor(now: float = 100.0) -> BeatAnchor:
    return BeatAnchor(
        deck=1,
        abs_beat_pos=64.0,
        bpm=120.0,
        captured_monotonic=now,
        playing=True,
        permitted=True,
    )


class FrameMirrorRingTests(unittest.TestCase):
    def test_append_is_bounded_and_drops_oldest(self) -> None:
        ring = FrameMirrorRing(maxlen=3, time_fn=lambda: 1.0)
        for i in range(5):
            ring.append([(i, 0, 0)])
        self.assertEqual(len(ring), 3)
        self.assertEqual(ring.maxlen, 3)
        latest = ring.latest()
        assert latest is not None
        self.assertEqual(latest[1][0], (4, 0, 0))


class TeeTransportTests(unittest.TestCase):
    def test_forwards_and_tees_immutable_snapshot(self) -> None:
        inner = _RecordingTransport(segments=2)
        ring = FrameMirrorRing(maxlen=8, time_fn=lambda: 42.0)
        tee = TeeTransport(inner, ring)
        frame = [(10, 20, 30), (1, 2, 3)]
        ok = tee.send_frame(frame)
        self.assertTrue(ok)
        self.assertEqual(inner.frames, [[(10, 20, 30), (1, 2, 3)]])
        entry = ring.latest()
        assert entry is not None
        self.assertEqual(entry[0], 42.0)
        self.assertEqual(entry[1], ((10, 20, 30), (1, 2, 3)))
        # Mutating the caller's list must not change the ring snapshot.
        frame[0] = (99, 99, 99)
        self.assertEqual(ring.latest()[1][0], (10, 20, 30))


class Awr269CadenceGateTests(unittest.TestCase):
    """Stalled mirror consumer must not change runner frame cadence."""

    def _run_n_ticks(
        self,
        *,
        tee: TeeTransport,
        n: int,
        fps: float = 40.0,
    ) -> tuple[float, list[float], dict]:
        clock = [1000.0]
        sleeps: list[float] = []
        step_done = threading.Event()
        proceed = threading.Event()

        def time_fn() -> float:
            return clock[0]

        def sleep_fn(interval: float) -> None:
            sleeps.append(float(interval))
            clock[0] += 1.0 / fps
            step_done.set()
            proceed.wait(timeout=2.0)
            proceed.clear()

        runner = GoveeRealtimeRunner(
            tee,
            GoveeFrameRenderer(),
            segments=4,
            fps=fps,
            time_fn=time_fn,
            sleep_fn=sleep_fn,
        )
        runner.set_desired(EffectSpec("solid", {"color": [8, 16, 24]}, 1, 100.0))
        runner.set_beat_provider(lambda: _anchor(clock[0]))
        runner.start()
        try:
            for _ in range(n):
                self.assertTrue(step_done.wait(timeout=2.0), "runner sleep_fn never fired")
                step_done.clear()
                proceed.set()
            proceed.set()
            status = runner.status()
        finally:
            proceed.set()
            runner.stop()
        # Cadence proxy: sleep_fn intervals under synthetic time. Runner status has
        # no frame_period_s field (confirmed); do not poke _frame_period_ema.
        self.assertNotIn("frame_period_s", status)
        mean_sleep = sum(sleeps) / max(1, len(sleeps))
        return mean_sleep, sleeps, status

    def test_stalled_sse_client_keeps_runner_cadence(self) -> None:
        fps = 40.0
        ring = FrameMirrorRing(maxlen=32, time_fn=time.monotonic)
        inner = _RecordingTransport(segments=4)
        tee = TeeTransport(inner, ring)

        baseline_mean, _, baseline_status = self._run_n_ticks(tee=tee, n=24, fps=fps)
        self.assertAlmostEqual(baseline_mean, 1.0 / fps, places=6)
        self.assertIn("frame_index", baseline_status)

        # Fresh tee/ring for the stalled-client leg (same harness).
        ring2 = FrameMirrorRing(maxlen=32, time_fn=time.monotonic)
        inner2 = _RecordingTransport(segments=4)
        tee2 = TeeTransport(inner2, ring2)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, path)
            playback = _FakePlayback(ring2)
            playback._playing = True
            playback._look = "rt_groove_chase"
            service = LedPadService(path, dry_run=True, playback=playback)
            with _pad_http(service) as server:
                # Connect and never read the body (stalled consumer).
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                conn.request("GET", "/api/mirror/stream")
                res = conn.getresponse()
                self.assertEqual(res.status, 200)
                # Read response headers only — leave the body unread.
                stalled_mean, _, stalled_status = self._run_n_ticks(tee=tee2, n=24, fps=fps)
                conn.close()

        self.assertAlmostEqual(stalled_mean, baseline_mean, places=6)
        self.assertAlmostEqual(stalled_mean, 1.0 / fps, places=6)
        self.assertNotIn("frame_period_s", stalled_status)


class Awr269CleanWithoutClientTests(unittest.TestCase):
    def test_ring_stays_at_maxlen_without_clients(self) -> None:
        clock = [0.0]
        ring = FrameMirrorRing(maxlen=5, time_fn=lambda: clock[0])
        tee = TeeTransport(_RecordingTransport(segments=2), ring)
        for i in range(40):
            clock[0] = float(i)
            tee.send_frame([(i, 0, 0), (0, 0, 0)])
        self.assertEqual(len(ring), 5)
        self.assertEqual(ring.maxlen, 5)
        latest = ring.latest()
        assert latest is not None
        self.assertEqual(latest[1][0], (39, 0, 0))

    def test_sse_handler_exits_on_service_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, path)
            ring = FrameMirrorRing(maxlen=4, time_fn=time.monotonic)
            service = LedPadService(path, dry_run=True, playback=_FakePlayback(ring))
            server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            conn.request("GET", "/api/mirror/stream")
            res = conn.getresponse()
            self.assertEqual(res.status, 200)
            # Shutdown must unblock the SSE handler thread.
            service.shutdown()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive())
            conn.close()


class Awr269DryRunMatchTests(unittest.TestCase):
    def test_reading_client_receives_transport_rgb_ordered(self) -> None:
        clock = [0.0]
        ring = FrameMirrorRing(maxlen=32, time_fn=lambda: clock[0])
        inner = GoveeRealtimeDryRunTransport(segments=4)
        tee = TeeTransport(inner, ring)
        sent = [
            [(1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12)],
            [(20, 0, 0), (0, 20, 0), (0, 0, 20), (1, 1, 1)],
            [(9, 9, 9), (8, 8, 8), (7, 7, 7), (6, 6, 6)],
        ]

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, path)
            playback = _FakePlayback(ring)
            playback._playing = True
            playback._look = "dry_look"
            service = LedPadService(path, dry_run=True, playback=playback)
            with _pad_http(service) as server:
                sock = __import__("socket").create_connection(
                    ("127.0.0.1", server.server_port), timeout=2.0
                )
                try:
                    sock.sendall(b"GET /api/mirror/stream HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
                    sock.settimeout(0.35)
                    buf = b""
                    header_done = False
                    got: list[list] = []
                    # Push frames while the client is connected so SSE emits each new ts.
                    send_i = 0
                    deadline = time.time() + 3.0
                    while time.time() < deadline and len(got) < len(sent):
                        if send_i < len(sent):
                            clock[0] = float(send_i + 1)
                            self.assertTrue(tee.send_frame(sent[send_i]))
                            send_i += 1
                            time.sleep(0.05)  # let the ~30 fps SSE loop notice
                        try:
                            chunk = sock.recv(4096)
                        except TimeoutError:
                            continue
                        if not chunk:
                            break
                        buf += chunk
                        if not header_done:
                            if b"\r\n\r\n" not in buf:
                                continue
                            header, buf = buf.split(b"\r\n\r\n", 1)
                            self.assertIn(b"200", header.split(b"\r\n", 1)[0])
                            self.assertIn(b"text/event-stream", header.lower())
                            header_done = True
                        while b"\n\n" in buf:
                            event, buf = buf.split(b"\n\n", 1)
                            for line in event.split(b"\n"):
                                if not line.startswith(b"data: "):
                                    continue
                                payload = json.loads(line[6:].decode("utf-8"))
                                if payload.get("rgb"):
                                    got.append(payload["rgb"])
                finally:
                    sock.close()

        self.assertEqual(len(got), len(sent))
        self.assertEqual(got, [[list(px) for px in frame] for frame in sent])
        self.assertEqual(inner.frames_sent, 3)

    def test_pad_playback_wraps_dry_run_with_tee(self) -> None:
        from rb_ss_bridge_v2.led_config import load_led_look_director_config
        from rb_ss_bridge_v2.tools.led_pad_playback import PadPlayback

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, path)
            result = load_led_look_director_config(path)
            self.assertTrue(result.available)
            clock = [0.0]
            sleeps: list[float] = []

            def sleep_fn(interval: float) -> None:
                sleeps.append(interval)
                clock[0] += float(interval)

            playback = PadPlayback(
                result.config,
                dry_run=True,
                time_fn=lambda: clock[0],
                sleep_fn=sleep_fn,
            )
            try:
                self.assertIsInstance(playback.mirror, FrameMirrorRing)
                transport = playback._runner._transport  # noqa: SLF001
                self.assertIsInstance(transport, TeeTransport)
                self.assertIsInstance(transport.wrapped, GoveeRealtimeDryRunTransport)
                # Runner status surface still has no frame_period_s (cadence gate note).
                self.assertNotIn("frame_period_s", playback._runner.status())  # noqa: SLF001
            finally:
                playback.shutdown()


class Awr269UiTripwireTests(unittest.TestCase):
    def test_lab_exposes_watch_live_source(self) -> None:
        lab_html = (_ROOT / "tools" / "led_pad_assets" / "lab.html").read_text(encoding="utf-8")
        lab_js = (_ROOT / "tools" / "led_pad_assets" / "lab.js").read_text(encoding="utf-8")
        self.assertIn("Watch live playback", lab_html)
        self.assertIn("watchLiveBtn", lab_html)
        self.assertIn("/api/mirror/stream", lab_js)
        self.assertIn("EventSource", lab_js)
        self.assertIn("paintPreviewFrame", lab_js)


if __name__ == "__main__":
    unittest.main()
