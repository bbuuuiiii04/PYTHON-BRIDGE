---
doc_status: research-tool-guide
truth_level: byte-and-capture-grounded
last_verified_commit: fd40843
last_verified_date: 2026-06-20
validation_scope: read-only research helpers; no production or hardware authority
---

# SoundSwitch Read-Only Research Helpers

These helpers inspect current project bytes and passive captures. They are not a
production exporter/parser, are not imported by bridge runtime code, and must
never write into `~/Music/SoundSwitch`.

Do not use them to start/stop/signal/restart the bridge or send MIDI, OS2L,
Art-Net, serial, Enttec, or physical DMX. Capture commands and SoundSwitch UI
operations are operator-owned. Status remains **SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**.

`WORKING_NOTES.md` is retained historical Stage-1 scratch. Its model and paths
are stale; use the current docs and tools instead.

## Tool map

| Tool | Purpose |
| --- | --- |
| `analyze_ssfile_structure.py` | Strict current-profile autoloop structure and continuation parse. |
| `analyze_scripted_ssfile.py` | Strict shared-441 scripted layout parse. |
| `analyze_scripted_layouts.py` | 45-file layout classifier and strict fallback dictionary/timeline boundary discovery. |
| `parse_venue_cues.py` | Current Venue attribute-cue records and sparse group patches. |
| `layered_renderer.py` | Pure research state model: inherited/main/control layers and clear events. |
| `parse_artnet_pcap.py` | Classic-pcap/ArtDmx passive decoder. |
| `validate_scripted_capture.py` | A5 event/frame equality and timing residuals. |
| `validate_autoloop_capture.py` | Segment phase fitting with static and explicitly transition-only modes. |
| `parse_autoloop_catalogs.py` | Exact base/extended catalog and category-table decoder. |
| `parse_track_map.py` | Repeated TrackMap identity subrecords, duplicates, stale paths, and optional audio tags. |
| `inventory_project_artifacts.py` | `.ssproj`, `.ssa`, preset, recordable, demo-media, and Venue-backup classification. |
| `analyze_fixture_prefix.py` | Six fixture groups, parent links, position slots, and Venue cross-reference. |
| `analyze_control_semantics.py` | Auxiliary/negative/ref-zero/cue/channel/capture residual correlation. |
| `analyze_deck_ownership.py` | Per-deck AppLog versus passive Universe-0 correlation and blockers. |
| `audit_legacy_capture.py` | Older pcap, frozen hashes, Venue snapshot, and derived index-library audit. |
| `build_coverage_reports.py` | Deterministic 42-row autoloop and 45-row scripted JSON report. |
| `ssparse.py` | Heuristic discovery token viewer only; never format authority. |

Four Stage-1 sources were reconstructed from surviving ignored Python bytecode
after the worktree loss: `uuidxref.py`, `correlate_midi_autoloop.py`,
`align_capture.py`, and `artnet_sniff.py`. They are retained as historical tools,
not current format authority. `artnet_sniff.py` binds a live UDP port and is
operator-owned; agents must not run it. `align_capture.py` writes beside its pcap,
so prefer the current stdout-only validators.

Every strict parser reports path, size, version where present, source offsets,
counts, and an unsupported/partial reason. Unsupported trailing bytes remain
visible. Validators separate byte equality, timing, initial-state policy, and
other-deck evidence.

## Environment

Run from the repo root:

```bash
cd /Users/bbui/rb_ss_bridge_v2
PROJ="$HOME/Music/SoundSwitch/default.ssproj"
VENUE="$PROJ/SoundSwitchVenues.bin"
```

Commands below read the project and write derived JSON only to `/tmp`.

## Structural corpus

```bash
python3 tools/ssfmt/re/analyze_ssfile_structure.py \
  "$PROJ"/SSAutoLoop*.ssfile > /tmp/autoloop_structure.json

python3 tools/ssfmt/re/analyze_scripted_layouts.py \
  "$PROJ"/'{'*.ssfile \
  --autoloop-reference "$PROJ/SSAutoLoop5.ssfile" \
  > /tmp/scripted_layouts.json

python3 tools/ssfmt/re/parse_venue_cues.py \
  "$VENUE" > /tmp/venue_cues.json
```

Expected current totals: 42/42 autoloops parsed; 44/45 scripted parsed; one
In-App Demo layout unsupported; 232 Venue cue records.

## Scripted A5 validation

```bash
python3 tools/ssfmt/re/validate_scripted_capture.py \
  tools/ssfmt/captures/scripted_sanfrandisco_a5_20260619.pcap \
  "$PROJ/{A5B0ACD1-D426-4BDB-9C8C-D05EA084F9CF}.ssfile" \
  --autoloop-reference "$PROJ/SSAutoLoop5.ssfile" \
  --venue "$VENUE" \
  --control-channels 11 \
  > /tmp/a5_validation.json
```

Expected: fit mode `exact_layered_state_anchor`, 16/16 event frames, 14/14
positive references, and 2/2 raw-zero events exact. Captured frames are not
renderer input.

## Combined autoloop validation

```bash
python3 tools/ssfmt/re/validate_autoloop_capture.py \
  tools/ssfmt/captures/bridge_driven_autoloops_20260619.pcap \
  tools/ssfmt/captures/bridge_driven_autoloops_20260619_logs/bridge.log \
  tools/ssfmt/captures/bridge_driven_autoloops_20260619_logs/AppLog*.txt \
  --proj "$PROJ" \
  --venue "$VENUE" \
  > /tmp/autoloop_validation.json
```

Expected current extraction: 30,821 Universe-0 frames, 68 usable segments, 17
byte-exact static segments, and 51 unresolved segments. A first-wire-frame mode
is labeled transition-only and does not establish a full static render.

## Catalogs, TrackMap, and artifacts

```bash
python3 tools/ssfmt/re/parse_autoloop_catalogs.py \
  "$PROJ/SoundSwitchAutoLoops.bin" \
  "$PROJ/SoundSwitchAutoLoopsEx.bin" \
  > /tmp/autoloop_catalogs.json

python3 tools/ssfmt/re/parse_track_map.py \
  "$PROJ/SoundSwitchTrackMap.bin" \
  --project-dir "$PROJ" \
  --check-tags \
  > /tmp/track_map.json

python3 tools/ssfmt/re/inventory_project_artifacts.py \
  "$PROJ" > /tmp/project_artifacts.json
```

Expected: 18 + 24 catalog entries with zero trailing bytes; 95 TrackMap mapping
records; 61/61 comparable tags exact; nine classified additional artifacts.

`--check-tags` reads metadata only from exact mapped paths. It does not scan the
filesystem or modify audio.

## Fixtures, control fields, and deck evidence

```bash
python3 tools/ssfmt/re/analyze_fixture_prefix.py \
  "$PROJ"/SSAutoLoop*.ssfile \
  --venue "$VENUE" \
  > /tmp/fixture_prefix.json

python3 tools/ssfmt/re/analyze_control_semantics.py \
  "$PROJ" \
  --venue "$VENUE" \
  --capture-report /tmp/autoloop_validation.json \
  > /tmp/control_semantics.json

python3 tools/ssfmt/re/analyze_deck_ownership.py \
  tools/ssfmt/captures/bridge_driven_autoloops_20260619.pcap \
  tools/ssfmt/captures/bridge_driven_autoloops_20260619_logs/AppLog*.txt \
  --validation-report /tmp/autoloop_validation.json \
  > /tmp/deck_ownership.json
```

These commands intentionally report `partial`/`blocked`: universe/address,
control ownership, auxiliary/sentinel behavior, and deterministic deck ownership
remain unresolved.

Audit the older capture without inventing its missing segment boundaries:

```bash
python3 tools/ssfmt/re/audit_legacy_capture.py \
  tools/ssfmt/captures/artnet_lo.pcap \
  --index-library tools/ssfmt/captures/index_dmx_library.json \
  --baseline-hashes tools/ssfmt/captures/baseline/ssproj_hashes_1781910365.txt \
  --snapshot-venue tools/ssfmt/captures/snap/SoundSwitchVenues.bin \
  --current-venue "$VENUE" \
  > /tmp/legacy_capture_audit.json
```

The derived library covers 41/42 catalog indices and all 42 frozen autoloop
hashes still match, but it retains only one sample state per index and no raw
segment timestamps. It is coverage evidence, not per-frame validation evidence.

## Coverage report

After producing both validation JSON files:

```bash
python3 tools/ssfmt/re/build_coverage_reports.py \
  "$PROJ" \
  --venue "$VENUE" \
  --catalog "$PROJ/SoundSwitchAutoLoops.bin" \
  --catalog "$PROJ/SoundSwitchAutoLoopsEx.bin" \
  --autoloop-capture-report /tmp/autoloop_validation.json \
  --autoloop-reference "$PROJ/SSAutoLoop5.ssfile" \
  --track-map "$PROJ/SoundSwitchTrackMap.bin" \
  --scripted-validation /tmp/a5_validation.json \
  > /tmp/soundswitch_coverage.json
```

Expected current summary:

- autoloops: 42 structural, 19 captured, 2 byte-exact files, 23 uncaptured;
- scripted: 45 total, 44 structural, 1 unsupported, 1 byte-exact captured;
- TrackMap: 39 current scripted SSIDs mapped, six unmapped.

## Local checks

```bash
python3 -m py_compile tools/ssfmt/re/*.py
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

The first three documentation checks are hard gates. Staleness is advisory.
None of these checks proves physical hardware behavior.
