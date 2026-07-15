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


# --- subcommands -------------------------------------------------------------
def cmd_select(args, ws):
    from . import selection as sel
    from .selection import LocatorRow
    from .session import write_card_manifest

    cfg = _load_json(args.config) if args.config else {}
    rows = []
    for d in _load_json(args.locators):
        d = dict(d)
        d["candidate_markers"] = tuple(d.get("candidate_markers", []))
        rows.append(LocatorRow(**d))
    res = sel.build_selection(
        rows, pilot_seed=args.pilot_seed, created_from_head=args.head,
        dev_content_ids=set(cfg.get("dev_content_ids", [])),
        dev_lineages=set(cfg.get("dev_lineages", [])),
        scripted_ids=set(cfg.get("scripted_ids", [])),
        unresolved_ids=set(cfg.get("unresolved_ids", [])),
        lineage_states=cfg.get("lineage_states", {}),
        adjudications=cfg.get("adjudications"),
    )
    if res.status != "OK":
        print(json.dumps({"status": res.status, "reason": res.reason}))
        return
    _write_jsonl(ws, "lineage_manifest.jsonl", [r.to_dict() for r in res.selected_rows])
    manifest_rows = sel.card_manifest_rows(args.pilot_seed, res.cards)
    write_card_manifest(ws, [m.to_dict() for m in manifest_rows])
    print(json.dumps({"status": "OK", "manifest_id": res.manifest_id, "cards": len(manifest_rows)}))


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

    ps = sub.add_parser("select")
    ps.add_argument("--locators", required=True)
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
    dispatch = {"select": cmd_select, "freeze": cmd_freeze,
                "session": cmd_session, "score": cmd_score}[args.cmd]
    _run_guarded([Path(w) for w in args.watch], lambda: dispatch(args, ws))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
