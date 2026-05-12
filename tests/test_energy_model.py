import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.energy_model import (  # noqa: E402
    EnergyWindow,
    LOW_CONFIDENCE_CUTOFF,
    classify_breakdown_intensity,
    classify_buildup_intensity,
    classify_drop_intensity,
    elapsed_ms_to_nearest_beat,
    energy_window_for_beat,
    map_index_to_elapsed_ms,
    normalize_energy_series,
)


class EnergyModelTests(unittest.TestCase):
    def test_normalize_energy_series_empty_and_zero(self) -> None:
        self.assertEqual(normalize_energy_series([]).values, ())
        self.assertEqual(normalize_energy_series([0.0, 0.0]).values, ())

    def test_normalize_energy_series_clamps_negative(self) -> None:
        values = normalize_energy_series([-1.0, 5.0, 10.0]).values
        self.assertEqual(values[0], 0.0)
        self.assertAlmostEqual(values[-1], 1.0)

    def test_map_index_to_elapsed_ms_handles_edges(self) -> None:
        self.assertEqual(map_index_to_elapsed_ms(0, 0, 1000.0), 0.0)
        self.assertEqual(map_index_to_elapsed_ms(2, 5, 0.0), 0.0)
        self.assertAlmostEqual(map_index_to_elapsed_ms(4, 5, 1000.0), 1000.0)

    def test_elapsed_ms_to_nearest_beat(self) -> None:
        self.assertIsNone(elapsed_ms_to_nearest_beat(100.0, []))
        self.assertEqual(elapsed_ms_to_nearest_beat(100.0, [0.0]), 0)
        grid = [0.0, 500.0, 1000.0, 1500.0]
        self.assertEqual(elapsed_ms_to_nearest_beat(50.0, grid), 0)
        self.assertEqual(elapsed_ms_to_nearest_beat(760.0, grid), 2)
        self.assertEqual(elapsed_ms_to_nearest_beat(5000.0, grid), 3)

    def test_energy_window_handles_empty_inputs(self) -> None:
        self.assertIsNone(
            energy_window_for_beat(
                16,
                [],
                [1, 2, 3],
                total_ms=1000.0,
                pre_beats=8,
                post_beats=8,
            )
        )
        self.assertIsNone(
            energy_window_for_beat(
                16,
                [0.0, 500.0],
                [],
                total_ms=1000.0,
                pre_beats=8,
                post_beats=8,
            )
        )

    def test_energy_window_total_ms_zero_uses_grid(self) -> None:
        grid = [float(i * 500) for i in range(80)]
        energy = [10.0] * 200
        window = energy_window_for_beat(
            32,
            grid,
            energy,
            total_ms=0.0,
            pre_beats=8,
            post_beats=8,
        )
        self.assertIsNotNone(window)
        assert window is not None
        self.assertAlmostEqual(window.pre_mean, window.post_mean, places=4)

    def test_drop_classification_subtle_medium_major_peak(self) -> None:
        subtle = classify_drop_intensity(
            EnergyWindow(
                beat=64,
                pre=(0.50,) * 16,
                post=(0.56,) * 16,
                pre_mean=0.50,
                post_mean=0.56,
                lift=0.06,
                peak=0.56,
                valley=0.50,
            )
        )
        self.assertEqual(subtle.class_name, "subtle")

        medium = classify_drop_intensity(
            EnergyWindow(
                beat=64,
                pre=(0.40,) * 16,
                post=(0.61,) * 16,
                pre_mean=0.40,
                post_mean=0.61,
                lift=0.21,
                peak=0.61,
                valley=0.40,
            )
        )
        self.assertEqual(medium.class_name, "medium")

        major = classify_drop_intensity(
            EnergyWindow(
                beat=64,
                pre=(0.20,) * 16,
                post=(0.54,) * 16,
                pre_mean=0.20,
                post_mean=0.54,
                lift=0.34,
                peak=0.54,
                valley=0.20,
            )
        )
        self.assertEqual(major.class_name, "major")

        peak = classify_drop_intensity(
            EnergyWindow(
                beat=64,
                pre=(0.05,) * 16,
                post=(0.60,) * 16,
                pre_mean=0.05,
                post_mean=0.60,
                lift=0.55,
                peak=0.60,
                valley=0.05,
            )
        )
        self.assertEqual(peak.class_name, "peak")

    def test_breakdown_low_energy_classification(self) -> None:
        result = classify_breakdown_intensity(
            EnergyWindow(
                beat=64,
                pre=(0.80,) * 16,
                post=(0.12,) * 16,
                pre_mean=0.80,
                post_mean=0.12,
                lift=-0.68,
                peak=0.80,
                valley=0.12,
            )
        )
        self.assertIn(result.class_name, ("major", "peak"))

    def test_buildup_rising_energy_classification(self) -> None:
        result = classify_buildup_intensity(
            EnergyWindow(
                beat=64,
                pre=(0.20,) * 16,
                post=(0.70,) * 16,
                pre_mean=0.20,
                post_mean=0.70,
                lift=0.50,
                peak=0.70,
                valley=0.20,
            )
        )
        self.assertIn(result.class_name, ("medium", "major"))

    def test_low_confidence_with_tiny_window(self) -> None:
        grid = [float(i * 500) for i in range(30)]
        energy = [1.0] * 20 + [20.0] * 20
        window = energy_window_for_beat(8, grid, energy, total_ms=15_000.0, pre_beats=1, post_beats=1)
        assert window is not None
        result = classify_drop_intensity(window)
        self.assertEqual(result.class_name, "low_confidence")

    def test_huge_lift_with_too_few_pre_samples_stays_low_confidence(self) -> None:
        result = classify_drop_intensity(
            EnergyWindow(
                beat=32,
                pre=(0.01,) * 2,
                post=(0.95,) * 16,
                pre_mean=0.01,
                post_mean=0.95,
                lift=0.94,
                peak=0.95,
                valley=0.01,
            )
        )
        self.assertEqual(result.class_name, "low_confidence")
        self.assertLessEqual(result.confidence, LOW_CONFIDENCE_CUTOFF)

    def test_huge_lift_with_too_few_post_samples_stays_low_confidence(self) -> None:
        result = classify_drop_intensity(
            EnergyWindow(
                beat=32,
                pre=(0.01,) * 16,
                post=(0.95,) * 2,
                pre_mean=0.01,
                post_mean=0.95,
                lift=0.94,
                peak=0.95,
                valley=0.01,
            )
        )
        self.assertEqual(result.class_name, "low_confidence")
        self.assertLessEqual(result.confidence, LOW_CONFIDENCE_CUTOFF)

    def test_beat_outside_range_uses_extrapolation(self) -> None:
        grid = [0.0, 500.0, 1000.0, 1500.0]
        energy = [1.0] * 64
        window = energy_window_for_beat(20, grid, energy, total_ms=8_000.0, pre_beats=4, post_beats=4)
        self.assertIsNotNone(window)


if __name__ == "__main__":
    unittest.main()
