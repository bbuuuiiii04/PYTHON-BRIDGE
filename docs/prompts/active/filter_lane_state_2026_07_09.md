---
doc_status: current
truth_level: handoff-report
last_verified_commit: d47e332
last_verified_date: 2026-07-09
validation_scope: >
  Filter-lane (AWR-173 CFX filter-sweep) state brief at mix-done park, 2026-07-09
  evening, written for the successor executive (GPT seat, ~21:15 handoff). Claims
  verified against the working tree and test runs at park time; the operator's
  ride-home retest is pending and everything remains SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.
---

# Filter lane state brief — AWR-173 CFX filter-sweep (2026-07-09 park)

**Seat:** Fable HIGH manager, tmux `filter`. **Registry row:** AWR-173 (row 82,
`docs/status/active_work_registry.md`). **Spec:** `docs/plans/active/cfx_filter_sweep_spec.md`.
**Memory topic:** `project_filter_knob_lighting.md` (bridge store).

## Where the feature stands (plain)

The bridge reads both decks' CFX FILTER knobs (RB 7.2.11 only, selected-effect-validated)
and drives a one-way LED gesture on the ACTIVE deck: clockwise from 12 floods the strips
with the track's darkest v2 hue; crossing the operator's ear-calibrated bloom point
(**0.642**, pinned live at the desk from 3 captures: 0.661/0.635/0.642) fires a one-shot
drain to **full black** (his ruling: dim_floor 0.0); riding home resumes the normal look
as if nothing happened; counterclockwise does nothing, ever. Live config
(`config/led_look_director.json`, gitignored) carries `cfx_sweep` with `enabled: true` +
those pins (a stale `rearm_hysteresis` key remains; the loader provably ignores it).

## The one OPEN item

**Operator ride-home retest next session.** His live feel pass caught a re-bloom on the
ride home that survived the first fix. Root-caused as TWO legs, both fixed + tested +
**STAGED** (mix was called done; NO restart happened — the fixes auto-load at the next
bridge start, batched with AWR-185):

1. **Release flare (his deterministic symptom):** the release ramped color-mix down and
   brightness up CONCURRENTLY; from the drained black room the visible product
   `mix*dim` peaked ≈0.25 for ≈400 ms right after crossing back under the bloom — the
   bloom color visibly flared back. Fix: release is now SEQUENTIAL (mix fades to 0
   under black first, then brightness rises to 1; never-fired releases byte-identical).
   Tests pin the visible product curve (≤0.05 while mix>0), not just state.
2. **Blip re-arm:** any one-tick gating/validity/v2 blip in `_compute_led_cfx_sweep`
   hard-reset the envelope (re-armed) mid-ride → full re-flood in the flood zone. Fix:
   inert paths preserve a fired engagement (`CfxEnvState(fired=prev.fired,
   released=prev.fired)`, `state_manager.py:4984`); only knob-at-neutral re-arms; a
   never-fired flood may resume after a mask lifts (knob-state behavior, intended).

One pre-existing test's meaning was deliberately flipped with rationale: the old
smart-drop-blackout test asserted the exact state wipe that caused post-blackout
re-bloom; it now asserts latched-release (still black during the mask, no re-bloom after).

## Verification at park

- Targeted: `tests.test_led_cfx_sweep` + `test_led_state_manager` +
  `test_laser_color_engine` = 211 green (manager-run at HEAD `d47e332`).
- Three hard docs checks green (manager-run).
- Full `discover tests` final proof was running at park (background); the whole night's
  baseline = exactly the five named environmental reds — flag any deviation.
- Commit-race note (pattern all night, content never lost): the release-fix diff is
  scattered — `led_dispatch_policy.py` rode the specbank commit `39713f1`,
  `state_manager.py` + tests rode auto-syncs (`f3c323d`/`70c148b`). Judge state by
  tree + registry row, never by commit titles (AWR-174 lesson).

## Day trail (all 2026-07-09, one day, in order)

spec `fd3dc9a` + contract-first CFX forbidden-assumption `64e7e82` → operator authorized
Claude round → impl Tasks 1-8 (`ed6dc05`+`967ea15` sweep+`7890220`) → adversarial review:
1 HIGH (pre-drop tactical blackout gate hole) fixed `98c82ca` → executive gate PASSED
(superman3, independent) `ade7f7f` → DESK: direction CONFIRMED (param0 0.000/0.500/1.000
= CCW/12/CW), bloom pinned 0.642, operator RE-RULED trigger-not-hold + peak-then-drain +
one-way (`d106492`) → feel-pass bug: ride-home re-bloom → re-arm fix (`389aceb` marker) →
STILL re-bloomed → two-leg root cause + staged fix (above) → routed side-fix `b1f360c`
(laser-color fake engine, 5 ERRORs → 28/28) → parked.

## Standing rules that bind this lane

- Live-session protocol (operator, still in force unless successor lifts it): STAGE
  only, one-line summary per change to the executive seat, no self-restart/activation,
  heads-up before restart-free runtime commands.
- CFX is tracking-only: never feeds active-deck authority; a failed CFX read must never
  invalidate mixer authority (contract forbidden-assumption + isolation test).
- Operator rulings are FINAL: low-to-high only; trigger-not-hold; peak-then-drain (no
  extra pulse); one-way resume; full-black floor.
- Next-session first steps: (1) bridge starts → staged fixes live; (2) operator rides
  up-over-bloom-and-home ONCE — expect black → normal rise, NO color flare, NO re-flood;
  (3) taste knobs if wanted: flood_ramp_ms 250 / drain_ms **400** (operator re-ruled
  "the bloom needs to last shorter" post-park; staged 800→400 in live config,
  loader-validated) / release_ramp_ms 400 (sequential: worst-case ride-home restore ≈
  2× release_ramp_ms).
