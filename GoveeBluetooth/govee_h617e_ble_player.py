#!/usr/bin/env python3
"""
Govee H617E BLE realtime look player.
Renders existing govee_frame_renderer effects directly onto the H617E via BLE.

Usage:
  python3 govee_h617e_ble_player.py <address> <effect_name> [bpm] [duration_sec]

Arguments:
  address       BLE address from scan (e.g. 644C98FF-...)
  effect_name   Any name from govee_frame_renderer (groove_chase_blue, breathe, etc.)
                Pass 'list' to print all available effect names.
  bpm           Beats per minute (default 128)
  duration_sec  How long to run in seconds (default 30; 0 = run until Ctrl+C)

Examples:
  python3 govee_h617e_ble_player.py 644C98FF-... groove_chase_blue
  python3 govee_h617e_ble_player.py 644C98FF-... breathe 120 60
  python3 govee_h617e_ble_player.py 644C98FF-... list
"""

import asyncio
import sys
import time
import os

# Allow importing from bridge repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from govee_frame_renderer import GoveeFrameRenderer, REALTIME_EFFECT_NAMES
from govee_h617e_ble_segment_probe import (
    _get_device,
    _find_write_char,
    _send,
    build_h617e_segment_color_packet,
    build_keepalive_packet,
    masks_for_segments,
    TOTAL_SEGMENTS,
)

SCAN_TIMEOUT = 12.0

# ponytail: 10fps is plenty for BLE; most effects look fine, strobe effects will lag
TARGET_FPS = 60
FRAME_INTERVAL = 1.0 / TARGET_FPS

# Round each channel to nearest QUANT_STEP to collapse near-identical comet gradient
# colors into fewer unique groups → fewer BLE writes per frame
QUANT_STEP = 8

# Render at the same virtual resolution the live system uses (60 segments),
# then downsample to the 15 physical BLE segments via max-channel pooling.
# ponytail: without this, a 0.8-segment comet on 15 segs is a single strobing dot.
RENDER_SEGMENTS = 60

_renderer = GoveeFrameRenderer()


def _quantize(r: int, g: int, b: int) -> tuple[int, int, int]:
    def q(v: int) -> int:
        return min(255, round(v / QUANT_STEP) * QUANT_STEP)
    return (q(r), q(g), q(b))


def _downsample(frame: list[tuple[int, int, int]], physical: int) -> list[tuple[int, int, int]]:
    """Max-pool RENDER_SEGMENTS virtual segments down to physical BLE segments."""
    out = []
    ratio = len(frame) / physical
    for i in range(physical):
        lo = int(i * ratio)
        hi = max(lo + 1, int((i + 1) * ratio))
        bucket = frame[lo:hi]
        r = max(c[0] for c in bucket)
        g = max(c[1] for c in bucket)
        b = max(c[2] for c in bucket)
        out.append((r, g, b))
    return out


def _frame_to_packets(frame: list[tuple[int, int, int]]) -> list[bytes]:
    """
    Group segments by (quantized) color → one mode=15 packet per unique color.
    Returns list of packets to write this frame.
    """
    color_to_segs: dict[tuple[int, int, int], list[int]] = {}
    for idx, rgb in enumerate(frame):
        qc = _quantize(*rgb)
        color_to_segs.setdefault(qc, []).append(idx)

    packets = []
    for color, segs in color_to_segs.items():
        lm, rm = masks_for_segments(segs)
        packets.append(build_h617e_segment_color_packet(*color, lm, rm))
    return packets


async def play(address: str, effect_name: str, bpm: float, duration_sec: float):
    device = await _get_device(address)
    ka = build_keepalive_packet()
    black = build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F)

    print(f"Effect:   {effect_name}")
    print(f"BPM:      {bpm}")
    print(f"Duration: {'∞' if duration_sec == 0 else f'{duration_sec}s'}")
    print(f"Target:   {TARGET_FPS}fps  quant={QUANT_STEP}")
    print(f"Segments: {TOTAL_SEGMENTS}")
    print()

    from bleak import BleakClient
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        print("Connected. Playing... Ctrl+C to stop.\n")

        beat_per_sec = bpm / 60.0
        start_wall = time.monotonic()
        frame_index = 0
        last_ka = start_wall
        frames_sent = 0
        writes_total = 0

        try:
            while True:
                now = time.monotonic()
                elapsed = now - start_wall

                if duration_sec > 0 and elapsed >= duration_sec:
                    break

                beat_pos = elapsed * beat_per_sec
                # local_t = time within current beat (0..1/beat_per_sec seconds)
                local_t = (elapsed % (1.0 / beat_per_sec)) if beat_per_sec > 0 else elapsed

                virtual = _renderer.render(
                    effect_name,
                    beat_pos=beat_pos,
                    local_t=local_t,
                    frame_index=frame_index,
                    params={},
                    segments=RENDER_SEGMENTS,
                    seed=42,
                )
                frame = _downsample(virtual, TOTAL_SEGMENTS)

                packets = _frame_to_packets(frame)
                for pkt in packets:
                    await _send(client, char, pkt, "", wwr)
                writes_total += len(packets)
                frames_sent += 1
                frame_index += 1

                # Keepalive every 5s
                if now - last_ka >= 5.0:
                    await _send(client, char, ka, "", wwr)
                    last_ka = now

                # Rate limit
                next_frame = start_wall + frame_index * FRAME_INTERVAL
                sleep_for = next_frame - time.monotonic()
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)

                # Print stats every 5s
                if frame_index % (TARGET_FPS * 5) == 0 and frame_index > 0:
                    actual_fps = frames_sent / max(0.001, elapsed)
                    avg_writes = writes_total / max(1, frames_sent)
                    print(f"  t={elapsed:.1f}s  beat={beat_pos:.2f}  fps={actual_fps:.1f}  {avg_writes:.1f} writes/frame")

        except KeyboardInterrupt:
            print("\nStopping...")

        # Clean up
        await _send(client, char, black, "cleanup", wwr)
        await asyncio.sleep(0.3)
        total = time.monotonic() - start_wall
        print(f"\nDone. {frames_sent} frames in {total:.1f}s ({frames_sent/max(0.001,total):.1f}fps avg), {writes_total} BLE writes total")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "list" or (len(sys.argv) >= 3 and sys.argv[2] == "list"):
        print("Available effects:")
        for name in sorted(REALTIME_EFFECT_NAMES):
            print(f"  {name}")
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Usage: govee_h617e_ble_player.py <address> <effect_name> [bpm] [duration_sec]")
        sys.exit(1)

    address = sys.argv[1]
    effect_name = sys.argv[2]
    bpm = float(sys.argv[3]) if len(sys.argv) > 3 else 128.0
    duration_sec = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0

    if effect_name not in REALTIME_EFFECT_NAMES:
        print(f"Unknown effect: {effect_name!r}")
        print(f"Run with 'list' to see available effects.")
        sys.exit(1)

    asyncio.run(play(address, effect_name, bpm, duration_sec))


if __name__ == "__main__":
    main()
