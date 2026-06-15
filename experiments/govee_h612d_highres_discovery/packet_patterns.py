import sys
import math

def clamp(val):
    return max(0, min(255, int(val)))

def traveling_marker(segment_count, step):
    """A single white marker that travels along the strip based on the step."""
    pattern = [(0, 0, 0)] * segment_count
    pos = step % max(1, segment_count)
    pattern[pos] = (200, 200, 200) # Not full white
    return pattern

def gradient(segment_count):
    """A smooth gradient from Red to Blue."""
    pattern = []
    for i in range(segment_count):
        if segment_count <= 1:
            ratio = 0
        else:
            ratio = i / (segment_count - 1)
        r = clamp(255 * (1 - ratio))
        g = 0
        b = clamp(255 * ratio)
        pattern.append((r, g, b))
    return pattern

def alternating_rg(segment_count):
    """Alternating Red and Green segments."""
    pattern = []
    for i in range(segment_count):
        if i % 2 == 0:
            pattern.append((200, 0, 0))
        else:
            pattern.append((0, 200, 0))
    return pattern

def sparse_marker(segment_count, every=5):
    """A blue marker every 'every' segments, rest off."""
    pattern = []
    for i in range(segment_count):
        if i % every == 0:
            pattern.append((0, 0, 200))
        else:
            pattern.append((0, 0, 0))
    return pattern

def binary_split(segment_count):
    """First half red, second half blue."""
    pattern = []
    half = segment_count // 2
    for i in range(segment_count):
        if i < half:
            pattern.append((200, 0, 0))
        else:
            pattern.append((0, 0, 200))
    return pattern

def sentinel(segment_count):
    """First segment green, last segment red, middle off."""
    pattern = [(0, 0, 0)] * segment_count
    if segment_count > 0:
        pattern[0] = (0, 200, 0)
    if segment_count > 1:
        pattern[-1] = (200, 0, 0)
    return pattern

def unique_bands(segment_count):
    """Cycle through a distinct set of colors to easily identify repeating or mirrored blocks."""
    colors = [
        (200, 0, 0),   # Red
        (0, 200, 0),   # Green
        (0, 0, 200),   # Blue
        (200, 200, 0), # Yellow
        (200, 0, 200), # Magenta
        (0, 200, 200)  # Cyan
    ]
    pattern = []
    for i in range(segment_count):
        pattern.append(colors[i % len(colors)])
    return pattern

if __name__ == "__main__":
    if "--demo" in sys.argv:
        print("Running packet_patterns.py --demo")
        counts = [5, 10]
        for count in counts:
            print(f"\n--- Segment Count: {count} ---")
            print(f"traveling_marker (step 2): {traveling_marker(count, 2)}")
            print(f"gradient: {gradient(count)}")
            print(f"alternating_rg: {alternating_rg(count)}")
            print(f"sparse_marker: {sparse_marker(count)}")
            print(f"binary_split: {binary_split(count)}")
            print(f"sentinel: {sentinel(count)}")
            print(f"unique_bands: {unique_bands(count)}")

        # Assertions
        assert len(traveling_marker(15, 0)) == 15
        assert len(gradient(20)) == 20
        assert len(alternating_rg(25)) == 25
        assert len(sparse_marker(30)) == 30
        assert len(binary_split(40)) == 40
        assert len(sentinel(50)) == 50
        assert len(unique_bands(10)) == 10
        print("\nAll internal assertions passed.")
