#!/usr/bin/env python3
"""Govee H612D Real-time Effects Player.

A clean canvas for building custom beat-synced realtime looks on the Bui Strip Light (IP: 192.168.0.219).
Controls Govee H612D using Razer/DreamView UDP protocol over port 4003.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import random
import socket
import sys
import time

# Add root folder to sys.path to import production govee_frame_renderer
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from govee_frame_renderer import GoveeFrameRenderer

# Target configuration from proof
DEFAULT_IP = "192.168.0.219"
CONTROL_PORT = 4003
DEFAULT_SEGMENTS = 20

# Razer/DreamView headers & activation payloads
DREAMS_HEADER = [0xBB, 0x00, 0xFA, 0xB0, 0x00]
ACTIVATE_PT = "uwABsQEK"     # BB 00 01 B1 01 0A
DEACTIVATE_PT = "uwABsQAL"   # BB 00 01 B1 00 0B


def xor_checksum(data: bytes | list[int]) -> int:
    """Compute XOR checksum over all bytes."""
    result = 0
    for b in data:
        result ^= b
    return result


def build_frame_packet(header: list[int], segments: list[tuple[int, int, int]]) -> bytes:
    """Build a Govee Razer frame packet.

    Format: header(5) + segment_count(1) + (R, G, B)*N + XOR_checksum(1)
    """
    seg_count = len(segments)
    packet = list(header) + [seg_count]
    for r, g, b in segments:
        packet.extend([r & 0xFF, g & 0xFF, b & 0xFF])
    packet.append(xor_checksum(packet))
    return bytes(packet)


class GoveeRealtimeController:
    """Handles UDP connection and lifecycle for Govee realtime control."""

    def __init__(self, ip: str, num_segments: int = DEFAULT_SEGMENTS) -> None:
        self.ip = ip
        self.num_segments = num_segments
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def activate(self) -> None:
        """Activate razer/realtime mode and set brightness to max."""
        print(f"\033[94m[Govee] Activating realtime mode on {self.ip}...\033[0m")
        # Send activation command
        self.send_raw_command(ACTIVATE_PT)
        time.sleep(0.3)

        # Set brightness to 100%
        brightness_msg = {"msg": {"cmd": "brightness", "data": {"value": 100}}}
        self.sock.sendto(json.dumps(brightness_msg).encode("utf-8"), (self.ip, CONTROL_PORT))
        time.sleep(0.2)

    def deactivate(self) -> None:
        """Deactivate razer/realtime mode and reset to dim blue rest frame."""
        print(f"\n\033[94m[Govee] Restoring dim blue idle and deactivating...\033[0m")
        try:
            # Send rest frame
            rest_frame = [(0, 0, 15)] * self.num_segments
            self.send_frame(rest_frame)
            time.sleep(0.3)

            # Send deactivate
            self.send_raw_command(DEACTIVATE_PT)
            time.sleep(0.2)
        except Exception as e:
            print(f"Error during deactivation: {e}")

    def send_raw_command(self, base64_payload: str) -> None:
        """Send raw base64 command wrapped in Govee razer protocol structure."""
        msg = {"msg": {"cmd": "razer", "data": {"pt": base64_payload}}}
        self.sock.sendto(json.dumps(msg).encode("utf-8"), (self.ip, CONTROL_PORT))

    def send_frame(self, segments: list[tuple[int, int, int]]) -> None:
        """Build, encode, and send a color frame to the device."""
        packet = build_frame_packet(DREAMS_HEADER, segments)
        b64_pt = base64.b64encode(packet).decode("utf-8")
        self.send_raw_command(b64_pt)

    def close(self) -> None:
        self.sock.close()


def print_progress_bar(progress: float, info: str = "") -> None:
    """Print a terminal progress bar showing the beat progression."""
    width = 40
    filled = int(width * progress)
    bar = "█" * filled + "░" * (width - filled)
    sys.stdout.write(f"\r\033[K\033[92mBeat Progress: |{bar}| {progress*100:5.1f}%  \033[36m{info}\033[0m")
    sys.stdout.flush()


# ── The Base EDM Buildup Looks ──────────────────────────────────────────────────

EDM_BUILDS = {
    "buildup_ramp_1": "32-beat continuous linear white sparkle ramp with very fast decay.",
    "buildup_ramp_2": "32-beat fast white chase particles strobing and scaling in count.",
    "buildup_ramp_3": "32-beat smooth white chase wave morphing into an accelerating strobe.",
    "buildup_white_zone_strobe": "32-beat buildup: expanding stroboscopic sparkles into 4 zones that strobe chase.",
    "buildup_white_half_strobe": "32-beat buildup: expanding stroboscopic sparkles into 2 alternating stroboscopic halves.",
    "buildup_freestyle_nebula": "32-beat freestyle: opposite comets + breathing purple/magenta bg + shutter strobe + climax flash.",
    "groove_chase_blue": "32-beat smooth blue dual-head chase.",
    "groove_chase_cyan": "32-beat smooth cyan dual-head chase.",
    "groove_chase_red": "32-beat smooth red dual-head chase.",
    "groove_chase_green": "32-beat smooth green dual-head chase.",
    "groove_chase_cyan_white": "32-beat smooth alternating cyan/white dual-head chase.",
    "groove_freestyle_nebula": "32-beat smooth freestyle groove: opposite comets + breathing purple/magenta bg.",
    "drop_chase_blue": "32-beat drop: 8-beat sparkle strobe burst + 2-beat blue chase strobe.",
    "drop_chase_cyan": "32-beat drop: 8-beat sparkle strobe burst + 2-beat cyan chase strobe.",
    "drop_center_burst_blue_cyan": "32-beat drop: half-beat bursts from center to edges.",
    "post_drop_center_comet_blue_cyan": "32-beat post-drop: strobing dual comets chasing outward from center.",
    "drop_chase_red": "32-beat drop: 8-beat sparkle strobe burst + 2-beat red chase strobe.",
    "drop_chase_green": "32-beat drop: 8-beat sparkle strobe burst + 2-beat green chase strobe.",
    "drop_chase_freestyle_nebula": "32-beat freestyle drop: 8-beat sparkle strobe burst + 2-beat opposite comets strobe.",
    "drop_chase_cyan_white": "32-beat drop: 8-beat sparkle strobe burst + 2-beat cyan/white chase strobe.",
    "drop_white_aggressive": "Drop: full-strip pure-white 16th-note strobe (bridge-owned duration).",
    "post_drop_white_shatter": "Post-drop: per-frame full-white stroboscopic static dissolving 13->3 over 4 beats then held low.",
    "twinkle_blue": "32-beat super twinkly blue cyan look that pulses on beat.",
    "test_combo": "Native 32-beat combo of aggressive strobe -> white shatter",
}


def generate_buildup_frame(
    look: str,
    current_beat: float,
    elapsed: float,
    num_segs: int,
    sparkle_states: list[float],
    strobe_state: dict,
) -> list[tuple[int, int, int]]:
    """Generate the RGB frame for a given look and current beat progression."""
    progress = min(1.0, current_beat / 32.0)

    if look in ("groove_chase_blue", "groove_chase_cyan", "groove_chase_red", "groove_chase_green", "groove_chase_cyan_white"):
        # 1. No strobe gating (always on for smooth groove chase)
        strobe_on = True

        # 2. Dual-head chase taking exactly 4 beats per full loop (1/4 speed)
        # Head 2 is offset by 2.0 beats (180 degrees in a 4-beat loop cycle)
        # We use float positions for sub-segment anti-aliased rendering.
        pos1 = ((current_beat / 4.0) % 1.0) * num_segs
        pos2 = (((current_beat + 2.0) / 4.0) % 1.0) * num_segs
        
        # Determine colors for both heads
        if look == "groove_chase_blue":
            color1 = color2 = (0, 0, 255)
        elif look == "groove_chase_cyan":
            color1 = color2 = (0, 255, 255)
        elif look == "groove_chase_red":
            color1 = color2 = (255, 0, 0)
        elif look == "groove_chase_green":
            color1 = color2 = (0, 255, 0)
        else:  # groove_chase_cyan_white
            # Smoothly swap color every beat (1/1 notes)
            swap = int(current_beat) % 2 == 0
            color1 = (0, 255, 255) if swap else (255, 255, 255)
            color2 = (255, 255, 255) if swap else (0, 255, 255)
            
        # Anti-aliased rendering of the two heads
        frame = [(0, 0, 0)] * num_segs
        width = 0.8  # smaller falloff width in segments (was 1.8)
        
        for idx in range(num_segs):
            # Compute shortest distance on the circular strip
            diff1 = abs(idx - pos1)
            dist1 = min(diff1, num_segs - diff1)
            
            diff2 = abs(idx - pos2)
            dist2 = min(diff2, num_segs - diff2)
            
            intensity1 = max(0.0, 1.0 - (dist1 / width))
            intensity2 = max(0.0, 1.0 - (dist2 / width))
            
            # Combine contributions from both heads (clamping to 255)
            r = min(255, int(color1[0] * intensity1 + color2[0] * intensity2))
            g = min(255, int(color1[1] * intensity1 + color2[1] * intensity2))
            b = min(255, int(color1[2] * intensity1 + color2[2] * intensity2))
            
            frame[idx] = (r, g, b)
            
        return frame

    elif look in ("drop_chase_blue", "drop_chase_cyan", "drop_chase_red", "drop_chase_green", "drop_chase_cyan_white"):
        # Determine colors based on the look
        if look == "drop_chase_blue":
            color1 = color2 = (0, 0, 255)
        elif look == "drop_chase_cyan":
            color1 = color2 = (0, 255, 255)
        elif look == "drop_chase_red":
            color1 = color2 = (255, 0, 0)
        elif look == "drop_chase_green":
            color1 = color2 = (0, 255, 0)
        else:  # drop_chase_cyan_white
            # Swap colors every beat (1/1 notes)
            swap = int(current_beat) % 2 == 0
            color1 = (0, 255, 255) if swap else (255, 255, 255)
            color2 = (255, 255, 255) if swap else (0, 255, 255)

        # 1/16 note strobe gate (applies to both sparkle and chase phases)
        division = 16.0
        strobe_cycle = int(current_beat * division)
        strobe_on = (strobe_cycle % 2 == 0)
        
        if not strobe_on:
            return [(0, 0, 0)] * num_segs

        # Phase splitting based on beat
        if current_beat < 8.0:
            # First 8 beats: burst twinkle sparkle strobe
            decay = 0.15
            # Spawn rate starts high (4.0 twinkles/frame) and decays to 0.5 at beat 8
            progress_8 = current_beat / 8.0
            spawn_rate = 4.0 * (1.0 - progress_8) + 0.5
            
            # Decay existing sparkles
            for idx in range(num_segs):
                sparkle_states[idx] = max(0.0, sparkle_states[idx] * decay)
                
            # Spawn new sparkles
            num_to_spawn = int(spawn_rate) + (1 if random.random() < (spawn_rate % 1.0) else 0)
            for _ in range(num_to_spawn):
                start_idx = random.randint(0, num_segs - 1)
                sparkle_states[start_idx] = 1.0
                
            # Render sparkle frame using the look's color palette
            frame = []
            for idx in range(num_segs):
                val = sparkle_states[idx]
                val_pow = val ** 1.5
                c = color1
                r_val = int(c[0] * val_pow)
                g_val = int(c[1] * val_pow)
                b_val = int(c[2] * val_pow)
                frame.append((r_val, g_val, b_val))
            return frame
        else:
            # Beats 8 to 32: 2-beat cycle chase with strobe
            # Dual-head chase taking exactly 2 beats per loop (offset by 1.0 beat)
            pos1 = (((current_beat - 8.0) / 2.0) % 1.0) * num_segs
            pos2 = (((((current_beat - 8.0) + 1.0) / 2.0) % 1.0) * num_segs)
            
            frame = [(0, 0, 0)] * num_segs
            width = 0.8  # sharp head size
            
            for idx in range(num_segs):
                diff1 = abs(idx - pos1)
                dist1 = min(diff1, num_segs - diff1)
                
                diff2 = abs(idx - pos2)
                dist2 = min(diff2, num_segs - diff2)
                
                intensity1 = max(0.0, 1.0 - (dist1 / width))
                intensity2 = max(0.0, 1.0 - (dist2 / width))
                
                r = min(255, int(color1[0] * intensity1 + color2[0] * intensity2))
                g = min(255, int(color1[1] * intensity1 + color2[1] * intensity2))
                b = min(255, int(color1[2] * intensity1 + color2[2] * intensity2))
                
                frame[idx] = (r, g, b)
            return frame

    elif look == "groove_freestyle_nebula":
        # 1. Breathing purple/magenta background (cycles every 4 beats)
        breath = 0.5 + 0.5 * math.sin(current_beat * math.pi / 2.0)
        bg_r = int(15 * breath)
        bg_g = 0
        bg_b = int(50 * breath)

        # 2. Opposite comets looping every 4 beats
        pos1 = ((current_beat / 4.0) % 1.0) * num_segs
        pos2 = ((1.0 - (current_beat / 4.0)) % 1.0) * num_segs

        # Render background
        frame = [(bg_r, bg_g, bg_b)] * num_segs
        
        # Draw comets with anti-aliasing (width 0.8)
        width = 0.8
        for idx in range(num_segs):
            diff1 = abs(idx - pos1)
            dist1 = min(diff1, num_segs - diff1)
            intensity1 = max(0.0, 1.0 - (dist1 / width))
            
            diff2 = abs(idx - pos2)
            dist2 = min(diff2, num_segs - diff2)
            intensity2 = max(0.0, 1.0 - (dist2 / width))
            
            # Comet 1 is Cyan, Comet 2 is White
            r = int(frame[idx][0] * (1.0 - intensity1 - intensity2) + 0 * intensity1 + 255 * intensity2)
            g = int(frame[idx][1] * (1.0 - intensity1 - intensity2) + 255 * intensity1 + 255 * intensity2)
            b = int(frame[idx][2] * (1.0 - intensity1 - intensity2) + 255 * intensity1 + 255 * intensity2)
            
            frame[idx] = (min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)))
        return frame

    elif look == "drop_chase_freestyle_nebula":
        # 1. 1/16 note strobe gate
        division = 16.0
        strobe_cycle = int(current_beat * division)
        strobe_on = (strobe_cycle % 2 == 0)
        
        if not strobe_on:
            return [(0, 0, 0)] * num_segs

        if current_beat < 8.0:
            # Phase 1: Nebula sparkle burst
            decay = 0.15
            progress_8 = current_beat / 8.0
            spawn_rate = 4.0 * (1.0 - progress_8) + 0.5
            
            for idx in range(num_segs):
                sparkle_states[idx] = max(0.0, sparkle_states[idx] * decay)
                
            num_to_spawn = int(spawn_rate) + (1 if random.random() < (spawn_rate % 1.0) else 0)
            for _ in range(num_to_spawn):
                start_idx = random.randint(0, num_segs - 1)
                sparkle_states[start_idx] = 1.0
                
            frame = []
            for idx in range(num_segs):
                val = sparkle_states[idx]
                val_pow = val ** 1.5
                is_cyan = (idx % 2 == 0)
                c = (0, 255, 255) if is_cyan else (255, 255, 255)
                r_val = int(c[0] * val_pow)
                g_val = int(c[1] * val_pow)
                b_val = int(c[2] * val_pow)
                frame.append((r_val, g_val, b_val))
            return frame
        else:
            # Phase 2: 2-beat opposite comets cycle with purple/magenta breathing background
            breath = 0.5 + 0.5 * math.sin((current_beat - 8.0) * math.pi)  # cycles every 2 beats
            bg_r = int(15 * breath)
            bg_g = 0
            bg_b = int(50 * breath)

            pos1 = (((current_beat - 8.0) / 2.0) % 1.0) * num_segs
            pos2 = ((1.0 - ((current_beat - 8.0) / 2.0)) % 1.0) * num_segs

            frame = [(bg_r, bg_g, bg_b)] * num_segs
            width = 0.8
            for idx in range(num_segs):
                diff1 = abs(idx - pos1)
                dist1 = min(diff1, num_segs - diff1)
                intensity1 = max(0.0, 1.0 - (dist1 / width))
                
                diff2 = abs(idx - pos2)
                dist2 = min(diff2, num_segs - diff2)
                intensity2 = max(0.0, 1.0 - (dist2 / width))
                
                r = int(frame[idx][0] * (1.0 - intensity1 - intensity2) + 0 * intensity1 + 255 * intensity2)
                g = int(frame[idx][1] * (1.0 - intensity1 - intensity2) + 255 * intensity1 + 255 * intensity2)
                b = int(frame[idx][2] * (1.0 - intensity1 - intensity2) + 255 * intensity1 + 255 * intensity2)
                
                frame[idx] = (min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)))
            return frame

    elif look == "drop_to_groove_freestyle_nebula":
        if current_beat < 16.0:
            return generate_buildup_frame("drop_chase_freestyle_nebula", current_beat, elapsed, num_segs, sparkle_states, strobe_state)
        else:
            return generate_buildup_frame("groove_freestyle_nebula", current_beat, elapsed, num_segs, sparkle_states, strobe_state)

    elif look == "buildup_freestyle_nebula":
        # 1. Background color progression
        if current_beat < 16.0:
            # Deep purple/blue breathing
            breath = 0.5 + 0.5 * math.sin(current_beat * math.pi / 2.0)  # cycles every 4 beats
            bg_r = int(10 * breath)
            bg_g = 0
            bg_b = int(40 * breath)
        elif current_beat < 24.0:
            # Ramping to magenta
            p = (current_beat - 16.0) / 8.0
            bg_r = int(10 + 70 * p)
            bg_g = 0
            bg_b = int(40 + 40 * p)
        else:
            # Chaotic hot flicker
            bg_r = random.randint(120, 220)
            bg_g = 0
            bg_b = random.randint(50, 150)

        # 2. Accelerating comets moving in opposite directions
        # phase = integral of speed. speed starts at 0.15 loops/beat and ends at 0.9 loops/beat
        phase = 0.15 * current_beat + 0.012 * (current_beat ** 2)
        pos1 = (phase % 1.0) * num_segs
        pos2 = ((1.0 - phase) % 1.0) * num_segs

        # Render background
        frame = [(bg_r, bg_g, bg_b)] * num_segs
        
        # Draw comets with anti-aliasing (width 0.8)
        width = 0.8
        for idx in range(num_segs):
            diff1 = abs(idx - pos1)
            dist1 = min(diff1, num_segs - diff1)
            intensity1 = max(0.0, 1.0 - (dist1 / width))
            
            diff2 = abs(idx - pos2)
            dist2 = min(diff2, num_segs - diff2)
            intensity2 = max(0.0, 1.0 - (dist2 / width))
            
            # Comet 1 is Cyan, Comet 2 is White
            r = int(frame[idx][0] * (1.0 - intensity1 - intensity2) + 0 * intensity1 + 255 * intensity2)
            g = int(frame[idx][1] * (1.0 - intensity1 - intensity2) + 255 * intensity1 + 255 * intensity2)
            b = int(frame[idx][2] * (1.0 - intensity1 - intensity2) + 255 * intensity1 + 255 * intensity2)
            
            frame[idx] = (min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)))

        # 3. Shutter / Strobe gating
        if current_beat >= 16.0:
            if current_beat >= 31.0:
                # Blinding full-white stroboscopic flash for the final beat
                strobe_on = int(elapsed * 40) % 2 == 0
                if strobe_on:
                    frame = [(255, 255, 255)] * num_segs
                else:
                    frame = [(0, 0, 0)] * num_segs
            else:
                # Shutter effect: strobe frequency accelerates from 5Hz to 18Hz
                p_strobe = (current_beat - 16.0) / 15.0  # 16 to 31 beats
                strobe_freq = 5.0 + 13.0 * p_strobe
                strobe_on = math.sin(2 * math.pi * strobe_freq * elapsed) > 0
                if not strobe_on:
                    # Shutter: dim the frame by 85% instead of complete blackout
                    frame = [(int(r * 0.15), int(g * 0.15), int(b * 0.15)) for r, g, b in frame]

        return frame

    elif look == "buildup_white_half_strobe":
        if current_beat < 16.0:
            # Phase 1: White stroboscopic sparkles expanding in allowed width inside the 4 zones (same as buildup_white_zone_strobe)
            decay = 0.15
            hw = int(0.5 + 2.0 * (current_beat / 16.0))
            spawn_rate = 0.1 + 3.9 * (current_beat / 16.0)

            allowed_indices = []
            for i in range(4):
                center = 2 + 5 * i
                for offset in range(-hw, hw + 1):
                    allowed_indices.append(center + offset)

            for idx in range(num_segs):
                sparkle_states[idx] = max(0.0, sparkle_states[idx] * decay)

            num_to_spawn = int(spawn_rate) + (1 if random.random() < (spawn_rate % 1.0) else 0)
            for _ in range(num_to_spawn):
                if allowed_indices:
                    start_idx = random.choice(allowed_indices)
                    sparkle_states[start_idx] = 1.0

            strobe_freq = 4.0 + 8.0 * (current_beat / 16.0)
            strobe_on = math.sin(2 * math.pi * strobe_freq * elapsed) > 0
            if not strobe_on:
                return [(0, 0, 0)] * num_segs

            frame = []
            for idx in range(num_segs):
                val = sparkle_states[idx]
                r_val = int(255 * (val ** 1.5))
                frame.append((r_val, r_val, r_val))
            return frame
        elif current_beat < 20.0:
            # Phase 2a: Alternating strobe ramping from 4 frames/alternate (5Hz) to 2 frames/alternate (10Hz)
            t = current_beat - 16.0  # ranges from 0.0 to 4.0
            freq = 10.0 + 10.0 * (t / 4.0)
            strobe_on = int(elapsed * freq) % 2 == 0

            if strobe_on:
                return [(255, 255, 255)] * 10 + [(0, 0, 0)] * 10
            else:
                return [(0, 0, 0)] * 10 + [(255, 255, 255)] * 10
        else:
            # Phase 2b: Alternating strobe locked exactly to 2 frames per alternate (10Hz) for perfect symmetry
            strobe_on = int(elapsed * 20.0) % 2 == 0

            if strobe_on:
                return [(255, 255, 255)] * 10 + [(0, 0, 0)] * 10
            else:
                return [(0, 0, 0)] * 10 + [(255, 255, 255)] * 10

    elif look == "buildup_white_zone_strobe":
        # Blinding full-white stroboscopic flash for the final beat (tension climax)
        if current_beat >= 31.0:
            strobe_on = int(elapsed * 40) % 2 == 0
            return [(255, 255, 255)] * num_segs if strobe_on else [(0, 0, 0)] * num_segs

        if current_beat < 16.0:
            # Phase 1: White stroboscopic sparkles expanding in allowed width inside the 4 zones
            decay = 0.15
            # Allowed half-width inside each zone expands from 0 to 2 segments
            hw = int(0.5 + 2.0 * (current_beat / 16.0))
            spawn_rate = 0.1 + 3.9 * (current_beat / 16.0)

            # Build list of allowed segment indices in the expanding zones
            allowed_indices = []
            for i in range(4):
                center = 2 + 5 * i
                for offset in range(-hw, hw + 1):
                    allowed_indices.append(center + offset)

            # Decay existing sparkles
            for idx in range(num_segs):
                sparkle_states[idx] = max(0.0, sparkle_states[idx] * decay)

            # Spawn sparkles in allowed zones
            num_to_spawn = int(spawn_rate) + (1 if random.random() < (spawn_rate % 1.0) else 0)
            for _ in range(num_to_spawn):
                if allowed_indices:
                    start_idx = random.choice(allowed_indices)
                    sparkle_states[start_idx] = 1.0

            # Render stroboscopic frame
            strobe_freq = 4.0 + 8.0 * (current_beat / 16.0)  # accelerates from 4Hz to 12Hz
            strobe_on = math.sin(2 * math.pi * strobe_freq * elapsed) > 0
            if not strobe_on:
                return [(0, 0, 0)] * num_segs

            frame = []
            for idx in range(num_segs):
                val = sparkle_states[idx]
                r_val = int(255 * (val ** 1.5))
                frame.append((r_val, r_val, r_val))
            return frame
        else:
            # Phase 2: 4 zones are fully formed and perform an accelerating strobe chase
            # Chase speed (beats per loop) starts at 4 beats/loop and speeds up (chase_phase accelerates)
            t = current_beat - 16.0
            chase_phase = 2.0 * t + 0.133 * (t ** 2)
            active_zone = int((chase_phase % 1.0) * 4.0)

            # Strobe frequency starts at 12Hz and accelerates to 20Hz at the drop
            strobe_freq = 12.0 + 8.0 * (t / 15.0)
            strobe_on = math.sin(2 * math.pi * strobe_freq * elapsed) > 0

            frame = [(0, 0, 0)] * num_segs
            if strobe_on:
                # Turn active zone to full white
                start_seg = active_zone * 5
                for idx in range(start_seg, start_seg + 5):
                    frame[idx] = (255, 255, 255)
            return frame

    elif look in ("twinkle_blue", "drop_white_aggressive", "post_drop_white_shatter", "test_combo", "drop_center_burst_blue_cyan", "post_drop_center_comet_blue_cyan"):
        renderer = GoveeFrameRenderer()
        frame_idx = int(elapsed * 40.0)
        return renderer.render(
            look,
            beat_pos=current_beat,
            local_t=elapsed,
            frame_index=frame_idx,
            params={},
            segments=num_segs,
            seed=42,
        )
    elif look == "test_combo":
        renderer = GoveeFrameRenderer()
        frame_idx = int(elapsed * 40.0)
        if current_beat < 16.0:
            return renderer.render(
                "drop_white_aggressive",
                beat_pos=current_beat,
                local_t=elapsed,
                frame_index=frame_idx,
                params={},
                segments=num_segs,
                seed=42,
            )
        else:
            return renderer.render(
                "post_drop_white_shatter",
                beat_pos=current_beat - 16.0,
                local_t=elapsed,
                frame_index=frame_idx,
                params={},
                segments=num_segs,
                seed=42,
            )

    elif look == "buildup_ramp_3":
        # 1. Strobe frequency starts at 4Hz and accelerates to 16Hz
        strobe_freq = 4.0 + 12.0 * progress
        strobe_on_off = 1.0 if (math.sin(2 * math.pi * strobe_freq * elapsed) > 0) else 0.0
        
        # 2. Gate reaches full strobe depth by beat 16 (progress 0.5)
        strobe_depth = min(1.0, progress * 2.0)
        gate = (1.0 - strobe_depth) + strobe_depth * strobe_on_off

        # 3. Smooth chase head position moving at 35 segments/second
        speed = 35.0
        pos = int((speed * elapsed) % num_segs)
        
        frame = [(0, 0, 0)] * num_segs
        val = int(255 * gate)
        frame[pos] = (val, val, val)
        return frame

    elif look == "buildup_ramp_2":
        # 1. Strobe frequency starts at 6Hz and accelerates to 18Hz
        strobe_freq = 6.0 + 12.0 * progress
        strobe_on = (math.sin(2 * math.pi * strobe_freq * elapsed) > 0)
        
        if not strobe_on:
            return [(0, 0, 0)] * num_segs

        # 2. Number of active chasing particles scales from 1 to 5
        num_particles = int(1.0 + 4.0 * progress)
        
        # 3. Particle speed is super fast (65 segments per second)
        speed = 65.0
        frame = [(0, 0, 0)] * num_segs

        for i in range(num_particles):
            # Space out the particles evenly along the strip length
            offset = i * (num_segs / num_particles)
            pos = int((speed * elapsed + offset) % num_segs)
            frame[pos] = (255, 255, 255)

        return frame

    else:
        # Default: buildup_ramp_1 logic
        decay = 0.15
        spawn_rate = 0.05 + 3.95 * progress

        # Decay existing sparkles
        for idx in range(num_segs):
            sparkle_states[idx] = max(0.0, sparkle_states[idx] * decay)

        # Determine how many sparkles to spawn this frame
        num_to_spawn = int(spawn_rate) + (1 if random.random() < (spawn_rate % 1.0) else 0)
        for _ in range(num_to_spawn):
            start_idx = random.randint(0, num_segs - 1)
            sparkle_states[start_idx] = 1.0

        # Build output frame
        frame = []
        for idx in range(num_segs):
            val = sparkle_states[idx]
            val_pow = val ** 1.5  # Gamma-like curve for crisp contrast
            r_val = int(255 * val_pow)
            frame.append((r_val, r_val, r_val))
        return frame


def run_edm_buildup(controller: GoveeRealtimeController, bpm: float, look: str) -> None:
    """Run the 32-beat EDM buildup effect using the selected look pattern."""
    look_desc = EDM_BUILDS.get(look, "Unknown Look")
    print(f"\n\033[95m=== Starting EDM Buildup: '{look}' ({bpm} BPM) ===\033[0m")
    print(f"\033[90mStyle: {look_desc}\033[0m")

    beat_duration = 60.0 / bpm
    total_beats = 32
    fps = 40
    frame_duration = 1.0 / fps

    start_time = time.time()
    num_segs = controller.num_segments

    # States
    sparkle_states: list[float] = [0.0] * num_segs
    strobe_state = {
        "last_strobe_on": False,
        "active_indices": []
    }

    try:
        while True:
            elapsed = time.time() - start_time
            current_beat = elapsed / beat_duration

            if current_beat >= total_beats:
                break

            progress = current_beat / total_beats

            # Generate frame
            frame = generate_buildup_frame(look, current_beat, elapsed, num_segs, sparkle_states, strobe_state)

            # Send frame
            controller.send_frame(frame)

            # Draw progress
            info_str = f"{look.upper()} (Beat {int(current_beat) + 1}/32)"
            print_progress_bar(progress, info_str)
            time.sleep(frame_duration)

        # Drop Blackout
        controller.send_frame([(0, 0, 0)] * num_segs)
        print_progress_bar(1.0, "DROP! (Blackout)")
        print(f"\n\033[92mEDM Buildup '{look}' Complete!\033[0m")

    except KeyboardInterrupt:
        print("\n\033[91mEffect interrupted by user.\033[0m")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Govee H612D Real-time Effects Player",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ip", default=DEFAULT_IP, help=f"Device IP address (default: {DEFAULT_IP})")
    parser.add_argument("--segments", type=int, default=DEFAULT_SEGMENTS, help=f"Number of segments (default: {DEFAULT_SEGMENTS})")
    parser.add_argument("--bpm", type=float, default=128.0, help="Tempo in BPM (default: 128.0)")
    parser.add_argument(
        "--look",
        choices=list(EDM_BUILDS.keys()) + ["all"],
        default="buildup_ramp_1",
        help="Which buildup look style to run (default: buildup_ramp_1)",
    )
    parser.add_argument("--list", action="store_true", help="List all available EDM buildup looks and descriptions")
    args = parser.parse_args()

    if args.list:
        print("\n=== Available 32-Beat EDM Buildup Looks ===")
        for name, desc in EDM_BUILDS.items():
            print(f"  \033[96m{name:<20}\033[0m : {desc}")
        print()
        sys.exit(0)

    controller = GoveeRealtimeController(args.ip, args.segments)
    
    try:
        controller.activate()
        if args.look == "all":
            looks_to_run = list(EDM_BUILDS.keys())
            for idx, look_name in enumerate(looks_to_run):
                run_edm_buildup(controller, args.bpm, look_name)
                if idx < len(looks_to_run) - 1:
                    print("\nTransitioning to next look in 2 seconds...")
                    time.sleep(2.0)
        else:
            run_edm_buildup(controller, args.bpm, args.look)
    finally:
        controller.deactivate()
        controller.close()
        print("\nAll done!")


if __name__ == "__main__":
    main()
