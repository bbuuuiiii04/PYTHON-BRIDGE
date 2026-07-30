"""Tests for the E3 per-drop energy grades (drop_energy_v0) + the drop-path
wiring: gain-invariance, product law, window edges, plan attach, the four-surface
flag-off kill test, the E2xE3 four-flag matrix (no cross-flag coupling), the
gates verdict, and the static import fence.
"""
import ast
import queue
import random
import sys
import tokenize
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import drop_energy_v0  # noqa: E402
from rb_ss_bridge_v2 import section_energy_v0  # noqa: E402
from rb_ss_bridge_v2.drop_energy_v0 import (  # noqa: E402
    MIN_WINDOW_BEATS, DROP_WINDOW_BEATS, grade_drops, grades_by_beat,
    gates_verdict, drop_body_levels, score_windows, _percentile)
from rb_ss_bridge_v2.track_weight_v0 import spearman  # noqa: E402
from rb_ss_bridge_v2 import state_manager as state_manager_mod  # noqa: E402
from rb_ss_bridge_v2.state_manager import _read_runtime_anlz_data, StateManager  # noqa: E402
from rb_ss_bridge_v2.models import Ev  # noqa: E402
from rb_ss_bridge_v2.anlz_reader import TrackAnlzData, WaveformContext  # noqa: E402
from rb_ss_bridge_v2.drop_presentation import (  # noqa: E402
    DropDecision, plan_track, DropPresentationConfig)
from rb_ss_bridge_v2.smart_phrasing import PhraseSegment  # noqa: E402
from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    SCHEMA_VERSION_V4, SpectralFeaturesV4, V4_SCALAR_KEYS, V4_SERIES_KEYS,
    V4_SUB4_KEYS)
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _p95(xs):
    v = sorted(xs)
    if not v:
        return 0.0
    pos = 0.95 * (len(v) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(v) - 1)
    return v[lo] * (1 - (pos - lo)) + v[hi] * (pos - lo)


def _v4(n_beats=80, full=None, flux=None, perc=None, growl=None, ref="auto"):
    z = tuple(0.0 for _ in range(n_beats))
    if full is None:
        full = tuple(-2.0 + 0.05 * i for i in range(n_beats))   # near-ceiling body
    if flux is None:
        flux = tuple(2.0 for _ in range(n_beats))               # fluxsum p90 > 0
    if perc is None:
        perc = tuple(0.3 + 0.002 * i for i in range(n_beats))   # non-degenerate p90
    if growl is None:
        growl = tuple(0.2 + 0.001 * i for i in range(n_beats))
    series = {k: z for k in V4_SERIES_KEYS}
    series.update({"full_db": tuple(full),
                   "fluxsum_midhigh": tuple(flux),
                   "perc_high": tuple(perc), "growl_flatness": tuple(growl)})
    scalars = {k: 0.5 for k in V4_SCALAR_KEYS}      # growl_timbre_p90 = 0.5 (>0)
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


class GainInvarianceTests(unittest.TestCase):
    def test_uniform_shift_within_exact(self):
        v4 = _v4()
        base = grade_drops(v4, drop_beats=[16, 40], track_weight=None)
        self.assertTrue(base)
        for d in (6.0, -6.0):
            g = grade_drops(_shifted(v4, d), drop_beats=[16, 40], track_weight=None)
            for a, b in zip(base, g):
                self.assertAlmostEqual(a["within_track"], b["within_track"], places=9)

    def test_per_track_shift_library_scaled_unchanged(self):
        v4 = _v4()
        base = grade_drops(v4, drop_beats=[16, 40], track_weight=0.5)
        sh = grade_drops(_shifted(v4, 6.0), drop_beats=[16, 40], track_weight=0.5)
        self.assertAlmostEqual(base[0]["library_scaled"], sh[0]["library_scaled"], places=9)


class ProductAndWindowTests(unittest.TestCase):
    def test_product_law_and_null(self):
        g = grade_drops(_v4(), drop_beats=[16, 40], track_weight=0.5)
        for row in g:
            self.assertAlmostEqual(row["library_scaled"], row["within_track"] * 0.5, places=9)
        g0 = grade_drops(_v4(), drop_beats=[16, 40], track_weight=None)
        self.assertTrue(all(row["library_scaled"] is None for row in g0))

    def test_drop_body_levels_window(self):
        v4 = _v4(n_beats=80)
        self.assertEqual(len(drop_body_levels(v4, [16, 40])), 2)
        self.assertEqual(drop_body_levels(v4, [75]), [])            # coverage < 8
        self.assertEqual(len(drop_body_levels(v4, [80 - MIN_WINDOW_BEATS])), 1)  # == 8
        self.assertEqual(drop_body_levels(_v4(ref=None), [16]), [])  # absent ref
        bad = list(-2.0 + 0.05 * i for i in range(80))
        bad[18] = float("nan")
        self.assertEqual(drop_body_levels(_v4(full=bad), [16]), [])  # non-finite window

    def test_facet_publication_terms_on_grade_dict(self):
        # §2 (Task 3a): every E3 grade dict PUBLISHES the four term values beside
        # within_track/library_scaled/coverage/body_basis, and within_track is still
        # exactly their mean (identity preserved — the facets are additive).
        g = grade_drops(_v4(), drop_beats=[16, 40], track_weight=0.5)
        self.assertTrue(g)
        for row in g:
            for k in ("body", "activity", "perc_high", "growl"):
                self.assertIn(k, row)
            self.assertAlmostEqual(
                row["within_track"],
                (row["body"] + row["activity"] + row["perc_high"] + row["growl"])
                / 4.0, places=12)
            self.assertNotIn("onset", row)     # the retired v1 key never returns

    def test_body_basis_selection(self):
        v4 = _v4()
        g = grade_drops(v4, drop_beats=[16, 40], track_weight=None)
        self.assertTrue(g and all(x["body_basis"] == "track_drops" for x in g))
        g1 = grade_drops(v4, drop_beats=[16], track_weight=None,
                         corpus_drop_levels=[-2.0, -1.0, 0.0, 1.0])
        self.assertEqual([x["body_basis"] for x in g1], ["corpus"])
        self.assertEqual(grade_drops(v4, drop_beats=[16], track_weight=None), [])

    def test_two_drop_granularity_and_ties(self):
        # 2 drops at DIFFERENT levels -> body in {0.25, 0.75}
        v4 = _v4()
        pool = drop_body_levels(v4, [16, 40])
        terms = score_windows(v4, [16, 40], body_pool=pool)
        self.assertEqual(sorted(t["body"] for t in terms), [0.25, 0.75])
        # 2 drops at the SAME level -> both 0.5 (mid-rank tie)
        vf = _v4(full=tuple(-3.0 for _ in range(80)))
        tf = score_windows(vf, [16, 40], body_pool=drop_body_levels(vf, [16, 40]))
        self.assertTrue(all(abs(t["body"] - 0.5) < 1e-9 for t in tf))

    def test_four_terms_or_omit(self):
        base = grade_drops(_v4(), drop_beats=[16, 40], track_weight=None)
        self.assertEqual(len(base), 2)
        # R4: the SECOND required normaliser is the in-module fluxsum p90 (onset_mh_p90
        # retired). Absent / <= 0 / non-finite fluxsum omits the drop.
        # fluxsum p90 <= 0 (all-zero flux series)
        self.assertEqual(grade_drops(_v4(flux=tuple(0.0 for _ in range(80))),
                                     drop_beats=[16, 40], track_weight=None), [])
        # fluxsum series non-finite
        nanflux = [2.0] * 80
        nanflux[18] = float("nan")
        self.assertEqual(grade_drops(_v4(flux=tuple(nanflux)),
                                     drop_beats=[16, 40], track_weight=None), [])
        # fluxsum series absent
        va = _v4(); sa = dict(va.series); del sa["fluxsum_midhigh"]
        self.assertEqual(grade_drops(replace(va, series=sa), drop_beats=[16, 40],
                                     track_weight=None), [])
        # growl_timbre_p90 non-finite
        vg = _v4()
        sc = dict(vg.scalars); sc["growl_timbre_p90"] = float("nan")
        self.assertEqual(grade_drops(replace(vg, scalars=sc), drop_beats=[16, 40],
                                     track_weight=None), [])
        # perc_high p90 <= 0 (all-zero series)
        self.assertEqual(grade_drops(_v4(perc=tuple(0.0 for _ in range(80))),
                                     drop_beats=[16, 40], track_weight=None), [])
        # body basis absent (1 own drop, no corpus)
        self.assertEqual(grade_drops(_v4(), drop_beats=[16], track_weight=None), [])
        # renamed term: the key is 'activity' (not 'onset') and within_track is the
        # mean over EXACTLY the four terms body/activity/perc_high/growl.
        pool = drop_body_levels(_v4(), [16, 40])
        for row in score_windows(_v4(), [16, 40], body_pool=pool):
            self.assertIn("activity", row)
            self.assertNotIn("onset", row)
            self.assertAlmostEqual(
                row["within_track"],
                (row["body"] + row["activity"] + row["perc_high"] + row["growl"]) / 4.0,
                places=12)

    def test_perc_high_only_variation_still_differs(self):
        # drops identical in level/onset/growl, differing ONLY in perc_high: v1's
        # level+sub+onset composite tied them; v2 must separate them. THE reason
        # this revision exists.
        n = 80
        perc = [0.1] * n
        for i in range(40, 56):
            perc[i] = 0.9
        v4 = _v4(n_beats=n, full=tuple(-3.0 for _ in range(n)),
                 flux=tuple(2.0 for _ in range(n)),
                 growl=tuple(0.2 for _ in range(n)), perc=tuple(perc))
        g = grade_drops(v4, drop_beats=[0, 40], track_weight=None)
        self.assertEqual(len(g), 2)
        self.assertNotAlmostEqual(g[0]["within_track"], g[1]["within_track"])

    def test_missing_ref_empty(self):
        self.assertEqual(grade_drops(_v4(ref=None), drop_beats=[16], track_weight=None), [])


def _cfg():
    return DropPresentationConfig()


class PlanAttachTests(unittest.TestCase):
    def _roles(self):
        return [PhraseSegment(start_beat=0.0, end_beat=32.0, label="up")]

    def test_matched_unmatched_and_flag_off(self):
        grades = grade_drops(_v4(), drop_beats=[16, 40], track_weight=0.5)
        mapping = grades_by_beat(grades)
        plan = plan_track([16.0, 40.0, 200.0], self._roles(), [], [], _cfg(),
                          drop_grades=mapping)
        by_beat = {int(d.beat): d for d in plan.decisions}
        self.assertIsNotNone(by_beat[16].energy_grade)               # matched
        self.assertEqual(by_beat[16].energy_grade["drop_beat"], 16)
        self.assertIsNone(by_beat[200].energy_grade)                 # unmatched
        # flag off ⇒ no kwarg ⇒ all None (byte-identical call shape)
        plan_off = plan_track([16.0], self._roles(), [], [], _cfg())
        self.assertIsNone(plan_off.decisions[0].energy_grade)

    def test_equality_and_repr(self):
        a = DropDecision(beat=1.0, tagged=False, learned=False, is_finale=True,
                         personality_presentation="leds_only", runway=8.0)
        b = DropDecision(beat=1.0, tagged=False, learned=False, is_finale=True,
                         personality_presentation="leds_only", runway=8.0)
        self.assertEqual(a, b)                                       # both None
        self.assertIn("energy_grade=None", repr(a))
        c = DropDecision(beat=1.0, tagged=False, learned=False, is_finale=True,
                         personality_presentation="leds_only", runway=8.0,
                         energy_grade={"within_track": 0.9})
        self.assertNotEqual(a, c)


def _anlz_fixture(n=80):
    return TrackAnlzData(
        [16, 40], buildup_beat_indices=[0], breakdown_beat_indices=[56],
        waveform_context=WaveformContext(
            heights=tuple([1] * n), ms_per_entry=500.0,
            beatgrid_times_ms=tuple(i * 500.0 for i in range(n))))


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


class KillTests(unittest.TestCase):
    def test_four_surfaces_flag_off(self):
        calls = {"grade": 0}

        def _grade(*a, **k):
            calls["grade"] += 1
            return [{"drop_beat": 16, "within_track": 0.9, "library_scaled": None,
                     "coverage": 16}]

        # surface 1: no compute when off; compute when on
        with patch.object(state_manager_mod, "read_anlz_drops", return_value=_anlz_fixture()), \
             patch.object(drop_energy_v0, "grade_drops", side_effect=_grade):
            off = _read_runtime_anlz_data("/tmp/x.DAT", audio_filepath="/tmp/a.wav",
                                          spectral_enabled=True,
                                          drop_energy_enabled=False, sidecar_v4=_v4())
            self.assertIsNone(off.drop_grades)
            self.assertEqual(calls["grade"], 0)
            on = _read_runtime_anlz_data("/tmp/x.DAT", audio_filepath="/tmp/a.wav",
                                         spectral_enabled=True,
                                         drop_energy_enabled=True, sidecar_v4=_v4())
            self.assertIsNotNone(on.drop_grades)
            self.assertGreaterEqual(calls["grade"], 1)

    def test_payload_key_surface(self):
        for flag, want in ((False, False), (True, True)):
            sm = _make_sm()
            sm._drop_energy_enabled = flag
            sm._deck[1].load_gen = 7
            with patch.object(state_manager_mod, "read_anlz_drops", return_value=_anlz_fixture()):
                sm._start_anlz_worker("/tmp/x.DAT", 1, 7, audio_filepath="/tmp/a.wav",
                                      spectral_enabled=True, drop_energy_enabled=flag,
                                      sidecar_v4=_v4())
                ev = _drain_for(sm._eq, Ev.ANLZ_DATA)
            self.assertIsNotNone(ev)
            self.assertEqual(("drop_grades" in ev.payload), want)

    def test_status_key_surface(self):
        for flag, want in ((False, False), (True, True)):
            sm = _make_sm()
            sm._drop_energy_enabled = flag
            dec = DropDecision(beat=16.0, tagged=False, learned=False, is_finale=True,
                               personality_presentation="leds_only", runway=8.0,
                               energy_grade={"within_track": 0.9, "library_scaled": None})
            sm._drop_presentation_plan = plan_track(
                [16.0], [PhraseSegment(start_beat=0.0, end_beat=32.0, label="up")],
                [], [], _cfg(),
                drop_grades={16: {"drop_beat": 16, "within_track": 0.9, "library_scaled": None}})
            sm._drop_presentation_plan_deck = 1
            sm._publish_snapshot()
            deck1 = sm.snapshot()["deck"]["1"]
            self.assertEqual(("drop_energy" in deck1), want)
            if want:
                self.assertEqual(deck1["drop_energy"]["drops"], 1)


class FourFlagMatrixTests(unittest.TestCase):
    """E2 x E3 independence (Part C): each flag drives only its own surface."""

    def test_matrix(self):
        for se, de in ((False, False), (True, False), (False, True), (True, True)):
            data = _read_runtime_anlz_data(
                "/tmp/x.DAT", audio_filepath="/tmp/a.wav", spectral_enabled=True,
                section_energy_enabled=se, drop_energy_enabled=de,
                sidecar_v4=_v4())
            self.assertEqual(data.section_grades is not None, se, (se, de, "E2"))
            self.assertEqual(data.drop_grades is not None, de, (se, de, "E3"))

    def setUp(self):
        # fresh TrackAnlzData per call — the worker MUTATES it, so a shared object
        # would leak one combo's grades into the next.
        self._p = patch.object(state_manager_mod, "read_anlz_drops",
                               side_effect=lambda *a, **k: _anlz_fixture())
        self._p.start()

    def tearDown(self):
        self._p.stop()


class GatesVerdictTests(unittest.TestCase):
    def test_precedence_every_branch(self):
        # (n_elig, n_graded, term_railed_max, term_rho_max, iqr, rankable,
        #  level_sep_db, grade_sep). A clean-pass baseline:
        ok = (200, 195, 0.05, 0.24, 0.14, 0.99, 6.5, 0.19)
        self.assertEqual(gates_verdict(*ok), (True, "ok"))
        self.assertEqual(gates_verdict(50, *ok[1:]), (False, "insufficient_corpus"))
        self.assertEqual(gates_verdict(200, 100, *ok[2:]), (False, "insufficient_coverage"))
        self.assertEqual(gates_verdict(200, 195, 0.5, *ok[3:]), (False, "saturated_term"))
        self.assertEqual(gates_verdict(200, 195, None, *ok[3:]), (False, "saturated_term"))
        self.assertEqual(gates_verdict(200, 195, 0.05, 0.7, *ok[4:]), (False, "redundant_terms"))
        self.assertEqual(gates_verdict(200, 195, 0.05, None, *ok[4:]), (False, "redundant_terms"))
        self.assertEqual(gates_verdict(200, 195, 0.05, 0.24, 0.02, *ok[5:]),
                         (False, "degenerate_distribution"))
        self.assertEqual(gates_verdict(200, 195, 0.05, 0.24, None, *ok[5:]),
                         (False, "degenerate_distribution"))
        self.assertEqual(gates_verdict(200, 195, 0.05, 0.24, 0.14, 0.5, 6.5, 0.19),
                         (False, "unrankable_grades"))
        self.assertEqual(gates_verdict(200, 195, 0.05, 0.24, 0.14, None, 6.5, 0.19),
                         (False, "unrankable_grades"))
        self.assertEqual(gates_verdict(200, 195, 0.05, 0.24, 0.14, 0.99, 1.0, 0.19),
                         (False, "inverted_level_separation"))
        self.assertEqual(gates_verdict(200, 195, 0.05, 0.24, 0.14, 0.99, None, 0.19),
                         (False, "inverted_level_separation"))
        self.assertEqual(gates_verdict(200, 195, 0.05, 0.24, 0.14, 0.99, 6.5, 0.05),
                         (False, "inverted_or_flat_grade_separation"))
        self.assertEqual(gates_verdict(200, 195, 0.05, 0.24, 0.14, 0.99, 6.5, None),
                         (False, "inverted_or_flat_grade_separation"))

    def test_random_composite_rejected_by_g7(self):
        # EREV1 F3: a pure RNG passed all six of the first draft's E3 gates because
        # none read the grade. G7 reads the grade. An all-random four-term composite
        # must be REJECTED, and the reason must be G7 specifically — this is the
        # test that proves the E3 gate set is no longer noise-passable.
        rng = random.Random(20260724)
        terms = {k: [rng.random() for _ in range(2000)]
                 for k in ("body", "activity", "perc", "growl")}
        drops = [sum(terms[k][i] for k in terms) / 4.0 for i in range(2000)]
        lows = [rng.random() for _ in range(600)]

        def railed(vs):
            return sum(1 for v in vs if v <= 0.0 or v >= 1.0) / len(vs)

        term_railed_max = max(railed(terms[k]) for k in terms)
        keys = list(terms)
        term_rho_max = max(
            abs(spearman(terms[a], terms[b]))
            for i, a in enumerate(keys) for b in keys[i + 1:])
        ds = sorted(drops)
        iqr = _percentile(ds, 75) - _percentile(ds, 25)
        grade_sep = _percentile(ds, 50) - _percentile(sorted(lows), 50)
        # earlier gates all PASS; only G7 (grade separation) is meant to trip:
        self.assertLessEqual(term_railed_max, drop_energy_v0.TERM_SATURATION_MAX)
        self.assertLessEqual(term_rho_max, drop_energy_v0.TERM_CORRELATION_MAX)
        self.assertGreaterEqual(iqr, drop_energy_v0.IQR_GATE)
        self.assertLess(abs(grade_sep), drop_energy_v0.GRADE_SEPARATION_GATE)
        verdict = gates_verdict(2000, 2000, term_railed_max, term_rho_max, iqr,
                                1.0, 6.5, grade_sep)
        self.assertEqual(verdict, (False, "inverted_or_flat_grade_separation"))


def _imports_drop_energy_v0(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "drop_energy_v0" in text
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "drop_energy_v0" in node.module:
                return True
            if any("drop_energy_v0" in a.name for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any("drop_energy_v0" in a.name for a in node.names):
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None)
            if fname in ("import_module", "__import__"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and "drop_energy_v0" in arg.value:
                        return True
    return False


class ImportFenceTests(unittest.TestCase):
    SKIP_DIRS = {".git", "graphify-out", "__pycache__", "node_modules", "build",
                 "dist", "local"}
    ALLOW = ("state_manager.py",)

    def test_only_allowlisted_import_drop_energy_v0(self):
        importers = []
        for path in REPO_ROOT.rglob("*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part in self.SKIP_DIRS or part.startswith(".")
                   for part in rel.split("/")):
                continue
            if rel == "drop_energy_v0.py":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _imports_drop_energy_v0(text):
                importers.append(rel)
        offenders = [r for r in importers
                     if not (r in self.ALLOW or r.startswith("tools/")
                             or r.startswith("tests/"))]
        self.assertEqual(offenders, [],
                         "drop_energy_v0 imported outside allowlist: %s" % offenders)


# --------------------------------------------------------------------------- #
# §4 pool-selection law — the DENY-BY-DEFAULT grade-key lexicon tripwire       #
# (AWR-291 Task 5c; law text in the ladder §B.0 / AMENDMENT-3 clause 3b)       #
# --------------------------------------------------------------------------- #
class GradeLexiconFenceTests(unittest.TestCase):
    """Stage-1 tripwire for the pool-selection law: *energy grades select pools and pick
    within pools; they NEVER scale a level.*

    Built DENY-BY-DEFAULT, in the same style as the import fence above: it WALKS
    `REPO_ROOT.rglob("*.py")` and fails on any file mentioning a grade CARRIER
    identifier outside an explicit allowlist. Because it is a walk and not a fixed
    target list, `led_dispatch_coordinator.py`, `beat_sync_engine.py`, `osl_output.py`,
    `soundswitch_*.py`, `streamdeck/` and every FUTURE module are covered by default —
    which is the whole point: silent consumer growth becomes loud.

    **What this is, at its true strength.** It is a COARSE TRIPWIRE, not the law's real
    enforcement. It cannot tell a lawful pool selection from an unlawful level mapping;
    it only says "a non-allowlisted module now mentions a grade carrier". The test that
    actually enforces the law — grade identifiers never an argument to a level-lexicon
    parameter — is the E4-stage assertion, out of scope this round, landing with E4's own
    spec (which adds the cast resolver to the allowlist).

    **What it does NOT cover, said out loud.** The identifier set is CLOSED to the six
    CARRIER names. The seven grade-VALUE keys the facet round publishes — `body`,
    `activity`, `perc_high`, `growl` (E3) and `slope`, `segmentation_basis`,
    `contrast_class` (E2) — are deliberately NOT in it, so a module that receives a grade
    dict and reads `["slope"]` trips nothing here. That is by design (the lexicon is
    design-fixed by AMENDMENT-3 clause 3b), not an oversight, and not a licence to widen
    it in this round: facet reads are governed by the E4-stage assertion, where reading a
    facet is the thing under governance. (`section_energy_v0`'s own
    `SlopeConsumerFenceTests` separately forbids a production read of an individual
    `slope` value, with its own four disclosed blind spots.)
    """

    # PINNED VERBATIM from ImportFenceTests above (and identical to
    # tests/test_section_energy_v0.py). This set is the line that decides green-vs-red:
    # measured at this desk, the scan returns 0 offenders WITH it and 35 WITHOUT the
    # `local/` skip (research and sealed-package copies). That count DRIFTS with what
    # sits under local/ (the spec measured 33, an earlier review 23) — which is exactly
    # why the PINNED thing is the skip set and never a fixed offender or allowlist list.
    # A seat that omits it gets a fence RED on arrival and is pushed toward widening the
    # ALLOWLIST with dozens of fictional "reasons", permanently narrowing the fence.
    # PINNED as an EXACT SET, and governed as the THIRD exclusion surface
    # (EBUILD5REV2 finding 1). A skipped directory excludes EVERYTHING beneath it from
    # the walk — a broader exemption than either an exact file or a prefix — and it was
    # the one surface `_governance_violations()` never saw: the reviewer added
    # `future_consumer` to this set, put `brightness = grade["within_track"] * 255`
    # under it, and governance, the carrier scan and the pinned-skip test all stayed
    # green. The set is pinned as a whole rather than made reason-bearing per member,
    # because that is how the spec defines it — copied VERBATIM from the sibling fence
    # (`ImportFenceTests` above; identical in tests/test_section_energy_v0.py), with one
    # documented rationale for the set rather than seven: measured at this desk, the scan
    # returns 0 offenders WITH it and 35 WITHOUT the `local/` skip, and that count drifts
    # with whatever sits under local/ (the spec measured 33, an earlier review 23).
    PINNED_SKIP_DIRS = frozenset({".git", "graphify-out", "__pycache__", "node_modules",
                                  "build", "dist", "local"})
    SKIP_DIRS = set(PINNED_SKIP_DIRS)

    # The CARRIER identifiers — closed set, design-fixed (AMENDMENT-3 clause 3b).
    GRADE_IDENTIFIERS = ("within_track", "library_scaled", "track_weight",
                         "drop_grades", "section_grades", "energy_grade")

    # Every entry carries its STATED REASON, because each addition NARROWS the fence.
    # An entry added without a reason is a review-blocking defect in that change.
    ALLOW = {
        "track_weight_v0.py": "E1 grade module — computes the weight",
        "section_energy_v0.py": "E2 grade module — computes the section grades",
        "drop_energy_v0.py": "E3 grade module — computes the drop grades",
        "state_manager.py": "the ONE runtime owner: computes on the ANLZ worker and "
                            "attaches; the only authorized wiring",
        "models.py": "DEFINES the DeckState fields that CARRY the grades (declared and "
                     "reset in clear()); never consumes them",
        "anlz_reader.py": "the ANLZ payload dataclass fields carrying E2/E3 grades; "
                          "never consumes them",
        "drop_presentation.py": "the DropDecision.energy_grade slot/ctor/repr and the "
                                "plan-builder attach; never consumes it",
    }
    # PREFIX exemptions are held in a REASON-BEARING mapping, exactly like the
    # exact-file allowlist above, and are governed by the SAME two tests
    # (EBUILD5REV finding 1). They were a bare tuple, outside both governance tests and
    # trusted wholesale by the scan — so a future unreasoned prefix could hide a whole
    # directory's carrier mentions while both governance tests stayed green. A prefix
    # exempts far MORE than a single file, so it needs at least as much justification.
    ALLOW_PREFIXES = {
        "tools/": "offline tooling lane — computes, reports and verifies the grades; "
                  "zero runtime importers, so no live path is exempted here",
        "tests/": "the tests that verify the grades and enforce these fences; test code "
                  "must mention the carriers to assert on them",
    }

    def _scan(self, skip_dirs=None, allow=None, prefixes=None):
        """The tripwire itself, parameterised ONLY so the tests below can prove it
        discriminates. Production behaviour always uses the pinned defaults."""
        skip_dirs = self.SKIP_DIRS if skip_dirs is None else skip_dirs
        allow = self.ALLOW if allow is None else allow
        prefixes = self.ALLOW_PREFIXES if prefixes is None else prefixes
        prefix_tuple = tuple(prefixes)
        offenders = []
        for path in sorted(REPO_ROOT.rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part in skip_dirs or part.startswith(".")
                   for part in rel.split("/")):
                continue
            if rel in allow or (prefix_tuple and rel.startswith(prefix_tuple)):
                continue
            # READ FAILURE FAILS CLOSED (fence-scope adjudication Ruling A). This used
            # to `continue` on OSError/UnicodeDecodeError — i.e. inability to inspect was
            # treated as permission, and a VALID Python module with a
            # `# -*- coding: latin-1 -*-` cookie (importable, executing the forbidden
            # grade->brightness expression) became invisible inside the stated walk.
            # `tokenize.open()` honors coding cookies, so such a file is now SCANNED
            # rather than skipped; anything still unreadable is REPORTED as a violation
            # naming the file, never silently passed.
            try:
                with tokenize.open(path) as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
                offenders.append((rel, ["<unreadable: %s: %s>"
                                        % (type(exc).__name__, exc)]))
                continue
            hits = sorted(k for k in self.GRADE_IDENTIFIERS if k in text)
            if hits:
                offenders.append((rel, hits))
        return offenders

    def test_no_unallowlisted_module_mentions_a_grade_carrier(self):
        offenders = self._scan()
        self.assertEqual(
            offenders, [],
            "POOL-SELECTION LAW tripwire: non-allowlisted module(s) now mention grade "
            "carrier identifiers: %s. Energy grades select pools and pick within pools; "
            "they NEVER scale a level — no grade value may be multiplied into, added to, "
            "or mapped onto any brightness/intensity/dimmer/floor/level parameter, at "
            "any layer, on any path. If this is a lawful new consumer, it needs an "
            "allowlist entry WITH a stated reason (and, for a real consumer, its own "
            "spec); if it maps a grade onto a level, it is invalid by construction, not "
            "a tuning choice." % offenders)

    MIN_REASON_CHARS = 15

    @classmethod
    def _governance_violations(cls, allow=None, prefixes=None, skip_dirs=None):
        """Every governance problem across the THREE NAMED GOVERNANCE SURFACES, as
        `[(kind, entry, problem), …]`. Empty list == those three surfaces are governed.

        **Scope, not completeness (fence-scope adjudication Ruling C).** Earlier versions
        of this docstring claimed "three ways to hide a module … and all three are checked
        here". That was FALSE and the claim is banned: EBUILD5REV3 executed four further
        pre-inspection exits (a latin-1-cookie module, a dot-hidden path, a symlinked
        directory, a `.pyw`). What this helper governs is exactly the three surfaces a
        seat can WIDEN by editing this class — nothing more:
          1. `ALLOW` — an exact-file exemption; must carry a stated reason and exist;
          2. `ALLOW_PREFIXES` — a prefix exemption, hiding a whole subtree; same rules;
          3. `SKIP_DIRS` — a skipped directory, hiding everything beneath it ANYWHERE in
             the walk. Governed as an EXACT SET against `PINNED_SKIP_DIRS`: any added or
             missing member is a violation, because the spec pins this set verbatim and
             it is the line that decides green-vs-red for the whole scan.

        **The instrumented scope of the scan itself** (r8 spec fence clause, as corrected
        under Ruling B): UTF-8/`tokenize`-readable `*.py` files reachable by the stated
        walk from the repo root — dot-prefixed components and the pinned skip dirs
        excluded, directory symlinks not descended — with a read/decode failure REPORTED
        as a violation. FOUR blind categories are disclosed and each is ASSERTED BLIND by
        a test above: dot-hidden paths, directory symlinks, non-`*.py` extensions, and
        dynamically generated source. **The §4 pool-selection LAW binds everywhere,
        including inside those four**; the instrument simply cannot see them. A green
        fence proves no carrier mention exists IN THE INSTRUMENTED SCOPE — never that no
        consumer exists anywhere.

        Parameterised so the CAN-FAIL tests can run the REAL governance logic against a
        planted surface — the check and the thing checked are the same code, so a green
        production result cannot come from a governance path that is never exercised.
        That property is what these cures keep re-learning: each round's hole was a
        surface the helper did not receive.
        """
        allow = cls.ALLOW if allow is None else allow
        prefixes = cls.ALLOW_PREFIXES if prefixes is None else prefixes
        skip_dirs = cls.SKIP_DIRS if skip_dirs is None else skip_dirs
        bad = []
        # --- surface 3: the skipped-directory set, pinned exactly --------------------
        try:
            given = set(skip_dirs)
        except TypeError:
            given = None
            bad.append(("skip-dir", repr(skip_dirs),
                        "skip dirs must be a set of directory names"))
        if given is not None:
            for extra in sorted(given - set(cls.PINNED_SKIP_DIRS)):
                bad.append(("skip-dir", extra,
                            "NOT in the pinned skip set — a skipped directory hides "
                            "every file beneath it from the carrier scan; adding one is "
                            "the broadest exemption available and is not permitted "
                            "without a spec amendment"))
            for missing in sorted(set(cls.PINNED_SKIP_DIRS) - given):
                bad.append(("skip-dir", missing,
                            "MISSING from the pinned skip set — removing a pin changes "
                            "what the fence measures (the 0-vs-35 result depends on it)"))
        # a bare sequence of prefixes is itself the defect this cure removes
        if not isinstance(prefixes, dict):
            bad.append(("prefix", repr(prefixes),
                        "prefix exemptions must be a reason-bearing mapping, not a bare "
                        "%s — a bare sequence cannot carry the required reasons"
                        % type(prefixes).__name__))
            return bad
        for kind, mapping in (("file", allow), ("prefix", prefixes)):
            for entry, reason in mapping.items():
                if not isinstance(reason, str) or not reason.strip():
                    bad.append((kind, entry, "no stated reason"))
                elif len(reason.strip()) < cls.MIN_REASON_CHARS:
                    bad.append((kind, entry, "reason too thin to be a real reason"))
                target = REPO_ROOT / entry
                if kind == "file" and not target.is_file():
                    bad.append((kind, entry, "names a missing file (stale exemption)"))
                if kind == "prefix" and not target.is_dir():
                    bad.append((kind, entry,
                                "names a missing directory (stale exemption)"))
        return bad

    def test_every_exemption_has_a_stated_reason_and_exists(self):
        """The rule the spec makes enforceable, over the three NAMED GOVERNANCE SURFACES
        (not a completeness claim — see the helper's scope statement): exact-file and
        prefix exemptions must each state why they exist and still point at something
        real (a stale exemption silently widens the blind area), and the skipped-directory
        set must match its pin exactly (a skipped directory hides everything beneath it,
        so an addition is the broadest exemption available)."""
        self.assertEqual(
            self._governance_violations(), [],
            "exclusion governance violations — the three named governance surfaces are "
            "exact-file exemptions, prefix exemptions and skipped directories: "
            "files/prefixes need a stated reason and an existing target, and SKIP_DIRS "
            "must equal PINNED_SKIP_DIRS exactly. (Governing these three is NOT a claim "
            "that nothing else can hide source — four blind categories are disclosed and "
            "asserted-blind above.) Violations: %s" % self._governance_violations())

    def test_governance_rejects_an_unreasoned_or_stale_prefix(self):
        """CAN-FAIL for finding 1, run through the REAL governance logic.

        The reviewer planted an unreasoned `future_consumer/` prefix and a
        `brightness = grade["within_track"] * 255` module under it; both governance tests
        stayed GREEN and the scan reported no offenders, so a forbidden module became
        invisible with no reason and no existence check. Each planted shape below must
        now be REJECTED."""
        cases = {
            "bare tuple (the pre-cure shape)": ("tools/", "tests/"),
            "unreasoned new prefix": {"tools/": self.ALLOW_PREFIXES["tools/"],
                                      "future_consumer/": ""},
            "reason-free None": {"tools/": None},
            "thin reason": {"tools/": "because"},
            "stale prefix (no such directory)": {
                "no_such_dir_xyz/": "a plausible-sounding but false justification "
                                    "that points nowhere at all"},
        }
        for label, planted in cases.items():
            with self.subTest(planted=label):
                bad = self._governance_violations(prefixes=planted)
                self.assertTrue(bad, "planted prefix surface %r was ACCEPTED" % label)
        # and the production surface is clean, so the test above is not vacuous
        self.assertEqual(self._governance_violations(), [])

    # ---- the scan's own reader, exposed so boundary tests drive the REAL logic ------
    @staticmethod
    def _read_source(path):
        """Exactly what `_scan()` does to read one file: `tokenize.open()`, honoring
        coding cookies. Raises on unreadable input — the caller reports, never skips."""
        with tokenize.open(path) as fh:
            return fh.read()

    def _scan_tree(self, root, skip_dirs=None, allow=(), prefixes=()):
        """`_scan()`'s walk + read + report logic against an arbitrary root, so the
        boundary tests below exercise the SAME rules the production scan uses rather
        than a paraphrase of them."""
        skip_dirs = self.SKIP_DIRS if skip_dirs is None else skip_dirs
        prefix_tuple = tuple(prefixes)
        out = []
        for p in sorted(root.rglob("*.py")):
            rel = p.relative_to(root).as_posix()
            if any(part in skip_dirs or part.startswith(".")
                   for part in rel.split("/")):
                continue
            if rel in allow or (prefix_tuple and rel.startswith(prefix_tuple)):
                continue
            try:
                text = self._read_source(p)
            except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
                out.append((rel, ["<unreadable: %s>" % type(exc).__name__]))
                continue
            hits = sorted(k for k in self.GRADE_IDENTIFIERS if k in text)
            if hits:
                out.append((rel, hits))
        return out

    def test_coding_cookie_source_is_scanned_not_skipped(self):
        """CAN-FAIL for adjudication Ruling A, BOTH DIRECTIONS.

        EBUILD5REV3 wrote a valid `# -*- coding: latin-1 -*-` module carrying
        `brightness = grade["within_track"] * 255`, imported it (brightness == 255), and
        the fence returned `[]` — because `read_text(encoding="utf-8")` raised
        `UnicodeDecodeError` and the old code treated inability to inspect as
        permission. `tokenize.open()` honors the cookie, so:

          direction 1 — a cookie file WITH a carrier must be REPORTED;
          direction 2 — a legitimate cookie file WITHOUT a carrier must scan CLEAN
                        (proving the cure reads such files rather than blanket-failing
                        them, which would be a different kind of dishonest green).
        """
        import shutil
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="fence_cookie_"))
        try:
            carrier = ("# -*- coding: latin-1 -*-\n"
                       "LABEL = 'caf\xe9 na\xefve'\n"
                       'grade = {"within_track": 1}\n'
                       'brightness = grade["within_track"] * 255\n')
            (tmp / "latin1_consumer.py").write_bytes(carrier.encode("latin-1"))
            clean = ("# -*- coding: latin-1 -*-\n"
                     "LABEL = 'caf\xe9 na\xefve'\n"
                     "value = 1\n")
            (tmp / "latin1_innocent.py").write_bytes(clean.encode("latin-1"))

            found = dict(self._scan_tree(tmp))
            # direction 1: the planted carrier is now VISIBLE
            self.assertIn("latin1_consumer.py", found,
                          "a latin-1 module carrying a grade carrier must be REPORTED")
            self.assertEqual(found["latin1_consumer.py"], ["within_track"])
            # direction 2: the innocent cookie file is read and passes cleanly
            self.assertNotIn("latin1_innocent.py", found,
                             "a legitimate coding-cookie file must scan CLEAN, not be "
                             "reported as unreadable")
        finally:
            shutil.rmtree(tmp)

    def test_unreadable_source_is_reported_never_skipped(self):
        """The other half of Ruling A: whatever `tokenize.open()` still cannot read is a
        REPORTED VIOLATION naming the file. Inability to inspect is never permission."""
        import shutil
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="fence_unreadable_"))
        try:
            # a declared-utf-8 file containing bytes that are not valid utf-8
            (tmp / "broken.py").write_bytes(
                b"# -*- coding: utf-8 -*-\nx = '\xff\xfe not utf8'\n")
            found = dict(self._scan_tree(tmp))
            self.assertIn("broken.py", found,
                          "an undecodable module must be REPORTED, never skipped")
            self.assertTrue(found["broken.py"][0].startswith("<unreadable:"),
                            "the report must name it as unreadable: %r"
                            % (found["broken.py"],))
        finally:
            shutil.rmtree(tmp)

    # ---- the FOUR disclosed blind categories, each ASSERTED BLIND -------------------
    # Modelled on the E2 slope fence's DISCLOSED LIMITS pattern: enumerate the blind
    # categories, assert each one blind with a test so the disclosure cannot go stale,
    # and state that the LAW binds inside them even though the instrument cannot see
    # them. Authorized by the fence-scope adjudication Ruling B: the walk is
    # NARROWED-AND-DISCLOSED, not widened — a consumer deliberately hidden behind a
    # symlink, a dot-path or an alternate extension is adversarial evasion no static
    # scan defeats, and this fence exists to catch ACCIDENTAL drift.
    #
    # If any of these four starts FAILING, the walk has widened and the disclosure in
    # the r8 spec fence clause + the docstrings must be updated to claim the new
    # coverage. An honest limit is a TESTED limit.

    def _blind_tree(self, layout):
        """Build a temp tree, return the scan result. `layout` maps relpath -> source."""
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="fence_blind_"))
        for rel, src in layout.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(src, encoding="utf-8")
        return tmp

    CARRIER_SRC = ('grade = {"within_track": 1}\n'
                   'brightness = grade["within_track"] * 255\n')

    def test_blind_category_1_dot_hidden_paths(self):
        """BLIND (1/4): dot-prefixed components. The spec's own walk text requires
        skipping them, so this is a spec-required exclusion, not an implementation
        choice — and it is still a way an executable module stays unseen."""
        import shutil
        tmp = self._blind_tree({".future_consumer/bad.py": self.CARRIER_SRC})
        try:
            self.assertEqual(self._scan_tree(tmp), [],
                             "dot-hidden paths are a DISCLOSED blind category; if this "
                             "now reports, the walk widened — update the disclosure")
        finally:
            shutil.rmtree(tmp)

    def test_blind_category_2_directory_symlinks(self):
        """BLIND (2/4): `rglob()` does not descend directory symlinks."""
        import shutil
        tmp = self._blind_tree({"real_pkg/bad.py": self.CARRIER_SRC})
        try:
            (tmp / "linked_consumer").symlink_to(tmp / "real_pkg",
                                                 target_is_directory=True)
            found = [rel for rel, _ in self._scan_tree(tmp)]
            self.assertNotIn("linked_consumer/bad.py", found,
                             "directory symlinks are a DISCLOSED blind category; if "
                             "this now reports, the walk widened — update the "
                             "disclosure")
            # the REAL directory is still seen — the blindness is the symlink, not the
            # content, so this test cannot pass by the tree being empty
            self.assertIn("real_pkg/bad.py", found)
        finally:
            shutil.rmtree(tmp)

    def test_blind_category_3_non_py_extensions(self):
        """BLIND (3/4): the walk is `rglob("*.py")`, so `.pyw` (and any other executable
        extension) is out of scope."""
        import shutil
        tmp = self._blind_tree({"consumer.pyw": self.CARRIER_SRC,
                                "consumer.py": self.CARRIER_SRC})
        try:
            found = [rel for rel, _ in self._scan_tree(tmp)]
            self.assertNotIn("consumer.pyw", found,
                             "non-.py extensions are a DISCLOSED blind category; if "
                             "this now reports, the walk widened — update the "
                             "disclosure")
            self.assertIn("consumer.py", found)   # the .py sibling IS seen
        finally:
            shutil.rmtree(tmp)

    def test_blind_category_4_dynamically_generated_source(self):
        """BLIND (4/4): source that does not exist on disk as a file at scan time —
        built at run time, `exec`'d from a string, or fetched — cannot be walked. Same
        class as the E2 slope fence's computed-key blind spot: the literal never appears
        in a file the scanner reads."""
        import shutil
        tmp = self._blind_tree({
            "generator.py": (
                "KEY = 'within' + '_track'\n"          # the carrier is COMPUTED
                "SRC = 'brightness = grade[KEY] * 255'\n"
                "def run(grade):\n"
                "    exec(SRC)\n")})
        try:
            self.assertEqual(
                self._scan_tree(tmp), [],
                "dynamically generated source is a DISCLOSED blind category; if this "
                "now reports, the instrument gained reach — update the disclosure")
        finally:
            shutil.rmtree(tmp)

    def test_governance_rejects_an_added_or_missing_skip_directory(self):
        """CAN-FAIL for EBUILD5REV2 finding 1, run through the REAL governance helper.

        The reviewer added `future_consumer` to `SKIP_DIRS`, placed
        `brightness = grade["within_track"] * 255` beneath it, and got: governance `[]`,
        scan `[]`, and all three guard tests GREEN — the forbidden module invisible again,
        one surface over. Each planted skip set below must now be REJECTED."""
        cases = {
            "the reviewer's plant (+future_consumer)":
                set(self.SKIP_DIRS) | {"future_consumer"},
            "an innocuous-looking addition (+vendor)":
                set(self.SKIP_DIRS) | {"vendor"},
            "a pin REMOVED (-local)": set(self.SKIP_DIRS) - {"local"},
            "emptied entirely": set(),
            "not a set at all": 42,
        }
        for label, planted in cases.items():
            with self.subTest(planted=label):
                bad = self._governance_violations(skip_dirs=planted)
                self.assertTrue(bad, "planted skip set %r was ACCEPTED" % label)
                self.assertTrue(any(k == "skip-dir" for k, _e, _p in bad),
                                "rejection must name the skip-dir surface: %r" % (bad,))
        # production is clean, so the rejections above are not vacuous
        self.assertEqual(self._governance_violations(), [])

    def test_a_planted_skip_dir_hides_a_carrier_but_governance_catches_it(self):
        """The two halves of the combined gate, stated together, because neither alone is
        the protection.

        A skipped directory DOES blind the scan — that is what skipping means, and the
        raw scan cannot be blamed for it. What stands between a new skip dir and a silent
        blind area is governance. This proves both halves against the reviewer's exact
        plant: the scan goes blind, AND governance goes red, so the COMBINED gate holds."""
        planted = set(self.SKIP_DIRS) | {"future_consumer"}
        # half 1: the scan is blind to anything under the planted skip dir (by design)
        self.assertEqual(self._scan(skip_dirs=planted), [],
                         "the raw scan necessarily ignores a skipped directory")
        # half 2: governance rejects the planted set, so the combined gate is RED
        bad = self._governance_violations(skip_dirs=planted)
        self.assertTrue(bad)
        self.assertIn("future_consumer", [e for _k, e, _p in bad])
        # and the direction test stays non-vacuous: real carriers DO live under local/,
        # so the pinned skip set is still doing measurable work in this checkout.
        revealed = self._scan(skip_dirs=set(self.SKIP_DIRS) - {"local"})
        self.assertTrue(revealed,
                        "expected real carrier mentions under local/ — without them the "
                        "pinned-skip direction test would be passing vacuously")

    def test_an_unreasoned_prefix_cannot_hide_a_carrier_mention(self):
        """The consequence the governance protects, stated as its own case: the scan
        WILL go blind to anything under a new prefix — that is what a prefix does — so
        the only thing standing between a new prefix and a silent blind area is the
        governance test above. This pins that dependency: with `tools/` exempted the
        tools lane is invisible to the scan, and removing the exemption reveals it."""
        with_tools = self._scan()
        self.assertEqual(with_tools, [])
        without_tools = self._scan(prefixes={"tests/": self.ALLOW_PREFIXES["tests/"]})
        self.assertTrue(
            without_tools,
            "expected tools/ modules to mention grade carriers — if this is empty the "
            "tools/ prefix exemption is no longer load-bearing and should be removed")
        self.assertTrue(all(r.startswith("tools/") for r, _ in without_tools),
                        "only tools/ paths should appear: %s" % without_tools)

    def test_the_pinned_skip_set_is_what_makes_the_fence_green(self):
        """CAN-FAIL on the pinned style itself: dropping `local/` from the skip set makes
        the same scan RED on research/sealed copies. Recorded because a seat that omits
        the skip set is pushed toward widening the ALLOWLIST instead — permanently
        narrowing the fence. The exact count drifts with what sits under local/, so this
        asserts the DIRECTION, never a number."""
        self.assertEqual(self._scan(), [])
        without_local = self._scan(skip_dirs=self.SKIP_DIRS - {"local"})
        self.assertTrue(without_local,
                        "expected local/ research copies to trip a scan without the "
                        "local/ skip — if this is empty the pinned skip set is no longer "
                        "load-bearing and the comment above must be re-measured")
        self.assertTrue(all(r.startswith("local/") for r, _ in without_local),
                        "only local/ paths should appear: %s" % without_local)

    def test_fence_discriminates_a_planted_consumer(self):
        """CAN-FAIL for the tripwire's own logic: with `state_manager.py` removed from the
        allowlist, the scan must FIND it. Proves the walk actually reads files and that a
        real consumer is caught — the fence is not vacuously green."""
        allow_without_sm = {k: v for k, v in self.ALLOW.items()
                            if k != "state_manager.py"}
        offenders = self._scan(allow=allow_without_sm)
        self.assertIn("state_manager.py", [r for r, _ in offenders])


if __name__ == "__main__":
    unittest.main()
