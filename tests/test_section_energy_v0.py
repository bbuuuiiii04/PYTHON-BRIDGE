"""Tests for the E2 per-section energy grades (section_energy_v0) and the
flag-off byte-identity kill test on the runtime wiring. Covers gain-invariance,
the store refusal matrix, the product law, the segmentation fallback chain, the
G1/G2 verdict, current_section, the kill test (no computation + no payload key +
no status key when off), and the static import fence.
"""
import ast
import json
import queue
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import section_energy_v0  # noqa: E402
from rb_ss_bridge_v2.section_energy_v0 import (  # noqa: E402
    MIN_SECTION_BEATS,
    current_section,
    gates_verdict,
    grade_sections,
    load_track_weight_store,
    store_track_weight,
)
from rb_ss_bridge_v2 import state_manager as state_manager_mod  # noqa: E402
from rb_ss_bridge_v2.state_manager import _read_runtime_anlz_data, StateManager  # noqa: E402
from rb_ss_bridge_v2.models import Ev  # noqa: E402
from rb_ss_bridge_v2.anlz_reader import TrackAnlzData, WaveformContext  # noqa: E402
from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    SCHEMA_VERSION_V4,
    SpectralFeaturesV4,
    V4_SCALAR_KEYS,
    V4_SERIES_KEYS,
    V4_SUB4_KEYS,
)
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _p95(xs):
    v = sorted(xs)
    if not v:
        return 0.0
    pos = 0.95 * (len(v) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(v) - 1)
    return v[lo] * (1 - (pos - lo)) + v[hi] * (pos - lo)


def _v4(n_beats=64, full=None, ref="auto"):
    z = tuple(0.0 for _ in range(n_beats))
    if full is None:
        # a rising body so the two halves grade differently (real arc)
        full = tuple(-10.0 + 0.20 * i for i in range(n_beats))
    series = {k: z for k in V4_SERIES_KEYS}
    series["full_db"] = tuple(full)
    scalars = {k: 0.5 for k in V4_SCALAR_KEYS}
    if ref == "auto":
        scalars["loudness_ref_db"] = _p95(full)
    elif ref is None:
        del scalars["loudness_ref_db"]
    else:
        scalars["loudness_ref_db"] = ref
    return SpectralFeaturesV4(
        sr=22050, schema_version=SCHEMA_VERSION_V4, n_beats=n_beats,
        duration_s=n_beats * 0.5, frame_hop_s=0.0232,
        sub_bass_envelope=z, kick_envelope=z, low_mid_envelope=z,
        high_mid_envelope=z, high_band_envelope=z, kick_max_envelope=z,
        onset_strength_envelope=z, spectral_flatness_envelope=z,
        series=series,
        sub4={k: tuple((0.0, 0.0, 0.0, 0.0) for _ in range(n_beats))
              for k in V4_SUB4_KEYS},
        growl_band_frames=(0.0, 1.0), scalars=scalars)


def _shifted(v4, delta):
    series = {k: (tuple(x + delta for x in v) if k.endswith("_db") else v)
              for k, v in v4.series.items()}
    scalars = dict(v4.scalars)
    scalars["loudness_ref_db"] = _p95(series["full_db"])
    return replace(v4, series=series, scalars=scalars)


def _store(cache_key="k", tw=0.4, **over):
    d = {"schema_version": 2, "accepted": True,
         "distribution": {"body_duty": [0.1, 0.9]},
         "tracks": {cache_key: {"track_weight": tw}}}
    d.update(over)
    return d


class GainInvarianceTests(unittest.TestCase):
    def test_uniform_shift_within_track_exact(self):
        v4 = _v4()
        base = grade_sections(v4, anlz_drops=[32], anlz_buildups=[0],
                              anlz_breakdowns=[], track_weight=None)
        self.assertTrue(base)
        for d in (6.0, -6.0):
            g = grade_sections(_shifted(v4, d), anlz_drops=[32], anlz_buildups=[0],
                               anlz_breakdowns=[], track_weight=None)
            self.assertEqual(len(g), len(base))
            for a, b in zip(base, g):
                self.assertAlmostEqual(a["within_track"], b["within_track"], places=9)

    def test_per_track_shift_library_scaled_unchanged(self):
        v4 = _v4()
        base = grade_sections(v4, anlz_drops=[32], anlz_buildups=[0],
                              anlz_breakdowns=[], track_weight=0.5)
        shifted = grade_sections(_shifted(v4, 6.0), anlz_drops=[32],
                                 anlz_buildups=[0], anlz_breakdowns=[],
                                 track_weight=0.5)
        for a, b in zip(base, shifted):
            self.assertAlmostEqual(a["library_scaled"], b["library_scaled"], places=9)


class StoreRefusalTests(unittest.TestCase):
    def _write(self, obj):
        d = tempfile.mkdtemp()
        p = Path(d) / "s.json"
        p.write_text(obj if isinstance(obj, str) else json.dumps(obj))
        return p

    def test_missing_path(self):
        self.assertIsNone(load_track_weight_store(Path("/no/such/store.json")))

    def test_unparseable(self):
        self.assertIsNone(load_track_weight_store(self._write("{not json")))

    def test_wrong_version(self):    # a v1 store is refused by the v2 loader
        self.assertIsNone(load_track_weight_store(self._write(_store(schema_version=1))))

    def test_not_accepted(self):
        self.assertIsNone(load_track_weight_store(self._write(_store(accepted=False))))

    def test_tracks_not_dict(self):
        self.assertIsNone(load_track_weight_store(self._write(_store(tracks=[]))))

    def test_wellformed_returns_dict(self):
        self.assertIsInstance(load_track_weight_store(self._write(_store())), dict)

    def test_store_track_weight_absent_key(self):
        self.assertIsNone(store_track_weight(_store(), "missing"))
        self.assertEqual(store_track_weight(_store("k", 0.4), "k"), 0.4)

    def test_v1_store_refused_but_within_track_still_grades(self):
        # EREV1 N6: a refused (v1) store yields no library_scaled, but within_track
        # takes no store input — the section still grades, never an empty list.
        self.assertIsNone(load_track_weight_store(self._write(_store(schema_version=1))))
        g = grade_sections(_v4(), anlz_drops=[32], anlz_buildups=[0],
                           anlz_breakdowns=[], track_weight=None)
        self.assertTrue(g)
        self.assertTrue(all(row["library_scaled"] is None for row in g))


class ProductLawTests(unittest.TestCase):
    def test_product_and_null(self):
        v4 = _v4()
        g = grade_sections(v4, anlz_drops=[32], anlz_buildups=[0],
                           anlz_breakdowns=[], track_weight=0.5)
        for row in g:
            self.assertAlmostEqual(row["library_scaled"],
                                   row["within_track"] * 0.5, places=9)
        g0 = grade_sections(v4, anlz_drops=[32], anlz_buildups=[0],
                            anlz_breakdowns=[], track_weight=None)
        self.assertTrue(all(row["library_scaled"] is None for row in g0))


class SegmentationTests(unittest.TestCase):
    def test_markers_give_labelled_segments(self):
        g = grade_sections(_v4(), anlz_drops=[32], anlz_buildups=[0],
                           anlz_breakdowns=[], track_weight=None)
        labels = {row["label"] for row in g}
        self.assertTrue(labels & {"up", "chorus"})

    def test_no_markers_falls_back_to_section_map(self):
        g = grade_sections(_v4(), anlz_drops=[], anlz_buildups=[],
                           anlz_breakdowns=[], track_weight=None)
        self.assertTrue(g)                      # section_map blocks
        self.assertTrue(all(row["label"] == "other" for row in g))

    def test_missing_ref_and_short_track_empty(self):
        self.assertEqual(grade_sections(_v4(ref=None), anlz_drops=[32],
                                        anlz_buildups=[0], anlz_breakdowns=[],
                                        track_weight=None), [])
        self.assertEqual(grade_sections(_v4(n_beats=0), anlz_drops=[],
                                        anlz_buildups=[], anlz_breakdowns=[],
                                        track_weight=None), [])

    def test_min_section_beats_skip(self):
        # a 2-beat window (< MIN_SECTION_BEATS) between markers is skipped
        g = grade_sections(_v4(n_beats=64), anlz_drops=[2], anlz_buildups=[0],
                           anlz_breakdowns=[], track_weight=None)
        for row in g:
            self.assertGreaterEqual(row["end_beat"] - row["start_beat"],
                                    MIN_SECTION_BEATS)


class SpanAndMedianTests(unittest.TestCase):
    def test_span_maps_and_clips(self):
        # -12 dB -> 0.0, -6 -> 0.5, 0 -> 1.0, and clips outside [-12, 0].
        for rel, want in ((-12.0, 0.0), (-6.0, 0.5), (0.0, 1.0),
                          (5.0, 1.0), (-20.0, 0.0)):
            v4 = _v4(n_beats=64, full=tuple(0.0 for _ in range(64)), ref=-rel)
            g = grade_sections(v4, anlz_drops=[32], anlz_buildups=[0],
                               anlz_breakdowns=[], track_weight=None)
            self.assertTrue(g)
            self.assertAlmostEqual(g[0]["within_track"], want, places=9,
                                   msg="rel=%s" % rel)

    def test_median_aggregator_encodes_e2b(self):
        # A section whose beats are [-3,-3,-3,-100] grades from the MEDIAN (-3 dB ->
        # 1.0), not the mean (-27.25 dB -> 0.0). One silent beat can no longer drag
        # the whole section to zero. This single assertion IS E2-b.
        full = tuple([-3.0, -3.0, -3.0, -100.0] + [-3.0] * 60)
        v4 = _v4(n_beats=64, full=full, ref=-3.0)
        g = grade_sections(v4, anlz_drops=[4], anlz_buildups=[0],
                           anlz_breakdowns=[], track_weight=None)
        first = [s for s in g if s["start_beat"] == 0]
        self.assertTrue(first)
        self.assertAlmostEqual(first[0]["within_track"], 1.0, places=9)


class GatesVerdictTests(unittest.TestCase):
    def test_precedence_every_branch(self):
        # (n_by_genre_eligible, n_graded, railed_fraction, rankable_fraction, sep)
        self.assertEqual(gates_verdict(50, 50, 0.1, 0.95, 0.3),
                         (False, "insufficient_corpus"))
        self.assertEqual(gates_verdict(200, 100, 0.1, 0.95, 0.3),
                         (False, "insufficient_coverage"))
        self.assertEqual(gates_verdict(200, 195, 0.5, 0.95, 0.3),
                         (False, "saturated_grades"))
        self.assertEqual(gates_verdict(200, 195, None, 0.95, 0.3),
                         (False, "saturated_grades"))            # None fails closed
        self.assertEqual(gates_verdict(200, 195, 0.1, 0.5, 0.3),
                         (False, "unrankable_grades"))
        self.assertEqual(gates_verdict(200, 195, 0.1, None, 0.3),
                         (False, "unrankable_grades"))           # None fails closed
        self.assertEqual(gates_verdict(200, 195, 0.1, 0.95, 0.1),
                         (False, "inverted_or_flat_separation"))
        self.assertEqual(gates_verdict(200, 195, 0.1, 0.95, None),
                         (False, "inverted_or_flat_separation"))  # None fails closed
        self.assertEqual(gates_verdict(200, 195, 0.1, 0.95, 0.3), (True, "ok"))


class CurrentSectionTests(unittest.TestCase):
    def test_inside_outside_boundary(self):
        grades = [{"start_beat": 0, "end_beat": 8, "label": "up"},
                  {"start_beat": 8, "end_beat": 16, "label": "chorus"}]
        self.assertEqual(current_section(grades, 4)["label"], "up")
        self.assertEqual(current_section(grades, 8)["label"], "chorus")  # boundary
        self.assertIsNone(current_section(grades, 99))                   # outside


# --- §2/§3 facet publication + slope channel + 3e status-shape projection -------
_FROZEN_STATUS_KEYS = {"start_beat", "end_beat", "label",
                       "within_track", "library_scaled"}
_SEG_VOCAB = {"markers", "section_map"}
_CONTRAST_VOCAB = {"flat", "normal"}


class FacetPublicationTests(unittest.TestCase):
    def _grade(self, v4=None, drops=(32,), ups=(0,), downs=(), tw=None):
        return grade_sections(v4 or _v4(), anlz_drops=list(drops),
                              anlz_buildups=list(ups), anlz_breakdowns=list(downs),
                              track_weight=tw)

    def test_facets_present_and_closed_vocab(self):
        g = self._grade()
        self.assertTrue(g)
        for row in g:
            # segmentation_basis + contrast_class on EVERY grade; slope present on
            # each here (a valid v4 clock: duration_s = n_beats*0.5).
            self.assertIn("segmentation_basis", row)
            self.assertIn("contrast_class", row)
            self.assertIn("slope", row)
            self.assertIn(row["segmentation_basis"], _SEG_VOCAB)
            self.assertIn(row["contrast_class"], _CONTRAST_VOCAB)

    def test_facets_do_not_move_within_or_library(self):
        # additive facets must not perturb the two graded scalars (G3.1 identity)
        g = self._grade(tw=0.5)
        for row in g:
            self.assertTrue(0.0 <= row["within_track"] <= 1.0)
            self.assertAlmostEqual(row["library_scaled"],
                                   row["within_track"] * 0.5, places=12)

    def test_segmentation_basis_markers_vs_section_map(self):
        gm = self._grade(drops=(32,), ups=(0,))
        self.assertTrue(gm and all(r["segmentation_basis"] == "markers" for r in gm))
        gs = grade_sections(_v4(), anlz_drops=[], anlz_buildups=[],
                            anlz_breakdowns=[], track_weight=None)     # no markers
        self.assertTrue(gs and all(r["segmentation_basis"] == "section_map"
                                   for r in gs))

    def test_contrast_class_flat_vs_normal(self):
        # two 32-beat sections at fixed levels -> unclipped rel range = |L1 - L2|.
        flat = _v4(n_beats=64, full=tuple([-3.0] * 32 + [-6.0] * 32), ref=-3.0)
        gflat = self._grade(v4=flat)                       # range 3.0 < 5.0
        self.assertTrue(gflat and all(r["contrast_class"] == "flat" for r in gflat))
        norm = _v4(n_beats=64, full=tuple([-3.0] * 32 + [-10.0] * 32), ref=-3.0)
        gnorm = self._grade(v4=norm)                       # range 7.0 >= 5.0
        self.assertTrue(gnorm and all(r["contrast_class"] == "normal"
                                      for r in gnorm))

    def test_slope_sign_positive_on_rising_section(self):
        # the default _v4 full_db rises monotonically -> t_pos > 0 on graded sections.
        g = self._grade()
        slopes = [r["slope"] for r in g if "slope" in r]
        self.assertTrue(slopes)
        self.assertTrue(all(s >= 0.0 for s in slopes))     # non-negative (t_pos)
        self.assertTrue(any(s > 0.0 for s in slopes))      # a rise reads positive

    def test_trailing_mode_is_structurally_unreachable(self):
        # the in-section slope has no MODE knob; grade_sections can never select the
        # sign-inverting trailing window (structurally excluded, not merely untested).
        import inspect
        params = inspect.signature(section_energy_v0._section_slope).parameters
        self.assertNotIn("mode", params)
        self.assertNotIn("MODE", params)

    def test_slope_absent_without_a_beat_clock(self):
        # duration_s <= 0 or non-finite -> no derivable bpm -> slope ABSENT (never a
        # fabricated 0.0), while within_track / library_scaled are unaffected.
        for dur in (0.0, -1.0, float("nan"), float("inf")):
            v4 = replace(_v4(), duration_s=dur)
            g = self._grade(v4=v4, tw=0.5)
            self.assertTrue(g, "sections still grade without a clock (dur=%s)" % dur)
            self.assertTrue(all("slope" not in r for r in g))
            self.assertTrue(all(r["within_track"] is not None for r in g))
            self.assertTrue(all(r["library_scaled"] is not None for r in g))

    def test_3e_current_section_projects_to_frozen_five_keys(self):
        # grades carry the three facet keys; current_section must strip them so the
        # per-deck status block SHAPE stays frozen (RED against 3b without 3e).
        g = self._grade(tw=0.5)
        self.assertTrue(g and any("slope" in r for r in g))
        proj = current_section(g, g[0]["start_beat"])
        self.assertEqual(set(proj.keys()), _FROZEN_STATUS_KEYS)
        for facet in ("slope", "segmentation_basis", "contrast_class"):
            self.assertNotIn(facet, proj)


def _anlz_fixture(n=80):
    return TrackAnlzData(
        [64], buildup_beat_indices=[0, 32], breakdown_beat_indices=[48],
        waveform_context=WaveformContext(
            heights=tuple([1] * n), ms_per_entry=500.0,
            beatgrid_times_ms=tuple(i * 500.0 for i in range(n))))


class FlagOffKillTests(unittest.TestCase):
    """N1 byte-identity: flag off ⇒ no computation, no payload key, no status key."""

    def test_read_runtime_no_compute_when_off(self):
        calls = {"grade": 0, "store": 0}

        def _grade(*a, **k):
            calls["grade"] += 1
            return [{"x": 1}]

        def _store_once():
            calls["store"] += 1
            return None

        with patch.object(state_manager_mod, "read_anlz_drops",
                          return_value=_anlz_fixture()), \
             patch.object(section_energy_v0, "grade_sections", side_effect=_grade), \
             patch.object(state_manager_mod, "_track_weight_store_once",
                          side_effect=_store_once):
            off = _read_runtime_anlz_data(
                "/tmp/x.DAT", audio_filepath="/tmp/a.wav", spectral_enabled=True,
                section_energy_enabled=False, sidecar_v4=_v4(80))
            self.assertIsNone(off.section_grades)
            self.assertEqual(calls, {"grade": 0, "store": 0})   # zero new work
            on = _read_runtime_anlz_data(
                "/tmp/x.DAT", audio_filepath="/tmp/a.wav", spectral_enabled=True,
                section_energy_enabled=True, sidecar_v4=_v4(80))
            self.assertIsNotNone(on.section_grades)             # gate works both ways
            self.assertGreaterEqual(calls["grade"], 1)

    def test_payload_has_no_section_grades_key_when_off(self):
        for flag, expect_key in ((False, False), (True, True)):
            sm = _make_sm()
            sm._section_energy_enabled = flag
            sm._deck[1].load_gen = 7
            with patch.object(state_manager_mod, "read_anlz_drops",
                              return_value=_anlz_fixture()):
                sm._start_anlz_worker(
                    "/tmp/x.DAT", 1, 7, audio_filepath="/tmp/a.wav",
                    spectral_enabled=True, section_energy_enabled=flag,
                    sidecar_v4=_v4(80))
                ev = _drain_for(sm._eq, Ev.ANLZ_DATA)
            self.assertIsNotNone(ev, "worker emitted no ANLZ_DATA")
            self.assertEqual(("section_grades" in ev.payload), expect_key)

    def test_status_snapshot_has_no_section_energy_key_when_off(self):
        for flag, expect_key in ((False, False), (True, True)):
            sm = _make_sm()
            sm._section_energy_enabled = flag
            sm._deck[1].meta.section_grades = [
                {"start_beat": 0, "end_beat": 8, "label": "up",
                 "within_track": 0.5, "library_scaled": None}]
            sm._deck[1].playing = True
            sm._deck[1].meta.bpm = 120.0
            sm._deck[1].elapsed_ms = 2000
            sm._publish_snapshot()
            deck1 = sm.snapshot()["deck"]["1"]
            self.assertEqual(("section_energy" in deck1), expect_key)
            if expect_key:
                self.assertEqual(deck1["section_energy"]["sections"], 1)


def _make_sm() -> StateManager:
    return StateManager(queue.Queue(maxsize=64), PositionCache(), Mock())


def _drain_for(q, kind, limit=50):
    for _ in range(limit):
        try:
            ev = q.get(timeout=5)
        except queue.Empty:
            return None
        if getattr(ev, "kind", None) == kind:
            return ev
    return None


# --------------------------------------------------------------------------- #
# Import fence (E2REV N2) — only state_manager.py, tools/, tests/ may import it #
# --------------------------------------------------------------------------- #
def _imports_section_energy_v0(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "section_energy_v0" in text
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "section_energy_v0" in node.module:
                return True
            if any("section_energy_v0" in a.name for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any("section_energy_v0" in a.name for a in node.names):
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None)
            if fname in ("import_module", "__import__"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and "section_energy_v0" in arg.value:
                        return True
    return False


class ImportFenceTests(unittest.TestCase):
    SKIP_DIRS = {".git", "graphify-out", "__pycache__", "node_modules", "build",
                 "dist", "local"}
    ALLOW = ("state_manager.py",)   # the ONE runtime importer

    def test_only_allowlisted_import_section_energy_v0(self):
        importers = []
        for path in REPO_ROOT.rglob("*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part in self.SKIP_DIRS or part.startswith(".")
                   for part in rel.split("/")):
                continue
            if rel == "section_energy_v0.py":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _imports_section_energy_v0(text):
                importers.append(rel)
        offenders = [r for r in importers
                     if not (r in self.ALLOW or r.startswith("tools/")
                             or r.startswith("tests/"))]
        self.assertEqual(offenders, [],
                         "section_energy_v0 imported outside allowlist: %s" % offenders)


if __name__ == "__main__":
    unittest.main()
