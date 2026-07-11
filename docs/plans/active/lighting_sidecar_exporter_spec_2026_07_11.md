---
doc_status: current
truth_level: spec
last_verified_commit: 85cb8ea
last_verified_date: 2026-07-11
validation_scope: >
  Implementation spec for AWR-210 — the lighting-sidecar EXPORTER: an offline
  tool that writes a portable lighting memory of every analyzed track onto the
  stick's bridge payload. R3 of the AWR-208 binding outcome. Offline tool
  only; ZERO runtime imports; the runtime consumer is AWR-211 (separate spec).
---

# Implementation Spec — AWR-210 Lighting sidecar exporter (offline tool)

## Part A — Context (verified; read, do not implement)
- [confirmed] Binding R3: on a foreign laptop (no local collection), any track
  his Rekordbox ever analyzed — loading from HIS stick or a GUEST stick
  plugged alongside — must light fully. The data must live on his stick.
- [confirmed] Rekordbox exports no PSSI to USB; the local ANLZ EXT files under
  `~/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/...` carry it. The proven
  runtime handoff is an ANLZ path (`local_anlz_path`, AWR-207) — so the
  sidecar copies the ANLZ FILES themselves and the runtime source (AWR-211)
  will hand paths INTO the sidecar. This spec builds only the exporter.
- [confirmed] Identity levers at runtime will be beatgrid fingerprint + tags
  (title/artist/duration/BPM) — the sidecar index must carry both per track.
- [confirmed] The v4 spectral cache exists locally (`spectral_cache.py`
  storage); per-track v4 records must travel too (AWR-211 will overlay them
  read-only). Laser tag beats + SoundSwitch ssid ride the AWR-207 payload
  today — the index carries them per track.
- [confirmed] The stick payload root exists: "RBSS BRIDGE USB/" (AWR-186 M2
  make_stick). The exporter targets `<payload root>/lighting_sidecar/`.
- [unknown → measure and report] Total sidecar size for his full library
  (ANLZ copies + v4 blobs). Report MB by component; no size optimization
  work tonight unless it exceeds free stick space — then BLOCK with numbers.

## Part B — Tasks (in order; commit by explicit paths after each)
### Absolute Rules
- New offline tool file(s) only: `tools/lighting_sidecar_export.py` (+ tests).
  NO runtime module edits, NO imports from/into runtime paths beyond what
  offline tools already use (pyrekordbox read-only, spectral cache READ).
- Sources are READ-ONLY always: master.db, local ANLZ share, v4 cache, stores.
  Never write anything outside the target sidecar directory.
- The live bridge may be RUNNING — never touch it. Guest/mounted sticks are
  never written except the explicit target stick payload directory the
  operator names on the command line.
- Fail closed + loud: unreadable/missing per-track data → that track is
  SKIPPED and listed in the report manifest with a reason, never half-written.

### Task 1 — the exporter tool
`python3 tools/lighting_sidecar_export.py --dest <stick payload root>` :
1. Walk master.db (read-only, pyrekordbox pattern from filepath_resolver):
   every content with analysis (AnalysisDataPath present + local ANLZ
   readable). For each: copy the ANLZ set (DAT + EXT/2EX siblings —
   `_candidate_anlz_paths` semantics) into
   `lighting_sidecar/anlz/<content_id>/`; extract beatgrid fingerprint
   (reuse the AWR-207 fingerprint helpers — import from the tool side or
   factor into a shared pure module IF that requires no runtime-module edit;
   otherwise reimplement the pure math in the tool with a parity test);
   read v4 from the spectral cache for (filepath, beatgrid) if present;
   read ssid (`_read_soundswitch_id` equivalent) + laser-tag beats the way
   the resolver does.
2. Write `lighting_sidecar/index.json`: schema_version, built_at HEAD +
   timestamp, per-track records {content_id, title, artist, duration_s, bpm,
   beatgrid_fingerprint, anlz_relpaths, v4_relpath or inline, ssid,
   laser_tag_beats, source_filepath (provenance only)}. Deterministic order.
3. v4 records: one file per track `lighting_sidecar/v4/<content_id>.json`
   (or the cache's native serialization — reuse, don't invent).
4. Incremental: unchanged tracks (same source ANLZ mtime+size and same cache
   record) are skipped on re-export; `--full` forces rebuild. Deleted-from-
   library tracks are pruned from the sidecar (report them).
5. End-of-run report: track counts (exported/skipped+reasons/pruned), MB by
   component (anlz/v4/index), elapsed. Nonzero exit if ANY track skipped for
   an unexpected reason class.

### Task 2 — tests (`tests/test_lighting_sidecar_export.py`)
Pure seams (synthetic content rows + temp dirs; no real DB/cache in units):
index build determinism; incremental skip/prune logic; sibling ANLZ copy
completeness; skip-with-reason on unreadable input; fingerprint parity with
the resolver's values (same input → same fingerprint); never-write-outside-
dest guard.

### Task 3 — real run + docs
- Real export run against his library to the mounted stick if present
  (/Volumes/MINK payload root) else to a local staging dir; report the real
  numbers (Part A unknown).
- Registry AWR-210 row (re-check max id); contract: offline tooling — extend
  `spectral_analysis`-style coverage or add a sidecar contract key if the
  contracts file has no fit (§7 contract-first); 3 hard checks; scoped tests.

## Part C — Invariants
Zero runtime behavior change (no runtime file touched); bridge untouched;
sources read-only; secrets/live-config never copied into the sidecar (the
sidecar carries analysis data only — assert no config/*.json, no govee.env,
nothing from config/ lands in dest).

## Part D/E — per Task 2; acceptance = tool runs end-to-end on the real
library with honest counts + sizes; tests green; hard checks green; explicit-
path commits; report at /tmp/rbss_lane_signals/<session>.SIDECAR.report.md +
.done signal (park-with-state on quota cut).
