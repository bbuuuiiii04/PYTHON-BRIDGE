---
doc_status: current
truth_level: handoff-report
last_verified_commit: c1402a6
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff brief for the FILTER-KNOB SWEEP workflow manager (Fable, HIGH effort, tmux
  `filter`, spawned 2026-07-09 morning on operator directive). Manages the feature
  end-to-end: spec → routing → implementation chain → desk calibration session with the
  operator (he attends the calibration step himself).
---

# Filter-knob sweep — workflow manager kickoff (2026-07-09)

You are the **filter-knob workflow manager** (Fable, HIGH). You own this feature's
whole workflow. Brandon will join in-session for the desk calibration step.

## The feature (operator-confirmed; his final ruling is binding)
Memory: `~/.claude/projects/-Users-bbui-rb-ss-bridge-v2/memory/project_filter_knob_lighting.md` — read it first.
- **LOW-TO-HIGH (clockwise / high-pass) sweeps ONLY. Counterclockwise does NOTHING** —
  his final word; no mirror variant, ever.
- Knob leaves 12 o'clock clockwise → strips flood quick-but-not-instant with the
  track's DARKEST palette hue (from the v2 identity palette).
- Past his ear-defined bloom threshold (the resonant widening just before the lows
  vanish) → brightness DIMS continuously, tracking knob travel.
- Riding back toward 12 → fades back in; normal at 12.

## Build order (executive-ruled)
1. **CFX runtime read first** — the FIRST runtime consumer of the mixer RE evidence:
   `docs/research/rekordbox_mixer_active_deck_re_evidence.md` (RB 7.2.11, CFX FILTER
   param0/param1 decks 1/2; Ghidra + passive memory proof). Passive read, reader thread
   only, NEVER the push loop; offsets pinned; same discipline as the upfader/LOW-EQ
   groundwork. No runtime read exists today — rb_memory/rb_offsets carry no CFX.
2. **LED behavior on top** — flood/dim/refill state machine; darkest-hue pick from the
   track palette; kill switch + example-config OFF default; fail toward today (no CFX
   read ⇒ feature inert).
3. **Desk calibration with Brandon** — he sets the bloom-threshold knob position by ear
   (capture while he sweeps; "that's the point" → pinned constant) + the flood ramp
   speed (tune-live constant). Design the capture flow before he sits down.

## Routing decision (surface to him at spec-ready, one line)
Codex quota returns Jul 11 18:28 — default per repo roles is Codex implements
(spec via `.claude/skills/codex-spec/SKILL.md`, Part A–E + checklist). If he wants it
sooner, HE can authorize a Claude implementation round (Opus implementer, adversarial
review, executive gate) — that is his call, not yours; present it once, no re-asking.

## Rules
- Spec through the repo skill; contract-first (`docs/agents/change_contracts.yml`) —
  a CFX reader change likely extends the `rekordbox_readers` contract; add/extend FIRST.
- Live safety: reason the live-mixing scenario in the spec (he rides this knob
  constantly mid-mix — flood/dim must never fight blackout masks or emergency; masks
  win). Bridge stays untouched by this lane; software tests only.
- Suite baseline: repo-root, the named five environmental reds; three hard checks green.
- Org: Opus implementers / Sonnet subagents via tools/agents/dispatch_lane.sh +
  watch_lane.sh (TAG param); never Fable below you; signal files at
  /tmp/rbss_lane_signals/<session>.<TAG>.{done,blocked}.
- Escalations → the executive seat (tmux `superman3`), send-keys.
