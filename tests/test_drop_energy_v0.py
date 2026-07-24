"""Tests for the E3 per-drop energy grades (drop_energy_v0) + the drop-path
wiring: gain-invariance, product law, window edges, plan attach, the four-surface
flag-off kill test, the E2xE3 four-flag matrix (no cross-flag coupling), the
gates verdict, and the static import fence.
"""
import ast
import queue
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import drop_energy_v0  # noqa: E402
from rb_ss_bridge_v2 import section_energy_v0  # noqa: E402
from rb_ss_bridge_v2.drop_energy_v0 import (  # noqa: E402
    MIN_WINDOW_BEATS, DROP_WINDOW_BEATS, grade_drops, grades_by_beat, gates_verdict)
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


def _v4(n_beats=80, full=None, sub=None, onset=None, ref="auto", p90=2.0):
    z = tuple(0.0 for _ in range(n_beats))
    if full is None:
        full = tuple(-2.0 + 0.05 * i for i in range(n_beats))   # near-ceiling body
    if sub is None:
        sub = tuple(-4.0 + 0.02 * i for i in range(n_beats))
    if onset is None:
        onset = tuple(2.0 for _ in range(n_beats))
    series = {k: z for k in V4_SERIES_KEYS}
    series.update({"full_db": tuple(full), "sub_db": tuple(sub),
                   "onset_density_midhigh": tuple(onset)})
    scalars = {k: 0.5 for k in V4_SCALAR_KEYS}
    scalars["onset_mh_p90"] = p90
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
        base = grade_drops(v4, drop_beats=[16], track_weight=0.5)
        sh = grade_drops(_shifted(v4, 6.0), drop_beats=[16], track_weight=0.5)
        self.assertAlmostEqual(base[0]["library_scaled"], sh[0]["library_scaled"], places=9)


class ProductAndWindowTests(unittest.TestCase):
    def test_product_law_and_null(self):
        g = grade_drops(_v4(), drop_beats=[16], track_weight=0.5)
        self.assertAlmostEqual(g[0]["library_scaled"], g[0]["within_track"] * 0.5, places=9)
        self.assertIsNone(grade_drops(_v4(), drop_beats=[16], track_weight=None)[0]["library_scaled"])

    def test_coverage_floor_and_end_clamp(self):
        # a drop < MIN_WINDOW_BEATS from the end is ungraded (omitted)
        g = grade_drops(_v4(n_beats=80), drop_beats=[75], track_weight=None)
        self.assertEqual(g, [])
        g2 = grade_drops(_v4(n_beats=80), drop_beats=[80 - MIN_WINDOW_BEATS], track_weight=None)
        self.assertEqual(len(g2), 1)
        self.assertEqual(g2[0]["coverage"], MIN_WINDOW_BEATS)

    def test_p90_zero_omits_onset_term(self):
        with_p90 = grade_drops(_v4(p90=2.0), drop_beats=[16], track_weight=None)[0]["within_track"]
        no_p90 = grade_drops(_v4(p90=0.0), drop_beats=[16], track_weight=None)[0]["within_track"]
        # both finite [0,1]; the term-omission path must not blow up or fabricate
        self.assertTrue(0.0 <= with_p90 <= 1.0 and 0.0 <= no_p90 <= 1.0)

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
    def test_five_outcomes(self):
        self.assertEqual(gates_verdict(50, 50, 0.2, 0.3), (False, "insufficient_corpus"))
        self.assertEqual(gates_verdict(200, 100, 0.2, 0.3), (False, "insufficient_coverage"))
        self.assertEqual(gates_verdict(200, 195, 0.02, 0.3), (False, "degenerate_distribution"))
        self.assertEqual(gates_verdict(200, 195, 0.2, 0.05), (False, "inverted_or_flat_separation"))
        self.assertEqual(gates_verdict(200, 195, 0.2, 0.3), (True, "ok"))


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


if __name__ == "__main__":
    unittest.main()
