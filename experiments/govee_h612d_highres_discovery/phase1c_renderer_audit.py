import sys
import os
import json

sys.path.insert(0, os.path.abspath('.'))

from govee_frame_renderer import GoveeFrameRenderer

def analyze_frame(name, frame, segments):
    length = len(frame)
    unique_colors = len(set(frame))
    non_black = sum(1 for c in frame if c != (0, 0, 0))
    transitions = sum(1 for i in range(1, length) if frame[i] != frame[i-1])
    first_12 = frame[:12]
    last_12 = frame[-12:]
    
    print(f"--- Cue: {name} (segments={segments}) ---")
    print(f"frame length: {length}")
    print(f"unique RGB tuple count: {unique_colors}")
    print(f"transition count: {transitions}")
    print(f"non-black segment count: {non_black}")
    print(f"first 12 RGB: {first_12}")
    print(f"last 12 RGB: {last_12}")
    print()

def main():
    renderer = GoveeFrameRenderer()
    
    cues_to_test = [
        "groove_chase_cyan",
        "drop_chase_red",
        "beat_chase"
    ]
    
    print("=================== FRAME AUDIT ===================")
    for cue in cues_to_test:
        for segs in [20, 60]:
            # Simulate beat 1.5, frame 10
            frame = renderer.render(
                cue,
                beat_pos=1.5,
                local_t=0.5,
                frame_index=10,
                params={"color": (255, 0, 0), "span_beats": 4.0},
                segments=segs,
                seed=42
            )
            analyze_frame(cue, frame, segs)

if __name__ == "__main__":
    main()
