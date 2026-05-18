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
    _extract_beatgrid_times,
    _extract_pssi_phrases,
    _extract_smart_drop_energy_shadow,
    _extract_waveform_context,
    _extract_waveform_phrases,
    _extract_waveform,
    _broad_onset_score,
    _distance_penalty,
    _downbeat_alignment,
    _high_mid_pattern_onset,
    _low_mid_pattern_onset,
    _make_multi_feature_scorer,
    _multi_feature_score,
    _onset_score,
    _pattern_onset,
    _post_lift,
    _pre_valley_depth,
    _score_confidence,
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
            schema_version=2,
            sub_bass_envelope=silent + loud,
            kick_envelope=silent + loud,
            low_mid_envelope=silent + loud,
            high_mid_envelope=silent + loud,
            high_band_envelope=silent + loud,
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
            schema_version=2,
            sub_bass_envelope=buildup + drop,
            kick_envelope=buildup + drop,
            low_mid_envelope=buildup + drop,
            high_mid_envelope=inv_buildup + inv_drop,
            high_band_envelope=inv_buildup + inv_drop,
        )

        self.assertGreater(_centroid_drop(16, features), 0.05)
        self.assertGreater(_spectral_flux_onset(16, features), 0.5)
        self.assertEqual(_centroid_drop(2, features), 0.0)
        self.assertAlmostEqual(_spectral_flux_onset(2, features), 0.0, delta=0.1)

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
