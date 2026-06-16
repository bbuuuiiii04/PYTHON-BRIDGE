import math
import random
from typing import List, Tuple, Mapping, Any

# ==========================================
# M2 Architecture Core
# ==========================================
MAX_SLOTS = 5
RGB = Tuple[int, int, int]
Frame = List[RGB]

# MotionField: For each pixel, a list of intensities (0.0 to 1.0) corresponding to each slot.
# Shape: [segments][MAX_SLOTS]
MotionField = List[List[float]]

def clamp(val: float) -> int:
    """Clamps a color channel to 0-255."""
    return max(0, min(255, int(val)))

def universal_colorizer(motion_field: MotionField, slot_colors: List[RGB]) -> Frame:
    """
    M2 Universal Colorizer:
    rgb[px] = clamp( Σ_slot slot_color[slot] · intensity[px][slot] )
    """
    frame = []
    # Pad slot_colors with black if fewer than MAX_SLOTS are provided
    padded_colors = list(slot_colors)
    while len(padded_colors) < MAX_SLOTS:
        padded_colors.append((0, 0, 0))
    
    for px_intensities in motion_field:
        r, g, b = 0.0, 0.0, 0.0
        for slot, intensity in enumerate(px_intensities):
            if slot < MAX_SLOTS and intensity > 0:
                color = padded_colors[slot]
                r += color[0] * intensity
                g += color[1] * intensity
                b += color[2] * intensity
        frame.append((clamp(r), clamp(g), clamp(b)))
    return frame

def empty_motion_field(segments: int) -> MotionField:
    """Creates an empty (all zeros) motion field for the given number of segments."""
    return [[0.0] * MAX_SLOTS for _ in range(segments)]

# ==========================================
# Motion Skeleton Backbones (Cues)
# ==========================================

def groove_center_chase(beat: float, segments: int, params: Mapping[str, Any]) -> MotionField:
    """
    32-beat cue: Comets spawn in the middle and travel outwards.
    Travel time of 2 beats. 5 possible colors (slots) cycled sequentially per comet.
    No strobe.
    """
    field = empty_motion_field(segments)
    center = segments / 2.0
    
    # Comet tail length (e.g. 15% of the half-strip)
    comet_width = max(2.0, center * 0.15) 
    
    travel_beats = 4.0
    
    # Comets spawn every 1 beat. Travel time is 1 beat.
    for age_offset in range(int(math.ceil(travel_beats))):
        age = (beat % 1.0) + age_offset
        if age > travel_beats:
            continue
            
        # Position of the comet head from the center
        comet_head_dist = (age / travel_beats) * center
        
        for idx in range(segments):
            dist_from_center = abs(idx - center)
            
            # If pixel falls within the comet body (from tail end to head)
            if comet_head_dist - comet_width <= dist_from_center <= comet_head_dist:
                # relative_pos is 0.0 at the tail, and 1.0 at the head
                relative_pos = (dist_from_center - (comet_head_dist - comet_width)) / comet_width
                base_intensity = relative_pos 
                
                # Multi-color mapping: Map the comet body across all 5 slots!
                # Head (1.0) maps to slot 4, tail (0.0) maps to slot 0.
                slot_coord = relative_pos * (MAX_SLOTS - 1)
                
                slot_below = int(math.floor(slot_coord))
                slot_above = int(math.ceil(slot_coord))
                weight_above = slot_coord - slot_below
                weight_below = 1.0 - weight_above
                
                # We blend the intensity into the two adjacent color slots
                # creating a smooth gradient comet
                if slot_below == slot_above:
                    field[idx][slot_below] = min(1.0, field[idx][slot_below] + base_intensity)
                else:
                    field[idx][slot_below] = min(1.0, field[idx][slot_below] + base_intensity * weight_below)
                    field[idx][slot_above] = min(1.0, field[idx][slot_above] + base_intensity * weight_above)
                
    return field

def backbone_multi_sparkle(beat: float, segments: int, params: Mapping[str, Any], seed: int) -> MotionField:
    field = empty_motion_field(segments)
    return field

def groove_center_burst_retract(beat: float, segments: int, params: Mapping[str, Any]) -> MotionField:
    """
    Volume bar effect: 1 active burst per beat.
    Shoots outward from the center very quickly, then retracts.
    Comet tail stretches all the way to the center.
    Multi-colored across slots.
    """
    field = empty_motion_field(segments)
        
    center = segments / 2.0
    
    burst_beats = params.get('burst_beats', 1.0)
    fraction = (beat % burst_beats) / burst_beats
    
    # Envelope: 
    # 0.0 -> 0.60 : Attack (burst outward slower)
    # 0.60 -> 0.85 : Decay (retract inward)
    # 0.85 -> 1.0 : Black
    
    max_length = center * 0.8 # Make the physical length slightly shorter
    
    if fraction < 0.60:
        progress = fraction / 0.60
        # Linear sweep instead of fast ease out so you can see the animation
        comet_head_dist = max_length * progress
    elif fraction < 0.85:
        progress = (fraction - 0.60) / 0.25
        # Fast ease-in for retraction
        comet_head_dist = max_length * (1.0 - progress**2)
    else:
        # Black for the rest of the beat
        return field
        
    comet_width = comet_head_dist
    if comet_width <= 0.01:
        return field
        
    for idx in range(segments):
        dist_from_center = abs(idx - center)
        
        # If pixel is inside the volume bar
        if dist_from_center <= comet_head_dist:
            relative_pos = dist_from_center / comet_head_dist
            
            # Map head to slot 4, center to slot 0
            slot_coord = relative_pos * (MAX_SLOTS - 1)
            
            slot_below = int(math.floor(slot_coord))
            slot_above = int(math.ceil(slot_coord))
            weight_above = slot_coord - slot_below
            weight_below = 1.0 - weight_above
            
            # Solid intensity, fading as it retracts
            base_intensity = 1.0 
            if fraction >= 0.60:
                base_intensity *= (1.0 - progress)
                
            if slot_below == slot_above:
                field[idx][slot_below] = min(1.0, field[idx][slot_below] + base_intensity)
            else:
                field[idx][slot_below] = min(1.0, field[idx][slot_below] + base_intensity * weight_below)
                field[idx][slot_above] = min(1.0, field[idx][slot_above] + base_intensity * weight_above)
                
    return field

def ambient_full_breathing(beat: float, segments: int, params: Mapping[str, Any]) -> MotionField:
    """
    Ambient full strip breathing.
    Entire strip fades in and out smoothly using a sine wave.
    The intensity breathes every `breath_beats`.
    The color smoothly drifts across all slots every `drift_beats`.
    """
    field = empty_motion_field(segments)
    
    breath_beats = params.get('breath_beats', 8.0)
    drift_beats = params.get('drift_beats', 32.0)
    
    # Breathing Intensity Envelope
    # 0.0 to 0.5 (Beats 0-4): Brightens to 50% (Inhale)
    # 0.5 to 0.75 (Beats 4-6): Dims to 0% (Exhale)
    # 0.75 to 1.0 (Beats 6-8): Pitch Black (Darkness Rest)
    breath_fraction = (beat % breath_beats) / breath_beats
    
    if breath_fraction <= 0.5:
        intensity = (breath_fraction / 0.5) * 0.50
    elif breath_fraction <= 0.75:
        progress = (breath_fraction - 0.5) / 0.25
        intensity = (1.0 - progress) * 0.50
    else:
        intensity = 0.0
    
    # Color Drift (0.0 to MAX_SLOTS-1 using half a sine wave)
    drift_fraction = (beat % drift_beats) / drift_beats
    color_phase = math.sin(drift_fraction * math.pi)
    slot_coord = color_phase * (MAX_SLOTS - 1)
    
    slot_below = int(math.floor(slot_coord))
    slot_above = int(math.ceil(slot_coord))
    weight_above = slot_coord - slot_below
    weight_below = 1.0 - weight_above
    
    # Apply to entire strip uniformly
    for idx in range(segments):
        if slot_below == slot_above:
            field[idx][slot_below] = min(1.0, field[idx][slot_below] + intensity)
        else:
            field[idx][slot_below] = min(1.0, field[idx][slot_below] + intensity * weight_below)
            field[idx][slot_above] = min(1.0, field[idx][slot_above] + intensity * weight_above)
            
    return field

def ambient_star_twinkle(beat: float, segments: int, params: Mapping[str, Any]) -> MotionField:
    """
    Ambient breathing star twinkle effect.
    Majority of strip is dim. Individual segments breathe in and out.
    Lifespan of a breath is 1-4 beats.
    Stateless procedural generation using the segment index as a seed.
    """
    field = empty_motion_field(segments)
    
    import random
    
    for idx in range(segments):
        # Deterministic randomness so each pixel has stable properties over time
        random.seed(idx)
        
        lifespan_beats = random.uniform(1.0, 4.0)
        # Sleep for a long time so the majority of the strip is dim/off
        sleep_beats = random.uniform(4.0, 12.0) 
        total_cycle = lifespan_beats + sleep_beats
        
        # Random starting phase so they all breathe at different times
        phase_offset = random.uniform(0.0, 100.0)
        # Randomly assign this star to one of the 5 color slots
        color_slot = random.randint(0, MAX_SLOTS - 1)
        
        # Where are we in this pixel's personal lifecycle?
        cycle_pos = (beat + phase_offset) % total_cycle
        
        if cycle_pos < lifespan_beats:
            # It's alive! Smooth sine wave breathing
            fraction = cycle_pos / lifespan_beats
            intensity = math.sin(fraction * math.pi)
            
            # Cap max brightness at 30% so it stays truly ambient
            intensity *= 0.3
            
            field[idx][color_slot] = min(1.0, field[idx][color_slot] + intensity)
            
    return field

def ambient_star_twinkle_sand(beat: float, segments: int, params: Mapping[str, Any]) -> list[tuple[int, int, int]]:
    """
    Hardcoded RGB version of ambient_star_twinkle specifically for the Dune Sand palette.
    Bypasses the MotionField and universal_colorizer entirely.
    """
    import random
    frame = [(0, 0, 0) for _ in range(segments)]
    
    sand_palette = [
        (255, 140, 50),   # Deep Dune Spice
        (255, 180, 100),  # Warm Desert Sand
        (255, 210, 150),  # Pale Sunlit Sand
        (255, 235, 200),  # Warm Ivory
        (255, 250, 235),  # Soft Warm White
    ]
    
    for idx in range(segments):
        random.seed(idx)
        lifespan_beats = random.uniform(1.0, 4.0)
        sleep_beats = random.uniform(4.0, 12.0) 
        total_cycle = lifespan_beats + sleep_beats
        phase_offset = random.uniform(0.0, 100.0)
        
        # Hardcode selection from the sand palette
        color_rgb = sand_palette[random.randint(0, len(sand_palette) - 1)]
        
        cycle_pos = (beat + phase_offset) % total_cycle
        if cycle_pos < lifespan_beats:
            fraction = cycle_pos / lifespan_beats
            intensity = math.sin(fraction * math.pi)
            intensity *= 0.3 # 30% max brightness
            
            frame[idx] = (
                int(color_rgb[0] * intensity),
                int(color_rgb[1] * intensity),
                int(color_rgb[2] * intensity)
            )
            
    return frame

def post_drop_chase(beat: float, segments: int, params: Mapping[str, Any]) -> MotionField:
    """
    Ported from bridge _post_drop_chase.
    Strobing comets that wrap around the strip.
    """
    field = empty_motion_field(segments)
    
    # 16th-note strobe
    strobe_on = (int(beat * 16.0) % 2) == 0
    if not strobe_on:
        return field
        
    travel_beats = params.get('travel_beats', 2.0)
    
    # Comets spawn every 1.0 beat.
    for age_offset in range(int(math.ceil(travel_beats))):
        age = (beat % 1.0) + age_offset
        if age > travel_beats:
            continue
            
        progress = age / travel_beats
        head_pos = progress * segments
        
        comet_width = max(2.0, segments * 0.15)
        
        for idx in range(segments):
            # linear wrap-around chase
            dist = (head_pos - idx) % segments
            if dist <= comet_width:
                intensity = 1.0 - (dist / comet_width)
                # Map intensity entirely to slot 0
                field[idx][0] = min(1.0, field[idx][0] + intensity)
                
    return field

# ==========================================
# Verification / Testing
# ==========================================
if __name__ == "__main__":
    import sys
    import time
    from pathlib import Path
    
    print("M2 Motion Skeletons Prototype initialized.")
    
    # 5 possible colors: All Blue for testing
    palette = [
        (0, 0, 255),
        (0, 0, 255),
        (0, 0, 255),
        (0, 0, 255),
        (0, 0, 255),
    ]
    
    if "--live" in sys.argv:
        print("\n--- LIVE MODE: Attempting to send to physical Govee LEDs ---")
        sys.path.insert(0, "/Users/bbui")
        from rb_ss_bridge_v2.led_config import load_led_look_director_config
        from rb_ss_bridge_v2.govee_realtime_transport import GoveeRealtimeTransport
        
        config_path = "/Users/bbui/rb_ss_bridge_v2/config/led_look_director.json"
        loaded = load_led_look_director_config(config_path)
        if not loaded.available:
            print(f"Failed to load config: {loaded.errors}")
            sys.exit(1)
            
        rt = loaded.config.targets["room_perimeter"].realtime
        
        segments = 60
        ip = "192.168.0.216"
        port = 4003

        transport = GoveeRealtimeTransport(
            ip, port=port, segments=segments,
            header_bytes=(0xBB, 0x00, 0xFA, 0xB0, 0x00), # dreams header
            stretch=rt.stretch,
            activate_pt=rt.activate_pt, deactivate_pt=rt.deactivate_pt
        )
        
        print(f"Connected to Govee LEDs at {ip}:{port} ({segments} segments)")
        transport.activate()
        transport.set_brightness(100)
        
        bpm = 155.0
        fps = 60.0
        t0 = time.time()
        print(f"Playing `post_drop_chase` with travel_beats=4.0 at {bpm} BPM...")
        
        try:
            print(f"Phase 1: Playing `post_drop_chase` with travel_beats=4.0 at {bpm} BPM for 15s...")
            while time.time() - t0 < 15.0:
                beat = (time.time() - t0) * (bpm / 60.0)
                field = post_drop_chase(beat=beat, segments=segments, params={"travel_beats": 4.0})
                frame = universal_colorizer(field, palette)
                transport.send_frame(frame)
                time.sleep(1.0 / fps)
                
            print(f"Phase 2: Playing `post_drop_chase` with travel_beats=2.0 at {bpm} BPM for 15s...")
            while time.time() - t0 < 30.0:
                beat = (time.time() - t0) * (bpm / 60.0)
                field = post_drop_chase(beat=beat, segments=segments, params={"travel_beats": 2.0})
                frame = universal_colorizer(field, palette)
                transport.send_frame(frame)
                time.sleep(1.0 / fps)
        except KeyboardInterrupt:
            pass
        finally:
            print("Shutting down... sending blackout.")
            transport.blackout()
            transport.close()
            
    else:
        segments = 40
        print(f"\nTesting `cue_center_multi_chase` across 4 beats with {segments} segments:")
        
        # Render a few frames
        for b in [0.0, 1.0, 2.0, 3.0, 3.5]:
            field = groove_center_chase(beat=b, segments=segments, params={})
            frame = universal_colorizer(field, palette)
            
            # Count non-black pixels to show movement
            lit_pixels = sum(1 for px in frame if px != (0, 0, 0))
            print(f"Beat {b:0.1f} -> Lit Pixels: {lit_pixels}")
            
            # Optional ASCII visualization (using left half of strip to visualize outbound)
            ascii_half = ""
            for idx in range(20, 40):  # Show outward from center to right edge
                intensity = frame[idx][2] / 255.0  # Since it's all blue, check blue channel
                if intensity > 0.8: ascii_half += "O"
                elif intensity > 0.3: ascii_half += "o"
                elif intensity > 0.0: ascii_half += "."
                else: ascii_half += "-"
            print(f"  Center -> Edge: |{ascii_half}|")
        print("\nNote: Run with `--live` to see this on your physical Govee LEDs!")
