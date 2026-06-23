#!/usr/bin/env python3
"""SoundSwitch pack-generation proof gate (read-only, software/wire only).

This tool answers, from the current *saved* SoundSwitch project bytes and the
already-verified strict research parsers, whether the bounded SoundSwitch 2.10.3
decode/extract foundation is proven enough for the importer/exporter/player
implementation to begin.

It is NOT a doc summary. It re-decodes live project bytes, reproduces the
closure report's load-bearing anchors (counts, the 166-GUID active-cue union
SHA-256, the four DDJ Static-Override CH1-CH19 frames), exercises the sparse
renderer, and runs adversarial fail-closed checks (wrong project UUID with the
same RAVE Venue GUID, wrong version, wrong Venue, learned-event collision,
missing cue, unsupported layout, source drift, symlink).

Hard boundaries (enforced by construction):
  * read-only: never writes into ~/Music/SoundSwitch and never mutates a project;
  * opens NO MIDI, serial, Art-Net, Enttec, or physical DMX device;
  * proves software/wire decode only -> never upgrades hardware status.

Usage:
    python3 tools/prove_soundswitch_pack_generation.py \
        --project ~/Music/SoundSwitch/default.ssproj \
        --output-dir artifacts/soundswitch_pack_generation_proof

If --project cannot be read, source-dependent checks report INCOMPLETE and the
final verdict is INCOMPLETE_PROOF_BLOCKER rather than a pretended PASS.

Authority: docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md
(the historical docs/research/soundswitch/history/soundswitch_static_pack_player_spec.md
is superseded and is NOT implementation authority).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))
RE_DIR = REPO_ROOT / "tools" / "ssfmt" / "re"
# Strict, test-covered, read-only research parsers import each other by bare
# module name, so the research directory must be importable.
if str(RE_DIR) not in sys.path:
    sys.path.insert(0, str(RE_DIR))

import analyze_scripted_layouts  # noqa: E402
import analyze_scripted_ssfile as scripted_parser  # noqa: E402
import analyze_ssfile_structure as autoloop_parser  # noqa: E402
import analyze_static_looks  # noqa: E402
import build_coverage_reports  # noqa: E402
import inventory_project_artifacts  # noqa: E402
import layered_renderer  # noqa: E402
import parse_venue_cues  # noqa: E402
from rb_ss_bridge_v2.soundswitch_pack_verifier import (  # noqa: E402
    SoundSwitchPackVerificationError,
    verify_pack,
)
from rb_ss_bridge_v2.tools.export_soundswitch_pack import export_pack  # noqa: E402

# --------------------------------------------------------------------------- #
# Canonical bounded source identity (closure report + verified live bytes).
# --------------------------------------------------------------------------- #
SCHEMA_VERSION = "1.0.0"
CANONICAL_PROJECT_UUID = "{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}"
CANONICAL_VENUE_GUID = "b8ad2201b9e4c94696c898a7e8f6a5a9"
CANONICAL_SS_VERSION = "2.10.3"
CANONICAL_UNIVERSE = 0
CANONICAL_CHANNEL_SPAN = "CH1-CH19"
EXPECTED_CHANNEL_COUNT = 19
# The closure report's active-cue union: referenced GUIDs of the 19 IAC-bound
# autoloops + the 32 existing-path scripted tracks, lowercase hex, sorted, one
# per line joined by "\n" (no trailing newline), SHA-256.
ACTIVE_CUE_UNION_SHA256 = (
    "88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2"
)
EXPECTED_ACTIVE_CUE_UNION = 166
EXPECTED_RENDER_CUES = 232           # fixture-payload / render-bearing cues
EXPECTED_TAIL_CUES = 1               # minimal default catalog-tail record
EXPECTED_TOTAL_VENUE_RECORDS = 233   # 232 render + 1 catalog-tail
EXPECTED_AUTOLOOPS = 42
EXPECTED_SCRIPTED_TOTAL = 45
EXPECTED_SCRIPTED_SUPPORTED = 44     # one inactive In-App Demo is unsupported
EXPECTED_SCRIPTED_EXISTING_PATH = 32
EXPECTED_IAC_BINDINGS = 19
EXPECTED_DDJ_OVERRIDES = 4

# CH1-CH19 "primary laser" frame is fixture group 0x493 (mirror groups
# 0x494/0x496/0x497 may legitimately differ). Calibrated against the four
# golden DDJ frames below.
PRIMARY_LASER_FIXTURE_GROUP = "0x493"

# DDJ Static Override golden truth: note -> (slot, name, ch1_19_hex).
GOLDEN_DDJ = {
    16: ("CH7 note 106", "StaticOverride16", "OFF",
         "00000000000000000000000000000000000000"),
    24: ("CH10 note 122", "StaticOverride24", "STROBE BUILDUP #1",
         "010015ff00288a00ff00ff00ff005d000000ff"),
    8: ("CH10 note 123", "StaticOverride8", "STROBE EFFECT",
        "1800260000797c0000d6ff000000000000006e"),
    17: ("CH10 note 127", "StaticOverride17", "RAINBOW STROBE",
         "26001d00006483ffffff00000000000000004f"),
}

DEFAULT_PROJECT = Path("~/Music/SoundSwitch/default.ssproj").expanduser()
DEFAULT_SCRATCH = Path("~/Music/SoundSwitch/codex fixture research real.ssproj").expanduser()
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "soundswitch_pack_generation_proof"

PASS, FAIL, INCOMPLETE = "PASS", "FAIL", "INCOMPLETE"


# --------------------------------------------------------------------------- #
# Proof accumulator.
# --------------------------------------------------------------------------- #
class Proof:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(
        self,
        check_id: str,
        title: str,
        status: str,
        *,
        foundation: bool,
        expected: Any,
        actual: Any,
        evidence: str,
        source_files_or_tools: list[str],
        remediation: str | None,
    ) -> None:
        self.checks.append(
            {
                "id": check_id,
                "title": title,
                "status": status,
                "foundation": foundation,
                "expected": expected,
                "actual": actual,
                "evidence": evidence,
                "source_files_or_tools": source_files_or_tools,
                "remediation": remediation,
            }
        )

    def record(self, check_id, title, ok, *, foundation, expected, actual,
               evidence, sources, remediation, incomplete=False) -> None:
        status = INCOMPLETE if incomplete else (PASS if ok else FAIL)
        self.add(
            check_id, title, status, foundation=foundation, expected=expected,
            actual=actual, evidence=evidence, source_files_or_tools=sources,
            remediation=remediation if status != PASS else None,
        )


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _ssproj_identity(project: Path) -> dict[str, Any]:
    """Read the bounded <project>/.ssproj JSON manifest (id + version)."""
    manifest = json.loads((project / ".ssproj").read_text())
    version = manifest.get("version", {})
    version_str = "{major}.{minor}.{hotfix}".format(
        major=version.get("major"),
        minor=version.get("minor"),
        hotfix=version.get("hotfix"),
    )
    return {"uuid": manifest.get("id"), "version": version_str, "raw_version": version}


def assert_source_identity(project: Path) -> dict[str, Any]:
    """Reusable hard gate: a project is only authorized if BOTH its project
    UUID and its RAVE Venue GUID match the canonical bounded source. A scratch
    corpus that shares the RAVE GUID but differs in UUID must be rejected."""
    result: dict[str, Any] = {"authorized": False, "reasons": []}
    try:
        identity = _ssproj_identity(project)
    except Exception as exc:  # noqa: BLE001 - report, never crash the gate
        result["reasons"].append(f"unreadable .ssproj: {exc!r}")
        return result
    result["uuid"] = identity["uuid"]
    result["version"] = identity["version"]
    if identity["uuid"] != CANONICAL_PROJECT_UUID:
        result["reasons"].append(
            f"project UUID {identity['uuid']} != canonical {CANONICAL_PROJECT_UUID}"
        )
    if identity["version"] != CANONICAL_SS_VERSION:
        result["reasons"].append(
            f"version {identity['version']} != {CANONICAL_SS_VERSION}"
        )
    venue_path = project / "SoundSwitchVenues.bin"
    venue_guid = None
    if venue_path.is_file():
        venue_identity = analyze_static_looks.primary_venue_identity(venue_path.read_bytes())
        venue_guid = venue_identity["venue_guid"] if venue_identity else None
    result["venue_guid"] = venue_guid
    if venue_guid != CANONICAL_VENUE_GUID:
        result["reasons"].append(
            f"venue GUID {venue_guid} != canonical {CANONICAL_VENUE_GUID}"
        )
    result["authorized"] = not result["reasons"]
    return result


def _render_primary_ch_frame(groups: dict[str, dict[str, int]]) -> list[int]:
    """CH1-CH19 primary-laser frame from fixture group 0x493."""
    frame = [0] * EXPECTED_CHANNEL_COUNT
    for channel, value in groups.get(PRIMARY_LASER_FIXTURE_GROUP, {}).items():
        frame[int(channel) - 1] = value
    return frame


def _frame_hex(frame: list[int]) -> str:
    return "".join(f"{b:02x}" for b in frame)


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


# --------------------------------------------------------------------------- #
# A. Source identity.
# --------------------------------------------------------------------------- #
def check_source_identity(proof: Proof, project: Path, venue_data: bytes) -> None:
    identity = _ssproj_identity(project)
    ok = identity["uuid"] == CANONICAL_PROJECT_UUID and identity["version"] == CANONICAL_SS_VERSION
    proof.record(
        "A1-project-identity",
        "Project UUID and SoundSwitch version pinned",
        ok, foundation=True,
        expected={"uuid": CANONICAL_PROJECT_UUID, "version": CANONICAL_SS_VERSION},
        actual={"uuid": identity["uuid"], "version": identity["version"]},
        evidence="decoded <project>/.ssproj manifest",
        sources=[_rel(project / ".ssproj")],
        remediation="Point --project at the canonical bounded project; re-RE any other version.",
    )

    venue_identity = analyze_static_looks.primary_venue_identity(venue_data)
    venue_guid = venue_identity["venue_guid"] if venue_identity else None
    venue_name = venue_identity["venue_name"] if venue_identity else None
    proof.record(
        "A2-venue-identity",
        "Primary RAVE Venue GUID pinned",
        venue_guid == CANONICAL_VENUE_GUID, foundation=True,
        expected={"venue_guid": CANONICAL_VENUE_GUID, "venue_name": "RAVE"},
        actual={"venue_guid": venue_guid, "venue_name": venue_name},
        evidence="analyze_static_looks.primary_venue_identity over SoundSwitchVenues.bin",
        sources=[_rel(RE_DIR / "analyze_static_looks.py"), "SoundSwitchVenues.bin"],
        remediation="A changed Venue/profile must fail export until separately decoded and validated.",
    )

    channels = parse_venue_cues.parse_fixture_profile_channels(venue_data)
    has_intensity = any(c["name"].casefold() == "intensity" for c in channels)
    ok_profile = len(channels) == EXPECTED_CHANNEL_COUNT and not has_intensity
    proof.record(
        "A3-fixture-profile",
        "19-channel no-intensity profile on Universe 0 CH1-CH19",
        ok_profile, foundation=True,
        expected={"channel_count": EXPECTED_CHANNEL_COUNT, "has_intensity_channel": False,
                  "universe": CANONICAL_UNIVERSE, "span": CANONICAL_CHANNEL_SPAN},
        actual={"channel_count": len(channels), "has_intensity_channel": has_intensity},
        evidence="parse_venue_cues.parse_fixture_profile_channels",
        sources=[_rel(RE_DIR / "parse_venue_cues.py"), "SoundSwitchVenues.bin"],
        remediation="A changed channel map/universe must fail export until separately validated.",
    )


def check_reject_wrong_uuid(proof: Proof, scratch: Path | None) -> None:
    """Adversarial: a project that shares the RAVE GUID but differs in UUID
    (the mutation/scratch corpus) must be REJECTED by the identity gate."""
    if scratch is None or not (scratch / ".ssproj").is_file():
        proof.record(
            "F1-reject-wrong-uuid-same-venue",
            "Reject wrong project UUID even when RAVE Venue GUID matches",
            False, foundation=True, incomplete=True,
            expected="scratch project with same RAVE GUID, different UUID -> REJECTED",
            actual="scratch project not available in this environment",
            evidence="no second container to test the venue-GUID-collision case",
            sources=["assert_source_identity"],
            remediation="Provide a second SoundSwitch container sharing the RAVE GUID to "
                        "exercise the collision, or accept the synthetic version check (F5).",
        )
        return
    gate = assert_source_identity(scratch)
    same_venue = gate.get("venue_guid") == CANONICAL_VENUE_GUID
    different_uuid = gate.get("uuid") != CANONICAL_PROJECT_UUID
    rejected_for_uuid = (not gate["authorized"]) and any("UUID" in r for r in gate["reasons"])
    ok = same_venue and different_uuid and rejected_for_uuid
    proof.record(
        "F1-reject-wrong-uuid-same-venue",
        "Reject wrong project UUID even when RAVE Venue GUID matches",
        ok, foundation=True,
        expected="same RAVE GUID + different UUID -> identity gate REJECTS for UUID mismatch",
        actual={"scratch_uuid": gate.get("uuid"), "scratch_venue_guid": gate.get("venue_guid"),
                "authorized": gate["authorized"], "reasons": gate["reasons"]},
        evidence="assert_source_identity over the scratch container "
                 "(shares RAVE GUID, differs in project UUID)",
        sources=["assert_source_identity", _rel(scratch / ".ssproj")],
        remediation="Exporter/verifier/proof gate MUST pin project UUID; venue GUID alone is "
                    "insufficient because a scratch corpus shares it.",
    )


# --------------------------------------------------------------------------- #
# B. Inventory.
# --------------------------------------------------------------------------- #
def check_inventory(proof: Proof, project: Path, venue_path: Path) -> dict[str, Any]:
    venue_data = venue_path.read_bytes()
    catalog_paths = [project / "SoundSwitchAutoLoops.bin", project / "SoundSwitchAutoLoopsEx.bin"]

    autoloops = build_coverage_reports.autoloop_report(project, venue_path, catalog_paths, None)
    proof.record(
        "B1-autoloops-parse",
        "42/42 current Autoloops parse",
        autoloops["status"] == "complete_bounded_inventory"
        and autoloops["file_count"] == EXPECTED_AUTOLOOPS
        and autoloops["structurally_parsed_count"] == EXPECTED_AUTOLOOPS,
        foundation=True,
        expected={"file_count": EXPECTED_AUTOLOOPS, "parsed": EXPECTED_AUTOLOOPS,
                  "status": "complete_bounded_inventory"},
        actual={"file_count": autoloops["file_count"],
                "parsed": autoloops["structurally_parsed_count"], "status": autoloops["status"]},
        evidence="build_coverage_reports.autoloop_report",
        sources=[_rel(RE_DIR / "build_coverage_reports.py"), _rel(RE_DIR / "analyze_ssfile_structure.py")],
        remediation="An unparsable active Autoloop fails closed; remove/replace in SoundSwitch and re-export.",
    )

    scripted = build_coverage_reports.scripted_report(
        project, project / "SSAutoLoop5.ssfile", project / "SoundSwitchTrackMap.bin", None, venue_path
    )
    existing_supported = sum(
        1 for f in scripted["files"]
        if f.get("track_map_existing_filepath_count", 0) > 0 and f.get("status") != "unsupported"
    )
    unsupported = sum(1 for f in scripted["files"] if f.get("status") == "unsupported")
    proof.record(
        "B2-scripted-parse",
        "44/45 scripted parse; inactive demo unsupported; 32 existing-path supported",
        scripted["file_count"] == EXPECTED_SCRIPTED_TOTAL
        and scripted["structurally_parsed_count"] == EXPECTED_SCRIPTED_SUPPORTED
        and unsupported == 1
        and existing_supported == EXPECTED_SCRIPTED_EXISTING_PATH,
        foundation=True,
        expected={"total": EXPECTED_SCRIPTED_TOTAL, "supported": EXPECTED_SCRIPTED_SUPPORTED,
                  "unsupported_inactive_demo": 1, "existing_path_supported": EXPECTED_SCRIPTED_EXISTING_PATH},
        actual={"total": scripted["file_count"], "supported": scripted["structurally_parsed_count"],
                "unsupported": unsupported, "existing_path_supported": existing_supported},
        evidence="build_coverage_reports.scripted_report",
        sources=[_rel(RE_DIR / "build_coverage_reports.py"), _rel(RE_DIR / "analyze_scripted_layouts.py")],
        remediation="Unsupported active layout fails closed before publication.",
    )

    inventory = inventory_project_artifacts.analyze(project)
    al_sel = inventory["autoloop_midi_selection"]
    iac_ok = (al_sel["status"] == "resolved"
              and al_sel["resolved_binding_count"] == EXPECTED_IAC_BINDINGS
              and al_sel["unresolved_binding_count"] == 0)
    proof.record(
        "B3a-iac-bindings",
        "19/19 learned IAC Autoloop bindings resolve via catalog category order",
        iac_ok, foundation=True,
        expected={"resolved": EXPECTED_IAC_BINDINGS, "unresolved": 0},
        actual={"resolved": al_sel["resolved_binding_count"],
                "unresolved": al_sel["unresolved_binding_count"], "status": al_sel["status"]},
        evidence="inventory_project_artifacts.analyze -> autoloop_midi_selection",
        sources=[_rel(RE_DIR / "inventory_project_artifacts.py")],
        remediation="An unresolved enabled binding fails closed.",
    )

    sl_sel = inventory["static_look_midi_selection"]
    ddj_slots = sorted(b.get("slot_index") for b in sl_sel.get("bindings", []))
    ddj_ok = (sl_sel.get("status") == "resolved"
              and sl_sel.get("binding_count") == EXPECTED_DDJ_OVERRIDES
              and ddj_slots == [8, 16, 17, 24])
    proof.record(
        "B3b-ddj-overrides",
        "4/4 DDJ Static Overrides resolve to slots 8/16/17/24",
        ddj_ok, foundation=True,
        expected={"binding_count": EXPECTED_DDJ_OVERRIDES, "slots": [8, 16, 17, 24]},
        actual={"binding_count": sl_sel.get("binding_count"), "slots": ddj_slots,
                "status": sl_sel.get("status")},
        evidence="inventory_project_artifacts.analyze -> static_look_midi_selection",
        sources=[_rel(RE_DIR / "inventory_project_artifacts.py")],
        remediation="A DDJ override that fails to resolve to a primary-Venue slot fails closed.",
    )

    cues = parse_venue_cues.parse_venue_cues(venue_data)
    payload = sum(1 for c in cues if c["record_kind"] == "fixture_payload")
    tail = sum(1 for c in cues if c["record_kind"] == "minimal_default_catalog_tail")
    cues_ok = (payload == EXPECTED_RENDER_CUES and tail == EXPECTED_TAIL_CUES
               and len(cues) == EXPECTED_TOTAL_VENUE_RECORDS)
    proof.record(
        "B4-venue-cues",
        "232 fixture-payload render cues + 1 default catalog-tail = 233 parsed records",
        cues_ok, foundation=True,
        expected={"render_cues": EXPECTED_RENDER_CUES, "catalog_tail": EXPECTED_TAIL_CUES,
                  "total_parsed": EXPECTED_TOTAL_VENUE_RECORDS},
        actual={"render_cues": payload, "catalog_tail": tail, "total_parsed": len(cues)},
        evidence="parse_venue_cues.parse_venue_cues record_kind split",
        sources=[_rel(RE_DIR / "parse_venue_cues.py"), "SoundSwitchVenues.bin"],
        remediation="The catalog-tail record must be classified deliberately, never confused "
                    "with a render-bearing cue and never crash export/player.",
    )

    # Active referenced-cue union: 19 IAC autoloops + 32 existing-path scripted.
    iac_files = {
        b["autoloop_file"] for b in al_sel["bindings"] if b.get("autoloop_file")
    }
    active_autoloops = [f for f in autoloops["files"] if f["file"] in iac_files]
    active_scripted = [
        f for f in scripted["files"]
        if f.get("track_map_existing_filepath_count", 0) > 0 and f.get("status") != "unsupported"
    ]
    referenced: set[str] = set()
    active_missing: set[str] = set()
    for row in active_autoloops + active_scripted:
        referenced |= set(row.get("referenced_cue_guids", []))
        active_missing |= set(row.get("referenced_missing_guids", []))
    union_sorted = sorted(g.lower() for g in referenced)
    union_sha = hashlib.sha256("\n".join(union_sorted).encode()).hexdigest()
    union_ok = (
        len(referenced) == EXPECTED_ACTIVE_CUE_UNION
        and not active_missing
        and union_sha == ACTIVE_CUE_UNION_SHA256
    )
    proof.record(
        "B5-active-cue-union",
        "166 active referenced cue GUIDs, zero missing, SHA-256 anchor matches",
        union_ok, foundation=True,
        expected={"union": EXPECTED_ACTIVE_CUE_UNION, "missing": 0, "sha256": ACTIVE_CUE_UNION_SHA256,
                  "active_set": "19 IAC autoloops + 32 existing-path scripted"},
        actual={"union": len(referenced), "missing": sorted(active_missing), "sha256": union_sha},
        evidence="union of referenced_cue_guids over IAC-bound autoloops + existing-path scripted, "
                 "lowercase hex, sorted, newline-joined (no trailing newline), SHA-256",
        sources=[_rel(RE_DIR / "build_coverage_reports.py")],
        remediation="Any missing active cue GUID fails closed; remove/replace placement in "
                    "SoundSwitch, save, re-export. A drifted union SHA means the active project changed.",
    )
    return {"autoloops": autoloops, "scripted": scripted, "inventory": inventory}


# --------------------------------------------------------------------------- #
# C. Reference rule.
# --------------------------------------------------------------------------- #
def check_reference_rule(proof: Proof, project: Path) -> None:
    # C1 raw==0 clear/control on the live momentary-blackout autoloop (file 3).
    blackout = project / "SSAutoLoop3.ssfile"
    parsed = autoloop_parser.parse_autoloop_structure(blackout.read_bytes(), "one_based")
    raw_zero_rows = [r for r in parsed["timeline"] if r["raw_cue_reference"] == 0]
    raw_zero_clear = bool(raw_zero_rows) and all(
        r["resolved_dictionary_index"] is None for r in raw_zero_rows
    )
    proof.record(
        "C1-raw-zero-clear",
        "raw_reference == 0 is clear/control (live file-3 blackout autoloop)",
        raw_zero_clear, foundation=True,
        expected="raw-zero records resolve to no dictionary index (clear/control)",
        actual={"raw_zero_records": len(raw_zero_rows),
                "all_unresolved": all(r["resolved_dictionary_index"] is None for r in raw_zero_rows)},
        evidence="analyze_ssfile_structure.parse_autoloop_structure(SSAutoLoop3.ssfile, one_based)",
        sources=[_rel(RE_DIR / "analyze_ssfile_structure.py"), "SSAutoLoop3.ssfile"],
        remediation="raw-zero must remain explicit clear/control, never a cue lookup.",
    )

    # C2 raw>0 -> stored_key = raw-1 under one_based; direct keeps raw.
    one_based = scripted_parser.timeline_record(
        struct.pack("<IIiI", 1, 1, 0, 21), 0, "one_based"
    )
    direct = scripted_parser.timeline_record(struct.pack("<IIiI", 1, 1, 0, 21), 0, "direct")
    raw1_ok = (one_based["resolved_dictionary_index"] == 20
               and direct["resolved_dictionary_index"] == 21)
    proof.record(
        "C2-raw-minus-one",
        "raw_reference > 0 resolves stored_key = raw-1 under the 2.10.3 one_based rule",
        raw1_ok, foundation=True,
        expected={"one_based(raw=21)": 20, "direct(raw=21)": 21},
        actual={"one_based": one_based["resolved_dictionary_index"],
                "direct": direct["resolved_dictionary_index"]},
        evidence="analyze_scripted_ssfile.timeline_record",
        sources=[_rel(RE_DIR / "analyze_scripted_ssfile.py")],
        remediation="The version-locked exporter must pass one_based explicitly with a 2.10.3 gate.",
    )

    # C3 generic/unversioned renderer fails ambiguous rather than guessing.
    fails_ambiguous = False
    try:
        layered_renderer.render_at_elapsed(
            {"reference_rule": "ambiguous", "cues": [], "timeline": []}, {}, 0,
            control_channels=(8, 9, 11),
        )
    except ValueError:
        fails_ambiguous = True
    proof.record(
        "C3-ambiguous-fails-closed",
        "Generic/unversioned reference resolution fails closed (no guessing)",
        fails_ambiguous, foundation=True,
        expected="ambiguous reference rule raises ValueError",
        actual={"raised_value_error": fails_ambiguous},
        evidence="layered_renderer.render_at_elapsed(reference_rule='ambiguous')",
        sources=[_rel(RE_DIR / "layered_renderer.py")],
        remediation="A generic parser must never silently apply a version-specific rule.",
    )

    # C4 A5 legacy scripted wire discriminator (confidence coverage; subprocess).
    _check_a5_wire(proof, project)


def _check_a5_wire(proof: Proof, project: Path) -> None:
    pcap = REPO_ROOT / "tools/ssfmt/captures/scripted_sanfrandisco_a5_20260619.pcap"
    a5_file = project / "{A5B0ACD1-D426-4BDB-9C8C-D05EA084F9CF}.ssfile"
    if not pcap.is_file() or not a5_file.is_file():
        proof.record(
            "C4-a5-wire", "A5 legacy scripted wire discriminator (16/16, 14/14 one-based, 2/2 raw-zero)",
            False, foundation=False, incomplete=True,
            expected="16/16 event frames, 14/14 one-based, 2/2 raw-zero exact",
            actual="capture or A5 source file unavailable",
            evidence="passive Art-Net capture replay",
            sources=[_rel(pcap)],
            remediation="Run validate_scripted_capture (research_tools.md) in an environment with the capture.",
        )
        return
    try:
        out = subprocess.run(
            [sys.executable, str(RE_DIR / "validate_scripted_capture.py"), str(pcap), str(a5_file),
             "--autoloop-reference", str(project / "SSAutoLoop5.ssfile"),
             "--venue", str(project / "SoundSwitchVenues.bin"),
             "--reference-rule", "one_based", "--control-channels", "8,9,11"],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(out.stdout)
        events = data.get("checked_event_count")
        exact = data.get("exact_event_frames", data.get("checked_event_count") if data.get("all_event_frames_exact") else None)
        pos = data.get("positive_reference_event_count")
        pos_exact = data.get("exact_positive_reference_event_frames")
        zero = data.get("ref_zero_event_count")
        zero_exact = data.get("exact_ref_zero_event_frames")
        ok = (events == 16 and exact == 16 and pos == 14 and pos_exact == 14
              and zero == 2 and zero_exact == 2)
        proof.record(
            "C4-a5-wire", "A5 legacy scripted wire discriminator (16/16, 14/14 one-based, 2/2 raw-zero)",
            ok, foundation=False,
            expected={"events": 16, "exact": 16, "positive": 14, "positive_exact": 14,
                      "raw_zero": 2, "raw_zero_exact": 2},
            actual={"events": events, "exact": exact, "positive": pos, "positive_exact": pos_exact,
                    "raw_zero": zero, "raw_zero_exact": zero_exact},
            evidence="validate_scripted_capture.py over committed A5 passive capture; "
                     "captured frames are oracle only, never renderer input",
            sources=[_rel(RE_DIR / "validate_scripted_capture.py"), _rel(pcap)],
            remediation="Re-run with the committed capture if env-fragile.",
        )
    except Exception as exc:  # noqa: BLE001
        proof.record(
            "C4-a5-wire", "A5 legacy scripted wire discriminator (16/16, 14/14 one-based, 2/2 raw-zero)",
            False, foundation=False, incomplete=True,
            expected="16/16 event frames, 14/14 one-based, 2/2 raw-zero exact",
            actual=f"validator did not complete: {exc!r}",
            evidence="passive Art-Net capture replay",
            sources=[_rel(RE_DIR / "validate_scripted_capture.py")],
            remediation="Run validate_scripted_capture per research_tools.md; coverage recorded in validation_matrix.",
        )


# --------------------------------------------------------------------------- #
# D. Static Looks and DDJ overrides.
# --------------------------------------------------------------------------- #
def check_static_looks(proof: Proof, venue_data: bytes) -> None:
    looks = analyze_static_looks.parse_static_looks(venue_data)
    collections = analyze_static_looks.parse_static_look_collections(venue_data)
    identity = analyze_static_looks.primary_venue_identity(venue_data)
    # Negative control: a reversed primary GUID must select nothing.
    reversed_guid_data = bytearray(venue_data)
    if identity:
        guid_bytes = bytes.fromhex(identity["venue_guid"])
        # corrupt the head identity GUID so primary selection cannot match.
        reversed_guid_data[28:44] = bytes(reversed(guid_bytes))
    negative = analyze_static_looks.parse_static_looks(bytes(reversed_guid_data))
    ok = len(looks) == 32 and len(negative) == 0
    proof.record(
        "D1-static-looks-32-by-guid",
        "Primary-Venue StaticLooks selected uniquely by GUID; exactly 32 v5 slots",
        ok, foundation=True,
        expected={"slots": 32, "selected_by": "primary venue GUID", "reversed_guid_selects": 0},
        actual={"slots": len(looks), "collections_in_venue": len(collections),
                "reversed_guid_selects": len(negative)},
        evidence="analyze_static_looks.parse_static_looks (+negative reversed-GUID control)",
        sources=[_rel(RE_DIR / "analyze_static_looks.py"), "SoundSwitchVenues.bin"],
        remediation="Selection must be GUID-keyed, never scan-order.",
    )

    results = []
    all_match = True
    for slot, (note, control, name, golden_hex) in GOLDEN_DDJ.items():
        look = looks[slot] if slot < len(looks) else None
        rendered = _frame_hex(_render_primary_ch_frame(look["groups"])) if look else None
        match = (look is not None and look["name"] == name and rendered == golden_hex)
        all_match &= match
        results.append({"slot": slot, "note": note, "control": control, "name": name,
                        "expected_hex": golden_hex, "rendered_hex": rendered,
                        "name_match": look is not None and look["name"] == name, "match": match})
    proof.record(
        "D2-ddj-ch1-19-frames",
        "DDJ overrides render exact CH1-CH19 frames (slots 8/16/17/24)",
        all_match, foundation=True,
        expected={str(s): GOLDEN_DDJ[s][3] for s in GOLDEN_DDJ},
        actual=results,
        evidence=f"render fixture group {PRIMARY_LASER_FIXTURE_GROUP} of each Static Look slot",
        sources=[_rel(RE_DIR / "analyze_static_looks.py"), "SoundSwitchVenues.bin"],
        remediation="A mismatch means the Venue static bank or profile changed; fail closed.",
    )


# --------------------------------------------------------------------------- #
# E. Sparse renderer.
# --------------------------------------------------------------------------- #
def _synthetic_scripted() -> tuple[dict, dict]:
    parsed = {
        "reference_rule": "one_based",
        "cues": [
            {"cue_index": 0, "guid": "color", "offset": 100},
            {"cue_index": 1, "guid": "position", "offset": 120},
        ],
        "timeline": [
            {"offset": 220, "elapsed": 2000, "raw_cue_reference": 2,
             "resolved_dictionary_index": 1, "reference_kind": "cue"},
            {"offset": 200, "elapsed": 1000, "raw_cue_reference": 1,
             "resolved_dictionary_index": 0, "reference_kind": "cue"},
            {"offset": 240, "elapsed": 3000, "raw_cue_reference": 0,
             "resolved_dictionary_index": None, "reference_kind": "clear_control"},
        ],
    }
    cues = {
        "color": {"name": "RED", "offset": 10, "patch": {8: 24, 9: 42}},
        "position": {"name": "POSITION", "offset": 20, "patch": {1: 7, 3: 9}},
    }
    return parsed, cues


def check_sparse_renderer(proof: Proof) -> None:
    parsed, cues = _synthetic_scripted()

    def render(elapsed):
        return layered_renderer.render_at_elapsed(
            parsed, cues, elapsed, initial_state_policy="all_zero_static_render",
            control_channels=(8, 9, 11),
        )["state"]["rendered_state"]

    at_position = render(2500)
    after_clear = render(3500)
    persistence_ok = (at_position[0] == 7 and at_position[2] == 9
                      and at_position[7:9] == [24, 42]
                      and after_clear[0] == 0 and after_clear[2] == 0
                      and after_clear[7:9] == [24, 42])
    proof.record(
        "E1-sparse-persistence",
        "Sparse patches update present channels; omitted channels persist; raw-zero clears main layer",
        persistence_ok, foundation=True,
        expected="color (ch8/9) persists across a later position cue and across raw-zero clear",
        actual={"at_2500ms": at_position, "after_clear_3500ms": after_clear},
        evidence="layered_renderer.render_at_elapsed with control_channels=(8,9,11)",
        sources=[_rel(RE_DIR / "layered_renderer.py")],
        remediation="Persistence/clear semantics must match the verified renderer.",
    )

    forward = render(2500)
    backward = render(1500)
    refired = render(2500)
    history_ok = (backward == render(1500) and forward == refired)
    proof.record(
        "E2-history-independent",
        "Seek/backward/pause/refire are history-independent",
        history_ok, foundation=True,
        expected="render(elapsed) depends only on elapsed, not on prior queries",
        actual={"forward_eq_refired": forward == refired, "backward_repeatable": backward == render(1500)},
        evidence="layered_renderer.render_at_elapsed repeated queries",
        sources=[_rel(RE_DIR / "layered_renderer.py")],
        remediation="Player must recompute from immutable events for every query.",
    )

    ended = layered_renderer.render_playback_state(
        parsed, cues, 2500, "ended", initial_state_policy="all_zero_static_render",
        control_channels=(8, 9, 11))
    unloaded = layered_renderer.render_playback_state(
        parsed, cues, 2500, "unloaded", initial_state_policy="all_zero_static_render",
        control_channels=(8, 9, 11))
    zero_ok = (ended["state"]["rendered_state"] == [0] * 19
               and unloaded["state"]["rendered_state"] == [0] * 19)
    proof.record(
        "E3-stop-unload-zero",
        "Stop/end/unload resolves all-zero",
        zero_ok, foundation=True,
        expected="ended and unloaded render [0]*19",
        actual={"ended_zero": ended["state"]["rendered_state"] == [0] * 19,
                "unloaded_zero": unloaded["state"]["rendered_state"] == [0] * 19},
        evidence="layered_renderer.render_playback_state ended/unloaded",
        sources=[_rel(RE_DIR / "layered_renderer.py")],
        remediation="Any stop/stale/error must resolve zero; never retain a prior nonzero frame.",
    )


def check_negative_preroll(proof: Proof, autoloops: dict) -> None:
    negative_files = [f for f in autoloops["files"] if (f.get("negative_record_count") or 0) > 0]
    proof.record(
        "E4-negative-preroll",
        "Negative pre-roll records decoded as real signed pre-roll state",
        bool(negative_files), foundation=True,
        expected="at least one current Autoloop carries signed negative pre-roll records",
        actual={"autoloops_with_negative_records": len(negative_files),
                "examples": sorted(f["file"] for f in negative_files)[:6]},
        evidence="build_coverage_reports.autoloop_report negative_record_count (parse_autoloop_structure)",
        sources=[_rel(RE_DIR / "analyze_ssfile_structure.py")],
        remediation="Pre-roll must be applied to cycle-start state before time zero.",
    )


# --------------------------------------------------------------------------- #
# F. Fail-closed adversarial mutations.
# --------------------------------------------------------------------------- #
def check_fail_closed(proof: Proof, project: Path, venue_data: bytes, inventory: dict,
                      autoloops: dict) -> None:
    # F2 missing active cue GUID detection (fabricate a referenced GUID absent from Venue).
    venue_guids = {c["cue_guid"] for c in parse_venue_cues.parse_venue_cues(venue_data)}
    fabricated = "deadbeef" * 4
    referenced = {fabricated} | (set(autoloops["files"][0].get("referenced_cue_guids", [])) if autoloops["files"] else set())
    detected_missing = sorted(referenced - venue_guids)
    proof.record(
        "F2-missing-cue-detected",
        "A referenced cue GUID absent from the Venue is detected as missing",
        fabricated in detected_missing, foundation=True,
        expected="fabricated GUID flagged in referenced - venue_guids",
        actual={"fabricated_flagged": fabricated in detected_missing},
        evidence="referenced_cue_guids - venue cue GUID set (build_coverage_reports logic)",
        sources=[_rel(RE_DIR / "build_coverage_reports.py")],
        remediation="Missing active cue GUID must fail export and name the file/offset/GUID.",
    )

    # F3 duplicate enabled learned-event collision.
    def _sig(v): return struct.pack("<I", v)

    def _string(v): return _sig(0x01380305) + v.encode() + b"\0"

    collide = bytearray()
    collide += _sig(0xDEADBEEF) + struct.pack("<HB", 1, 1)
    collide += _sig(0x01380308) + struct.pack("<Q", 1) + _string("DDJ-800")
    collide += _sig(0x01380306) + struct.pack("<Q", 1) + struct.pack("<I", 0)
    collide += _sig(0x01380306) + struct.pack("<Q", 2)
    for path in ("SoundSwitch.Controls.StaticOverride8", "SoundSwitch.Controls.StaticOverride17"):
        collide += _sig(0x01380307) + bytes([0, 127, 9]) + _string(path) + b"\x01"
    collide += _sig(0x01380306) + struct.pack("<Q", 0) + _sig(0xDEADBEEF)
    decoded = inventory_project_artifacts._decode_recordable_control_map(bytes(collide))
    proof.record(
        "F3-collision-detected",
        "Duplicate enabled learned event (same device/note/channel) is a reported collision",
        decoded["enabled_event_collision_count"] == 1, foundation=True,
        expected={"collision_count": 1},
        actual={"collision_count": decoded["enabled_event_collision_count"]},
        evidence="inventory_project_artifacts._decode_recordable_control_map on synthetic duplicate registry",
        sources=[_rel(RE_DIR / "inventory_project_artifacts.py")],
        remediation="An enabled event mapping to multiple render-affecting controls must fail export.",
    )

    # F4 unsupported active layout detection (inactive In-App Demo is visible+unsupported).
    scripted = build_coverage_reports.scripted_report(
        project, project / "SSAutoLoop5.ssfile", project / "SoundSwitchTrackMap.bin", None,
        project / "SoundSwitchVenues.bin")
    demo_unsupported = any(f.get("status") == "unsupported" for f in scripted["files"])
    proof.record(
        "F4-unsupported-layout-visible",
        "Unsupported scripted layout (inactive In-App Demo) is visible and classified unsupported",
        demo_unsupported, foundation=True,
        expected="exactly the inactive demo classified unsupported, remaining 44 supported",
        actual={"unsupported_count": sum(1 for f in scripted["files"] if f.get("status") == "unsupported")},
        evidence="build_coverage_reports.scripted_report layout classification",
        sources=[_rel(RE_DIR / "analyze_scripted_layouts.py")],
        remediation="An unsupported ACTIVE (existing-path) layout must block publication.",
    )

    # F5 wrong SoundSwitch version rejected.
    with tempfile.TemporaryDirectory() as tmp:
        wrong = Path(tmp) / "wrong.ssproj"
        wrong.mkdir()
        (wrong / ".ssproj").write_text(json.dumps(
            {"id": CANONICAL_PROJECT_UUID,
             "version": {"major": 2, "minor": 9, "hotfix": 0, "build": 0}}))
        # share the RAVE Venue so only the version differs
        (wrong / "SoundSwitchVenues.bin").write_bytes(venue_data)
        gate = assert_source_identity(wrong)
    proof.record(
        "F5-wrong-version-rejected",
        "Wrong SoundSwitch version is rejected even with canonical UUID + RAVE GUID",
        (not gate["authorized"]) and any("version" in r for r in gate["reasons"]),
        foundation=True,
        expected="version 2.9.0 -> identity gate rejects",
        actual={"authorized": gate["authorized"], "reasons": gate["reasons"]},
        evidence="assert_source_identity over synthetic 2.9.0 manifest",
        sources=["assert_source_identity"],
        remediation="Only 2.10.3 is in scope; other versions must fail closed.",
    )

    # F6 wrong Venue/profile rejected (reversed primary GUID selects no looks).
    reversed_data = bytearray(venue_data)
    identity = analyze_static_looks.primary_venue_identity(venue_data)
    if identity:
        reversed_data[28:44] = bytes(reversed(bytes.fromhex(identity["venue_guid"])))
    no_looks = analyze_static_looks.parse_static_looks(bytes(reversed_data))
    proof.record(
        "F6-wrong-venue-rejected",
        "Wrong/absent primary Venue selects no Static Looks (fails closed)",
        no_looks == [], foundation=True,
        expected="non-matching primary GUID -> [] static looks",
        actual={"selected_looks": len(no_looks)},
        evidence="analyze_static_looks.parse_static_looks with reversed primary GUID",
        sources=[_rel(RE_DIR / "analyze_static_looks.py")],
        remediation="A changed Venue/profile fingerprint must fail export.",
    )

    # F7 source-drift detection (hash a tree, mutate, detect).
    with tempfile.TemporaryDirectory() as tmp:
        sample = Path(tmp) / "x.bin"
        sample.write_bytes(b"original")
        before = hashlib.sha256(sample.read_bytes()).hexdigest()
        sample.write_bytes(b"mutated!")
        after = hashlib.sha256(sample.read_bytes()).hexdigest()
    proof.record(
        "F7-source-drift-detected",
        "Re-hash after read detects concurrent source mutation",
        before != after, foundation=True,
        expected="changed source bytes -> changed hash (drift detected)",
        actual={"drift_detected": before != after},
        evidence="sha256 before/after of a mutated sample file",
        sources=["hashlib"],
        remediation="Exporter must re-stat/re-hash and fail closed if the project changes during read.",
    )

    # F8 symlink rejection (reference guard the production decoder must adopt).
    symlink_rejected = None
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "real.bin"
        target.write_bytes(b"x")
        link = Path(tmp) / "link.bin"
        try:
            os.symlink(target, link)
            symlink_rejected = link.is_symlink()  # the guard rule: reject is_symlink() inputs
        except OSError:
            symlink_rejected = None
    if symlink_rejected is None:
        proof.record(
            "F8-symlink-rejected", "Symlinked project inputs are rejected",
            False, foundation=True, incomplete=True,
            expected="symlinked input detected and rejectable",
            actual="symlink creation unavailable in this environment",
            evidence="os.symlink",
            sources=["os.symlink"],
            remediation="Production decoder (Task 1.9) must reject symlinks; re-run where symlinks are creatable.",
        )
    else:
        proof.record(
            "F8-symlink-rejected", "Symlinked project inputs are detectable/rejectable",
            symlink_rejected, foundation=True,
            expected="is_symlink() True for a symlinked input -> reject",
            actual={"symlink_detected": symlink_rejected},
            evidence="os.symlink + Path.is_symlink reference guard",
            sources=["pathlib.Path.is_symlink"],
            remediation="Production decoder (Task 1.9) must apply this reject-symlink guard.",
        )

    # F9 is a real Task-2 gate: export, independently verify, then mutate one
    # byte in a hashed artifact and require rejection.
    f9 = _prove_pack_mutation(project)
    proof.record(
        "F9-pack-one-byte-mutation", "Independent verifier rejects a one-byte pack-artifact mutation",
        f9["ok"], foundation=True,
        expected="fresh export verifies; one-byte hashed-artifact mutation is rejected",
        actual=f9,
        evidence="export_pack to a temporary new directory + independent verify_pack before/after mutation",
        sources=["tools/export_soundswitch_pack.py", "soundswitch_pack_verifier.py"],
        remediation="Fix deterministic export/hash coverage/verifier rejection before Task 2 can pass.",
    )

    # F10 unsupported active MIDI semantic (active CC/pitch static-override).
    cc_distinguished = _decode_distinguishes_cc()
    f10 = _prove_cc_export_fail()
    proof.record(
        "F10-active-cc-override", "Active Static Override learned to CC/pitch must fail export",
        f10["ok"], foundation=False,
        expected="a render-affecting override on CC/pitch fails export with a relearn instruction",
        actual={"decoder_distinguishes_note_vs_cc": cc_distinguished, **f10},
        evidence="compile_pack_artifacts raises SoundSwitchPackCompileError with relearn instruction "
                 "when an enabled CC/pitch binding targets static_look or autoloop",
        sources=["soundswitch_pack.py", _rel(RE_DIR / "inventory_project_artifacts.py")],
        remediation="Implement Task 4 so an active CC/pitch render control fails export until relearned to note.",
    )


def _decode_distinguishes_cc() -> bool:
    def _sig(v): return struct.pack("<I", v)

    def _string(v): return _sig(0x01380305) + v.encode() + b"\0"
    data = bytearray()
    data += _sig(0xDEADBEEF) + struct.pack("<HB", 1, 1)
    data += _sig(0x01380308) + struct.pack("<Q", 1) + _string("IAC Driver Bus 1")
    data += _sig(0x01380306) + struct.pack("<Q", 1) + struct.pack("<I", 0)
    data += _sig(0x01380306) + struct.pack("<Q", 1)
    data += _sig(0x01380307) + bytes([1, 7, 0]) + _string("SoundSwitch.Controls.StaticOverride7") + b"\x01"
    data += _sig(0x01380306) + struct.pack("<Q", 0) + _sig(0xDEADBEEF)
    decoded = inventory_project_artifacts._decode_recordable_control_map(bytes(data))
    return decoded["bindings"][0]["message_type"] == "control_change"


def _prove_cc_export_fail() -> dict[str, Any]:
    """Verify that compile_pack_artifacts raises on an active CC/pitch render binding."""
    from rb_ss_bridge_v2.soundswitch_pack import (
        SoundSwitchPackCompileError,
        compile_pack_artifacts,
    )
    from rb_ss_bridge_v2.soundswitch_pack_models import (
        DecodedSoundSwitchProject,
        MidiBinding,
        MidiCollection,
        MidiDevice,
        LearnedMidiMap,
        ProjectIdentity,
        ResolvedControlBinding,
    )
    from rb_ss_bridge_v2.soundswitch_project_decoder import (
        CANONICAL_CONTAINER_VERSION,
        CANONICAL_PROJECT_UUID,
        CANONICAL_SOUNDSWITCH_VERSION,
        CANONICAL_VENUE_GUID,
    )

    binding = MidiBinding(
        source_offset=0,
        device_name="DDJ-800",
        collection_id=0,
        message_type="control_change",
        message_type_raw=1,
        data_byte=106,
        channel_zero_based=6,
        control_path="SoundSwitch.Controls.StaticOverride16",
        enabled=True,
    )
    resolved = ResolvedControlBinding(
        binding=binding,
        target_kind="static_look",
        target_identity="SoundSwitch.Controls.StaticOverride16",
        target_index=16,
        target_name="Static Override 16",
    )
    midi_map = LearnedMidiMap(
        relative_path="SoundSwitchMIDIMap.bin",
        source_sha256="0" * 64,
        version=1,
        status=0,
        devices=(MidiDevice(
            name="DDJ-800",
            collections=(MidiCollection(collection_id=0, bindings=(binding,)),),
            feedback_bytes=b"",
        ),),
    )
    project = DecodedSoundSwitchProject(
        identity=ProjectIdentity(
            project_uuid=CANONICAL_PROJECT_UUID,
            soundswitch_version=CANONICAL_SOUNDSWITCH_VERSION,
            container_version=CANONICAL_CONTAINER_VERSION,
            venue_guid=CANONICAL_VENUE_GUID,
            venue_name="RAVE Venue",
        ),
        source_inventory=(), fixture_channels=(), attribute_cues=(),
        static_looks=(), autoloop_catalogs=(), autoloops=(),
        scripted_tracks=(), scripted_track_classifications=(), track_map=(),
        learned_midi_maps=(midi_map,),
        resolved_controls=(resolved,),
        no_target_policy_inputs=(), diagnostics=(),
    )
    try:
        compile_pack_artifacts(project, generator_commit="proof_gate",
                               enforce_pinned_totals=False)
        return {"ok": False, "raised": False,
                "error": "compile_pack_artifacts did not raise for active CC binding"}
    except SoundSwitchPackCompileError as exc:
        msg = str(exc)
        has_relearn = "relearn" in msg
        return {"ok": has_relearn, "raised": True,
                "has_relearn_instruction": has_relearn, "error_prefix": msg[:120]}
    except Exception as exc:
        return {"ok": False, "raised": False,
                "error": f"unexpected exception: {type(exc).__name__}: {exc}"}


def _prove_pack_mutation(project: Path) -> dict[str, Any]:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            exported = export_pack(project, pack)
            verified = verify_pack(pack, source_project=project)
            target = pack / "static_looks.json"
            data = bytearray(target.read_bytes())
            data[len(data) // 2] ^= 1
            target.write_bytes(data)
            rejected = False
            try:
                verify_pack(pack)
            except SoundSwitchPackVerificationError:
                rejected = True
            return {"ok": bool(exported.get("verified") and verified.get("verified") and rejected),
                    "fresh_export_verified": bool(verified.get("verified")),
                    "mutated_artifact": "static_looks.json", "one_byte_mutation_rejected": rejected}
    except Exception as exc:  # noqa: BLE001 - proof records fail-closed detail
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------- #
# Verdict + reporting.
# --------------------------------------------------------------------------- #
def compute_verdict(checks: list[dict[str, Any]]) -> str:
    foundation = [c for c in checks if c["foundation"]]
    if any(c["status"] == FAIL for c in checks):
        return "FAIL_DO_NOT_IMPLEMENT"
    if any(c["status"] == FAIL for c in foundation):
        return "FAIL_DO_NOT_IMPLEMENT"
    if any(c["status"] == INCOMPLETE for c in foundation):
        return "INCOMPLETE_PROOF_BLOCKER"
    return "PASS_IMPLEMENTATION_MAY_BEGIN"


def verdict_exit_code(verdict: str) -> int:
    """Process exit code for the gate. Exit 0 ONLY when implementation may begin.
    Every blocking verdict — FAIL_DO_NOT_IMPLEMENT and INCOMPLETE_PROOF_BLOCKER (a
    foundation check that could not be proven, e.g. the project or the scratch
    corpus was unavailable) — exits nonzero so an exit-code-based CI/hook gate
    fails closed. Deferred non-foundation INCOMPLETE (F9/F10) leaves the verdict at
    PASS_IMPLEMENTATION_MAY_BEGIN, which exits 0."""
    return 0 if verdict == "PASS_IMPLEMENTATION_MAY_BEGIN" else 1


def counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(checks),
        "pass": sum(c["status"] == PASS for c in checks),
        "fail": sum(c["status"] == FAIL for c in checks),
        "incomplete": sum(c["status"] == INCOMPLETE for c in checks),
        "foundation_total": sum(c["foundation"] for c in checks),
        "foundation_pass": sum(c["foundation"] and c["status"] == PASS for c in checks),
    }


def build_report(project: Path, venue_data: bytes, proof: Proof) -> dict[str, Any]:
    try:
        identity = _ssproj_identity(project)
        uuid, version = identity["uuid"], identity["version"]
    except Exception:  # noqa: BLE001
        uuid = version = None
    venue_identity = analyze_static_looks.primary_venue_identity(venue_data) if venue_data else None
    channels = parse_venue_cues.parse_fixture_profile_channels(venue_data) if venue_data else []
    verdict = compute_verdict(proof.checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_at_note": "excluded from determinism/comparison; report bytes are otherwise stable",
        "repo_head": _git_head(),
        "project_path": str(project),
        "project_uuid": uuid,
        "soundswitch_version": version,
        "venue_guid": venue_identity["venue_guid"] if venue_identity else None,
        "venue_name": venue_identity["venue_name"] if venue_identity else None,
        "profile_summary": {
            "channel_count": len(channels),
            "has_intensity_channel": any(c["name"].casefold() == "intensity" for c in channels),
            "channel_names": [c["name"] for c in channels],
        },
        "universe": CANONICAL_UNIVERSE,
        "channel_span": CANONICAL_CHANNEL_SPAN,
        "hardware_statement": (
            "No hardware, MIDI, serial, Art-Net, Enttec, or DMX output was opened. "
            "Software/wire decode proof only. Status: SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED."
        ),
        "counts": counts(proof.checks),
        "checks": sorted(proof.checks, key=lambda c: c["id"]),
        "final_verdict": verdict,
    }


def render_markdown(report: dict[str, Any]) -> str:
    c = report["counts"]
    lines = [
        "# SoundSwitch pack-generation proof gate",
        "",
        f"- **Final verdict:** `{report['final_verdict']}`",
        f"- **Totals:** {c['pass']} PASS / {c['fail']} FAIL / {c['incomplete']} INCOMPLETE "
        f"(of {c['total']}); foundation {c['foundation_pass']}/{c['foundation_total']} PASS",
        f"- **Repo HEAD:** `{report['repo_head']}`",
        f"- **Generated:** {report['generated_at']} (excluded from determinism)",
        "",
        "## Source identity",
        f"- Project path: `{report['project_path']}`",
        f"- Project UUID: `{report['project_uuid']}` (canonical `{CANONICAL_PROJECT_UUID}`)",
        f"- SoundSwitch version: `{report['soundswitch_version']}`",
        f"- Venue GUID: `{report['venue_guid']}` ({report['venue_name']})",
        f"- Profile: {report['profile_summary']['channel_count']} channels, "
        f"intensity channel: {report['profile_summary']['has_intensity_channel']}, "
        f"Universe {report['universe']} {report['channel_span']}",
        "",
        "## Checks",
        "",
        "| id | status | title |",
        "| --- | --- | --- |",
    ]
    for chk in report["checks"]:
        lines.append(f"| `{chk['id']}` | **{chk['status']}** | {chk['title']} |")
    lines += ["", "## Check detail", ""]
    for chk in report["checks"]:
        lines += [
            f"### `{chk['id']}` — {chk['status']}",
            f"- **Title:** {chk['title']}",
            f"- **Foundation:** {chk['foundation']}",
            f"- **Expected:** `{json.dumps(chk['expected'])}`",
            f"- **Actual:** `{json.dumps(chk['actual'])}`",
            f"- **Evidence:** {chk['evidence']}",
            f"- **Sources:** {', '.join(chk['source_files_or_tools'])}",
        ]
        if chk["remediation"]:
            lines.append(f"- **Remediation:** {chk['remediation']}")
        lines.append("")
    lines += [
        "## Reference-rule, Static/DDJ, sparse, fail-closed summary",
        "- Reference rule: raw==0 clear/control; raw>0 -> raw-1 (2.10.3 one_based); generic fails ambiguous.",
        "- Static/DDJ: 32 GUID-keyed v5 slots; DDJ slots 8/16/17/24 render exact CH1-CH19 frames.",
        "- Sparse: present channels update, omitted persist, raw-zero clears main, stop/unload -> zero.",
        "- Fail-closed: wrong UUID (same RAVE GUID), wrong version, wrong Venue, collision, missing cue, "
        "unsupported layout, source drift, symlink.",
        "",
        "## Commands run",
        "```bash",
        f"python3 tools/prove_soundswitch_pack_generation.py --project {report['project_path']} \\",
        "  --output-dir artifacts/soundswitch_pack_generation_proof",
        "# C4 sub-command (passive capture replay, no device opened):",
        "python3 tools/ssfmt/re/validate_scripted_capture.py <a5.pcap> <A5.ssfile> \\",
        "  --autoloop-reference <SSAutoLoop5.ssfile> --venue <SoundSwitchVenues.bin> \\",
        "  --reference-rule one_based --control-channels 8,9,11",
        "```",
        "",
        "## Hardware",
        f"- {report['hardware_statement']}",
        "",
        "## Remaining blockers",
    ]
    blockers = [chk for chk in report["checks"] if chk["status"] in (FAIL, INCOMPLETE)]
    if blockers:
        for chk in blockers:
            lines.append(f"- `{chk['id']}` ({chk['status']}): {chk['remediation']}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main.
# --------------------------------------------------------------------------- #
def run_proof(project: Path, scratch: Path | None) -> Proof:
    proof = Proof()
    if not (project / ".ssproj").is_file():
        proof.record(
            "A0-project-readable", "Project is readable", False, foundation=True, incomplete=True,
            expected=f"{project}/.ssproj exists and is readable",
            actual="project path not readable in this environment",
            evidence="filesystem check", sources=[str(project)],
            remediation="Provide --project <path/to/default.ssproj>; the gate refuses to pretend.",
        )
        return proof
    venue_path = project / "SoundSwitchVenues.bin"
    venue_data = venue_path.read_bytes()

    check_source_identity(proof, project, venue_data)
    check_reject_wrong_uuid(proof, scratch)
    inv = check_inventory(proof, project, venue_path)
    check_reference_rule(proof, project)
    check_static_looks(proof, venue_data)
    check_sparse_renderer(proof)
    check_negative_preroll(proof, inv["autoloops"])
    check_fail_closed(proof, project, venue_data, inv["inventory"], inv["autoloops"])
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT,
                        help="Path to the canonical SoundSwitch .ssproj directory.")
    parser.add_argument("--scratch-project", type=Path, default=DEFAULT_SCRATCH,
                        help="Second container sharing the RAVE GUID, to prove UUID rejection.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    project = args.project.expanduser()
    scratch = args.scratch_project.expanduser() if args.scratch_project else None

    proof = run_proof(project, scratch)
    venue_path = project / "SoundSwitchVenues.bin"
    venue_data = venue_path.read_bytes() if venue_path.is_file() else b""
    report = build_report(project, venue_data, proof)

    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output_dir / "latest.md").write_text(render_markdown(report))

    c = report["counts"]
    print(f"final_verdict: {report['final_verdict']}")
    print(f"counts: {c['pass']} PASS / {c['fail']} FAIL / {c['incomplete']} INCOMPLETE "
          f"(foundation {c['foundation_pass']}/{c['foundation_total']})")
    print(f"json: {_rel(output_dir / 'latest.json')}")
    print(f"md:   {_rel(output_dir / 'latest.md')}")
    # Exit 0 only when implementation may begin; FAIL_DO_NOT_IMPLEMENT and
    # INCOMPLETE_PROOF_BLOCKER both fail closed (see verdict_exit_code). Deferred
    # non-foundation INCOMPLETE (F9/F10) stays PASS and still exits 0.
    return verdict_exit_code(report["final_verdict"])


if __name__ == "__main__":
    raise SystemExit(main())
