import sys
import unittest
from pathlib import Path

# Add the project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.beat_math import (
    _compute_beat_pos,
    _compute_beatgrid_position,
    _beatgrid_elapsed_for_abs_beat,
)

class TestBeatMath(unittest.TestCase):
    def test_compute_beat_pos(self):
        self.assertEqual(_compute_beat_pos(0.0, 120.0), 0.0)
        self.assertEqual(_compute_beat_pos(500.0, 120.0), 1.0)
        self.assertEqual(_compute_beat_pos(2000.0, 120.0), 0.0)
        self.assertEqual(_compute_beat_pos(-500.0, 120.0), 3.0)
        self.assertEqual(_compute_beat_pos(0.0, 0.0), 0.0)
        self.assertEqual(_compute_beat_pos(500.0, 120.0, first_beat_ms=250.0), 0.5)

    def test_compute_beatgrid_position(self):
        grid = [0.0, 500.0, 1000.0, 1500.0]
        
        # Exact markers
        self.assertEqual(_compute_beatgrid_position(0.0, grid), (0.0, 0.0))
        self.assertEqual(_compute_beatgrid_position(500.0, grid), (1.0, 1.0))
        
        # Between markers
        self.assertEqual(_compute_beatgrid_position(250.0, grid), (0.5, 0.5))
        self.assertEqual(_compute_beatgrid_position(750.0, grid), (1.5, 1.5))
        
        # Before first marker (extrapolated)
        self.assertEqual(_compute_beatgrid_position(-500.0, grid), (3.0, -1.0))
        
        # After last marker (extrapolated)
        self.assertEqual(_compute_beatgrid_position(2000.0, grid), (0.0, 4.0))

    def test_beatgrid_elapsed_for_abs_beat(self):
        grid = [0.0, 500.0, 1000.0, 1500.0]
        
        # Exact markers
        self.assertEqual(_beatgrid_elapsed_for_abs_beat(0, grid), (0, "grid"))
        self.assertEqual(_beatgrid_elapsed_for_abs_beat(1, grid), (500, "grid"))
        self.assertEqual(_beatgrid_elapsed_for_abs_beat(3, grid), (1500, "grid"))
        
        # Beyond grid
        self.assertEqual(_beatgrid_elapsed_for_abs_beat(4, grid), (2000, "grid-extrapolated"))
        self.assertEqual(_beatgrid_elapsed_for_abs_beat(5, grid), (2500, "grid-extrapolated"))

if __name__ == '__main__':
    unittest.main()
