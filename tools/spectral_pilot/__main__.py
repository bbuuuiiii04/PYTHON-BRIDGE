"""Thin CLI for the Phase-0 spectral pilot (spec B1 entrypoints, B11 no-write proof).

    python3 -m tools.spectral_pilot --workspace W <select|freeze|session|score> ...

Every subcommand runs inside ``no_network_guard`` and, over an explicit ``--watch``
set (the live cache/labels/config/RB/logs dirs at Phase-1; a temp dir under test),
records a byte-identity ``listing_hash`` before and after and fails on any change
(spec B11c/d). Logging is configured into ``<workspace>/scratch/`` BEFORE any
package module is imported, so an import-time logger can never write outside the
pilot namespace. All writes are fenced under the passed workspace; no subcommand
reads the live library/cache/labels unless an explicit path is given — tests drive
it with synthetic fixtures only.

This CLI is NOT permission to run the pilot: Phase-1 execution still needs its own
operator authorization (spec B0).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path


# --- logging + workspace fence (configured before importing package internals) ---
def _resolve_workspace(ws: str) -> Path:
    p = Path(ws).resolve()
    p.mkdir(parents=True, exist_ok=True)
    (p / "scratch").mkdir(exist_ok=True)
    return p


def _configure_logging(ws: Path) -> None:
    # ponytail: logging into scratch/ BEFORE any runtime-surface import (spec B11d)
    logging.basicConfig(filename=str(ws / "scratch" / "pilot.log"), level=logging.INFO, force=True)


# --- small IO helpers (all fenced under the workspace) -----------------------
def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(ws, name, obj):
    from .canonical import canonical_bytes
    from .session import _safe_path
    _safe_path(ws, name).write_bytes(canonical_bytes(obj))


def _write_jsonl(ws, name, rows):
    from .canonical import jsonl_line
    from .session import _safe_path
    p = _safe_path(ws, name)
    with p.open("wb") as fh:
        for r in rows:
            fh.write(jsonl_line(r))


def _read_jsonl(path):
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]   # tools/spectral_pilot -> repo root


def _warm_bridge_imports():
    """Import pyrekordbox + bridge modules BEFORE ``no_network_guard`` patches
    ``socket.socket``. ``ssl`` (pulled in transitively via pdb/asyncio) subclasses
    ``socket.socket`` at import; once the guard replaces it with a function that
    raises, that subclassing fails with a TypeError. Importing here (one-time,
    cached) means only socket *instantiation* is blocked under the guard, not the
    import-time class definitions. The DB reads still run inside the guard, so
    read-only egress is still proven."""
    import sys
    import warnings

    parent = str(_repo_root().parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import pyrekordbox.db6  # noqa: F401
    import rb_ss_bridge_v2.anlz_reader        # noqa: F401
    import rb_ss_bridge_v2.approach_features_v0  # noqa: F401
    import rb_ss_bridge_v2.filepath_resolver  # noqa: F401
    import rb_ss_bridge_v2.hardness_v0         # noqa: F401
    import rb_ss_bridge_v2.lighting_moments_v2  # noqa: F401
    import rb_ss_bridge_v2.spectral_cache     # noqa: F401
    import rb_ss_bridge_v2.spectral_profile   # noqa: F401


def _locator_from_dict(d):
    """Build a ``LocatorRow`` from a JSON dict, re-tupling the sequence fields so the
    frozen dataclass round-trips (JSON has no tuples). Missing optional keys fall to
    the dataclass defaults."""
    from .selection import LocatorRow
    d = dict(d)
    d["candidate_markers"] = tuple(d.get("candidate_markers", []) or [])
    if d.get("anchor_montage_beats") is not None:
        d["anchor_montage_beats"] = tuple(d["anchor_montage_beats"])
    return LocatorRow(**d)


# --- subcommands -------------------------------------------------------------
def cmd_select(args, ws):
    from . import selection as sel
    from .session import write_card_manifest

    cfg = _load_json(args.config) if args.config else {}
    rows = [_locator_from_dict(d) for d in _load_json(args.locators)]
    anchors = [_locator_from_dict(d) for d in _load_json(args.anchors)] if args.anchors else []

    dev_ids = set(cfg.get("dev_content_ids", []))
    scripted_ids = set(cfg.get("scripted_ids", []))
    # spec B3.2: suspicious pairs over the 60-row pool ∪ anchors; fail closed —
    # every affected row is unresolved unless the manual review confirmed unrelated.
    pool = sel.seed_pool(rows, pilot_seed=args.pilot_seed, dev_content_ids=dev_ids, scripted_ids=scripted_ids)
    pairs = sel.find_suspicious_pairs(pool + anchors, pilot_seed=args.pilot_seed)
    adj = cfg.get("adjudications") or {}
    unresolved = set(cfg.get("unresolved_ids", []))
    for a, b in pairs:
        for cid in (a, b):
            if adj.get(cid) != "confirmed_unrelated":
                unresolved.add(cid)
    # lineage_review_state proxy: confirmed for every pool row unless config overrides
    # (the 30-min human lineage curation is NOT part of this prep round — see report).
    lineage_states = cfg.get("lineage_states") or {r.content_id_locator: "confirmed" for r in pool}

    _write_json(ws, "suspicious_pairs.json", {
        "pilot_seed": args.pilot_seed, "pairs": [list(p) for p in pairs],
        "unresolved_ids": sorted(unresolved),
        "note": "fail-closed: every emitted suspicious pair recorded unresolved (no adjudication in prep)"})

    res = sel.build_selection(
        rows, pilot_seed=args.pilot_seed, created_from_head=args.head,
        dev_content_ids=dev_ids, dev_lineages=set(cfg.get("dev_lineages", [])),
        scripted_ids=scripted_ids, unresolved_ids=unresolved, lineage_states=lineage_states,
        anchor_rows=anchors, adjudications=adj or None,
    )
    if res.status != "OK":
        _write_json(ws, "selection_status.json", {
            "status": res.status, "reason": res.reason,
            "eligible_lineage_count": res.eligible_lineage_count,
            "suspicious_pairs": len(pairs), "unresolved_rows": len(unresolved)})
        print(json.dumps({"status": res.status, "reason": res.reason,
                          "eligible_lineage_count": res.eligible_lineage_count}))
        return
    _write_jsonl(ws, "lineage_manifest.jsonl", [r.to_dict() for r in res.selected_rows])
    manifest_rows = sel.card_manifest_rows(args.pilot_seed, res.cards)
    write_card_manifest(ws, [m.to_dict() for m in manifest_rows])
    print(json.dumps({"status": "OK", "manifest_id": res.manifest_id, "cards": len(manifest_rows),
                      "suspicious_pairs": len(pairs), "unresolved_rows": len(unresolved)}))


def cmd_enumerate(args, ws):
    """Produce the real-library locators.json + anchors.json from the DB copy in
    scratch/ (spec B3.1). READ-ONLY: opens the COPY (never the live master.db), reads
    ANLZ/audio/v4-cache in place (no mtime/size change). Enriches the 60-row pool +
    the seven anchors ONLY. All live-bridge imports live behind ``real_readers``.
    """
    import dataclasses
    import warnings

    from . import library_adapter as la

    cfg = _load_json(args.config) if args.config else {}
    dev_ids = set(cfg.get("dev_content_ids", []))
    scripted_ids = set(cfg.get("scripted_ids", []))
    readers = la.real_readers(repo_root=str(_repo_root()))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
    db = Rekordbox6Database(args.db_copy, unlock=True)
    try:
        # read every needed ORM attribute into plain LocatorMeta while the session is
        # open — the ORM lazy-loads (e.g. Artist) and detaches once the DB is closed.
        metas = la.list_locators(list(db.get_content()), scripted_ids=scripted_ids)
    finally:
        db.close()
    _write_jsonl(ws, "library_listing.jsonl", [dataclasses.asdict(m) for m in metas])  # audit: all rows, no audio
    by_id = {m.content_id_locator: m for m in metas}
    pool_ids = la.seed_pool_ids(metas, pilot_seed=args.pilot_seed,
                                dev_content_ids=dev_ids, scripted_ids=scripted_ids)
    pool_rows = [la.enrich(by_id[cid], readers) for cid in pool_ids]

    # anchors: F2 plan tier per covered drop drives T2/T3 pinning (real tier_fn).
    def tier_fn(meta, covered):
        import rb_ss_bridge_v2.lighting_moments_v2 as lm  # noqa: WPS433
        import rb_ss_bridge_v2.spectral_cache as sc       # noqa: WPS433
        times = readers.beatgrid_times(meta.analysis_data_path) or []
        v4 = sc.get_cached_v4(meta.audio_path, times)
        plan = lm.build_track_plan(v4, drops=covered, buildups=[], hotcues=[], beatgrid_times_ms=times)
        return [(e.drop_beat, e.decision.tier) for e in plan.entries]

    anchor_rows, pins = la.build_anchor_rows(lambda cid: by_id.get(cid), readers, tier_fn)

    _write_json(ws, "locators.json", [dataclasses.asdict(r) for r in pool_rows])
    _write_json(ws, "anchors.json", [dataclasses.asdict(r) for r in anchor_rows])
    print(json.dumps({"library_rows": len(metas), "pool_rows": len(pool_rows),
                      "anchors": len(anchor_rows), "pinned": pins}))


def _coerce(obj):
    """JSON round-trip a diagnostic descriptor into canonical-safe builtins (floats
    for numpy scalars, lists for tuples). Diagnostics carry raw analyzer output, so
    this keeps it byte-canonical without the descriptor knowing about numpy."""
    return json.loads(json.dumps(obj, default=float))


def cmd_freeze(args, ws):
    """FREEZE stage (spec B3 dev-manifest, B4 all methods, B7 artifacts). Reads the
    frozen selection + gold labels + live v4/F2 (READ-ONLY), runs every method at the
    frozen targets, and writes predictions/contracts/manifests. All writes fenced to
    the workspace; runs inside the CLI's no-network + byte-identity guard."""
    import dataclasses
    import resource
    import time

    from .canonical import sha256_hex
    from .schemas import PredictionHashes, ResourceReport, SCHEMA_VERSION
    from .session import _safe_path, load_card_manifest
    from . import candidates as cand
    from . import freeze as fz
    from . import library_adapter as la

    t0 = time.time()
    seed = args.pilot_seed
    cards = load_card_manifest(_safe_path(ws, "card_manifest.jsonl"))
    lineage = _read_jsonl(_safe_path(ws, "lineage_manifest.jsonl"))
    anchors = _load_json(_safe_path(ws, "anchors.json"))
    listing = _read_jsonl(_safe_path(ws, "library_listing.jsonl"))
    gold = _load_json(args.gold)["rows"]
    cfg = _load_json(args.config) if args.config else {}
    dev_ids = set(cfg.get("dev_content_ids", []))

    meta = {m["content_id_locator"]: m for m in listing}
    tid_map = {r["track_instance_id"]: (r["content_id_locator"], r["recording_lineage_id"],
                                        r["audio_duplicate_group"]) for r in lineage}
    readers = la.real_readers(repo_root=str(_repo_root()))

    # --- live read closures (v4 cached once per track) ---
    _v4c = {}

    def _v4(cid):
        if cid not in _v4c:
            import rb_ss_bridge_v2.spectral_cache as sc
            m = meta.get(cid)
            times = readers.beatgrid_times(m["analysis_data_path"]) or [] if m else []
            v4 = sc.get_cached_v4(m["audio_path"], times) if (m and times) else None
            _v4c[cid] = (v4, times)
        return _v4c[cid]

    def window_fn(cid, beat):
        import rb_ss_bridge_v2.spectral_profile as sp
        v4, _ = _v4(cid)
        if v4 is None or int(beat) < 0:
            return None
        win = sp.drop_window_vector(v4, int(beat), width=16)
        return win if win.get("coverage", 0.0) >= 16.0 else None

    def plan_fn(cid, beat):
        import rb_ss_bridge_v2.lighting_moments_v2 as lm
        v4, times = _v4(cid)
        if v4 is None:
            return None
        plan = lm.build_track_plan(v4, [int(beat)], [], hotcues=[], beatgrid_times_ms=times)
        if not plan.entries:
            return None
        d = plan.entries[0].decision
        return (d.family, d.tier)

    def baseline_fn(method, cid, beat):
        v4, _ = _v4(cid)
        if v4 is None:
            return None
        if method == cand.DIAG_HARDNESS:
            import rb_ss_bridge_v2.hardness_v0 as h0
            drops = [int(b) for b in (readers.phrase_drops(meta[cid]["analysis_data_path"]) or [])]
            baseline = h0.track_baseline(v4, drops)
            return _coerce(cand.diagnostic_hardness_v0(v4, int(beat), baseline))
        # NOTE (assumption): diagnostic approach window = 16 beats (one phrase, matches the
        # drop_window_vector width). Diagnostics are never in integrated PASS (spec B4).
        af = cand.diagnostic_approach_v0(v4, int(beat), approach_len=16)
        return _coerce(dataclasses.asdict(af))

    sha_by_cid = {cid: (readers.audio_sha256(meta[cid]["audio_path"]) if cid in meta else "cid:" + cid)
                  for cid in dev_ids}
    label_hashes = {p.name: sha256_hex(p.read_text(encoding="utf-8"))
                    for p in sorted((_repo_root() / "local" / "labels").glob("*")) if p.is_file()}

    # --- dev manifest, scalers, contracts (spec B3/B4) ---
    dm = fz.build_dev_manifest(pilot_seed=seed, gold_rows=gold, dev_content_ids=dev_ids,
                               sha_by_cid=sha_by_cid, window_fn=window_fn, anchor_rows=anchors,
                               label_hashes=label_hashes)
    scalers = fz.fit_scalers(dm)
    code_hash = sha256_hex([(Path(fz.__file__).read_text(encoding="utf-8")),
                            (Path(cand.__file__).read_text(encoding="utf-8"))])
    contracts = fz.candidate_contracts(pilot_seed=seed, scalers=scalers,
                                       dev_manifest_hash=dm.hash, code_hash=code_hash)

    # --- run every method at the frozen targets ---
    card_manifest_hash = sha256_hex(cards)
    method_rows = fz.run_all_methods(pilot_seed=seed, cards=cards, resolve=lambda t: tid_map[t],
                                     window_fn=window_fn, plan_fn=plan_fn, dev=dm, scalers=scalers,
                                     manifest_hash=card_manifest_hash, baseline_fn=baseline_fn)

    # --- write artifacts (all fenced) ---
    _write_json(ws, "development_training_manifest.json", dm.manifest)
    _write_json(ws, "candidate_contracts.json", {"contracts": [c.to_dict() for c in contracts]})
    (ws / "predictions").mkdir(exist_ok=True)
    method_hashes = {}
    counts = {}
    for method, rws in method_rows.items():
        _write_jsonl(ws, f"predictions/{method}.jsonl", rws)
        method_hashes[method] = sha256_hex(rws)
        counts[method] = _axis_counts(rws)
    ph = PredictionHashes(schema_version=SCHEMA_VERSION, pilot_seed=seed, method_hashes=method_hashes,
                          card_manifest_hash=card_manifest_hash, lineage_manifest_hash=sha256_hex(lineage),
                          freeze_utc=args.utc)
    _write_json(ws, "prediction_hashes.json", ph.to_dict())

    # artifact manifest: every artifact written + the session-time placeholders (spec B7)
    artifacts = ["development_training_manifest.json", "candidate_contracts.json",
                 "prediction_hashes.json", "lineage_manifest.jsonl", "card_manifest.jsonl",
                 "locators.json", "anchors.json"] + [f"predictions/{m}.jsonl" for m in sorted(method_rows)]
    art_rows = []
    for name in artifacts:
        p = _safe_path(ws, name)
        art_rows.append({"name": name, "present": p.exists(),
                         "sha256": sha256_hex(p.read_bytes().decode("utf-8")) if p.exists() else None,
                         "size_bytes": (p.stat().st_size if p.exists() else 0)})
    # playbacks.jsonl is written at session time — recorded as a placeholder here (spec B7 §387)
    for name in ("playbacks.jsonl", "responses.jsonl", "metrics.json", "verdict.json", "report.md"):
        art_rows.append({"name": name, "present": False, "sha256": None, "size_bytes": 0,
                         "note": "session-time artifact; placeholder at freeze"})
    _write_json(ws, "artifact_manifest.json", {"pilot_seed": seed, "freeze_utc": args.utc,
                                               "artifacts": art_rows})

    # resource report (telemetry only; ceilings from the dispatch)
    wall = time.time() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes on macOS
    scratch = sum(f.stat().st_size for f in (ws / "scratch").rglob("*") if f.is_file())
    retained = sum(f.stat().st_size for f in ws.rglob("*")
                   if f.is_file() and "scratch" not in f.relative_to(ws).parts)
    ceilings = {"wall_seconds": 1800, "rss_bytes": 2 * 1024**3,
                "scratch_bytes": 500 * 1024**2, "retained_bytes": 50 * 1024**2}
    breaches = [k for k, v in {"wall_seconds": wall, "rss_bytes": rss,
                               "scratch_bytes": scratch, "retained_bytes": retained}.items() if v > ceilings[k]]
    rr = ResourceReport(schema_version=SCHEMA_VERSION, pilot_seed=seed, analysis_wall_seconds=round(wall, 2),
                        peak_rss_bytes=int(rss), scratch_peak_bytes=int(scratch), retained_bytes=int(retained),
                        manual_prep_minutes=0.0, human_active_seconds=0.0, decisions_total=0,
                        cleanup_seconds=0.0, ceilings=ceilings, breaches=breaches)
    _write_json(ws, "resource_report.json", rr.to_dict())

    print(json.dumps({"dev_manifest_hash": dm.hash, "dev_rows": len(dm.dev_rows),
                      "dev_montages": len(dm.dev_montages), "method_hashes": method_hashes,
                      "counts": counts, "card_manifest_hash": card_manifest_hash,
                      "wall_s": round(wall, 1), "breaches": breaches}))


def _axis_counts(rows):
    """Per-axis (prediction, abstention) counts for a method's rows."""
    out = {}
    for r in rows:
        ax = r.get("axis", "diagnostic")
        p, a = out.get(ax, (0, 0))
        out[ax] = (p + (0 if r.get("abstained") else 1), a + (1 if r.get("abstained") else 0))
    return {k: {"predicted": v[0], "abstained": v[1]} for k, v in out.items()}


def cmd_session(args, ws):
    import datetime

    from .session import _safe_path, SessionRunner

    script = _load_json(args.answers)                  # {session_index, resume?, actions:[...]}

    def clock():
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def local_date():
        return datetime.date.today().isoformat()

    runner = SessionRunner.from_manifest_file(
        ws, _safe_path(ws, "card_manifest.jsonl"), pilot_seed=args.pilot_seed,
        clock=clock, local_date=local_date,
        expected_methods=(args.methods.split(",") if args.methods else None),
    )
    runner.start_session(script["session_index"], resume=script.get("resume", False))
    for act in script["actions"]:
        kind = act["kind"]
        if kind == "play":
            runner.play(act["card_id"])
        elif kind == "skip":
            runner.skip(act["card_id"])
        elif kind == "commit":
            runner.commit(act["card_id"], act["question"], act["displayed"], act["canonical"],
                          recognized=act.get("recognized", False),
                          response_seconds=act["response_seconds"])
        else:
            raise ValueError(f"unknown session action kind: {kind!r}")
    print(json.dumps({"decisions": runner.decisions_total(),
                      "active_seconds": runner.active_seconds()}))


def cmd_score(args, ws):
    from . import verdict

    inp = _load_json(args.inputs)                      # {verdict_inputs: {...}, metrics: {...}}
    v = verdict.compute_verdict(**inp["verdict_inputs"])
    _write_json(ws, "verdict.json", v.to_dict())
    _write_json(ws, "metrics.json", inp.get("metrics", {}))
    print(json.dumps({"integrated": v.integrated}))


# --- guarded dispatch --------------------------------------------------------
def _run_guarded(watch_paths, fn):
    """Run ``fn`` under the no-network guard and a byte-identity check over the
    watch set (spec B11c/d). The watch set must exclude the workspace itself — the
    pilot writes there by design; it must NOT touch the live dirs it watches.
    """
    from .guards import assert_unchanged, listing_hash, no_network_guard
    with no_network_guard():
        before = listing_hash(watch_paths)
        result = fn()
        after = listing_hash(watch_paths)
        assert_unchanged(before, after)
        return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m tools.spectral_pilot")
    parser.add_argument("--workspace", required=True, help="pilot workspace (all writes fenced here)")
    parser.add_argument("--pilot-seed", default="spectral-ai-pilot-v1-790c625-2026-07-14")
    parser.add_argument("--watch", action="append", default=[],
                        help="a live dir to prove unchanged; repeatable (never the workspace)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("enumerate")
    pe.add_argument("--db-copy", required=True, help="path to the master.db COPY in scratch/ (never the live DB)")
    pe.add_argument("--config")

    ps = sub.add_parser("select")
    ps.add_argument("--locators", required=True)
    ps.add_argument("--anchors")
    ps.add_argument("--config")
    ps.add_argument("--head", default="unknown")

    pf = sub.add_parser("freeze")
    pf.add_argument("--gold", required=True, help="gold_drop_labels JSON (read-only dev targets)")
    pf.add_argument("--config")
    pf.add_argument("--utc", default="1970-01-01T00:00:00+00:00")

    pn = sub.add_parser("session")
    pn.add_argument("--answers", required=True)
    pn.add_argument("--methods", default=None)

    pc = sub.add_parser("score")
    pc.add_argument("--inputs", required=True)

    args = parser.parse_args(argv)
    ws = _resolve_workspace(args.workspace)
    _configure_logging(ws)      # before importing any package internals below
    if args.cmd in ("enumerate", "freeze"):
        _warm_bridge_imports()  # before no_network_guard patches socket (ssl subclasses it)
    dispatch = {"enumerate": cmd_enumerate, "select": cmd_select, "freeze": cmd_freeze,
                "session": cmd_session, "score": cmd_score}[args.cmd]
    _run_guarded([Path(w) for w in args.watch], lambda: dispatch(args, ws))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
