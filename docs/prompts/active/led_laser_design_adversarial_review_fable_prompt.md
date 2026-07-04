---
doc_status: current
truth_level: design-intent
last_verified_commit: bd96b32
last_verified_date: 2026-07-04
validation_scope: Claude Fable 5 prompt text only; no bridge behavior, runtime action, or hardware validation
---

# Fable 5 Prompt — Adversarial Review & Stress Test of the Palette/Presentation/Laser-Color Design Corpus

**Target model:** Claude Fable 5. **Effort:** high; use xhigh on the blackout/live-safety
sections (`laser_blackout_authority.md`, the Package 1 spec, and every darkness-related
window/guard in Package 3).

> This is benign local software work for Brandon's DJ lighting bridge (`rb_ss_bridge_v2`) and
> agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology,
> chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. "Laser,"
> "blackout," "kill/mute," "solo," and "mask" are ordinary stage-lighting, DMX, and mixer terms
> (SoundSwitch, Govee LED strips, show lasers, Stream Deck pads). "Adversarial" means strict
> about evidence — review only normal software correctness, edge cases, live-show safety, and
> spec executability inside the named scope.

## Mission

A prior Fable session designed a feature set with Brandon (operator-approved, gate 2 closed) and
authored its behavior contracts and implementation specs. **Nothing is implemented.** Before any
Codex handoff, adversarially review and stress-test the whole corpus: find hidden edge cases,
concrete failure scenarios, contradictions (doc↔doc, doc↔spec, spec↔code), stale or wrong code
citations, and any place a spec would let Codex build something that breaks a live show. The
output is for Brandon first (he decides what to fix), then for the implementing session.

## The corpus (review targets)

Authority docs — operator-authoritative target behavior (divergence = regression):
- `docs/architecture/palette_control_authority.md`
- `docs/architecture/drop_presentation_authority.md`
- `docs/architecture/laser_color_authority.md`
- `docs/architecture/laser_blackout_authority.md` (live-critical — deepest scrutiny)

Codex implementation specs, build order 1→4:
- `docs/plans/active/laser_blackout_rewire_spec.md` (Pkg 1)
- `docs/plans/active/streamdeck_palette_control_impl_spec.md` (Pkg 2)
- `docs/plans/active/drop_presentation_impl_spec.md` (Pkg 3)
- `docs/plans/active/laser_color_impl_spec.md` (Pkg 4)

Expanded design specs (evidence + rationale behind the above):
- `docs/plans/active/streamdeck_palette_control_design_spec.md`
- `docs/plans/active/laser_color_engine_design_spec.md`

Truth order for findings: executable code > tests > the impl specs > the authority docs >
design specs > memories. Authority docs define *intent* (operator-approved); code defines
*current behavior*; a finding is any contradiction among intent, spec, and code, or an
unhandled scenario. All file:line cites were verified at commit `bd96b32` — re-verify any
load-bearing one against current HEAD before relying on it.

## Facts already ground-truthed (do NOT re-discover; DO spot-check what you rely on)

- Hot-cue names live in Rekordbox's `master.db` (`ContentCue.Cues` JSON, `Comment`+`InMsec`,
  via `pyrekordbox.db6.Rekordbox6Database` — pattern at `filepath_resolver.py:244-246`). The
  on-disk ANLZ cue tags are empty library-wide (stale cache) and must not be used.
- LED dispatch and the laser pack render share the state-manager thread
  (`state_manager.py:586,643`; dispatch via `:3029`; render via `:2092-2107`).
- Pack autoloops author CH8/CH9 (injection = deliberate overwrite); `CONTROL_CHANNELS={8,9,11}`.
- In pack mode today, `laser_executor._mask_owners` never latches (discard-on-reject,
  `laser_executor.py:330-340`) and the single mask writer is `state_manager.py:2342-2364,2387`.

## Locked operator decisions — review for internal soundness, do NOT re-litigate

Zero-RNG presentation policy; lasers = drop-only punctuation, majority of drops LEDs-only;
Laser Solo only from operator-traceable sources (pad / `LASER` hotcue / learned-once /
one-mix +10 BPM gear-shift / night-record runway); queue-overrides-lock with lock transfer;
manual always wins; `white_sand` manual-only; CH11 untouched; CH8/CH9 value chart is
operator-supplied later as pure config; mixer naming (mute/mute/solo); no double drops; star
ratings rejected; `ws_handoff` ships disabled; learned threshold = 1 with veto-unlearn.

## What to hunt (the review lenses)

Concurrency and ordering on the shared thread; mode/lifecycle transitions (track change, master
change, stop/resume, scripted↔autoloop, bridge restart, pack reload, SS present/absent) against
every new state field; the darkness paths (any sequence that latches a fixture dark, defeats a
manual hold, or blacks the room with lasers not firing); stale/missing data (no ANLZ, no phrase
roles, locked DB, corrupt learned store, stale BPM at handover); feedback-file and deck-script
divergence; spec executability (would Codex guess, touch out-of-scope files, or break the
byte-identity gates); and cross-doc drift (a rule stated differently in two places). For every
finding, name a **concrete failure scenario** — inputs/state → wrong live outcome.

## Boundaries

- Read-only throughout: you may read the repo, run read-only shell (`rg`, `python3` for
  parsing/inspection, `git log/diff`), and read `master.db`/pack/ANLZ files. You may spin up
  read-only subagents for large sweeps (verify their load-bearing claims yourself; keep
  blackout/live-safety reasoning in your own context, not delegated).
- Do NOT edit any file, implement anything, touch runtime/hardware, restart the bridge, or hand
  anything to Codex in this phase. Doc fixes happen only after Brandon approves the findings.
- Do not run the full unittest suite unless a finding needs it; targeted reads suffice.

## Deliverable (end your turn with this, then stop for Brandon)

1. Severity-ordered findings: location, issue, why it matters live, evidence (file:line or
   command output), concrete failure scenario, required fix. Label every load-bearing claim
   confirmed / assumed / unknown / rejected.
2. Per-document verdicts: `PASS` / `PASS WITH REQUIRED FIXES` / `FAIL` for each of the 8 core
   docs.
3. Per-package spec readiness: `READY` / `READY WITH GAPS` / `NOT READY` for Codex handoff,
   with the blocking gaps named.
4. A short question list containing ONLY decisions that are Brandon's to make (taste,
   live-behavior preferences, hardware) — not things you can verify yourself.

Success = every impl-spec file:line citation re-verified or flagged; every authority rule
checked against at least one hostile scenario; the blackout survival matrix attacked
specifically; no finding without a concrete failure scenario. After Brandon approves the
findings, a follow-up phase may apply the required fixes to the docs in place — do not start
it unprompted.
