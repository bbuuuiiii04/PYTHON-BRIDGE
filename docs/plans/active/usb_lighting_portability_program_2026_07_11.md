---
doc_status: current
truth_level: program-charter (design only; zero implementation authorized)
last_verified_commit: 38e127a
last_verified_date: 2026-07-11
validation_scope: >
  AWR-208 program charter — portable lighting data so the operator's USB stick
  lights correctly on ANY laptop, including foreign machines with none of his
  local Rekordbox collection. Operator mandate 2026-07-11: "THIS NEEDS CAREFUL
  PLANNING, IMPLEMENTATION, AND REVIEW LOOPS." Every stage below gates on an
  independent review before the next begins.
---

# AWR-208 — USB lighting portability program (charter)

## The requirement (operator, verbatim intent)
The USB stick is how ALL tracks are played. It must produce full lighting
(phrase, drops, darkness/F2, spectral behavior, SoundSwitch, lasers) in two
environments:
- **E1 — his laptop** (full local collection): AWR-207 (in flight) solves this
  by matching USB tracks to their local library twin and parsing phrase from
  the local ANLZ files.
- **E2 — a foreign laptop** (no collection, bridge running from the stick's
  frozen app): nothing local exists, and **Rekordbox does not export phrase
  data (PSSI) to USB** [operator-confirmed 2026-07-11]. The data must therefore
  TRAVEL ON THE STICK.

## Verified ground truth this design stands on
- [confirmed] USB ANLZ paths are readable by the direct reader on load
  (`[ANLZ][DIRECT] path=/Volumes/MINK/PIONEER/USBANLZ/...`, live log 2026-07-11).
- [confirmed] USB export ANLZ lacks PSSI phrase sections (operator fact; the
  runtime phrase parse consumes ANLZ paths at `state_manager.py:2259/:2567`).
- [confirmed] The stick already carries a bridge payload: AWR-186 M2
  `make_stick` builds "RBSS BRIDGE USB/" with the frozen app + pack carriage
  (software-gated; foreign-Mac frozen-app fixes exist on branch
  `claude/rbss-bridge-install-debug-59yrn6`, operator-unvalidated).
- [confirmed] All lighting truth (phrase plans, v4 spectral features, SS
  scripted ids, laser tags) exists ONLY on his laptop, derivable at
  stick-build time.

## Proposed architecture (to be attacked in D1 review, not assumed)
**Build-time sidecar, runtime fallback chain.**
1. At stick build/refresh (on his laptop), a `make_stick` step exports a
   per-track **lighting sidecar** onto the stick: phrase data (PSSI-derived),
   beatgrid fingerprint, the spectral fields the runtime actually consumes
   (v4 or its derived subset — size question below), SoundSwitch scripted id,
   laser-tag beats — keyed by the stick's own USBANLZ id AND fingerprint.
2. Runtime resolution chain (extends AWR-207's payload-driven seam):
   local DB twin → stick sidecar → honest unresolved. Foreign laptops hit the
   sidecar path; his laptop keeps preferring local truth.
3. Staleness: fingerprint mismatch (re-analyzed/re-gridded track) = honest
   miss + a build-tool warning listing stale tracks; never guess.

## ⚠ BINDING FINAL OUTCOME (operator mandate 2026-07-11, verbatim; the
## executive seat is FULLY responsible for delivering both)
> "Playing tracks from USB that is a mirror of my collection: LIGHTING MUST
> FULLY WORK. Playing tracks from FOREIGN USB after exporting their collection
> to my rekordbox to do phrase analysis: MUST ALSO WORK. You need to consider
> ALL edge cases."

**R1 (mirror USB)** = AWR-207 (built; under ultracode review).
**R1-S (operator addition 2026-07-11): SCRIPTED TRACKS MUST ALSO WORK from
USB** — the resolved twin payload must carry the local SSID so scripted
detection/arming engages exactly as a local load, the async-resolution latency
must not let a scripted track audibly start in autoloop mode before flipping,
and ambiguous/unresolved USB loads must not leave stale scripted state. Added
as mandatory surface 7 of the AWR-207 ultracode review; any gap is a required
fix, not a future item. (R2 corollary: a guest track he scripts after import
becomes his scripted content and must behave identically.)
**R2 (foreign USB + operator import/analyze workflow)**: the operator imports
the guest stick's tracks into HIS Rekordbox and analyzes them — his Rekordbox
then owns local copies WITH fresh PSSI. The bridge must twin-match the guest
stick's loads to those imported local copies. Mechanically this is AWR-207's
matcher pointed at cross-analysis twins; the deltas that MUST be engineered
and reviewed (AWR-207 extension round):
- [confirmed risk] Cross-analysis beatgrid variance: the guest stick carries
  THEIR grid (possibly hand-edited); the local import carries HIS fresh grid.
  Grid-fingerprint confirmation must tolerate benign variance without
  admitting false matches — and needs a grid-independent second lever:
- [design] `export.pdb` identity lever: every export stick carries its own
  track DB (title/artist/duration/paths). Parse it read-only and match
  title+artist+duration against the imported local contents. Strong, grid-free,
  and also fixes R1 sticks whose grids he edits after export.
- [design] Duplicate/near-duplicate handling: guest tracks he also owns, or
  same-BPM edits — deterministic pick or honest-unresolved; never a guess.
- [design] Unanalyzed imports: imported but not-yet-analyzed tracks miss with
  a visible log reason ("imported-not-analyzed") so the operator knows to
  finish analysis, not debug the bridge.
- [design] Both Rekordbox import styles (audio copied to disk vs referenced on
  the mounted stick) must resolve; v4 extraction needs the audio path readable
  (stick is mounted while playing — state the assumption).
- [operator workflow doc] The import→analyze ritual becomes a documented
  pre-show checklist step with a verification command (e.g. the resolver's
  miss-reasons surfaced via runtime status) so R2 is checkable BEFORE guests
  arrive.
E2 (foreign laptop, sidecar) and the degraded no-import tiers below remain the
fallback ladder when the R2 workflow wasn't done.

## E3 — SOMEONE ELSE'S USB on his laptop (operator question 2026-07-11)
A guest stick carries tracks that were NEVER in his collection: no local twin,
no sidecar, and no PSSI on their stick either. Honest capability ladder, to be
settled/ranked in D1 (levers verified in current code, quality unproven):
- [confirmed lever] Their stick's ANLZ DOES carry beatgrid + waveform data —
  readable today (`[ANLZ][DIRECT]` reads any mounted stick's files).
- [confirmed lever] The runtime already extracts v4 spectral features AT LOAD
  for uncached tracks (`state_manager.py:~2553`, `extract_spectral_features_v4`
  behind `_V4_AT_LOAD_MAX_S`) — the guest AUDIO file on their stick is
  readable, so spectral lighting can work on HIS laptop (extraction cost/cap
  is a D1 question).
- [confirmed lever] `anlz_reader` has a waveform-derived phrase fallback
  (`_extract_waveform_phrases` :285) — phrase-CLASS estimation without PSSI;
  fidelity vs real PSSI is unmeasured [unknown].
So E3 target = a DEGRADED-BUT-HONEST tier: beatgrid-true, spectral-live,
waveform-phrase-estimated; his hand-curated layers (scripted tracks, laser
tags, gold-tuned behavior) are impossible by definition for unknown tracks.
Pre-show import of guest tracks into the collection remains the full-quality
path (works today, manual).
- **E4 — guest stick on a foreign laptop** (worst case): no extraction on
  foreign machines (non-goal) → beat/BPM-tier lighting only. State it, don't
  oversell it.

## Design questions D1 MUST settle (honest unknowns)
- Sidecar payload size: full v4 per track vs the derived fields the runtime
  needs; per-track cost × library size vs stick capacity.
- Stability of USBANLZ ids (`P018/000086A0`) across Rekordbox re-exports —
  if unstable, fingerprint becomes the primary key, id the hint.
- Exact runtime consumer inventory: everything `_read_runtime_anlz_data` and
  downstream actually need in E2 (phrase, ctx, v4, identity key, f2 plan).
- Foreign-machine realities: frozen-app deps (no librosa extraction on a
  foreign Mac mid-set — sidecar must make extraction unnecessary), Rekordbox
  version on the foreign laptop, read-only stick mounts.
- Refresh UX: when he re-exports tracks to the stick, how the sidecar rebuild
  is triggered and verified (Test-the-Lights integration?).
- Relationship to the pending foreign-Mac frozen-app gates (that branch's 9
  fixes are operator-unvalidated — E2 cannot be validated before them).

## Stages and review loops (operator-mandated; no stage starts before the
## previous stage's gate passes)
- **D1 Design review**: an independent strongest-tier seat attacks this
  charter + produces the settled design (post quota reset; SOL or Fable
  one-shot). Gate: executive accepts; operator vetoes surprises.
- **D2 Spec**: codex-spec Part A–E with the full pre-handoff checklist;
  separate specs for build-time (sidecar exporter in make_stick) and runtime
  (resolution chain). Gate: adversarial spec self-review + executive pass.
- **D3 Implement** (Codex/lane, staged): build-time first (testable offline
  against the real stick), runtime second (behind the AWR-207 seam). Gate:
  suites by name + hard checks + executive desk re-run.
- **D4 Adversarial review**: independent reviewer per round (the AWR-206
  lesson: reviews catch unreachable-path bugs the builder's tests can't).
  Gate: PASS verdict committed.
- **D5 Operator hardware gates**: E1 = his next USB session after restart
  (AWR-207); E2 = the real foreign-Mac walkthrough (fold into the standing
  Saturday MINK gate: memory-read test + install→parity→purge). Nothing is
  called working until these pass — SOFTWARE-VALIDATED ONLY until then.

## Non-goals (fail closed on all)
- No spectral/librosa extraction on foreign machines at runtime.
- No cloud/network dependency for lighting data.
- No Rekordbox DB writes, ever, anywhere.
- No silent degradation: a track the sidecar can't serve reads as unresolved
  with a visible log reason, exactly like AWR-207's misses.

## Status
CHARTER ONLY. AWR-207 (E1 + the extensible seam) is the only authorized
implementation. D1 dispatches when quota returns (2026-07-15) unless the
operator re-prioritizes.
