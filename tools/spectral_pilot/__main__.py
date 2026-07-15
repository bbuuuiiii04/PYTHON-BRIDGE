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
    import rb_ss_bridge_v2.filepath_resolver  # noqa: F401
    import rb_ss_bridge_v2.lighting_moments_v2  # noqa: F401
    import rb_ss_bridge_v2.spectral_cache     # noqa: F401


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


def cmd_freeze(args, ws):
    from .canonical import jsonl_line, sha256_hex
    from .schemas import PredictionHashes, PredictionRow, SCHEMA_VERSION
    from .session import _safe_path, load_card_manifest

    preds = _load_json(args.predictions)               # {method: [prediction_row_dicts]}
    (ws / "predictions").mkdir(exist_ok=True)
    method_hashes = {}
    for method, prows in preds.items():
        for r in prows:
            PredictionRow.from_dict(r)                  # validate before freezing
        path = _safe_path(ws, f"predictions/{method}.jsonl")
        with path.open("wb") as fh:
            for r in prows:
                fh.write(jsonl_line(r))
        method_hashes[method] = sha256_hex(prows)
    cards = load_card_manifest(_safe_path(ws, "card_manifest.jsonl"))
    lineage = _read_jsonl(_safe_path(ws, "lineage_manifest.jsonl"))
    ph = PredictionHashes(
        schema_version=SCHEMA_VERSION, pilot_seed=args.pilot_seed, method_hashes=method_hashes,
        card_manifest_hash=sha256_hex(cards), lineage_manifest_hash=sha256_hex(lineage),
        freeze_utc=args.utc,
    )
    _write_json(ws, "prediction_hashes.json", ph.to_dict())
    print(json.dumps({"frozen_methods": sorted(method_hashes)}))


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
    pf.add_argument("--predictions", required=True)
    pf.add_argument("--utc", default="1970-01-01T00:00:00+00:00")

    pn = sub.add_parser("session")
    pn.add_argument("--answers", required=True)
    pn.add_argument("--methods", default=None)

    pc = sub.add_parser("score")
    pc.add_argument("--inputs", required=True)

    args = parser.parse_args(argv)
    ws = _resolve_workspace(args.workspace)
    _configure_logging(ws)      # before importing any package internals below
    if args.cmd == "enumerate":
        _warm_bridge_imports()  # before no_network_guard patches socket (ssl subclasses it)
    dispatch = {"enumerate": cmd_enumerate, "select": cmd_select, "freeze": cmd_freeze,
                "session": cmd_session, "score": cmd_score}[args.cmd]
    _run_guarded([Path(w) for w in args.watch], lambda: dispatch(args, ws))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
