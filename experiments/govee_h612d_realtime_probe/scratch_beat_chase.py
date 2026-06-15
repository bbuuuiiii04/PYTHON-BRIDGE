#!/usr/bin/env python3
"""Standalone script to drive Govee lights with a beat-driven blue chase.

Directly constructs and sends Razer/DreamView UDP packets to control the strip
without relying on any codebase engines, runners, or renderers.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import socket
import sys
import time


# UDP Configuration
CONTROL_PORT = 4003
DREAMS_HEADER = [0xBB, 0x00, 0xFA, 0xB0, 0x00]
ACTIVATE_PT = "uwABsQEK"    # BB 00 01 B1 01 0A base64
DEACTIVATE_PT = "uwABsQAL"  # BB 00 01 B1 00 0B base64


def xor_checksum(data: list[int]) -> int:
    """Compute XOR checksum over all packet bytes."""
    chk = 0
    for b in data:
        chk ^= b
    return chk


def build_frame_packet(header: list[int], segments: list[tuple[int, int, int]]) -> bytes:
    """Construct a Razer UDP packet: header(5) + segment_count(1) + R,G,B*N + checksum(1)."""
    packet = list(header) + [len(segments)]
    for r, g, b in segments:
        # Clamp channel values safely to [0, 255]
        packet.extend([
            max(0, min(255, int(round(r)))),
            max(0, min(255, int(round(g)))),
            max(0, min(255, int(round(b))))
        ])
    packet.append(xor_checksum(packet))
    return bytes(packet)


def send_razer_cmd(sock: socket.socket, ip: str, payload_b64: str) -> None:
    """Sends a base64 encoded payload inside a JSON command to the Govee UDP port."""
    msg = {"msg": {"cmd": "razer", "data": {"pt": payload_b64}}}
    sock.sendto(json.dumps(msg).encode("utf-8"), (ip, CONTROL_PORT))


class ActiveComet:
    """Tracks a single active comet's lifetime."""
    def __init__(self, spawn_time: float) -> None:
        self.spawn_time = spawn_time


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct Govee Beat-Driven Blue Chase (From Scratch)")
    parser.add_argument("--ip", default="192.168.0.219", help="Govee Device IP (default: 192.168.0.219)")
    parser.add_argument("--segments", type=int, default=20, help="Number of LED segments (default: 20)")
    parser.add_argument("--bpm", type=float, default=128.0, help="Tempo in BPM (default: 128.0)")
    parser.add_argument("--beats", type=float, default=32.0, help="Duration of test in beats (default: 32.0)")
    parser.add_argument("--fps", type=int, default=60, help="Frame updates per second (default: 60)")
    args = parser.parse_args()

    beat_duration_s = 60.0 / args.bpm
    total_duration_s = args.beats * beat_duration_s

    print("=" * 60)
    print("  STANDALONE GOVEE DIRECT UDP CHASE (FROM SCRATCH)")
    print(f"  Target IP:        {args.ip}:{CONTROL_PORT}")
    print(f"  LED Segments:     {args.segments}")
    print(f"  Tempo / Beats:    {args.bpm} BPM / {args.beats} beats ({total_duration_s:.2f} seconds)")
    print(f"  Framerate:        {args.fps} FPS")
    print("=" * 60)

    # Initialize Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # 1. Activate Razer/DreamView Mode
    print("\n  [1/4] Activating Govee Razer mode...", flush=True)
    send_razer_cmd(sock, args.ip, ACTIVATE_PT)
    time.sleep(0.3)

    # 2. Force Max Brightness Command
    brightness_msg = {"msg": {"cmd": "brightness", "data": {"value": 100}}}
    sock.sendto(json.dumps(brightness_msg).encode("utf-8"), (args.ip, CONTROL_PORT))
    time.sleep(0.2)

    # Animation setup
    comets: list[ActiveComet] = []
    fps_interval = 1.0 / args.fps
    t_start = time.monotonic()
    last_spawn_beat = -1

    # Comet rendering parameters
    travel_time_s = 1.0 * beat_duration_s  # travels strip in 1 beat
    trail_time_s = 0.25 * beat_duration_s  # trail duration
    comet_width = 0.8
    blue_color = (0, 0, 255)

    print("  [2/4] Running blue chase animation...", flush=True)

    try:
        while True:
            t_now = time.monotonic()
            elapsed_s = t_now - t_start
            if elapsed_s >= total_duration_s:
                break

            current_beat = elapsed_s / beat_duration_s
            current_beat_floor = math.floor(current_beat)

            # Spawn a new comet on every downbeat boundary
            if current_beat_floor > last_spawn_beat:
                # Calculate the exact time this beat occurred to reduce scheduling jitter
                beat_offset = (current_beat_floor - current_beat) * beat_duration_s
                spawn_time = t_now + beat_offset
                comets.append(ActiveComet(spawn_time))
                last_spawn_beat = current_beat_floor
                print(f"    - Beat {current_beat_floor + 1}/{int(args.beats)} (Active comets: {len(comets)})", flush=True)

            # Build segments list additively
            frame_buffer = [[0.0, 0.0, 0.0] for _ in range(args.segments)]

            # Compute contribution of each active comet
            still_active = []
            for comet in comets:
                age_s = t_now - comet.spawn_time
                if age_s < 0:
                    age_s = 0.0

                progress = age_s / travel_time_s
                # Comet position along the strip
                pos = progress * args.segments

                # Normalize intensity based on virtual neighbors so energy is stable
                radius = int(math.ceil(comet_width)) + 1
                center = math.floor(pos)
                ideal_sum = 0.0
                for sample in range(center - radius, center + radius + 1):
                    dist = abs(float(sample) - pos)
                    ideal_sum += max(0.0, 1.0 - dist / comet_width)

                if ideal_sum > 0.0:
                    for idx in range(args.segments):
                        dist = abs(float(idx) - pos)
                        intensity = max(0.0, 1.0 - dist / comet_width) / ideal_sum
                        if intensity > 0.0:
                            frame_buffer[idx][0] += blue_color[0] * intensity
                            frame_buffer[idx][1] += blue_color[1] * intensity
                            frame_buffer[idx][2] += blue_color[2] * intensity

                # Keep comets that haven't fully exited their travel + trail time yet
                if age_s <= travel_time_s + trail_time_s:
                    still_active.append(comet)

            comets = still_active

            # Convert accumulator buffer to integer RGB tuples
            segments = [
                (int(round(r)), int(round(g)), int(round(b)))
                for r, g, b in frame_buffer
            ]

            # Build and send the packet
            frame_packet = build_frame_packet(DREAMS_HEADER, segments)
            send_razer_cmd(sock, args.ip, base64.b64encode(frame_packet).decode("utf-8"))

            # Sleep to match targeted framerate
            elapsed_frame = time.monotonic() - t_now
            sleep_time = max(0.0, fps_interval - elapsed_frame)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n  [!] Interrupted by user.", flush=True)

    finally:
        # 3. Clean up: send a blackout frame and deactivate Razer mode
        print("\n  [3/4] Blacking out and deactivating Razer mode...", flush=True)
        try:
            blackout_segments = [(0, 0, 0)] * args.segments
            blackout_packet = build_frame_packet(DREAMS_HEADER, blackout_segments)
            send_razer_cmd(sock, args.ip, base64.b64encode(blackout_packet).decode("utf-8"))
            time.sleep(0.1)
            send_razer_cmd(sock, args.ip, DEACTIVATE_PT)
            time.sleep(0.2)
        except Exception as e:
            print(f"  Error cleaning up: {e}", flush=True)

        sock.close()
        print("  [4/4] Done.", flush=True)


if __name__ == "__main__":
    main()
