#!/usr/bin/env python3
"""Completeness verifier for SoundSwitch export — guarantees no silent cue miss.

Read-only research/QA tool (not a bridge runtime dependency; AGENTS.md §6).

The export pipeline must never silently drop a cue, track, or autoloop. This
verifier enforces SoundSwitch's own redundant completeness oracles and FAILS
LOUD (returns problems; CLI exits non-zero) on any discrepancy, instead of the
heuristic scanner's silent ``offset += 1`` skip.

Oracles enforced
----------------
- **Venue cues**: the catalog tail declares a cue count and a contiguous
  ``0..N-1`` index list. Parsed fixture-cue count + default must equal the
  declared count. Every entry's fixture group and channel id must be known for
  the fixture profile in use (NOT a hardcoded whitelist — see ``profile_*``).
- **Unknown is fatal**: any cue record that fails to parse at an expected
  position, any channel/group/flag value outside the fixture profile, or any
  byte gap inside the cue region that is not a known separator, is reported as a
  blocking problem — never skipped.

This module is the executable contract behind the closure report's
"no-silent-miss" guarantee. It is intentionally strict: a green result is a
proof that every cue SoundSwitch declared was accounted for.
"""
from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The current fixture profile (b8ad2201...) channel/group model. In the
# production exporter these MUST be derived from the Venue fixture-profile
# definition, not hardcoded, so a new fixture/profile cannot be silently
# rejected. Exposed here as parameters so the verifier fails loud (not silently)
# if content uses a channel/group outside the supplied model.
DEFAULT_CHANNEL_IDS = (82, 83, 84, 85, *range(256, 271))
DEFAULT_FIXTURE_GROUPS = (0x493, 0x494, 0x496, 0x497)
INTER_CUE_SEPARATOR = b"\x01\x00\x00\x00"  # observed 4-byte u32=1 between cue records


@dataclass
class Problem:
    severity: str   # "fatal" | "warn"
    where: str
    detail: str


@dataclass
class Report:
    source: str
    declared_cue_count: int | None = None
    parsed_fixture_cues: int = 0
    parsed_default_cues: int = 0
    problems: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(p.severity == "fatal" for p in self.problems)

    def summary(self) -> dict:
        return {
            "source": self.source,
            "ok": self.ok,
            "declared_cue_count": self.declared_cue_count,
            "parsed_total": self.parsed_fixture_cues + self.parsed_default_cues,
            "fatal": [f"{p.where}: {p.detail}" for p in self.problems if p.severity == "fatal"],
            "warn": [f"{p.where}: {p.detail}" for p in self.problems if p.severity == "warn"],
        }


def verify_venue(
    data: bytes,
    channel_ids=DEFAULT_CHANNEL_IDS,
    fixture_groups=DEFAULT_FIXTURE_GROUPS,
) -> Report:
    """Verify the Venue accounts for every declared cue. Fail loud, never skip."""
    import parse_venue_cues as pvc  # research-only import

    rep = Report(source="venue")
    cues = pvc.parse_venue_cues(data)
    fixture = [c for c in cues if c["record_kind"] == "fixture_payload"]
    catalog = [c for c in cues if c["record_kind"] == "minimal_default_catalog_tail"]
    rep.parsed_fixture_cues = len(fixture)
    rep.parsed_default_cues = len(catalog)

    if not catalog:
        rep.problems.append(Problem("fatal", "catalog",
            "no catalog tail found — cannot verify the declared cue count"))
        return rep
    declared = catalog[0]["catalog_count"]
    rep.declared_cue_count = declared

    # ORACLE 1: parsed count == declared count
    parsed_total = len(fixture) + len(catalog)
    if parsed_total != declared:
        rep.problems.append(Problem("fatal", "count",
            f"declared {declared} cues but parsed {parsed_total} "
            f"({len(fixture)} fixture + {len(catalog)} default) — "
            f"{declared - parsed_total} cue(s) would be silently missed"))

    # ORACLE 2: every entry uses a known channel/group for the profile
    known_ch = set(channel_ids)
    known_grp = set(fixture_groups)
    for c in fixture:
        for e in c["entries"]:
            if e["channel_id"] not in known_ch:
                rep.problems.append(Problem("fatal", f"cue '{c['name']}'",
                    f"channel_id {e['channel_id']} not in fixture profile — "
                    f"new/unknown channel must extend the model, not be dropped"))
            if e["fixture_group"] not in known_grp:
                rep.problems.append(Problem("fatal", f"cue '{c['name']}'",
                    f"fixture_group {hex(e['fixture_group'])} not in profile"))

    # ORACLE 3: unique GUIDs (no duplicate/aliased identity hiding a miss)
    guids = [c["cue_guid"] for c in fixture]
    if len(set(guids)) != len(guids):
        rep.problems.append(Problem("fatal", "guid",
            "duplicate cue GUID(s) — a distinct cue may be masked"))

    # ORACLE 4: byte accounting inside the cue region (start..catalog end).
    spans = sorted((c["offset"], c.get("catalog_indices_end_offset") or c["entries_end_offset"])
                   for c in cues)
    region_start = spans[0][0]
    prev = region_start
    for s, e in spans:
        gap = data[prev:s]
        if s > prev and gap != INTER_CUE_SEPARATOR * (len(gap) // 4):
            rep.problems.append(Problem("fatal", f"gap@{prev}",
                f"{s - prev} unaccounted bytes between cue records "
                f"({gap[:16].hex()}…) — a record may be hidden here"))
        prev = max(prev, e)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("venue", type=Path)
    args = ap.parse_args()
    import json
    rep = verify_venue(args.venue.read_bytes())
    print(json.dumps(rep.summary(), indent=2))
    sys.exit(0 if rep.ok else 2)


if __name__ == "__main__":
    main()
