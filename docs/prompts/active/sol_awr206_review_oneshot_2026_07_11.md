---
doc_status: current
truth_level: prompt-handoff
last_verified_commit: 5955e82
last_verified_date: 2026-07-11
validation_scope: >
  One-shot adversarial review handoff for GPT 5.6 SOL (xhigh) — AWR-206 laser
  pre-drop blackout relaxed arm gate. Review only; read-only on a possibly-LIVE
  system; no fixes applied.
---

# SOL one-shot — adversarial review of AWR-206 (laser blackout relaxed arm gate)

> Benign local DJ-lighting software; "laser" = stage fixture over MIDI/DMX.

**Seat:** independent adversarial reviewer (you did NOT build this; a Claude Opus
lane did; the Fable executive gated it — your job is to try to break it).
**Live boundary:** the operator may be live-mixing. Read-only everything; never
touch the bridge, MIDI, configs, code, or tests. Findings go in your report, not
in fixes.

## What changed (verify, don't trust)
Commits `d95d7ce` (code+tests, swept by auto-sync) + `f0da6b1` (docs). Spec:
`docs/plans/active/laser_blackout_gate_fix_spec_2026_07_11.md`. Build report +
release-path audit: `/tmp/rbss_lane_signals/claude3.LZFIX.report.md`. Triage that
motivated it: `/tmp/rbss_lane_signals/claude3.LZBLK.report.md`.
Summary: `laser_executor.py` `on_decision` now arms the pre-drop blackout under a
relaxed gate (`_passes_blackout_gates` = strict gate minus `autoloop_ready`) in
the auto-gate-blocked branch; scene MIDI stays behind the strict gate; skip
reasons now log at INFO. STAGED — activates at the operator's next restart.

## Review with your findings-first mindset, severity-ordered, file:line each
Attack surfaces to cover (not exhaustive — find what we missed):
1. **Live-mixing hazards:** can the relaxed gate arm a blackout that strands the
   lasers dark in ANY reachable state? Re-derive the release-path audit
   independently (the build lane's table is in its report — re-verify the
   load-bearing rows at HEAD, especially deck-swap/track-unload/mode-transition
   during the armed window, and the `_mask_owners` refcount interplay).
2. **Precedence:** emergency/manual blackout, master_switch, pack-disabled and
   shutdown zeroing must still outrank/clear everything.
3. **Double-arm / re-entrancy:** repeated arm signals across ticks in the blocked
   branch (30+/session now expected) — idempotent? Any MIDI spam risk?
4. **The two updated tests:** did dropping the `autoloop_ready=False` cases
   weaken any OTHER pinned behavior?
5. **Scene/blackout divergence:** any state where blackout arms but the scene
   path later fires into it inconsistently at the drop?
6. **The INFO log:** rate/content concerns at 200 Hz tick reality (arm signals
   are edge-triggered — verify that's actually true in code, not assumed).

Report everything including uncertain/low-severity findings; if there are none,
say so explicitly and name residual risks + testing gaps. Label every claim
confirmed/assumed/unknown with file:line evidence read at HEAD.

## Output
Write `docs/research/sol_awr206_review_2026_07_11.md` (commit that one file by
explicit path, message prefix `AWR-206 review:`). Print `A206REV-DONE` on its own
line AND write `/tmp/rbss_lane_signals/sol205.A206REV.done` (one-line verdict
inside). Verdict scale: PASS / PASS-with-required-fixes / FAIL, with the fix
shapes described (never applied).
