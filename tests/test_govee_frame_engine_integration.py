"""Integration proof for the Govee frame engine child (AWR-146, Part D 15-16).

Real subprocess + real AF_UNIX socketpair, dry-run transport only (no packets to
any strip). Timing-sensitive → skipped under CI. Precedent:
tests/test_bridge_log_integration.py, tests/test_ss_bridge_watcher.py.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_engine import decode_buffer, encode_msg  # noqa: E402
from rb_ss_bridge_v2.govee_frame_engine_client import GoveeFrameEngineClient  # noqa: E402
from rb_ss_bridge_v2.led_models import BeatAnchor  # noqa: E402

_REPO_PARENT = str(Path(__file__).resolve().parents[2])


def _init(**over) -> dict:
    base = {
        "t": "init", "dry_run": True, "ip": "127.0.0.1", "port": 4003,
        "segments": 60, "fps": 60, "grace_s": 0.25,
        "header_bytes": [0xBB, 0x00, 0xFA, 0xB0, 0x00], "stretch": False,
        "activate_pt": "uwABsQEK", "deactivate_pt": "uwABsQAL",
    }
    base.update(over)
    return base


def _spawn_child(init: dict) -> tuple[subprocess.Popen, socket.socket]:
    parent_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    child_fd = child_sock.fileno()
    proc = subprocess.Popen(
        [sys.executable, "-m", "rb_ss_bridge_v2.govee_frame_engine",
         "--fd", str(child_fd)],
        pass_fds=(child_fd,), cwd=_REPO_PARENT,
        stdout=subprocess.DEVNULL, stderr=None)
    child_sock.close()
    parent_sock.setblocking(False)
    parent_sock.sendall(encode_msg({**init, "t": "init"}))
    return proc, parent_sock


@unittest.skipIf(os.environ.get("CI") == "true", "timing-sensitive")
class FrameEngineIntegrationTests(unittest.TestCase):
    def test_15_sixty_fps_proof(self) -> None:
        clock = [time.monotonic()]

        def provider() -> BeatAnchor:
            now = time.monotonic()
            return BeatAnchor(
                deck=1, abs_beat_pos=(now * 128.0 / 60.0) % 1_000_000.0,
                bpm=128.0, captured_monotonic=now, playing=True, permitted=True)

        client = GoveeFrameEngineClient(_init(fps=60, segments=60, dry_run=True))
        client.set_beat_provider(provider)
        client.start()
        from rb_ss_bridge_v2.govee_realtime_runner import EffectSpec
        client.set_desired(EffectSpec("blackout", {}, 1, time.monotonic()))
        time.sleep(3.2)
        status = client.status()
        stopped = client.stop()
        self.assertTrue(status.get("engine_alive"), status)
        self.assertTrue(status.get("active"), status)  # streaming
        fps = float(status.get("achieved_fps", 0.0))
        # Record the measured number for the operator report.
        sys.stderr.write(f"\n[AWR-146] integration achieved_fps = {fps:.1f}\n")
        self.assertGreaterEqual(fps, 55.0, f"achieved_fps={fps}")
        self.assertTrue(stopped)

    def test_16_orphan_eof_exits_clean(self) -> None:
        proc, parent_sock = _spawn_child(_init())
        # Give the child a moment to finish setup, then orphan it.
        time.sleep(0.3)
        parent_sock.close()  # kernel closes the pair → child sees EOF
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            self.fail("child did not exit within 2 s of parent EOF")
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
