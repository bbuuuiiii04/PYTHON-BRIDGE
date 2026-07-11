---
doc_status: current
truth_level: spec
last_verified_commit: 85cb8ea
last_verified_date: 2026-07-11
validation_scope: >
  Implementation spec for AWR-209 — R2 of the AWR-208 binding outcome: tracks
  played from a FOREIGN USB resolve to the operator's imported+analyzed local
  copies (his workflow: import guest stick's tracks into his Rekordbox +
  analyze). Extends the AWR-207 seam. Operator mandate: TONIGHT, under the
  AWR-208 review doctrine. Dispatch gates on the AWR-207 ultracode review
  verdict (required fixes fold into this round).
---

# Implementation Spec — AWR-209 Foreign-USB resolution via the import workflow (R2)

## Part A — Context (verified; read, do not implement)
- [confirmed] AWR-207 (commits e6dc378..85cb8ea) resolves device-export loads
  to local twins via BPM/duration prefilter + beatgrid-fingerprint confirm +
  `local_anlz_path` phrase handoff. Its FILEPATH_RESOLVED payload is the
  designed extension seam (executive scope note to the builder, 2026-07-11).
- [confirmed] R2 workflow: the operator imports a guest stick's tracks into
  HIS Rekordbox and analyzes them → local copies exist WITH fresh PSSI. The
  matcher must connect the guest stick's loads to those copies.
- [confirmed risk] The guest stick's ANLZ carries the GUEST's beatgrid
  (possibly hand-edited, different RB version); the local import carries HIS
  fresh analysis. Grid-fingerprint confirm alone may reject true twins
  (cross-analysis variance) — the red-team lane (claude5.REDTEAM) is measuring
  the tolerance cliff on the real library; consume its numbers if available.
- [unknown → verify FIRST] pyrekordbox's capability to read a device stick's
  `PIONEER/rekordbox/export.pdb` (DeviceSQL). If pyrekordbox lacks it, parse
  ONLY the minimal fields needed (title/artist/duration per track id) via the
  documented PDB page format, read-only — or, if that is >1 focused task of
  work, BLOCK with the finding and fall back to grid+bpm+duration matching
  with tightened ambiguity handling (honest degradation, reported).
- [confirmed] Both Rekordbox import styles exist (audio copied to local disk
  vs referenced in place); FolderPath differs accordingly.

## Part B — Tasks (in order; commit by explicit paths after each)
### Absolute Rules
- Same live boundaries as AWR-207: bridge may be RUNNING — never touch it; no
  runtime-module edits beyond the named seams; master.db and export.pdb
  READ-ONLY always; fail closed — uncertain match = None; no broad try/except.
- Out of scope: the E2 stick-sidecar (foreign laptop), make_stick, frozen app.
- Behavior that must not change: AWR-207 mirror-stick resolution and all local
  resolution, byte-identical behavior (pin with regression tests).

### Task 1 — export.pdb identity lever (grid-independent)
On a device-export load whose AWR-207 twin match misses or is ambiguous:
locate the stick root from the ANLZ path (`/Volumes/<STICK>/PIONEER/...`),
read its `rekordbox/export.pdb` (read-only; verify pyrekordbox support first
per Part A), extract title/artist/duration for the LOADED track (keyed by the
stick's track id derivable from the USBANLZ path association in the pdb), and
match against DjmdContent (exact-normalized title+artist AND duration ±2s).
Exactly one hit → candidate twin; confirm with a RELAXED grid check (BPM
agreement + duration; do NOT require fingerprint identity across different
analyses) → emit the full local payload incl. `local_anlz_path` + ssid.
Zero or 2+ hits → None with reason `usb-pdb-miss` / `usb-pdb-ambiguous`.
Two agreeing independent levers (pdb tags + BPM/duration) justify the match;
a lever conflict (tags match, BPM wildly differs) → None with reason.

### Task 2 — imported-not-analyzed visibility
When a pdb-lever match finds the local content but its analysis is absent
(no AnalysisDataPath / unreadable local ANLZ): resolve to None with reason
`imported-not-analyzed` at INFO — the operator's fix is "finish analysis in
Rekordbox", and the log must say so in those words.

### Task 3 — duplicates and his-own-track overlap
If the pdb lever lands on a track he also owns in multiple versions
(2+ DjmdContent tag matches): None + `usb-pdb-ambiguous` listing the
candidate ids. Never pick by heuristic. (The red-team corpus round supplies
the regression cases.)

### Task 4 — tests (extend AWR-207's test seams; same pure-function style)
- pdb-lever match: synthetic pdb records + contents → exact behavior above,
  incl. both import styles' FolderPath shapes.
- Cross-analysis twin: grids differ beyond AWR-207 fingerprint tolerance but
  pdb tags + BPM/duration agree → match (this is THE R2 case).
- Lever conflict → None. Unanalyzed import → `imported-not-analyzed`.
- Ambiguity (his duplicates) → None with candidates listed.
- AWR-207 regression: mirror-stick fingerprint path unchanged when it hits
  (pdb lever only engages on miss/ambiguous).
- Scripted: a pdb-lever-resolved twin carries ssid exactly like AWR-207.

### Task 5 — contract + docs + checks
`rekordbox_readers` contract docs_update; AWR-209 registry row (re-check max
id); pre-show checklist doc section (import→analyze→verify ritual + the exact
log reasons to look for); 3 hard checks; scoped suites + full discover
reconciled BY NAME.

## Part C — Invariants
All AWR-207 Part C invariants verbatim, plus: export.pdb is never written;
a mounted guest stick is never modified in any way.

## Part D/E — Tests per Task 4; acceptance =
- [ ] All Task-4 cases green; AWR-207 + local regression pinned green.
- [ ] Real-stick spot run if /Volumes/MINK mounted (its pdb exercises the
      parser even though it's his own stick — report what resolved via which
      lever). Honest ceiling: a REAL foreign stick test = operator gate.
- [ ] Red-team corpus findings (claude5.REDTEAM.report.md) consumed: any
      matcher tolerance change it forced is applied + re-tested.
- [ ] 3 hard checks; registry; contract; explicit-path commits; nothing
      gitignored committed; bridge untouched.

## When You Finish
Report to /tmp/rbss_lane_signals/<session>.AWR209.report.md + .done signal
(park-with-state on quota cut). Plain-language summary: what the operator's
import ritual now guarantees, the exact miss-reasons he might see and what
each means, and what stays honest-unresolved by design.
