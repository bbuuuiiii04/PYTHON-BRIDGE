"""Offline spectral-tilt / harness watchdog battery — energy E1 (AWR-291 §5, Task 4c).

The REPLACEMENT half of the drama-gate demotion: Task 4b removed the dynamic-range
acceptance gate from ``track_weight_v0.acceptance_verdict``, and this tool is what
takes its place. Its trade is stated plainly, and printed verbatim in the report
header so it can never be silently mistaken for gate-for-gate:

    This trade removes one acceptance gate and adds ZERO — both new gates test the
    INSTRUMENT (harness integrity, extraction fidelity), and no configuration of any
    future E1 formulation can fail this battery on mastering grounds, because the tilt
    channel — the one place E1's mastering exposure actually lives — is
    comparative-only. The trade on offer is gate-for-diagnostic, not gate-for-gate.

Invoked WHEN AN E1 FORMULATION CHANGES — not per corpus run. It re-extracts real
audio under four perturbations on a pinned 100-track panel and compares the resulting
E1 track weights against the panel's recorded baseline:

  | probe           | class                                   | role                | floor |
  |-----------------|-----------------------------------------|---------------------|-------|
  | c0b_invert      | polarity-only exact null                | harness integrity   | rho = 1.0000 EXACTLY, displacement 0 |
  | c1a_gain        | per-track gain DRAWN in [-12, 0] dB +   | gain invariance by  | rho >= 0.999 |
  |                 | TPDF dither at -90 dBFS, reproduced     | real re-extraction  |       |
  |                 | from the c1_static seed stream          |                     |       |
  | c1c_tilt_mild   | EQ shelf +/-1 dB                        | tilt exposure, mild | INFORMATIONAL |
  | c1b_tilt        | EQ shelf +/-3 dB                        | tilt exposure, strong | INFORMATIONAL |

`c1a_gain` is NOT a fixed "gain to -12 dB" — that shorthand is inherited from the
sealed report and is wrong. The gain is DRAWN per track from U(-12, 0) dB, a tilt draw
is consumed-but-not-applied so the two halves of `c1_static` decompose, and TPDF dither
sits at -90 dBFS; reproducibility comes from reusing `c1_static`'s seed stream. The
corrected wording above is what this tool prints.

FLOOR HONESTY: `c1a_gain`'s 0.999 floor sits ON its single measured value 0.9990 with
NO margin. It is a HARNESS-REPRODUCTION gate ("the instrument still reproduces its one
measured behaviour"), never an accuracy claim; a marginal miss is REPORTED and
investigated as instrument drift and is NEVER quietly re-floored.

The two TILT probes are INFORMATIONAL by construction: the incumbent measurably fails
+/-3 dB (rho 0.7938) and sits at 0.9673 at +/-1 dB, so any pinned floor would either
instantly fail the accepted formulation or be tuned to pass it. They are the COMPARATIVE
channel — a future E1 component change reports its tilt dose-response beside the
incumbent's, and a challenger that is materially more tilt-exposed says so in its own
report. `brightness_med` is where the exposure lives (a +/-1 dB shelf moves a track up
to 22/100 ranks).

PANEL: read from the FROZEN ARTIFACT ``local/e1_scramble_2026_07_24/data/panel.json``
(100 tracks, 66 genre x baseline-weight-tercile cells, seed 20260724). It is NEVER
re-drawn: ``scripts/s1_baseline_panel.py`` is the panel's derivation RECORD, not its
source — re-running it reads the live Rekordbox playlists and computes terciles from
CURRENT weights, so a library that has moved yields different tracks. Re-derivation is
a FALLBACK only (if the artifact is lost) and then only with an equality check on the
100 content_ids; a mismatch is a reported failure, never a quiet re-draw. This matters
because c1a_gain's floor has no margin: a drifted panel would surface as a marginal
miss and be misread as instrument drift.

ZERO RUNTIME IMPORTERS (a static test enforces it). THREE hard safety rules, each of
which would corrupt the library if broken — identical to
``tools/energy_perturbation_check.py``:
  * NEVER call ``spectral_cache.put_cached_v4`` and never write under the cache dir —
    a perturbed entry in the real v4 cache would silently poison every future energy
    run. The extractor is called directly, never a get-or-compute helper.
  * Never write to / move / re-encode any file under the Rekordbox library path.
  * The only writes are inside a ``tempfile.TemporaryDirectory()`` and the optional
    ``--out`` report.

The probe ops are EXTRACTED VERBATIM from the E1SCRAMBLE chain code
(``local/e1_scramble_2026_07_24/scripts/chains.py``), never retyped: ``--verify-ops``
asserts each carried op is AST-body identical to its prototype, and the unit test does
the same, so the two copies cannot silently diverge.

Missing numpy / scipy / librosa / soundfile => exit 2 (an environment problem, not a
gate failure). Any gated probe below its floor => exit 1.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import track_weight_v0  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = REPO_ROOT / "local" / "e1_scramble_2026_07_24" / "data" / "panel.json"
PROTOTYPE_CHAINS = (REPO_ROOT / "local" / "e1_scramble_2026_07_24" / "scripts"
                    / "chains.py")

# ---- pinned constants, extracted from the E1SCRAMBLE scripts (never re-chosen) ----
SR = 22050
RUN_SEED = 20260724
PANEL_N = 100
PANEL_CELLS = 66
GATE_INVERT_RHO = 1.0000        # EXACTLY 1.0, measured achievable (E1SCRAMBLE §4)
GATE_INVERT_DISP = 0            # zero rank displacement
GATE_GAIN_RHO = 0.999           # ON the single measured 0.9990 — no margin
GATED_PROBES = ("c0b_invert", "c1a_gain")
INFORMATIONAL_PROBES = ("c1c_tilt_mild", "c1b_tilt")
PROBE_ORDER = ("c0b_invert", "c1a_gain", "c1c_tilt_mild", "c1b_tilt")

TRADE_SENTENCE = (
    "This trade removes one acceptance gate and adds ZERO — both new gates test the\n"
    "INSTRUMENT (harness integrity, extraction fidelity), and no configuration of any\n"
    "future E1 formulation can fail this battery on mastering grounds, because the tilt\n"
    "channel — the one place E1's mastering exposure actually lives — is\n"
    "comparative-only. The trade on offer is gate-for-diagnostic, not gate-for-gate."
)

PROBE_LABELS = {
    "c0b_invert": "polarity-only exact null (no DC removal); |STFT| identical, so any "
                  "movement is the harness",
    "c1a_gain": "per-track gain DRAWN in [-12, 0] dB + TPDF dither at -90 dBFS, "
                "reproduced from the c1_static seed stream "
                "(NOT a fixed 'gain to -12 dB')",
    "c1c_tilt_mild": "EQ shelf +/-1 dB (2 dB total) — tilt dose-response, mild",
    "c1b_tilt": "EQ shelf +/-3 dB (6 dB total) — tilt dose-response, strong",
}


# ===================================================================== #
# The PURE COMPARISON SEAM — the only part the unit test exercises.      #
# ===================================================================== #
def ranks(weights: "dict", ids: "Sequence[str]") -> "dict":
    """1-based rank of each id by ascending weight (E1SCRAMBLE s3_analyse.ranks)."""
    order = sorted(ids, key=lambda p: weights[p])
    return {p: i + 1 for i, p in enumerate(order)}


def max_displacement(a: "dict", b: "dict", ids: "Sequence[str]") -> "Optional[int]":
    """Largest rank move between two weight vectors (s3_analyse.max_displacement)."""
    if not ids:
        return None
    ra, rb = ranks(a, ids), ranks(b, ids)
    return max(abs(ra[p] - rb[p]) for p in ids)


def compare_probe(probe: str, baseline: "dict", perturbed: "dict") -> "dict":
    """THE comparison seam: two id->weight vectors + a probe class -> the per-probe
    rho / max displacement / n and the pass-fail verdict against the pinned floors.

    Pure: no audio, no extraction, no cache, no I/O. Only ids present in BOTH vectors
    with finite weights are compared, and `n` reports how many that was — a probe that
    lost tracks to extraction failures must not silently compare a different
    population. Fails CLOSED: a missing rho, or fewer than 3 usable pairs, is a
    verdict of False for a gated probe, never a pass.
    """
    ids = [p for p in sorted(baseline)
           if p in perturbed
           and isinstance(baseline[p], (int, float))
           and isinstance(perturbed[p], (int, float))]
    n = len(ids)
    rho = (track_weight_v0.spearman([baseline[p] for p in ids],
                                    [perturbed[p] for p in ids])
           if n >= 3 else None)
    disp = max_displacement(baseline, perturbed, ids) if n else None
    gated = probe in GATED_PROBES
    if probe == "c0b_invert":
        floor = "rho == %.4f EXACTLY and displacement == %d" % (GATE_INVERT_RHO,
                                                                GATE_INVERT_DISP)
        passed = (rho is not None and round(rho, 4) == GATE_INVERT_RHO
                  and disp == GATE_INVERT_DISP)
    elif probe == "c1a_gain":
        floor = "rho >= %.3f" % GATE_GAIN_RHO
        passed = (rho is not None and rho >= GATE_GAIN_RHO)
    else:
        floor = "INFORMATIONAL — no floor (comparative channel)"
        passed = None
    return {"probe": probe, "n": n, "rho": rho, "max_displacement": disp,
            "gated": gated, "floor": floor, "passed": passed}


def battery_verdict(results: "Sequence[dict]") -> "tuple":
    """(accepted, reason) over the whole battery. Only GATED probes can fail it; a
    gated probe that never ran fails closed."""
    seen = {r["probe"]: r for r in results}
    for probe in GATED_PROBES:
        r = seen.get(probe)
        if r is None:
            return (False, "missing_gated_probe:%s" % probe)
        if not r["passed"]:
            return (False, "failed:%s" % probe)
    return (True, "ok")


# ===================================================================== #
# Probe ops — VERBATIM copies of the E1SCRAMBLE chain code.              #
# `--verify-ops` and the unit test assert AST-body identity vs chains.py #
# ===================================================================== #
_VERBATIM_OPS = ("rng_for", "_one_pole_lp", "tilt", "dither_tpdf", "c0b_invert",
                 "c1a_gain", "c1b_tilt", "c1c_tilt_mild")
SEED_ALIAS = {"c1a_gain": "c1_static", "c1b_tilt": "c1_static"}

# The carried ops below are LITERAL copies of the prototype's text, so `--verify-ops`
# compares them with NO normalisation — nothing is massaged to make the check pass.
# That requires the prototype's module-level names (`np`, `lfilter`) to exist here
# under the same spellings, but bound LAZILY, because this tool must exit 2 on a
# missing optional dependency rather than fail at import (and the static
# import-fence test parses it without numpy installed).
np = None          # bound by _ensure_deps()
lfilter = None     # bound by _ensure_deps()


def _ensure_deps() -> "Optional[str]":
    """Bind `np` / `lfilter`, or return the name of the missing dependency."""
    global np, lfilter
    if np is not None and lfilter is not None:
        return None
    try:
        import numpy as _numpy  # noqa: PLC0415
        from scipy.signal import lfilter as _lfilter  # noqa: PLC0415
    except Exception as exc:                                       # noqa: BLE001
        return "numpy/scipy (%s)" % exc
    np, lfilter = _numpy, _lfilter
    return None


def rng_for(condition: str, content_id: str) -> "Any":
    """Independent, reproducible per (condition, track)."""
    h = hashlib.sha256(("%d|%s|%s" % (RUN_SEED, condition, content_id)).encode())
    return np.random.default_rng(int.from_bytes(h.digest()[:8], "big"))


def _one_pole_lp(x, fc):
    a = 1.0 - np.exp(-2.0 * np.pi * fc / SR)
    return lfilter([a], [1.0, -(1.0 - a)], x).astype(np.float32)


def tilt(x, total_db, fc=1000.0):
    """First-order spectral tilt about `fc`: low band gets -total/2 dB, high band
    +total/2 dB (a shelf pair, NOT a constant dB/octave slope — see report)."""
    lo = _one_pole_lp(x, fc)
    hi = x - lo
    gl = 10.0 ** (-total_db / 40.0)
    gh = 10.0 ** (+total_db / 40.0)
    return (gl * lo + gh * hi).astype(np.float32)


def dither_tpdf(x, rng, level_dbfs=-90.0):
    amp = 10.0 ** (level_dbfs / 20.0)
    n = (rng.random(len(x)) - rng.random(len(x))).astype(np.float32)  # TPDF
    return (x + amp * n).astype(np.float32)


def c0b_invert(x, rng):
    """POST-HOC harness probe: polarity inversion ONLY, no DC removal. |STFT| is
    mathematically identical, so ANY movement here is the harness, not an op."""
    return (-x).astype(np.float32), {}


def c1a_gain(x, rng):
    """POST-HOC DIAGNOSTIC (not one of the predeclared six): the gain+dither half
    of c1_static, drawing the SAME gain from the SAME stream position so the two
    halves are directly comparable."""
    g_db = float(rng.uniform(-12.0, 0.0))
    _t_db = float(rng.uniform(-6.0, 6.0))          # consume, do not apply
    y = (x * np.float32(10.0 ** (g_db / 20.0))).astype(np.float32)
    y = dither_tpdf(y, rng, -90.0)
    return y, {"gain_db": g_db, "dither_dbfs": -90.0}


def c1b_tilt(x, rng):
    """POST-HOC DIAGNOSTIC: the EQ-tilt half of c1_static, same drawn tilt."""
    _g_db = float(rng.uniform(-12.0, 0.0))         # consume, do not apply
    t_db = float(rng.uniform(-6.0, 6.0))
    return tilt(x, t_db), {"tilt_db": t_db}


def c1c_tilt_mild(x, rng):
    """POST-HOC dose-response: the same tilt op at a conservative +-1 dB shelf
    (2 dB total) instead of c1b's +-3 dB. Tests whether the tilt exposure is an
    artefact of an aggressive draw or a real sensitivity at realistic settings."""
    t_db = float(rng.uniform(-2.0, 2.0))
    return tilt(x, t_db), {"tilt_db": t_db}


CONDITIONS = {"c0b_invert": c0b_invert, "c1a_gain": c1a_gain,
              "c1b_tilt": c1b_tilt, "c1c_tilt_mild": c1c_tilt_mild}


def verbatim_op_diff() -> "list[str]":
    """Names of carried ops whose body differs from the chains.py prototype. Empty
    list == every op is a verbatim copy. Returns ['<prototype unavailable>'] when the
    machine-local prototype is absent (it is gitignored), so a missing file is never
    silently read as agreement."""
    import ast  # noqa: PLC0415
    import inspect  # noqa: PLC0415
    import textwrap  # noqa: PLC0415
    if not PROTOTYPE_CHAINS.is_file():
        return ["<prototype unavailable>"]
    proto = ast.parse(PROTOTYPE_CHAINS.read_text(encoding="utf-8"))
    proto_fns = {n.name: n for n in ast.walk(proto)
                 if isinstance(n, ast.FunctionDef)}
    mine = sys.modules[__name__]
    bad = []
    for name in _VERBATIM_OPS:
        p = proto_fns.get(name)
        if p is None:
            bad.append("%s (absent from prototype)" % name)
            continue
        try:
            mine_src = textwrap.dedent(inspect.getsource(getattr(mine, name)))
        except (OSError, TypeError):
            bad.append("%s (unreadable)" % name)
            continue
        m = ast.parse(mine_src).body[0]
        # Compare the STATEMENT BODY with NO normalisation of any kind: the carried
        # copies are literal prototype text, so anything that fails here is a real
        # divergence. (Only the docstring is skipped, and only because a docstring is
        # not behaviour; a differing docstring would not change the op.)
        if _body_dump(m) != _body_dump(p):
            bad.append(name)
    return bad


def _body_dump(fn) -> str:
    """ast.dump of a function's statements, docstring dropped. No normalisation."""
    import ast  # noqa: PLC0415
    body = list(fn.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return "\n".join(ast.dump(s) for s in body)


# ===================================================================== #
# Panel + extraction                                                     #
# ===================================================================== #
def load_panel(path: "Path") -> "tuple":
    """(tracks, meta) from the frozen panel artifact, or (None, reason)."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, "panel unreadable (%s: %s)" % (type(exc).__name__, exc)
    if not isinstance(doc, dict) or not isinstance(doc.get("tracks"), list):
        return None, "panel malformed (no tracks list)"
    if int(doc.get("seed", -1)) != RUN_SEED:
        return None, ("panel seed %r != pinned %d — refusing to run against a "
                      "different panel" % (doc.get("seed"), RUN_SEED))
    if int(doc.get("n", -1)) != PANEL_N:
        return None, "panel n %r != pinned %d" % (doc.get("n"), PANEL_N)
    return doc["tracks"], {"n": doc["n"], "seed": doc["seed"]}


def _extract_perturbed(filepath: str, grid: "Sequence[float]", probe: str,
                       content_id: str, tmpdir: str) -> "Optional[Any]":
    """Re-extract v4 features for one perturbed track. Writes ONLY inside `tmpdir`;
    never calls put_cached_v4, never touches the cache dir or the library file."""
    import librosa  # noqa: PLC0415
    import soundfile as sf  # noqa: PLC0415
    from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: PLC0415
        extract_spectral_features_v4)
    x, _sr = librosa.load(filepath, sr=SR, mono=True)
    rng = rng_for(SEED_ALIAS.get(probe, probe), content_id)
    y, _params = CONDITIONS[probe](np.asarray(x, dtype=np.float32), rng)
    wav = os.path.join(tmpdir, "%s_%s.wav" % (probe, content_id))
    sf.write(wav, y, SR, subtype="FLOAT")
    try:
        return extract_spectral_features_v4(wav, list(grid))
    finally:
        try:
            os.unlink(wav)
        except OSError:
            pass


def run(argv: "Sequence[str]") -> int:
    ap = argparse.ArgumentParser(
        description="E1 spectral-tilt / harness watchdog battery (AWR-291 §5 4c)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--panel", default=str(PANEL_PATH))
    ap.add_argument("--limit", type=int, default=None,
                    help="DEV ONLY: truncate the panel; forces partial_run")
    ap.add_argument("--verify-ops", action="store_true",
                    help="only check the carried probe ops against chains.py, then exit")
    args = ap.parse_args(list(argv))

    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    op_diff = verbatim_op_diff()
    if args.verify_ops:
        print("carried ops vs chains.py prototype: %s"
              % ("ALL VERBATIM" if op_diff == [] else "DIFFER: %s" % op_diff))
        return 0 if op_diff == [] else 1

    missing = _ensure_deps()
    if missing:
        sys.stderr.write("ENV ERROR: %s unavailable\n" % missing)
        return 2
    for mod in ("numpy", "scipy", "librosa", "soundfile"):
        try:
            __import__(mod)
        except Exception as exc:                                   # noqa: BLE001
            sys.stderr.write("ENV ERROR: %s unavailable (%s)\n" % (mod, exc))
            return 2

    tracks, meta = load_panel(Path(args.panel))
    if tracks is None:
        sys.stderr.write("PANEL ERROR: %s\n" % meta)
        return 2
    forced_partial = args.limit is not None
    if forced_partial:
        tracks = tracks[:max(0, args.limit)]

    # ---- report header: the trade sentence VERBATIM + the panel n beside the floors
    emit("# Energy E1 — spectral-tilt / harness watchdog battery (AWR-291 §5, Task 4c)")
    emit("# OFFLINE / read-only against the library. Temp-dir extractions only:")
    emit("# never put_cached_v4, never a write under the cache dir, never a write /")
    emit("# move / re-encode of any file under the Rekordbox library path.")
    emit("")
    emit("## THE TRADE THIS BATTERY MAKES (verbatim, per spec 4c)")
    for ln in TRADE_SENTENCE.splitlines():
        emit("  " + ln)
    emit("")
    emit("## PANEL BOUND ON EVERYTHING BELOW (AMENDMENT-4 clause 4c)")
    emit("  panel n = %d tracks in %d genre x weight-tercile cells, seed %d"
         % (PANEL_N, PANEL_CELLS, RUN_SEED))
    emit("  read from the FROZEN artifact %s (never re-drawn)" % args.panel)
    emit("  No significance claim beyond harness reproduction is available from this")
    emit("  design, and none is made. The two gated probes test the INSTRUMENT")
    emit("  (exact-null integrity, extraction fidelity), never a formulation's skill.")
    emit("  c1a_gain's %.3f floor sits ON its single measured value 0.9990 with NO"
         % GATE_GAIN_RHO)
    emit("  margin: a marginal miss is REPORTED as instrument drift, never re-floored.")
    emit("")
    emit("  carried probe ops vs the chains.py prototype: %s"
         % ("ALL VERBATIM (AST-body identical)" if op_diff == []
            else "DIFFER -> %s" % op_diff))
    emit("")

    baseline = {t["panel_id"]: t.get("baseline_track_weight") for t in tracks}
    emit("panel tracks loaded: %d   with a recorded baseline weight: %d"
         % (len(tracks), sum(1 for v in baseline.values()
                             if isinstance(v, (int, float)))))
    emit("")

    dist = track_weight_v0.build_distribution(
        [t["baseline_components"] for t in tracks
         if isinstance(t.get("baseline_components"), dict)])

    results = []
    skips = {}
    with tempfile.TemporaryDirectory(prefix="e1watchdog_") as td:
        for probe in PROBE_ORDER:
            perturbed = {}
            failed = 0
            for t in tracks:
                pid = t["panel_id"]
                fp = t.get("filepath") or ""
                if not fp or not os.path.isfile(fp):
                    failed += 1
                    continue
                try:
                    v4 = _extract_perturbed(fp, t.get("grid") or [], probe,
                                            str(t.get("content_id")), td)
                except Exception:                                  # noqa: BLE001
                    failed += 1
                    continue
                if v4 is None:
                    failed += 1
                    continue
                comps = track_weight_v0.components(v4)
                w = (track_weight_v0.track_weight(comps, dist)
                     if comps is not None else None)
                if w is not None:
                    perturbed[pid] = w
            skips[probe] = failed
            results.append(compare_probe(probe, baseline, perturbed))

    emit("## PROBE RESULTS")
    emit("  %-14s %-6s %-12s %-8s %-9s %s"
         % ("probe", "n", "rho", "maxdisp", "verdict", "floor"))
    for r in results:
        verdict = ("PASS" if r["passed"] else "FAIL") if r["gated"] else "INFO"
        emit("  %-14s %-6d %-12s %-8s %-9s %s"
             % (r["probe"], r["n"],
                ("%+.6f" % r["rho"]) if r["rho"] is not None else "n/a",
                ("%d" % r["max_displacement"]) if r["max_displacement"] is not None
                else "n/a",
                verdict, r["floor"]))
    emit("")
    for r in results:
        emit("  %-14s %s" % (r["probe"], PROBE_LABELS[r["probe"]]))
        if skips.get(r["probe"]):
            emit("  %-14s (tracks skipped: %d — extraction unavailable or failed)"
                 % ("", skips[r["probe"]]))
    emit("")
    emit("## TILT CHANNEL — COMPARATIVE ONLY, never a gate")
    emit("  The incumbent measures rho 0.7938 at +/-3 dB and 0.9673 at +/-1 dB; a")
    emit("  pinned floor here would either instantly fail the accepted formulation or")
    emit("  be tuned to pass it. Any FUTURE E1 component change reports its own tilt")
    emit("  dose-response beside those two numbers, and a challenger that is materially")
    emit("  more tilt-exposed says so in its own report. Exposure lives in")
    emit("  brightness_med: a +/-1 dB shelf moves a track up to 22/100 ranks.")
    emit("")
    emit("## LEVEL-INVARIANCE IS SILENT ABOUT SPECTRUM")
    emit("  Measured mastering leak: median +0.044 weight, p90 ~0.11, up to 32/100")
    emit("  ranks under a full chain. 'Level-invariant' never means 'mastering-immune'.")
    emit("")

    if forced_partial:
        accepted, reason = False, "partial_run"
    else:
        accepted, reason = battery_verdict(results)
    emit("BATTERY: %s   reason=%s" % ("ACCEPTED" if accepted else "NOT ACCEPTED",
                                      reason))
    if forced_partial:
        emit("!! PARTIAL RUN (--limit %s): verdict forced FALSE (partial_run)."
             % args.limit)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
