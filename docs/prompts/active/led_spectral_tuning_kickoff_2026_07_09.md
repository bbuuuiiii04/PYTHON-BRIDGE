---
doc_status: current
truth_level: handoff-report
last_verified_commit: cafd88e
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff brief for the LED × SPECTRAL EFFECTS TUNING session (Fable, MEDIUM effort,
  tmux `ledtune`, spawned 2026-07-09 on operator directive "create a session for led
  spectral audio analysis tuning for all of these"). Owns the whole workstream: the
  live taste knobs, the white-share consumer, the P1 growl-band-centroid unlock, and
  the queued P2/P3 riders. Operator attends the desk/tuning steps.
---

# LED × spectral effects tuning — kickoff (2026-07-09)

You are the **LED-spectral tuning workstream lead** (Fable, MEDIUM). Brandon attends
the desk steps and every taste verdict is his. Scope = the four tracks below, exactly
as relayed to him in chat (his approval: "all of these").

## Ground truth first (verify at HEAD before any work)
- Decision layer is DONE — do not re-tune: family/tier/darkness/texture/zone constants
  froze on his 41 desk verdicts + the 545-track re-check (AWR-147; tier via F2/AWR-163).
- `white_share` is computed per drop in the F2 plan (`lighting_moments_v2.build_track_plan`)
  and has ZERO LED consumers (grep-verified 2026-07-09 in led_dispatch_policy /
  led_color_engine / led_look_director / govee_frame_renderer).
- F4 sparkle grain is an explicit TUNE-LIVE constant pair:
  `_F4_BF_SPARKLE_MIN = 0.2` / `_F4_BF_SPARKLE_MAX = 0.6` (`led_dispatch_policy.py:48-49`,
  comment names it an operator taste call).
- The audit: `docs/research/spectral_upgrade_audit_2026_07_09.md` (AWR-166) — verdict
  KEEP v4, change by addition; **P1 = frame-rate growl-band centroid** is the named
  recommendation (§140 what/cost, §298 reasoning); P2 slow-wub + P3 kick-signature are
  riders with honest ceilings (§181: amplitude-only, kick-confound rejector is
  make-or-break).

## The four tracks
- **A — taste knobs (desk/live, him present).** F4 sparkle grain min/max; any LED item
  he raises from the veto list (comet width 2.5, strobe_red_white side B, balloon
  gray-zone 0.30–0.35). One knob at a time, his verdict verbatim, software change via
  the normal chain (these are code constants, not live-config keys — no hot edits).
  NOT yours: burn-down + darkness ladder + chase visibility (the `haze` session owns
  those; coordinate, don't double-own).
- **B — white-share consumer.** Design + build the first LED consumer of the per-drop
  `white_share`: how much white rides the drop look (big builds flash whiter).
  Kill-switched, example-config OFF default, byte-identical when off, normal chain
  (spec → Opus implementer → adversarial review → executive gate → suite at the named
  five-red repo-root baseline).
- **C — P1 growl-band centroid.** Spec the additive extraction field per the audit
  (harmonic 60–500 Hz spectral centroid per STFT frame, stored alongside
  `growl_band_frames`), the one-time cache re-sweep (OVERNIGHT ONLY, never against a
  mix, disk floor enforced), then the F4 wobble-following effect design + a desk
  session where he tunes what the wobble looks like. Zero change to existing
  calibration constants; extraction stays never-per-tick (at-load on miss + cache).
- **D — queued riders (do NOT start without his word):** P2 slow-wub tracker,
  P3 kick-signature. Keep as registry backlog rows with the audit's caveats attached.

## Order and gates
1. Build rounds (B, C) gate on his NEXT MIX confirming tonight's overnight work live —
   the executive's stated default, operator-approved. Until then: specs, contracts,
   and the Track-A desk pass may proceed.
2. Every change: contract-first (`docs/agents/change_contracts.yml` — extend
   `led_govee` / `spectral_analysis` as applicable BEFORE code), three hard checks,
   suite at the named five-red repo-root baseline.
3. Features must generalize across the whole EDM library; per-track tuning gets cut.
4. Zero bridge-runtime contact from this lane; no live-config edits; the 200 Hz loop
   never gains extraction or blocking I/O.

## Org
Opus implementers / Sonnet subagents via tools/agents/dispatch_lane.sh + watch_lane.sh
(TAG param; signal files /tmp/rbss_lane_signals/<session>.<TAG>.{done,blocked}); never
Fable below you. Escalations → the executive seat (tmux `superman3`), send-keys. Chat
is the surface with Brandon — say everything fully, plainly.
