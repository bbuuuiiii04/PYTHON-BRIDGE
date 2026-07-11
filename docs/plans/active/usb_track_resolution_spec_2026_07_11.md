---
doc_status: current
truth_level: spec
last_verified_commit: 38e127a
last_verified_date: 2026-07-11
validation_scope: >
  Implementation spec for AWR-207 — resolve USB-export tracks to their local
  library twin so phrase/spectral/F2/SoundSwitch lighting works when the
  operator plays from the USB device tree in Rekordbox (his primary play mode).
  Root cause verified live 2026-07-11. STAGED; activates at operator restart.
---

# Codex Implementation Spec — AWR-207 USB-export track resolution (local-twin match)

## Part A — Context & Root Cause (verified at the executive desk; read, do not implement)

- [confirmed] Operator plays ALL tracks from the USB device tree in Rekordbox
  (USB mounted on the laptop). Lighting is dark/degraded for those tracks:
  live heartbeats show `phrase:"other"`, `rgb_health:"degraded"` throughout.
- [confirmed] The direct reader captures the USB ANLZ path fine:
  `[ANLZ][DIRECT] deck=1 path=/Volumes/MINK/PIONEER/USBANLZ/P018/000086A0/ANLZ0000.DAT`
  (live log 2026-07-11 ~18:30). Local tracks look like
  `.../share/PIONEER/USBANLZ/967/938c2-a637-.../ANLZ0000.DAT`.
- [confirmed] `_db_lookup_by_anlz` (filepath_resolver.py:263-285) extracts the
  directory before `/ANLZ` via `re.search(r'USBANLZ/[^/]+/([^/]+)/ANLZ', ...)`
  and substring-matches it against each content's `AnalysisDataPath` in
  master.db. Local UUIDs match; USB device IDs (`000086A0`) match NOTHING →
  returns None.
- [confirmed] On None, `_resolve_anlz_worker` (:376-395) falls back to lsof —
  which tonight MIS-matched USB tracks to an unrelated open file
  (`[FRES] match src=lsof file=Click Sound 01 Electronic.wav`, three loads).
  So USB tracks get a wrong identity, not just a missing one.
- [confirmed] Consequence chain: no local content match → no content_id → no
  phrase plan, no v4 spectral cache, no F2, no scripted detection, no
  SoundSwitch ID, no laser-tag beats. Everything keys off local identity.
- [confirmed] `_extract_beatgrid_from_anlz(anlz_path)` already runs on the USB
  file (:276) BEFORE the DB loop — the USB copy's beatgrid is available at
  resolution time. Beatgrid-fingerprint identity is proven in this repo
  (AWR-200 resolves lineages by "library filepath + beatgrid fingerprint").
- [confirmed] The resolver runs in daemon threads (`resolve_by_anlz` spawns
  `anlz-d{deck}` threads, :367-374) — file I/O is allowed there; the 200 Hz
  push loop is not involved.
- [assumed] Every USB track has a local-library twin (the export was made from
  this library). A USB track with no local twin must resolve to UNRESOLVED,
  never to a wrong file.

## Part B — Tasks (in order; commit by explicit paths after each)

### Absolute Rules
- Out of scope: rb_state_reader event ordering (ANLZ_PATH before TRACK_LOADED
  stays), StateManager, the push loop, all lighting subsystems, anlz_reader
  parsing, the live bridge process (may be RUNNING — never touch it).
- Behavior that must not change: local-library resolution (UUID path) works
  exactly as today; TL/title fallbacks unchanged; unresolved stays unresolved.
- Fail closed: an uncertain match is NO match. Never emit FILEPATH_RESOLVED
  with a guessed identity. No broad try/except, no silent fallbacks.

### Task 1 — `filepath_resolver.py`: local-twin match for USB-export ANLZ paths
When the existing AnalysisDataPath lookup misses AND the anlz_path is a
device-export path (on `/Volumes/`, or the captured ID doesn't look like a
local UUID), match the local twin:
1. Cheap DB prefilter: candidate local contents by BPM (±0.05 after /100
   scaling) and duration (±2 s) using existing DjmdContent columns (reuse the
   existing `Rekordbox6Database` session pattern at :279-283; read-only).
2. Confirm by beatgrid fingerprint: compare the USB beatgrid (already
   extracted) against each candidate's local ANLZ beatgrid
   (`_extract_beatgrid_from_anlz` on the candidate's AnalysisDataPath-derived
   path; reuse `_candidate_anlz_paths` :148). Match = same beat count within
   tolerance AND first-beat + sampled beat-time agreement (define exact
   tolerances as constants; derive from what AWR-200's resolution lane used if
   its fingerprint exists to reuse — check `tools/spectral_ear_benchmark.py`
   and reuse rather than invent, per repo reuse rule).
3. Exactly ONE candidate passes → return the LOCAL twin's full payload
   (FolderPath, bpm, SSID via `_read_soundswitch_id`, content_id, laser-tag
   beats — the same payload shape :286-323 builds today) so every downstream
   consumer behaves as if the track was loaded locally. Zero or 2+ candidates
   → return None with an INFO log naming the reason (`usb-twin-miss` /
   `usb-twin-ambiguous` + counts).
Performance: prefilter first, read only prefiltered candidates' ANLZ files
(a handful, in the resolver thread). No whole-library ANLZ sweep per load; an
in-process per-session memo of confirmed usb-path→content_id matches is fine.

### Task 2 — stop the lsof mis-match for USB loads
When Task 1 returns None for a device-export path, the worker must NOT fall
back to lsof blindly: tonight lsof matched an unrelated open click-sound file.
Smallest honest change: for device-export paths, skip the lsof fallback (go
straight to unresolved + title fallback if the reader triggers it) OR keep
lsof only with a duration guard that must match the USB ANLZ-derived duration
within ±2 s. Pick whichever the existing lsof code supports more cleanly
(`_lsof_audio_files` :83, `_duration_ms` :98) and state the choice in the
report. An unresolved USB track must read as unresolved — the current
wrong-file identity is worse than nothing.

### Task 3 — tests (extend the resolver's existing test file; find it via the
tests/ tree and follow its harness patterns)
Pure-function seams (no live DB in unit tests — inject candidate lists /
synthetic beatgrids):
- USB-path detection: local UUID paths never enter the twin-match path.
- Fingerprint match: exact twin → match; off-by-beats / different track →
  no match; two candidates passing → ambiguous → None.
- Payload equivalence: a matched twin yields the same payload fields as a
  local resolve.
- lsof guard: a wrong-duration open file can no longer produce a match for a
  device-export path (regression pinning tonight's failure).
- Local resolution regression: existing UUID-path tests stay green.

### Task 4 — contract + docs + checks
Contract key `rekordbox_readers` (§7: extend `docs/agents/change_contracts.yml`
first if this resolver surface isn't listed); update every docs_update doc
(subsystem card `docs/subsystems/rekordbox_readers.md` at minimum); add the
AWR-207 registry row (re-check current max ID); run the 3 hard checks + the
resolver's scoped suite + `python3 -m unittest discover tests` reconciled BY
NAME against the environmental baseline.

## Part C — Invariants That MUST Still Hold
- `RBStateReader._tick_deck()` enqueues ANLZ_PATH before TRACK_LOADED (untouched).
- No blocking I/O added to the push loop; all new I/O stays in the existing
  resolver daemon threads.
- Events immutable; resolver publishes via the queue exactly as today.
- Never write to master.db (read-only, `unlock=True` pattern as today).
- STAGED: the running bridge is untouched; behavior changes at operator restart.

## Part D — Tests
Task 3. The fingerprint comparator must be a pure function testable without
files or DB.

## Part E — Acceptance
- [ ] A real USB-export ANLZ path resolves to its local twin at a desk test
      against the real DB (read-only spot run; report which track + content_id)
      — use a /Volumes/MINK path from the live log if the stick is mounted;
      if not mounted, say so and rely on the unit seams.
- [ ] Zero/ambiguous-match and lsof-guard behavior proven by tests.
- [ ] Local-resolution regression green; scoped suite + full discover
      reconciled by name; 3 hard checks green.
- [ ] Contract + registry + docs updated; commits by explicit paths; no
      gitignored/secret files committed; live bridge untouched.

## When You Finish
Report: changed files, test counts by name, the desk spot-run evidence, honest
ceilings (SOFTWARE-VALIDATED ONLY; the operator's next USB session is the real
gate), and the plain-language summary: after his next restart, tracks played
from the USB device tree light exactly like local tracks (phrase, drops, F2,
SoundSwitch, lasers); tracks with no local twin stay dark-but-honest instead
of impersonating a click sound. Print `AWR207-DONE` on its own line AND write
`/tmp/rbss_lane_signals/sol205.AWR207.done` (one-line summary inside); if
blocked or quota-cut, park with state: commit completed tasks, write
`.blocked` with exactly where you stopped.
