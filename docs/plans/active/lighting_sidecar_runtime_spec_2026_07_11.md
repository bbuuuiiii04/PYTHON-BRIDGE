---
doc_status: current
truth_level: spec
last_verified_commit: 85cb8ea
last_verified_date: 2026-07-11
validation_scope: >
  Implementation spec for AWR-211 — the runtime sidecar SOURCE: on any laptop,
  resolve loading tracks against the stick-carried lighting memory (AWR-210's
  sidecar) when the local DB can't answer. Completes R3 of the AWR-208 binding
  outcome (foreign laptop, incl. two-USB). Sequenced AFTER AWR-209 in the same
  lane (shared resolver seam). STAGED.
---

# Implementation Spec — AWR-211 Runtime sidecar source (foreign-laptop resolution)

## Part A — Context (verified)
- [confirmed] AWR-210 (building in parallel) writes the sidecar per its spec:
  `<stick>/RBSS BRIDGE USB/lighting_sidecar/` with `index.json` (per-track:
  content_id, title/artist/duration/bpm, beatgrid_fingerprint, anlz_relpaths,
  v4 ref, ssid, laser_tag_beats) + copied phrase-bearing ANLZ files + v4
  records. THE INDEX SCHEMA IN THAT SPEC IS THE CONTRACT — if claude6's
  landed format differs, reconcile to the SPEC (or BLOCK), don't improvise.
- [confirmed] Resolution source order (charter R3): local master.db (when
  present/readable) → sidecar → honest miss. On the operator's laptop nothing
  changes unless local misses; on a foreign laptop (no DB) the sidecar is the
  only source.
- [confirmed] TWO-USB case: the sidecar lives on HIS stick; tracks may load
  from a DIFFERENT (guest) stick. Sidecar discovery therefore scans all
  mounts for `*/RBSS BRIDGE USB/lighting_sidecar/index.json` and also checks
  `~/Library/Application Support/RBSS Bridge/lighting_sidecar/index.json` so an
  installed bridge survives eject. Implemented behavior revalidates every
  candidate and discovers rebuilds/unplug/replug/new mounts instead of pinning
  one root for the session. Byte-identical matching installed+mounted records
  deduplicate with App Support preferred; different matching generations fail
  closed as `sidecar-root-ambiguous`. Absence remains a silent miss.
- [binding] AWR-209 Task 0 identity rule applies IDENTICALLY here:
  fingerprint-only match = mirror-class strictness only; looser requires the
  tag lever (the sidecar index carries tags precisely for this); no
  corroboration = None with reason. The red-team collision regressions apply.
- [confirmed] Phrase handoff stays the proven contract: the resolved payload's
  `local_anlz_path` points INTO the sidecar's copied ANLZ files (they carry
  PSSI). v4: the payload carries the sidecar v4 record; the runtime worker
  prefers payload-provided v4 over a spectral-cache lookup (verify the exact
  seam in `_read_runtime_anlz_data`/its caller at HEAD; smallest change wins;
  no push-loop I/O). With smart rearm enabled, the resolved sidecar ANLZ worker
  must start even when spectral analysis and LED-v2 identity are disabled.

## Part B — Tasks
### Absolute Rules
Same as AWR-207/209 (bridge running = untouched; read-only everything; fail
closed; explicit-path commits). Out of scope: exporter internals (AWR-210),
make_stick, frozen-app packaging. Local-DB-present behavior must be pinned
unchanged when local resolution succeeds.

1. **Sidecar reader**: load + validate index.json (schema_version gate,
   fail-closed on unknown schema), lazy, cached per session, absence = silent
   no-op source.
2. **Source chaining**: on local-DB miss OR no-DB environment, run the
   sidecar match (BPM/duration prefilter → Task-0 identity rule with the
   index's fingerprint + tags) → emit the full payload (sidecar anlz path,
   v4 record, ssid, laser_tag_beats) with `source='sidecar'` provenance in
   the log. Ambiguity/miss reasons mirror AWR-209's naming.
3. **Foreign-environment guard**: master.db absent/unreadable must not error
   the resolver — log once at INFO ("no local library — sidecar-only mode"),
   proceed.
4. **Tests** (pure seams): schema gate; discovery across multiple mounts incl.
   guest-stick load + his-stick sidecar; Task-0 rule regressions from the
   red-team collision pairs; payload equivalence vs a local resolve (incl.
   ssid/scripted); v4-from-payload preference; no-DB mode; local-present
   regression (sidecar never consulted when local hits).
5. **Contract/docs/registry/checks** per house rules (AWR-211 row exists —
   update, don't duplicate — re-check registry state first).

## Part E — Acceptance
- [ ] All Task-4 cases green; scoped suites + discover BY NAME; 3 hard checks.
- [ ] Desk spot-run: with the real sidecar (claude6's export to the mounted
      stick or staging dir), resolve a real USB ANLZ path in sidecar-only mode
      (simulate no-DB by pointing the DB path at a nonexistent file in a test
      harness — never touch the real DB) and show the phrase-bearing payload.
- [ ] Honest ceilings stated: real foreign-laptop run = operator hardware
      gate (D5); two-USB live test = same gate.
Report + signals: /tmp/rbss_lane_signals/<session>.AWR211.{done,blocked,report.md}.
