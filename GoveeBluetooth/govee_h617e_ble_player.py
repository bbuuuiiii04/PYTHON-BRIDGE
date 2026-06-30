#!/usr/bin/env python3
"""
Govee H617E BLE realtime look player.
Renders existing govee_frame_renderer effects directly onto the H617E via BLE.

Usage:
  python3 govee_h617e_ble_player.py <address> <effect_name> [bpm] [duration_sec]
  python3 govee_h617e_ble_player.py <address> seq <effect1> <beats1> [<effect2> <beats2> ...] [bpm=128]

Arguments:
  address       BLE address from scan (e.g. 644C98FF-...)
  effect_name   Any name from govee_frame_renderer. Pass 'list' to print all.
  bpm           Beats per minute (default 128)
  duration_sec  How long to run in seconds (default 30; 0 = run until Ctrl+C)

  seq mode: effect/beat pairs played back-to-back on one BLE connection.
            Optional trailing bpm=<value> sets tempo (default 128).

Examples:
  python3 govee_h617e_ble_player.py 644C98FF-... groove_chase_blue
  python3 govee_h617e_ble_player.py 644C98FF-... breathe 120 60
  python3 govee_h617e_ble_player.py 644C98FF-... list
  python3 govee_h617e_ble_player.py 644C98FF-... seq buildup_freestyle_nebula 32 rt_drop_nebula 32 rt_post_drop_nebula 32 bpm=128
"""

import asyncio
import sys
import time
import os

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
TARGET_FPS = 60
FRAME_INTERVAL = 1.0 / TARGET_FPS
QUANT_STEP = 8
RENDER_SEGMENTS = 60

_renderer = GoveeFrameRenderer()


def _quantize(r: int, g: int, b: int) -> tuple[int, int, int]:
    def q(v: int) -> int:
        return min(255, round(v / QUANT_STEP) * QUANT_STEP)
    return (q(r), q(g), q(b))


def _downsample(frame: list[tuple[int, int, int]], physical: int) -> list[tuple[int, int, int]]:
    out = []
    ratio = len(frame) / physical
    for i in range(physical):
        lo = int(i * ratio)
        hi = max(lo + 1, int((i + 1) * ratio))
        bucket = frame[lo:hi]
        out.append((max(c[0] for c in bucket), max(c[1] for c in bucket), max(c[2] for c in bucket)))
    return out


def _frame_to_packets(frame: list[tuple[int, int, int]]) -> list[bytes]:
    color_to_segs: dict[tuple[int, int, int], list[int]] = {}
    for idx, rgb in enumerate(frame):
        qc = _quantize(*rgb)
        color_to_segs.setdefault(qc, []).append(idx)
    packets = []
    for color, segs in color_to_segs.items():
        lm, rm = masks_for_segments(segs)
        packets.append(build_h617e_segment_color_packet(*color, lm, rm))
    return packets


async def _run_effect(client, char, wwr, effect_name: str, bpm: float, duration_sec: float, last_ka_ref: list, params: dict | None = None):
    """Run one effect on an already-connected client. last_ka_ref = [float] shared across effects."""
    beat_per_sec = bpm / 60.0
    start_wall = time.monotonic()
    frame_index = 0
    frames_sent = 0
    writes_total = 0
    render_params = params or {}

    print(f"\n>>> {effect_name}  ({duration_sec:.1f}s / {duration_sec * bpm / 60:.0f} beats)")

    while True:
        now = time.monotonic()
        elapsed = now - start_wall

        if duration_sec > 0 and elapsed >= duration_sec:
            break

        beat_pos = elapsed * beat_per_sec
        local_t = (elapsed % (1.0 / beat_per_sec)) if beat_per_sec > 0 else elapsed

        virtual = _renderer.render(
            effect_name,
            beat_pos=beat_pos,
            local_t=local_t,
            frame_index=frame_index,
            params=render_params,
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

        if now - last_ka_ref[0] >= 5.0:
            await _send(client, char, build_keepalive_packet(), "", wwr)
            last_ka_ref[0] = now

        next_frame = start_wall + frame_index * FRAME_INTERVAL
        sleep_for = next_frame - time.monotonic()
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

    actual_fps = frames_sent / max(0.001, time.monotonic() - start_wall)
    print(f"    {frames_sent} frames  {actual_fps:.1f}fps  {writes_total/max(1,frames_sent):.1f} writes/frame")


async def play(address: str, effect_name: str, bpm: float, duration_sec: float, params: dict | None = None):
    device = await _get_device(address)
    black = build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F)

    print(f"Effect:   {effect_name}")
    print(f"BPM:      {bpm}")
    print(f"Duration: {'∞' if duration_sec == 0 else f'{duration_sec}s'}")
    print(f"Target:   {TARGET_FPS}fps  quant={QUANT_STEP}  render={RENDER_SEGMENTS}→{TOTAL_SEGMENTS}seg")

    from bleak import BleakClient
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        print("Connected. Playing... Ctrl+C to stop.")

        last_ka = [time.monotonic()]
        try:
            await _run_effect(client, char, wwr, effect_name, bpm, duration_sec, last_ka, params)
        except KeyboardInterrupt:
            print("\nStopping...")

        await _send(client, char, black, "cleanup", wwr)
        await asyncio.sleep(0.3)


async def play_sequence(address: str, steps: list[tuple[str, float]], bpm: float):
    """Play multiple effects back-to-back on one BLE connection."""
    device = await _get_device(address)
    black = build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F)

    total_beats = sum(b for _, b in steps)
    total_sec = total_beats / bpm * 60
    print(f"Sequence: {len(steps)} effects  {total_beats:.0f} beats  {total_sec:.1f}s  BPM={bpm}")
    for name, beats in steps:
        print(f"  {name}: {beats:.0f} beats ({beats/bpm*60:.1f}s)")

    from bleak import BleakClient
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        print("\nConnected.")

        last_ka = [time.monotonic()]
        try:
            for effect_name, beats in steps:
                duration_sec = beats / bpm * 60.0
                await _run_effect(client, char, wwr, effect_name, bpm, duration_sec, last_ka)
        except KeyboardInterrupt:
            print("\nStopping...")

        await _send(client, char, black, "cleanup", wwr)
        await asyncio.sleep(0.3)
        print("\nDone.")


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

    _COLORS = {
        "white": (255, 255, 255), "red": (255, 0, 0), "green": (0, 255, 0),
        "blue": (0, 0, 255), "cyan": (0, 255, 255), "magenta": (255, 0, 255),
        "yellow": (255, 255, 0), "orange": (255, 128, 0), "purple": (128, 0, 255),
    }

    address = sys.argv[1]

    if sys.argv[2] == "seq":
        # seq mode: effect beats effect beats ... [bpm=N]
        rest = sys.argv[3:]
        bpm = 128.0
        if rest and rest[-1].startswith("bpm="):
            bpm = float(rest[-1].split("=")[1])
            rest = rest[:-1]
        if len(rest) % 2 != 0:
            print("seq: expected effect/beat pairs")
            sys.exit(1)
        steps = []
        for i in range(0, len(rest), 2):
            name = rest[i]
            beats = float(rest[i + 1])
            if name not in REALTIME_EFFECT_NAMES:
                print(f"Unknown effect: {name!r}")
                sys.exit(1)
            steps.append((name, beats))
        asyncio.run(play_sequence(address, steps, bpm))
        return

    # Parse remaining args: effect [bpm] [duration] [color=name]
    remaining = sys.argv[2:]
    color_arg = next((a for a in remaining if a.startswith("color=")), None)
    if color_arg:
        remaining = [a for a in remaining if not a.startswith("color=")]
    positional = [a for a in remaining if not a.startswith("color=")]

    effect_name = positional[0] if positional else ""
    bpm = float(positional[1]) if len(positional) > 1 else 128.0
    duration_sec = float(positional[2]) if len(positional) > 2 else 30.0

    if effect_name not in REALTIME_EFFECT_NAMES:
        print(f"Unknown effect: {effect_name!r}")
        print("Run with 'list' to see available effects.")
        sys.exit(1)

    params = None
    if color_arg:
        cname = color_arg.split("=", 1)[1].lower()
        rgb = _COLORS.get(cname)
        if rgb is None:
            print(f"Unknown color: {cname!r}. Options: {', '.join(_COLORS)}")
            sys.exit(1)
        params = {"slot_colors": [list(rgb)]}

    asyncio.run(play(address, effect_name, bpm, duration_sec, params))


if __name__ == "__main__":
    main()
