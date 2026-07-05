import csv
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.anlz_reader import (  # noqa: E402
    _compute_bar_energies,
    TrackAnlzData,
    WaveformContext,
    _calculate_smart_drop_energy_shadow,
    _detect_drop_beats,
    _drum_attack_sustained,
    _drums_dominant_over_tonal,
    _extract_beatgrid_times,
    _extract_pssi_phrases,
    _extract_smart_drop_energy_shadow,
    _extract_waveform_context,
    _extract_waveform_phrases,
    _extract_waveform,
<<<<<<< Updated upstream
    _amplitude_jump_at_c,
    _bass_sustain_1bar,
    _broad_onset_score,
    _buildup_sweep_slope,
    _distance_penalty,
    _downbeat_alignment,
    _high_mid_pattern_onset,
    _kick_max_locked_in,
    _low_mid_pattern_onset,
    _make_multi_feature_scorer,
    _multi_feature_breakdown,
    _multi_feature_score,
    _no_bigger_drop_later,
    _onset_score,
    _pattern_onset,
    _post_drop_energy_stability,
    _post_drop_kick_continuity,
    _post_drop_minus_pre_drop,
    _post_lift,
    _pre_valley_depth,
    _phrase_grid_alignment,
    _score_confidence,
    _silence_frame_pre,
=======
    _broad_onset_score,
    _distance_penalty,
    _downbeat_alignment,
    _make_multi_feature_scorer,
    _multi_feature_score,
    _onset_score,
    _post_lift,
    _pre_valley_depth,
    _score_confidence,
>>>>>>> Stashed changes
    _v1_compute_shadows,
    read_anlz_drops,
)
from rb_ss_bridge_v2.audio_spectral_features import SpectralFeatures  # noqa: E402


class FakeEntry:
    def __init__(self, kind, beat):
        self.kind = kind
        self.beat = beat


class FakeTag:
    def __init__(self, entries=None, times_s=None):
        self.content = SimpleNamespace(entries=entries, mood=1) if entries is not None else None
        self._times_s = times_s or []

    def get_times(self):
        return self._times_s


class FakeAnlz:
    def __init__(self, tags):
        self._tags = tags

    def getall_tags(self, tag_type):
        return self._tags.get(tag_type, [])


def _beatgrid_ms(num_beats: int, beat_ms: float = 500.0) -> list[float]:
    return [i * beat_ms for i in range(num_beats)]


def _bar_heights(bars: list[int], entries_per_bar: int = 4) -> list[int]:
    heights: list[int] = []
    for energy in bars:
        heights.extend([energy] * entries_per_bar)
    return heights


def _beat_heights(values: dict[int, int], total_beats: int = 120, default: int = 10) -> list[int]:
    return [values.get(beat, default) for beat in range(total_beats)]


<<<<<<< Updated upstream
def _spectral_features(
    values,
    kick=None,
    high_mid=None,
    high_band=None,
    sub_bass=None,
    kick_max=None,
    onset=None,
    flatness=None,
) -> SpectralFeatures:
    series = tuple(float(value) for value in values)
    kick_series = tuple(float(value) for value in (kick if kick is not None else values))
    high_mid_series = tuple(float(value) for value in (high_mid if high_mid is not None else values))
    high_band_series = tuple(float(value) for value in (high_band if high_band is not None else values))
    sub_bass_series = tuple(float(value) for value in (sub_bass if sub_bass is not None else values))
    kick_max_series = tuple(
        float(value) for value in (kick_max if kick_max is not None else kick_series)
    )
    onset_series = tuple(float(value) for value in (onset if onset is not None else values))
    flatness_series = tuple(float(value) for value in (flatness if flatness is not None else values))
    return SpectralFeatures(
        sr=22050,
        schema_version=3,
        sub_bass_envelope=sub_bass_series,
        kick_envelope=kick_series,
        low_mid_envelope=series,
        high_mid_envelope=high_mid_series,
        high_band_envelope=high_band_series,
        kick_max_envelope=kick_max_series,
        onset_strength_envelope=onset_series,
        spectral_flatness_envelope=flatness_series,
    )


_POST_DROP_FEATURE_NAMES = (
    "silence_frame_pre",
    "buildup_sweep_slope",
    "amplitude_jump_at_c",
    "bass_sustain_1bar",
    "drum_attack_sustained",
    "kick_max_locked_in",
    "drums_dominant_over_tonal",
    "phrase_grid_alignment",
    "post_drop_kick_continuity",
    "post_drop_energy_stability",
    "post_drop_minus_pre_drop",
    "no_bigger_drop_later",
)


=======
>>>>>>> Stashed changes
def _shadow_v1_fields(shadow):
    return (
        shadow.anlz_beat,
        shadow.suggested_beat,
        shadow.anlz_elapsed_ms,
        shadow.suggested_elapsed_ms,
        shadow.lift_at_anlz,
        shadow.lift_at_suggested,
        shadow.confidence,
    )




def _detect_drop_beats_helper(heights, waveform_duration_ms, beatgrid_times_ms):
    energies = _compute_bar_energies(heights, waveform_duration_ms, beatgrid_times_ms)
    track_max = float(max(energies)) if energies else 0.0
    return _detect_drop_beats(energies, track_max)

class AnlzDropDetectTests(unittest.TestCase):
    def test_no_drops_flat_energy(self) -> None:
        bars = [20] * 40
        drops = _detect_drop_beats_helper(
            _bar_heights(bars),
            waveform_duration_ms=40 * 4 * 500,
            beatgrid_times_ms=_beatgrid_ms(41 * 4),
        )
        self.assertEqual(drops, [])

    def test_single_drop_detected(self) -> None:
        bars = [25] * 8 + [4] * 8 + [26] * 24
        drops = _detect_drop_beats_helper(
            _bar_heights(bars),
            waveform_duration_ms=40 * 4 * 500,
            beatgrid_times_ms=_beatgrid_ms(41 * 4),
        )
        self.assertEqual(drops, [64])

    def test_three_bar_pre_drop_valley_detected(self) -> None:
        bars = [25] * 12 + [1, 1, 4] + [26] * 25
        drops = _detect_drop_beats_helper(
            _bar_heights(bars),
            waveform_duration_ms=40 * 4 * 500,
            beatgrid_times_ms=_beatgrid_ms(41 * 4),
        )
        self.assertEqual(drops, [60])

    def test_intro_filtered(self) -> None:
        bars = [25] + [4] * 4 + [26] * 35
        drops = _detect_drop_beats_helper(
            _bar_heights(bars),
            waveform_duration_ms=40 * 4 * 500,
            beatgrid_times_ms=_beatgrid_ms(41 * 4),
        )
        self.assertEqual(drops, [])

    def test_outro_filtered(self) -> None:
        bars = [25] * 31 + [4] * 4 + [26] * 5
        drops = _detect_drop_beats_helper(
            _bar_heights(bars),
            waveform_duration_ms=40 * 4 * 500,
            beatgrid_times_ms=_beatgrid_ms(41 * 4),
        )
        self.assertEqual(drops, [])

    def test_first_outro_bar_boundary_filtered(self) -> None:
        bars = [25] * 29 + [4] * 3 + [26] * 8
        drops = _detect_drop_beats_helper(
            _bar_heights(bars),
            waveform_duration_ms=40 * 4 * 500,
            beatgrid_times_ms=_beatgrid_ms(41 * 4),
        )
        self.assertEqual(drops, [])

    def test_cooldown_deduplication(self) -> None:
        bars = [25] * 8 + [4] * 8 + [26] * 8 + [4] * 4 + [27] * 32
        drops = _detect_drop_beats_helper(
            _bar_heights(bars),
            waveform_duration_ms=len(bars) * 4 * 500,
            beatgrid_times_ms=_beatgrid_ms((len(bars) + 1) * 4),
        )
        self.assertEqual(drops, [64])

    def test_medium_buildup_after_breakdown_is_not_drop(self) -> None:
        bars = [25] * 8 + [4] * 4 + [12, 14, 16, 18, 19, 20] + [27] * 22
        drops = _detect_drop_beats_helper(
            _bar_heights(bars),
            waveform_duration_ms=len(bars) * 4 * 500,
            beatgrid_times_ms=_beatgrid_ms((len(bars) + 1) * 4),
        )
        self.assertEqual(drops, [])

    def test_buildup_hit_shifts_to_following_drop(self) -> None:
        bars = [25] * 20 + [1, 0, 6, 8, 9, 10, 6, 8, 9, 10, 10]
        bars += [26, 23, 26, 28, 25] + [1, 2, 6] + [28, 28, 26, 27] + [28] * 12
        drops = _detect_drop_beats_helper(
            _bar_heights(bars),
            waveform_duration_ms=len(bars) * 4 * 500,
            beatgrid_times_ms=_beatgrid_ms((len(bars) + 1) * 4),
        )
        self.assertEqual(drops, [156])

    def test_missing_file_returns_empty(self) -> None:
        result = read_anlz_drops("/tmp/does-not-exist/ANLZ0000.DAT")
        self.assertEqual(result, TrackAnlzData([]))


class SmartDropEnergyShadowTests(unittest.TestCase):
    def test_shadow_keeps_anlz_when_anlz_has_strongest_lift(self) -> None:
        heights = _beat_heights(
            {
                **{beat: 2 for beat in range(48, 64)},
                **{beat: 20 for beat in range(64, 88)},
            }
        )
        shadows = _calculate_smart_drop_energy_shadow(
            heights,
            waveform_duration_ms=len(heights) * 500,
            beatgrid_times_ms=_beatgrid_ms(len(heights) + 1),
            selected_drops=[64],
        )
        self.assertEqual(len(shadows), 1)
        self.assertEqual(shadows[0].anlz_beat, 64)
        self.assertEqual(shadows[0].suggested_beat, 64)
        self.assertGreater(shadows[0].lift_at_anlz, 0.0)
        self.assertEqual(shadows[0].confidence, 0.0)

    def test_shadow_can_suggest_eight_beats_later_without_moving_runtime(self) -> None:
        heights = _beat_heights(
            {
                **{beat: 20 for beat in range(48, 64)},
                **{beat: 2 for beat in range(64, 72)},
                **{beat: 30 for beat in range(72, 96)},
            }
        )
        shadows = _calculate_smart_drop_energy_shadow(
            heights,
            waveform_duration_ms=len(heights) * 500,
            beatgrid_times_ms=_beatgrid_ms(len(heights) + 1),
            selected_drops=[64],
        )
        self.assertEqual(len(shadows), 1)
        self.assertEqual(shadows[0].anlz_beat, 64)
        self.assertEqual(shadows[0].suggested_beat, 72)
        self.assertGreater(shadows[0].lift_at_suggested, shadows[0].lift_at_anlz)
        self.assertGreater(shadows[0].confidence, 0.0)

    def test_shadow_returns_empty_without_waveform_or_sufficient_grid(self) -> None:
        self.assertEqual(
            _calculate_smart_drop_energy_shadow(
                [],
                waveform_duration_ms=0,
                beatgrid_times_ms=_beatgrid_ms(120),
                selected_drops=[64],
            ),
            [],
        )
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PWV3": [FakeTag([10] * 120)],
                "PQT2": [FakeTag(times_s=[i * 0.5 for i in range(7)])],
            })),
        ]
        self.assertEqual(_extract_smart_drop_energy_shadow(parsed, [64]), [])

    def test_v1_behavior_preserved_when_scorer_kwarg_omitted(self) -> None:
        heights = _beat_heights(
            {
                **{beat: 20 for beat in range(48, 64)},
                **{beat: 2 for beat in range(64, 72)},
                **{beat: 30 for beat in range(72, 96)},
            }
        )
        beatgrid = _beatgrid_ms(len(heights) + 1)
        waveform_duration_ms = len(heights) * 500

        default = _calculate_smart_drop_energy_shadow(
            heights,
            waveform_duration_ms=waveform_duration_ms,
            beatgrid_times_ms=beatgrid,
            selected_drops=[64],
        )
        legacy = _v1_compute_shadows(
            heights,
            ms_per_entry=500.0,
            beatgrid_times_ms=beatgrid,
            selected_drops=[64],
        )

        self.assertEqual(len(default), 1)
        self.assertEqual([_shadow_v1_fields(item) for item in default],
                         [_shadow_v1_fields(item) for item in legacy])
        self.assertEqual(default[0].suggested_beat, 72)
        self.assertEqual(default[0].source, "v1")

<<<<<<< Updated upstream
    def test_wide_window_scores_seventeen_candidates_when_enabled(self) -> None:
        def scorer(beat, _heights, _beatgrid, _anlz_beat, _spectral):
            return float(beat)

        default = _calculate_smart_drop_energy_shadow(
            [1] * 20,
            waveform_duration_ms=10_000,
            beatgrid_times_ms=_beatgrid_ms(20),
            selected_drops=[0],
            scorer=scorer,
        )
        wide = _calculate_smart_drop_energy_shadow(
            [1] * 20,
            waveform_duration_ms=10_000,
            beatgrid_times_ms=_beatgrid_ms(20),
            selected_drops=[0],
            scorer=scorer,
            wide_window=True,
        )

        self.assertEqual(default[0].suggested_beat, 8)
        self.assertEqual(wide[0].suggested_beat, 16)

=======
>>>>>>> Stashed changes
    def test_onset_score_uses_max_single_beat_jump_in_post_window(self) -> None:
        self.assertEqual(
            _onset_score(0, [1, 1, 4, 10, 10, 10], _beatgrid_ms(6)),
            6,
        )

    def test_broad_onset_score_uses_two_beat_jump(self) -> None:
        self.assertEqual(
            _broad_onset_score(0, [1, 1, 5, 5, 5], _beatgrid_ms(5)),
            4,
        )

    def test_post_lift_matches_current_energy_lift_signal(self) -> None:
        heights = _beat_heights(
            {
                **{beat: 2 for beat in range(4, 20)},
                **{beat: 20 for beat in range(20, 36)},
            },
            total_beats=48,
        )
        self.assertGreater(_post_lift(20, heights, _beatgrid_ms(49)), 0.0)

    def test_pre_valley_depth_detects_quiet_section_before_drop(self) -> None:
        heights = _beat_heights(
            {
                **{beat: 20 for beat in range(0, 16)},
                **{beat: 2 for beat in range(16, 20)},
            },
            total_beats=33,
        )
        self.assertEqual(_pre_valley_depth(20, heights, _beatgrid_ms(33)), 18)

    def test_downbeat_alignment_scores_bar_and_half_bar_positions(self) -> None:
        self.assertEqual(_downbeat_alignment(64), 1.0)
        self.assertEqual(_downbeat_alignment(66), 0.5)
        self.assertEqual(_downbeat_alignment(67), 0.0)

    def test_distance_penalty_falls_off_from_anlz_beat(self) -> None:
        self.assertEqual(_distance_penalty(64, 64), 1.0)
        self.assertEqual(_distance_penalty(68, 64), 0.5)
        self.assertEqual(_distance_penalty(72, 64), 0.0)

<<<<<<< Updated upstream
    def test_distance_penalty_rescales_for_wide_window(self) -> None:
        self.assertEqual(_distance_penalty(72, 64, wide_window=True), 0.5)
        self.assertEqual(_distance_penalty(80, 64, wide_window=True), 0.0)

    def test_pattern_onset_discriminates_adjacent_beats(self) -> None:
        envelope = [0.0] * 16 + [1.0] * 16
        before, onset, after = [_pattern_onset(beat, envelope, window=8) for beat in (15, 16, 17)]

        self.assertGreater(onset, before)
        self.assertGreater(onset, after * 0.95)
        self.assertGreater(abs(onset - before), 0.05)

    def test_low_mid_and_high_mid_pattern_onsets_detect_transitions(self) -> None:
        silent, loud = (0.0,) * 16, (1.0,) * 16
        features = SpectralFeatures(
            sr=22050,
            schema_version=3,
            sub_bass_envelope=silent + loud,
            kick_envelope=silent + loud,
            low_mid_envelope=silent + loud,
            high_mid_envelope=silent + loud,
            high_band_envelope=silent + loud,
            kick_max_envelope=silent + loud,
            onset_strength_envelope=silent + loud,
            spectral_flatness_envelope=silent + loud,
        )

        self.assertGreater(_low_mid_pattern_onset(16, features), 0.5)
        self.assertGreater(_high_mid_pattern_onset(16, features), 0.5)
        self.assertLess(_low_mid_pattern_onset(2, features), 0.1)
        self.assertLess(_high_mid_pattern_onset(2, features), 0.1)

    def test_centroid_drop_and_flux_detect_synthetic_drop(self) -> None:
        from rb_ss_bridge_v2.anlz_reader import _centroid_drop, _spectral_flux_onset
        buildup, drop = (0.1,) * 16, (1.0,) * 16
        inv_buildup, inv_drop = (1.0,) * 16, (0.2,) * 16
        features = SpectralFeatures(
            sr=22050,
            schema_version=3,
            sub_bass_envelope=buildup + drop,
            kick_envelope=buildup + drop,
            low_mid_envelope=buildup + drop,
            high_mid_envelope=inv_buildup + inv_drop,
            high_band_envelope=inv_buildup + inv_drop,
            kick_max_envelope=buildup + drop,
            onset_strength_envelope=buildup + drop,
            spectral_flatness_envelope=buildup + drop,
        )

        self.assertGreater(_centroid_drop(16, features), 0.05)
        self.assertGreater(_spectral_flux_onset(16, features), 0.5)
        self.assertEqual(_centroid_drop(2, features), 0.0)
        self.assertAlmostEqual(_spectral_flux_onset(2, features), 0.0, delta=0.1)

    def test_silence_frame_pre_detects_kick_sub_gap(self) -> None:
        values = [1.0] * 40
        values[30:32] = [0.05, 0.05]

        self.assertGreater(_silence_frame_pre(32, _spectral_features(values)), 0.8)
        self.assertAlmostEqual(_silence_frame_pre(32, _spectral_features([1.0] * 40)), 0.0)

    def test_buildup_sweep_slope_detects_high_band_rise(self) -> None:
        rising = [0.0] * 40
        rising[8:32] = [0.0] * 8 + [0.5] * 8 + [1.0] * 8
        flat = [0.5] * 40

        self.assertGreater(_buildup_sweep_slope(32, _spectral_features(rising)), 0.8)
        self.assertAlmostEqual(_buildup_sweep_slope(32, _spectral_features(flat)), 0.0)

    def test_buildup_sweep_slope_uses_high_band_not_sub_bass(self) -> None:
        flat = [0.5] * 40
        rising = [0.0] * 8 + [0.0] * 8 + [0.5] * 8 + [1.0] * 8 + [0.0] * 8
        features = _spectral_features(flat, high_mid=rising, high_band=rising)
        self.assertGreater(_buildup_sweep_slope(32, features), 0.5)

    def test_amplitude_jump_at_c_detects_silence_to_slam(self) -> None:
        jump = [0.2] * 40
        jump[30:32] = [0.05, 0.05]
        jump[32:34] = [1.0, 1.0]
        flat = [0.5] * 40

        self.assertGreater(_amplitude_jump_at_c(32, _spectral_features(jump)), 0.9)
        self.assertAlmostEqual(_amplitude_jump_at_c(32, _spectral_features(flat)), 0.1, delta=0.01)

    def test_bass_sustain_1bar_sustained_drop_scores_high(self) -> None:
        sub = [0.1] * 100 + [0.9] * 50
        self.assertGreater(
            _bass_sustain_1bar(100, _spectral_features(sub, sub_bass=sub)),
            0.95,
        )

    def test_bass_sustain_1bar_fake_drop_scores_low(self) -> None:
        sub = [0.1] * 100 + [0.2] * 4 + [0.9] * 8 + [0.0] * 40
        self.assertLess(
            _bass_sustain_1bar(100, _spectral_features(sub, sub_bass=sub)),
            0.5,
        )

    def test_bass_sustain_1bar_none_spectral(self) -> None:
        self.assertEqual(_bass_sustain_1bar(100, None), 0.5)

    def test_bass_sustain_1bar_window_overrun(self) -> None:
        sub = [0.5] * 105
        self.assertEqual(
            _bass_sustain_1bar(100, _spectral_features(sub, sub_bass=sub)),
            0.5,
        )

    def test_drum_attack_sustained_scores_sustained_onsets_high(self) -> None:
        base = [0.1] * 100 + [0.9] * 50

        self.assertGreater(
            _drum_attack_sustained(100, _spectral_features(base, onset=base)),
            0.9,
        )

    def test_drum_attack_sustained_scores_brief_spike_low(self) -> None:
        onset = [0.0] * 100 + [0.9] + [0.0] * 49

        self.assertLess(
            _drum_attack_sustained(100, _spectral_features(onset, onset=onset)),
            0.5,
        )

    def test_drum_attack_sustained_ignores_global_outlier(self) -> None:
        onset = [0.1] * 100 + [0.7] * 8 + [0.1] * 40 + [10.0]

        self.assertGreater(
            _drum_attack_sustained(100, _spectral_features(onset, onset=onset)),
            0.9,
        )

    def test_kick_max_locked_in_scores_sustained_transients_high(self) -> None:
        kick_max = [0.1] * 100 + [0.9] * 50

        self.assertGreater(
            _kick_max_locked_in(100, _spectral_features(kick_max, kick_max=kick_max)),
            0.9,
        )

    def test_kick_max_locked_in_scores_brief_transient_low(self) -> None:
        kick_max = [0.0] * 100 + [0.9] + [0.0] * 49

        self.assertLess(
            _kick_max_locked_in(100, _spectral_features(kick_max, kick_max=kick_max)),
            0.5,
        )

    def test_kick_max_locked_in_ignores_global_outlier(self) -> None:
        kick_max = [0.1] * 100 + [0.7] * 8 + [0.1] * 40 + [10.0]

        self.assertGreater(
            _kick_max_locked_in(100, _spectral_features(kick_max, kick_max=kick_max)),
            0.9,
        )

    def test_drums_dominant_over_tonal_uses_flatness_window(self) -> None:
        noisy = [0.1] * 100 + [0.8] * 8 + [0.1] * 8
        tonal = [0.1] * 116

        self.assertGreater(
            _drums_dominant_over_tonal(100, _spectral_features(noisy, flatness=noisy)),
            0.7,
        )
        self.assertLess(
            _drums_dominant_over_tonal(100, _spectral_features(tonal, flatness=tonal)),
            0.2,
        )

    def test_richer_spectral_features_return_neutral_without_payload(self) -> None:
        self.assertEqual(_drum_attack_sustained(100, None), 0.5)
        self.assertEqual(_kick_max_locked_in(100, None), 0.5)
        self.assertEqual(_drums_dominant_over_tonal(100, None), 0.5)

    def test_phrase_grid_alignment_uses_soft_32_and_16_beat_grid(self) -> None:
        self.assertEqual(_phrase_grid_alignment(64, [32]), 1.0)
        self.assertEqual(_phrase_grid_alignment(66, [32]), 0.5)
        self.assertEqual(_phrase_grid_alignment(69, [32]), 0.0)
        self.assertEqual(_phrase_grid_alignment(80, [32]), 0.5)
        self.assertEqual(_phrase_grid_alignment(64, []), 0.0)

    def test_phrase_grid_alignment_picks_best_anchor_when_multiple(self) -> None:
        # Beat 64 is +32 from anchor 32 (exact, score 1.0) and +52 from anchor 12 (score 0.0).
        # max() should pick 1.0.
        self.assertEqual(_phrase_grid_alignment(64, [12, 32]), 1.0)

        # Beat 48 is +16 from anchor 32 (score 0.5) and +36 from anchor 12 (score 0.0).
        # max() should pick 0.5.
        self.assertEqual(_phrase_grid_alignment(48, [12, 32]), 0.5)

        # All anchors equally bad -> 0.0.
        self.assertEqual(_phrase_grid_alignment(21, [12, 32]), 0.0)

    def test_phase_1a_features_are_scoring_gated_until_wide_or_phrases(self) -> None:
        values = [1.0] * 80
        values[30:32] = [0.05, 0.05]
        features = _spectral_features(values)
        weights = {"silence_frame_pre": 1.0, "phrase_grid_alignment": 1.0}

        self.assertEqual(
            _multi_feature_score(32, [1] * 80, _beatgrid_ms(80), 32, features, weights),
            0.0,
        )
        self.assertGreater(
            _multi_feature_score(
                32,
                [1] * 80,
                _beatgrid_ms(80),
                32,
                features,
                weights,
                wide_window=True,
            ),
            0.8,
        )
        self.assertGreater(
            _multi_feature_score(
                64,
                [1] * 80,
                _beatgrid_ms(80),
                64,
                features,
                weights,
                phrases=[32],
            ),
            0.9,
        )

    def test_post_drop_kick_continuity_distinguishes_sustained_from_collapsed(self) -> None:
        base = [0.1] * 40
        sustained, collapsed = base.copy(), base.copy()
        for index in range(17, 33):
            sustained[index] = 1.0
        for index in range(17, 21):
            collapsed[index] = 1.0

        self.assertGreater(
            _post_drop_kick_continuity(16, _spectral_features(base, kick=sustained)),
            0.5,
        )
        self.assertLess(
            _post_drop_kick_continuity(16, _spectral_features(base, kick=collapsed)),
            0.3,
        )

    def test_post_drop_energy_stability_high_for_steady_groove(self) -> None:
        steady, spiky = [0.1] * 40, [0.1] * 40
        steady[17:33] = [1.0] * 16
        spiky[17:33] = [0.0 if index % 2 else 2.0 for index in range(16)]

        self.assertGreater(_post_drop_energy_stability(16, _spectral_features(steady)), 0.8)
        self.assertLess(_post_drop_energy_stability(16, _spectral_features(spiky)), 0.3)

    def test_post_drop_minus_pre_drop_positive_when_energy_lifts(self) -> None:
        lifted, same, falling = [0.1] * 40, [0.4] * 40, [1.0] * 40
        lifted[17:33] = [1.0] * 16
        falling[17:33] = [0.2] * 16

        self.assertGreater(_post_drop_minus_pre_drop(16, _spectral_features(lifted)), 0.5)
        self.assertAlmostEqual(_post_drop_minus_pre_drop(16, _spectral_features(same)), 0.0)
        self.assertEqual(_post_drop_minus_pre_drop(16, _spectral_features(falling)), 0.0)

    def test_no_bigger_drop_later_detects_fake_drop(self) -> None:
        fake, winner, short = [0.0] * 81, [0.0] * 81, [0.0] * 49
        fake[17:49], fake[49:81] = [1.0] * 32, [2.0] * 32
        winner[17:49] = [1.0] * 32
        short[17:49] = [1.0] * 32

        self.assertLess(_no_bigger_drop_later(16, _spectral_features(fake)), 0.5)
        self.assertGreater(_no_bigger_drop_later(16, _spectral_features(winner)), 0.5)
        self.assertEqual(_no_bigger_drop_later(16, _spectral_features(short)), 0.5)

    def test_multi_feature_breakdown_includes_new_features(self) -> None:
        breakdown = _multi_feature_breakdown(0, [1, 1, 1], _beatgrid_ms(3), 0, None)

        for name in _POST_DROP_FEATURE_NAMES:
            self.assertIn(name, breakdown)
            self.assertEqual(breakdown[name], 0.0)

    def test_multi_feature_breakdown_with_spectral_returns_finite_values(self) -> None:
        values = [0.1] * 80
        values[17:33] = [1.0] * 16
        breakdown = _multi_feature_breakdown(
            16,
            [1] * 80,
            _beatgrid_ms(80),
            16,
            _spectral_features(values),
        )

        for name in _POST_DROP_FEATURE_NAMES:
            self.assertIsInstance(breakdown[name], float)
            self.assertTrue(math.isfinite(breakdown[name]))

=======
>>>>>>> Stashed changes
    def test_multi_feature_score_uses_known_feature_values(self) -> None:
        score = _multi_feature_score(
            0,
            [1, 1, 4, 10, 10, 10],
            _beatgrid_ms(6),
            0,
            None,
            {
                "onset_score": 1.0,
                "distance_penalty": 2.0,
            },
        )
        self.assertEqual(score, 8.0)

    def test_make_multi_feature_scorer_applies_trained_weights_on_tiny_dataset(self) -> None:
        scorer = _make_multi_feature_scorer({
            "onset_score": 1.0,
            "downbeat_alignment": 0.25,
        })
        beatgrid = _beatgrid_ms(6)
        heights = [1, 1, 4, 10, 10, 10]

        self.assertGreater(
            scorer(0, heights, beatgrid, 0, None),
            scorer(1, heights, beatgrid, 0, None),
        )

<<<<<<< Updated upstream
    def test_v2_telemetry_appends_csv_when_enabled(self) -> None:
        scorer = _make_multi_feature_scorer({"onset_score": 1.0})
        beatgrid = _beatgrid_ms(12)
        heights = [1, 1, 4, 10, 10, 10, 10, 10, 10, 10, 10, 10]

        with tempfile.TemporaryDirectory() as td:
            telemetry_path = Path(td) / "smart_drop.csv"
            with patch.dict(os.environ, {"RBSS_SMART_DROP_TELEMETRY_CSV": str(telemetry_path)}):
                shadows = _calculate_smart_drop_energy_shadow(
                    heights,
                    waveform_duration_ms=len(heights) * 500,
                    beatgrid_times_ms=beatgrid,
                    selected_drops=[0],
                    scorer=scorer,
                )

            rows = list(csv.DictReader(telemetry_path.open(encoding="utf-8")))

        self.assertEqual(len(shadows), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["schema"], "1")
        self.assertEqual(rows[0]["source"], "v2_waveform")
        self.assertEqual(int(rows[0]["anlz_beat"]), shadows[0].anlz_beat)
        self.assertEqual(int(rows[0]["suggested_beat"]), shadows[0].suggested_beat)
        self.assertEqual(rows[0]["correct_beat"], "")
        candidates = json.loads(rows[0]["top_candidates_json"])
        self.assertEqual(candidates[0]["beat"], shadows[0].suggested_beat)
        self.assertIn("onset_score", json.loads(rows[0]["feature_breakdown_json"]))

=======
>>>>>>> Stashed changes
    def test_score_confidence_uses_best_second_best_margin(self) -> None:
        self.assertAlmostEqual(_score_confidence(10.0, 7.0), 0.3)
        self.assertEqual(_score_confidence(0.0, 0.0), 0.0)
        self.assertEqual(_score_confidence(1.0, 3.0), 0.0)


class AnlzExtractionTests(unittest.TestCase):
    def test_pssi_kind5_returns_bridge_beats_minus_one(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([FakeEntry(5, 161), FakeEntry(5, 417)])],
            })),
        ]
        self.assertEqual(_extract_pssi_phrases(parsed)[1], [160, 416])

    def test_pssi_mood1_extracts_breakdowns_and_buildups(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([
                    FakeEntry(5, 161),
                    FakeEntry(3, 65),
                    FakeEntry(2, 97),
                ])],
            })),
        ]

        mood, drops, breakdowns, buildups = _extract_pssi_phrases(parsed)

        self.assertEqual(mood, 1)
        self.assertEqual(drops, [160])
        self.assertEqual(breakdowns, [64])
        self.assertEqual(buildups, [96])

    def test_pssi_mood23_extracts_confirmed_buildups_breakdowns_and_drops(self) -> None:
        tag = FakeTag([
            FakeEntry(4, 65),
            FakeEntry(5, 81),
            FakeEntry(8, 97),
            FakeEntry(9, 129),
            FakeEntry(10, 161),
        ])
        tag.content.mood = 2
        parsed = [(Path("ANLZ0000.EXT"), FakeAnlz({"PSSI": [tag]}))]

        mood, drops, breakdowns, buildups = _extract_pssi_phrases(parsed)

        self.assertEqual(mood, 2)
        self.assertEqual(drops, [128])
        self.assertEqual(breakdowns, [96])
        self.assertEqual(buildups, [64, 80])

    def test_pssi_ignores_non_drop_kinds(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([FakeEntry(4, 161), FakeEntry(6, 417)])],
            })),
        ]
        self.assertEqual(_extract_pssi_phrases(parsed)[1], [])

    def test_pssi_sorts_and_dedupes(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([FakeEntry(5, 417), FakeEntry(5, 161), FakeEntry(5, 161)])],
            })),
        ]
        self.assertEqual(_extract_pssi_phrases(parsed)[1], [160, 416])

    def test_pssi_primary_skips_waveform_fallback_when_present(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([FakeEntry(5, 257), FakeEntry(5, 513)])],
                "PWV3": [FakeTag([31] * 400)],
                "PQT2": [FakeTag(times_s=[i * 0.5 for i in range(200)])],
            })),
        ]
        pssi_drops = _extract_pssi_phrases(parsed)[1]
        self.assertEqual(pssi_drops, [256, 512])
        self.assertNotEqual(_extract_waveform_phrases(parsed)[0], pssi_drops)

    def test_pssi_empty_falls_back_to_waveform(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([])],
                "PWV3": [FakeTag(_bar_heights([25] * 8 + [4] * 8 + [26] * 24))],
                "PQT2": [FakeTag(times_s=[i * 0.5 for i in range(41 * 4)])],
            })),
        ]
        self.assertEqual(_extract_pssi_phrases(parsed)[1], [])
        self.assertEqual(_extract_waveform_phrases(parsed)[0], [64])

    def test_validated_a2_pssi_fixture(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([FakeEntry(5, 257), FakeEntry(5, 513)])],
            })),
        ]
        self.assertEqual(_extract_pssi_phrases(parsed)[1], [256, 512])

    def test_candidate_ordering_prefers_ext_pssi(self) -> None:
        parsed = [
            (Path("ANLZ0000.DAT"), FakeAnlz({
                "PSSI": [FakeTag([FakeEntry(5, 129)])],
            })),
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([FakeEntry(5, 257)])],
            })),
        ]
        self.assertEqual(_extract_pssi_phrases(parsed)[1], [256])

    def test_validated_chiken_soup_pssi_fixture(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([FakeEntry(5, 161), FakeEntry(5, 417)])],
            })),
        ]
        self.assertEqual(_extract_pssi_phrases(parsed)[1], [160, 416])

    def test_validated_blaame_pssi_fixture(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PSSI": [FakeTag([FakeEntry(5, 193), FakeEntry(5, 481)])],
            })),
        ]
        self.assertEqual(_extract_pssi_phrases(parsed)[1], [192, 480])

    def test_waveform_accessor_content_entries(self) -> None:
        parsed = [(Path("ANLZ0000.EXT"), FakeAnlz({"PWV3": [FakeTag([224, 162, 31])] }))]
        waveform = _extract_waveform(parsed)
        self.assertIsNotNone(waveform)
        self.assertEqual(waveform[0], [0, 2, 31])
        self.assertEqual(waveform[1], "PWV3")

    def test_2ex_without_pwv3_falls_through_to_ext(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            two = Path(td) / "ANLZ0000.2EX"
            ext = Path(td) / "ANLZ0000.EXT"
            dat = Path(td) / "ANLZ0000.DAT"
            two.touch()
            ext.touch()
            dat.touch()

            def parse_file(path):
                suffix = Path(path).suffix
                if suffix == ".2EX":
                    return FakeAnlz({"PWV7": [FakeTag([1, 2, 3])]})
                if suffix == ".EXT":
                    return FakeAnlz({
                        "PWV3": [FakeTag([31] * 200)],
                        "PQT2": [FakeTag(times_s=[0.0, 60.0])],
                    })
                return FakeAnlz({"PQTZ": [FakeTag(times_s=[i * 0.5 for i in range(80)])]})

            with patch("pyrekordbox.anlz.AnlzFile.parse_file", side_effect=parse_file):
                result = read_anlz_drops(str(dat))

        self.assertEqual(result.drop_beat_indices, [])
        self.assertIsNotNone(result.waveform_context)

    def test_waveform_context_populated_when_waveform_and_beatgrid_present(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PWV3": [FakeTag([32, 33, 63, 5])],
                "PQT2": [FakeTag(times_s=[i * 0.5 for i in range(8)])],
            })),
        ]

        context = _extract_waveform_context(parsed)

        self.assertEqual(
            context,
            WaveformContext(
                heights=(0, 1, 31, 5),
                ms_per_entry=1000.0,
                beatgrid_times_ms=tuple(i * 500.0 for i in range(8)),
            ),
        )

    def test_waveform_context_is_none_without_waveform(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({
                "PQT2": [FakeTag(times_s=[i * 0.5 for i in range(8)])],
            })),
        ]

        self.assertIsNone(_extract_waveform_context(parsed))

    def test_read_anlz_drops_returns_waveform_context_with_pssi_result(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dat = Path(td) / "ANLZ0000.DAT"
            dat.touch()

            def parse_file(path):
                return FakeAnlz({
                    "PSSI": [FakeTag([FakeEntry(5, 9)])],
                    "PWV3": [FakeTag([10] * 16)],
                    "PQT2": [FakeTag(times_s=[i * 0.5 for i in range(16)])],
                })

            with patch("pyrekordbox.anlz.AnlzFile.parse_file", side_effect=parse_file):
                result = read_anlz_drops(str(dat))

        self.assertEqual(result.drop_beat_indices, [8])
        self.assertIsNotNone(result.waveform_context)
        self.assertEqual(result.waveform_context.heights, (10,) * 16)

    def test_candidate_ordering_ext_before_dat_for_waveform(self) -> None:
        parsed = [
            (Path("ANLZ0000.DAT"), FakeAnlz({"PWAV": [FakeTag([1] * 400)]})),
            (Path("ANLZ0000.EXT"), FakeAnlz({"PWV3": [FakeTag([31] * 1000)]})),
        ]
        waveform = _extract_waveform(parsed)
        self.assertIsNotNone(waveform)
        self.assertEqual(waveform[1], "PWV3")
        self.assertEqual(len(waveform[0]), 1000)

    def test_pqt2_sparse_falls_through_to_pqtz(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({"PQT2": [FakeTag(times_s=[0.049, 288.823])]})),
            (Path("ANLZ0000.DAT"), FakeAnlz({"PQTZ": [FakeTag(times_s=[i * 0.5 for i in range(16)])]})),
        ]
        self.assertEqual(_extract_beatgrid_times(parsed), [i * 500.0 for i in range(16)])

    def test_implausible_beatgrid_rejected(self) -> None:
        parsed = [
            (Path("ANLZ0000.EXT"), FakeAnlz({"PQT2": [FakeTag(times_s=[0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07])]})),
        ]
        self.assertEqual(_extract_beatgrid_times(parsed), [])

    def test_pyrekordbox_not_installed(self) -> None:
        with patch.dict(sys.modules, {"pyrekordbox.anlz": None}):
            result = read_anlz_drops("/tmp/does-not-exist/ANLZ0000.DAT")
        self.assertEqual(result, TrackAnlzData([]))

    def test_all_failures_return_dataclass_not_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dat = Path(td) / "ANLZ0000.DAT"
            dat.touch()
            with patch("pyrekordbox.anlz.AnlzFile.parse_file", side_effect=RuntimeError("boom")):
                result = read_anlz_drops(str(dat))
        self.assertIsInstance(result, TrackAnlzData)
        self.assertEqual(result.drop_beat_indices, [])


if __name__ == "__main__":
    unittest.main()
