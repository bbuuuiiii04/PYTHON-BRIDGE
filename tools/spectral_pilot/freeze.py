"""Freeze-stage engine for the Phase-0 pilot (spec B3 dev-manifest, B4 methods, B7).

PURE + INJECTABLE. Every live read (v4 window vector, F2 plan, audio SHA) is passed
in as a callable, so this module is deterministic by construction and unit-tested on
synthetic fixtures — the CLI (`__main__.cmd_freeze`) wires the real read-only bridge
surfaces. Two freeze runs over an unchanged cache therefore reproduce byte-identical
prediction rows (spec B4/B11 determinism).

Target derivation (spec-anchored; assumptions flagged NOTE and reported at handoff):
- genuine target  = gold `is_genuine_drop`  (True→genuine, False→not_genuine; null row
  excluded from the genuine axis).
- hardness target = gold `drop.tier` ∈ {1,2,3} → T1/T2/T3 (genuine drops only).
- family target   = gold `drop.family` → {house→HOUSE, comet→COMET, wall→WALL,
  neutral→none} (genuine drops only); a two-row montage reduces via the spec's own
  two-moment rule (spec §255-256: both match → that family, differ → mixed).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from . import candidates as cand
from .canonical import environment_lock, sha256_hex
from .firewall import ALLOWLIST, EligibleDevelopmentRow, build_query_row
from .schemas import SCHEMA_VERSION, CandidateContract
from .selection import track_instance_id

# gold enum → protocol enum maps (spec B3.7 family vocabulary, B4 tier ordinals)
_FAMILY_MAP = {"house": "HOUSE", "comet": "COMET", "wall": "WALL", "neutral": "none"}
_TIER_MAP = {1: "T1", 2: "T2", 3: "T3"}
# every method version the freeze runs, canonical order
PREDICTION_METHODS = (cand.BASELINE_A, cand.BASELINE_B, cand.CANDIDATE_C)
DIAGNOSTIC_METHODS = (cand.DIAG_HARDNESS, cand.DIAG_APPROACH)
STABILITY_SHIFTS = (-2, -1, 1, 2)   # spec B8: recompute each central marker at beat deltas -2,-1,+1,+2


def reduce_family(fa: str, fb: str) -> str:
    """Two-moment montage family (spec §255-256): both sides match → that family,
    otherwise → mixed. Sides are already mapped to the protocol vocabulary."""
    return fa if fa == fb else "mixed"


# --- development training manifest (spec B3 §238) ----------------------------
@dataclass(frozen=True)
class DevManifest:
    manifest: dict          # the frozen manifest document (carries its own output hash)
    dev_rows: tuple         # EligibleDevelopmentRow, genuine/hardness neighbours
    dev_montages: tuple     # (lineage_id, descriptor_features dict, family_target)

    @property
    def hash(self) -> str:
        return self.manifest["output_hash"]


def build_dev_manifest(*, pilot_seed, gold_rows, dev_content_ids, sha_by_cid,
                       window_fn, anchor_rows, label_hashes) -> DevManifest:
    """Freeze development rows + per-axis targets from the gold labels (read-only).

    ``gold_rows``   : list of gold label dicts (content_id, marker_beat,
                      is_genuine_drop, drop{tier,family}).
    ``sha_by_cid``  : content_id -> audio_sha256 (dev tracks, for lineage/dup + montage order).
    ``window_fn``   : (content_id, marker_beat) -> allowlist window dict or None
                      (None = missing/invalid v4 or off-grid → row excluded, spec B10).
    ``anchor_rows`` : the seven frozen anchor LocatorRow dicts (recorded, not trained on).
    Incomplete rows train only the axes they carry (spec §241).
    """
    dev = set(str(c) for c in dev_content_ids)
    dev_rows, exclusions, drop_records = [], [], []
    # collect per-lineage genuine drops (for the family montage) as we go
    per_lineage_genuine = {}
    for r in gold_rows:
        cid = str(r.get("content_id"))
        if cid not in dev:
            continue
        genuine = r.get("is_genuine_drop")
        if genuine is None:
            continue                                   # null = unlabeled, excluded (spec header)
        beat = int(r["marker_beat"])
        win = window_fn(cid, beat)
        if win is None:
            exclusions.append({"content_id": cid, "marker_beat": beat, "reason": "missing_or_invalid_v4"})
            continue
        frozen, reasons = build_query_row(win, query_lineage_id=cid, query_duplicate_group=cid,
                                          marker_beat=beat)
        if frozen is None:
            exclusions.append({"content_id": cid, "marker_beat": beat, "reason": ",".join(reasons)})
            continue
        targets = {"genuine": "genuine" if genuine else "not_genuine"}
        fam = None
        if genuine:
            drop = r.get("drop") or {}
            tier = drop.get("tier")
            if tier in _TIER_MAP:
                targets["hardness"] = _TIER_MAP[tier]
            fam = _FAMILY_MAP.get(str(drop.get("family")))
        sha = sha_by_cid.get(cid, "cid:" + cid)        # NOTE: fallback keeps lineage self-exclusion
        dev_rows.append(EligibleDevelopmentRow(
            features=dict(frozen.features), coverage=frozen.coverage,
            recording_lineage_id=cid, audio_duplicate_group=sha,
            track_instance_id=track_instance_id(pilot_seed, cid), marker_beat=beat, targets=targets))
        drop_records.append({"content_id": cid, "marker_beat": beat,
                             "targets": dict(targets), "family_drop": fam})
        if genuine and fam is not None:
            per_lineage_genuine.setdefault(cid, []).append((beat, fam, dict(frozen.features)))

    # family montages: per lineage with >=2 labelled genuine drops, the two markers
    # ordered by SHA256(audio_sha256 || marker_beat) (spec B3.4), reduced to one family.
    dev_montages = []
    for cid, drops in sorted(per_lineage_genuine.items()):
        if len(drops) < 2:
            continue
        sha = sha_by_cid.get(cid, "cid:" + cid)
        two = sorted(drops, key=lambda d: sha256_hex([sha, d[0]]))[:2]
        desc = cand.montage_descriptor_features(two[0][2], two[1][2])
        fam_target = reduce_family(two[0][1], two[1][1])
        dev_montages.append((cid, desc, fam_target))

    # per-axis permitted targets (spec §239) = the target dicts actually carried
    axis_counts = {ax: sum(1 for d in dev_rows if ax in d.targets) for ax in ("genuine", "hardness")}
    axis_counts["family"] = len(dev_montages)
    manifest = {
        "schema_version": SCHEMA_VERSION, "pilot_seed": pilot_seed,
        "dev_content_ids": sorted(dev),
        "dev_row_ids": sorted(d.track_instance_id for d in dev_rows),
        "drop_records": sorted(drop_records, key=lambda d: (d["content_id"], d["marker_beat"])),
        "montage_lineages": sorted(m[0] for m in dev_montages),
        "exclusions": sorted(exclusions, key=lambda d: (d["content_id"], d["marker_beat"])),
        "per_axis_target_counts": axis_counts,
        "lineage_groups": sorted({d.recording_lineage_id for d in dev_rows}),
        "duplicate_groups": sorted({d.audio_duplicate_group for d in dev_rows}),
        "scaler_population_ids": sorted(d.track_instance_id for d in dev_rows),
        "label_file_hashes": dict(sorted(label_hashes.items())),
        "label_provenance": "head: unknown",           # spec §240 provenance limitation retained
        "anchor_rows": sorted((a.get("content_id_locator") for a in anchor_rows)),
    }
    manifest["output_hash"] = sha256_hex(manifest)
    return DevManifest(manifest=manifest, dev_rows=tuple(dev_rows), dev_montages=tuple(dev_montages))


# --- frozen scalers (spec B4 candidate C) ------------------------------------
@dataclass(frozen=True)
class Scalers:
    marker: cand.ScalerStats            # 17-field marker space
    family: cand.ScalerStats            # montage descriptor space


class _PopRow:
    """Minimal row for fit_scaler (needs .features/.recording_lineage_id/
    .track_instance_id/.marker_beat)."""
    def __init__(self, features, lineage, tid, beat):
        self.features = features
        self.recording_lineage_id = lineage
        self.track_instance_id = tid
        self.marker_beat = beat


def fit_scalers(dev: DevManifest) -> Scalers:
    """Fit both frozen scalers over the development population (spec B4c)."""
    marker = cand.fit_scaler(list(dev.dev_rows), allowlist=ALLOWLIST)
    fam_pop = [_PopRow(desc, lineage, lineage, 0) for lineage, desc, _ in dev.dev_montages]
    family = cand.fit_scaler(fam_pop, allowlist=cand.FAMILY_ALLOWLIST)
    return Scalers(marker=marker, family=family)


# --- candidate contracts (spec B7) -------------------------------------------
def candidate_contracts(*, pilot_seed, scalers: Scalers, dev_manifest_hash, code_hash) -> list:
    """One contract row per method (spec B7). Only candidate C is scaler-bound (the
    17-field marker space); the family-space scaler is a sub-artifact of the same
    method. Baselines/diagnostics carry no scaler, so their scaler fields are empty."""
    env_hash = sha256_hex(environment_lock())
    out = []
    for method in PREDICTION_METHODS + DIAGNOSTIC_METHODS:
        bound = method == cand.CANDIDATE_C
        out.append(CandidateContract(
            schema_version=SCHEMA_VERSION, pilot_seed=pilot_seed, method_version=method,
            positive_allowlist=list(ALLOWLIST),
            scaler_population_hash=(scalers.marker.scaler_population_hash if bound else ""),
            retained_field_hash=(scalers.marker.retained_field_hash if bound else ""),
            code_hash=code_hash, environment_lock_hash=env_hash,
            development_manifest_hash=dev_manifest_hash))
    return out


# --- run every method at the frozen targets (spec B4d) -----------------------
def run_all_methods(*, pilot_seed, cards, resolve, window_fn, plan_fn, dev: DevManifest,
                    scalers: Scalers, manifest_hash, baseline_fn=None) -> dict:
    """Produce {method_version: [row_dict, ...]} for every method.

    ``cards``     : validated card_manifest dicts (36 marker_state + 18 family_montage
                    drive the targets; repeats/anchor_confirm are not prediction targets).
    ``resolve``   : track_instance_id -> (content_id, recording_lineage_id, audio_duplicate_group).
    ``window_fn`` : (content_id, beat) -> allowlist window dict or None.
    ``plan_fn``   : (content_id, beat) -> (f2_family:str, f2_tier:int|None) or None.
    ``baseline_fn``: optional (content_id, beat) -> hardness_v0 diagnostic dict / approach
                    dict; wired only for the diagnostics (kept out of the pure core).
    """
    prov = dict(pilot_seed=pilot_seed, manifest_hash=manifest_hash)
    rows = {m: [] for m in PREDICTION_METHODS + DIAGNOSTIC_METHODS}
    dev_rows = list(dev.dev_rows)
    dev_montages = [_MontRow(lin, desc, fam) for lin, desc, fam in dev.dev_montages]

    for c in cards:
        ct = c["card_type"]
        if ct == "marker_state":
            _marker_targets(rows, c, resolve, window_fn, plan_fn, dev_rows, scalers, prov, baseline_fn)
        elif ct == "family_montage":
            _montage_targets(rows, c, resolve, window_fn, plan_fn, dev_montages, scalers, prov)
    return rows


class _MontRow:
    def __init__(self, lineage, features, family):
        self.features = features
        self.recording_lineage_id = lineage
        self.audio_duplicate_group = lineage
        self.track_instance_id = lineage
        self.marker_beat = 0
        self.targets = {"family": family}


def _ih(win) -> str:
    """Real per-target input hash over the frozen query window (spec B4)."""
    return sha256_hex(win if win is not None else {"abstain": True})


def _marker_targets(rows, c, resolve, window_fn, plan_fn, dev_rows, scalers, prov, baseline_fn):
    tid = c["track_instance_id"]
    cid, lineage, dup = resolve(tid)
    beat = int(c["marker_beat"])
    tgt = c["card_id"]
    anchor_tier = c["anchor_role"]                       # frozen B3.5 assignment (T1/T2/T3)
    win = window_fn(cid, beat)
    plan = plan_fn(cid, beat)
    ih = _ih(win)

    # baseline A: genuine abstains; hardness = F2 marker tier vs anchor role tier
    rows[cand.BASELINE_A].append(cand.predict_baseline_a_genuine(tgt, input_hash=ih, **prov).to_dict())
    marker_tier = _TIER_MAP.get(plan[1]) if (plan and plan[1] in _TIER_MAP) else None
    rows[cand.BASELINE_A].append(
        cand.predict_baseline_a_hardness(tgt, marker_tier, anchor_tier, input_hash=ih, **prov).to_dict())
    # baseline B: development majority (genuine)
    rows[cand.BASELINE_B].append(
        cand.predict_baseline_b_genuine(tgt, dev_rows, input_hash=ih, **prov).to_dict())
    # candidate C: retrieval genuine + hardness at the frozen marker, then the -2,-1,+1,+2 shifts
    for shift in (0,) + STABILITY_SHIFTS:
        stgt = tgt if shift == 0 else f"{tgt}@{shift:+d}"
        swin = win if shift == 0 else window_fn(cid, beat + shift)
        sih = _ih(swin)
        frozen, reasons = (None, ["missing_or_invalid_v4"]) if swin is None else \
            build_query_row(swin, query_lineage_id=lineage, query_duplicate_group=dup, marker_beat=beat + shift)
        if frozen is None:
            rows[cand.CANDIDATE_C].append(cand.abstain(cand.CANDIDATE_C, "genuine", stgt, reasons,
                                                       input_hash=sih, **prov).to_dict())
            rows[cand.CANDIDATE_C].append(cand.abstain(cand.CANDIDATE_C, "hardness", stgt, reasons,
                                                       input_hash=sih, **prov).to_dict())
            continue
        rows[cand.CANDIDATE_C].append(cand.predict_retrieval_genuine(
            frozen, dev_rows, scalers.marker, stgt, input_hash=sih, **prov).to_dict())
        rows[cand.CANDIDATE_C].append(cand.predict_retrieval_hardness(
            frozen, dev_rows, scalers.marker, stgt, anchor_tier, input_hash=sih, **prov).to_dict())

    # diagnostics (never in integrated PASS): raw descriptor rows, not axis predictions
    if baseline_fn is not None:
        for method in DIAGNOSTIC_METHODS:
            desc = baseline_fn(method, cid, beat)
            rows[method].append({"schema_version": SCHEMA_VERSION, "pilot_seed": prov["pilot_seed"],
                                 "method_version": method, "target_id": tgt, "marker_beat": beat,
                                 "descriptor": desc, "abstained": desc is None})


def _montage_targets(rows, c, resolve, window_fn, plan_fn, dev_montages, scalers, prov):
    tid = c["track_instance_id"]
    cid, lineage, dup = resolve(tid)
    wins = c["clip_spec"]["windows"]
    # scored moment is the marker beat, not the run-in start (spec B7 amended clip rule);
    # keying off start_beat would drag montage features back by the presentation run-in.
    beats = [int(w["marker_beat"]) for w in wins]
    tgt = c["card_id"]
    # baseline A family from the two F2 plan families
    pa, pb = plan_fn(cid, beats[0]), plan_fn(cid, beats[1])
    fam_a = pa[0] if pa else None
    fam_b = pb[0] if pb else None
    ih = sha256_hex({"beats": beats})
    rows[cand.BASELINE_A].append(
        cand.predict_baseline_a_family(tgt, fam_a, fam_b, input_hash=ih, **prov).to_dict())
    # candidate C family over the two-window montage descriptor
    wa, wb = window_fn(cid, beats[0]), window_fn(cid, beats[1])
    if wa is None or wb is None:
        rows[cand.CANDIDATE_C].append(cand.abstain(cand.CANDIDATE_C, "family", tgt,
                                                   ["missing_or_invalid_v4"], input_hash=ih, **prov).to_dict())
        return
    desc = cand.montage_descriptor_features(wa, wb)
    query = _MontRow(lineage, desc, None)
    query.audio_duplicate_group = dup
    rows[cand.CANDIDATE_C].append(cand.predict_retrieval_family(
        query, dev_montages, scalers.family, tgt, input_hash=ih, **prov).to_dict())
