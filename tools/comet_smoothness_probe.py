#!/usr/bin/env python3
"""Standalone comet smoothness probe — isolates the Govee device from the bridge.

Sends a single smooth head+trail comet looping across the strip at a PRECISELY even
frame cadence, using the bridge's real transport + comet renderer but with NO bridge
threads competing. Run with the bridge stopped (so nothing else owns the strip).

The point: determine whether the H612D can render smooth realtime motion over UDP, and
at what frame rate / pacing. Try several --fps values and watch:

  - If some rate (e.g. 15-20) is smooth and higher rates stutter -> the device can't
    absorb high realtime frame rates; cap the bridge's realtime fps.
  - If EVERY rate stutters even with this metronome-even pacing -> the device does not
    render smooth realtime motion over UDP (pre-baked device scenes are the smooth path).
  - If this is smooth but the bridge is not -> the bridge is jittering its sends.

Usage:
    python3 tools/comet_smoothness_probe.py --fps 20 --bpm 128 --travel-beats 2
    (Ctrl-C to stop; it blacks out and deactivates on exit.)
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# Import the bridge's real transport + renderer so the protocol/visual matches the bridge.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # parent of the package dir

from rb_ss_bridge_v2.govee_realtime_transport import GoveeRealtimeTransport  # noqa: E402
from rb_ss_bridge_v2.govee_frame_renderer import _comet_frame, _clamp_channel  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Govee comet smoothness probe")
    p.add_argument("--ip", default="192.168.0.216")
    p.add_argument("--fps", type=float, default=20.0)
    p.add_argument("--bpm", type=float, default=128.0)
    p.add_argument("--travel-beats", type=float, default=2.0, help="beats for one full sweep")
    p.add_argument("--segments", type=int, default=20)
    p.add_argument("--head-soft", type=float, default=1.6)
    p.add_argument("--trail-len", type=float, default=4.0)
    p.add_argument("--color", default="0,0,255", help="R,G,B")
    p.add_argument("--seconds", type=float, default=0.0, help="auto-stop after N s (0 = until Ctrl-C)")
    args = p.parse_args()

    color = tuple(int(x) for x in args.color.split(","))
    sweep_s = max(1e-3, args.travel_beats * 60.0 / max(1e-3, args.bpm))
    interval = 1.0 / max(1e-3, args.fps)

    tx = GoveeRealtimeTransport(args.ip, segments=args.segments,
                                header_bytes=[187, 0, 250, 176, 0])
    tx.activate()
    tx.set_brightness(100)
    print(f"[PROBE] ip={args.ip} fps={args.fps} bpm={args.bpm} sweep={sweep_s:.3f}s "
          f"interval={interval*1000:.1f}ms head_soft={args.head_soft} trail_len={args.trail_len}")
    print("[PROBE] sending... Ctrl-C to stop")

    start = time.monotonic()
    next_at = start
    sent = 0
    worst_late = 0.0
    try:
        while True:
            now = time.monotonic()
            if args.seconds > 0 and (now - start) >= args.seconds:
                break
            progress = ((now - start) / sweep_s) % 1.0
            frame = _comet_frame(progress, args.segments, color,
                                 args.head_soft, args.trail_len, 1)
            frame = [(_clamp_channel(r), _clamp_channel(g), _clamp_channel(b)) for r, g, b in frame]
            tx.send_frame(frame)
            sent += 1
            next_at += interval
            late = time.monotonic() - next_at  # how far behind schedule we are
            if late > worst_late:
                worst_late = late
            sleep_s = next_at - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                next_at = time.monotonic()  # fell behind; resync (should be ~never standalone)
    except KeyboardInterrupt:
        pass
    finally:
        elapsed = time.monotonic() - start
        tx.blackout()
        tx.deactivate()
        tx.close()
        eff = sent / elapsed if elapsed > 0 else 0
        print(f"\n[PROBE] sent={sent} elapsed={elapsed:.1f}s effective_fps={eff:.1f} "
              f"worst_schedule_slip={worst_late*1000:.1f}ms send_errors={tx.send_error_count}")


if __name__ == "__main__":
    main()
