#!/usr/bin/env python3
"""Oracle-based canonicalization of MIXED/edited scripted tracks.

Read-only research tool. Reverse-engineering aid only; NOT a bridge runtime
dependency (no bridge module may import this; see AGENTS.md §6).

Problem it solves
-----------------
Edited/legacy SoundSwitch ``.ssfile`` timelines are MIXED: the per-record cue
reference convention (one-based vs direct) varies with no per-record byte
discriminator, so ``raw_ref -> cue`` cannot be resolved from the stored file
alone (see docs/research/soundswitch/soundswitch_re_closure_report.md, claim 10/12).

This module bypasses that ambiguity using an **observed-wire oracle**: for each
captured event it finds the Venue cue composition (layered render model:
pattern cue + decoupled color cue + independent strobe channel) that reproduces
the observed Universe-0 CH1-19 frame. The result is a provenance-free canonical
timeline of ``(elapsed_ms -> resolved composition / literal frame)`` that is, by
construction, byte-exact against the capture. Anything the cue model cannot
express is stored as a literal frame, so playback is always byte-exact.

The captured frame is used ONLY as a verification oracle, never as renderer
seed/state (mirrors the closure-spec invariant).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

CHANNEL_COUNT = 19
# Independent control channels in the layered render model: color (CH8),
# color-speed (CH9), strobe (CH11). These persist across a raw-0 clear.
CONTROL_CHANNELS = (8, 9, 11)
MAIN_CHANNELS = tuple(c for c in range(1, CHANNEL_COUNT + 1) if c not in CONTROL_CHANNELS)
ZERO_FRAME = tuple([0] * CHANNEL_COUNT)


@dataclass(frozen=True)
class Cue:
    name: str
    guid: str
    patch: dict  # {channel(1..19): value}


@dataclass
class Resolution:
    kind: str  # clear | cue | cue+color | cue+color+strobe | persist | literal
    pattern_guid: str | None = None
    color_guid: str | None = None
    strobe_value: int | None = None
    frame: tuple = ZERO_FRAME


def apply_patch(state, patch) -> list:
    out = list(state)
    for channel, value in patch.items():
        out[channel - 1] = value
    return out


def is_clear(prior, observed) -> bool:
    """Raw-0 clear: main channels zeroed, control channels persisted."""
    if any(observed[c - 1] != 0 for c in MAIN_CHANNELS):
        return False
    return all(observed[c - 1] == prior[c - 1] for c in CONTROL_CHANNELS)


def resolve_frame(prior, observed, cuelib, colorcues) -> Resolution:
    """Pure function: find the cue composition reproducing ``observed``.

    Resolution order (most specific structural meaning first):
      1. exact persist (no change)
      2. raw-0 clear (main zero, control persist)
      3. single pattern cue
      4. pattern cue + decoupled color cue
      5. pattern cue + color cue + independent strobe (CH11) value
      6. literal frame fallback (always byte-exact)
    """
    observed = tuple(observed)
    if tuple(prior) == observed:
        return Resolution("persist", frame=observed)
    if is_clear(prior, observed):
        return Resolution("clear", frame=observed)
    for cue in cuelib:
        if tuple(apply_patch(prior, cue.patch)) == observed:
            return Resolution("cue", pattern_guid=cue.guid, frame=observed)
    for cue in cuelib:
        base = apply_patch(prior, cue.patch)
        for color in colorcues:
            if tuple(apply_patch(base, color.patch)) == observed:
                return Resolution("cue+color", pattern_guid=cue.guid,
                                  color_guid=color.guid, frame=observed)
    for cue in cuelib:
        base = apply_patch(prior, cue.patch)
        for color in colorcues:
            b2 = apply_patch(base, color.patch)
            if b2[10] != observed[10]:
                b2 = list(b2)
                b2[10] = observed[10]
            if tuple(b2) == observed:
                return Resolution("cue+color+strobe", pattern_guid=cue.guid,
                                  color_guid=color.guid, strobe_value=observed[10],
                                  frame=observed)
    return Resolution("literal", frame=observed)


def render_resolution(prior, res: Resolution, cue_by_guid) -> tuple:
    """Re-render a Resolution to a frame (verification path, no oracle input)."""
    if res.kind in ("persist", "clear", "literal"):
        return res.frame
    state = apply_patch(prior, cue_by_guid[res.pattern_guid].patch)
    if res.color_guid is not None:
        state = apply_patch(state, cue_by_guid[res.color_guid].patch)
    if res.strobe_value is not None:
        state = list(state)
        state[10] = res.strobe_value
    return tuple(state)


def load_cuelib(venue_path: Path, group: str = "0x493"):
    import parse_venue_cues as pvc  # local import; research-only dependency

    data = venue_path.read_bytes()
    cuelib = []
    for cue in pvc.parse_venue_cues(data):
        groups = cue.get("groups", {})
        if group in groups:
            patch = {int(k): v for k, v in groups[group].items()}
            cuelib.append(Cue(cue["name"], cue["cue_guid"], patch))
    colorcues = [c for c in cuelib if set(c.patch) <= {1, 8, 9}]
    return cuelib, colorcues


def canonicalize(observed_sequence, cuelib, colorcues):
    """Return (pack, stats). ``observed_sequence`` = list of (elapsed_ms, frame)."""
    cue_by_guid = {c.guid: c for c in cuelib}
    pack = []
    prior = list(ZERO_FRAME)
    stats: dict = {}
    literal_events = []
    for elapsed, frame in observed_sequence:
        frame = tuple(frame)
        res = resolve_frame(prior, frame, cuelib, colorcues)
        # verification: the recorded resolution must re-render to the frame
        assert render_resolution(prior, res, cue_by_guid) == frame, (elapsed, res)
        pack.append({
            "elapsed_ms": elapsed,
            "kind": res.kind,
            "pattern_guid": res.pattern_guid,
            "color_guid": res.color_guid,
            "strobe_value": res.strobe_value,
            "frame": list(frame),
        })
        if res.kind == "literal":
            literal_events.append(elapsed)
        stats[res.kind] = stats.get(res.kind, 0) + 1
        prior = list(frame)
    total = len(observed_sequence)
    cue_resolved = total - stats.get("literal", 0)
    return pack, {
        "total_events": total,
        "by_kind": stats,
        "cue_resolved": cue_resolved,
        "literal_fallback": stats.get("literal", 0),
        "cue_resolution_rate_pct": (100 * cue_resolved // total) if total else 0,
        "byte_exact": True,  # guaranteed: every entry re-renders to its frame (asserted above)
        "literal_event_elapsed_ms": literal_events,
    }


def _events_from_validator_json(path: Path):
    data = json.loads(path.read_text())
    seq = []
    for event in data.get("events", []):
        frame = event.get("observed_wire_state")
        if frame:
            seq.append((event.get("time"), frame))
    return seq


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("validator_json", type=Path,
                        help="final validator report (has events[].observed_wire_state)")
    parser.add_argument("venue", type=Path, help="SoundSwitchVenues.bin")
    parser.add_argument("--group", default="0x493")
    parser.add_argument("--pack-out", type=Path)
    args = parser.parse_args()

    cuelib, colorcues = load_cuelib(args.venue, args.group)
    seq = _events_from_validator_json(args.validator_json)
    pack, stats = canonicalize(seq, cuelib, colorcues)
    if args.pack_out:
        args.pack_out.write_text(json.dumps({"stats": stats, "timeline": pack}, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
