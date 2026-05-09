import re

with open('tests/test_anlz_reader.py', 'r') as f:
    content = f.read()

# Add import
content = content.replace(
    'from rb_ss_bridge_v2.anlz_reader import (  # noqa: E402',
    'from rb_ss_bridge_v2.anlz_reader import (  # noqa: E402\n    _compute_bar_energies,'
)

# Add helper
helper_code = """

def _detect_drop_beats_helper(heights, waveform_duration_ms, beatgrid_times_ms):
    energies = _compute_bar_energies(heights, waveform_duration_ms, beatgrid_times_ms)
    track_max = float(max(energies)) if energies else 0.0
    return _detect_drop_beats(energies, track_max)

class AnlzDropDetectTests(unittest.TestCase):"""
content = content.replace('class AnlzDropDetectTests(unittest.TestCase):', helper_code)

# Replace _detect_drop_beats with _detect_drop_beats_helper
content = content.replace('_detect_drop_beats(', '_detect_drop_beats_helper(')

with open('tests/test_anlz_reader.py', 'w') as f:
    f.write(content)
