---
doc_status: current
truth_level: handoff-report
last_verified_commit: d106492
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff for the F3 BLEND DESIGN lane (Fable/HIGH, tmux f3design, spawned final
  Fable afternoon 2026-07-09). DESIGN ONLY — no implementation, no runtime contact.
  The operator is live-mixing RIGHT NOW and the session recorder is capturing it to
  the exact dataset F3 has been waiting for.
---

# F3 blend design — kickoff (2026-07-09, design-only)

You are the **F3 design lane** (Fable/HIGH). F3 = the lighting engine's within-MIX
phase: how the room behaves while the operator BLENDS two tracks — today the bridge
picks one active deck and follows it; F3 makes the transition itself a designed
lighting moment. This is the hardest remaining lighting-engine design; bank it as a
complete design + spec skeleton while top-tier reasoning still exists (access ends
tonight).

## Ground truth (verify at HEAD)
- **He mixes with per-deck upfaders + LOW-EQ + filter, NEVER the crossfader** —
  operator fact, repeated. F3 follows his real hands from those signals.
- Mixer runtime reads ALREADY EXIST (upfader/LOW = mixer authority in
  `rb_state_reader.py` `_tick_mixer`); CFX filter read landed today (AWR-173,
  `_tick_cfx`, tracking-only pattern — copy its isolation discipline for anything new).
- **The recording**: `local/sessions/f3_live_feedback_20260709.jsonl` (schema=2) is
  being written LIVE from his real mixing this afternoon. It is your primary
  evidence: extract real blend shapes (fader curves, LOW-EQ moves, durations,
  double-drops, bailouts) once it has substance (check size/growth; full analysis
  after his mix ends). `session_replayer.py` / `session_phase_trace.py` are the
  replay/analysis seams.
- Active-deck authority: `active_deck_resolver.py` (only_audible etc.) — F3 must
  never fight it; F3 rides WITHIN the authority's transition window.
- v2 architecture anchors: docs/architecture/ (current_architecture, bridge_design,
  LIGHTING_ENGINE_V2_DESIGN if present) + the F2 plan surface
  (`lighting_moments_v2.py`) — F3 composes with F2 moments, never re-decides them.

## Deliverables (in order; each committed, checks green)
1. **Design doc** `docs/architecture/f3_blend_design.md`: the blend state machine
   (incoming-deck detection → blend-in-progress → handover → settled), driven by
   upfader+LOW-EQ signals; how LED palette/looks and lasers behave per phase;
   interaction table vs F2 darkness/drops on BOTH decks (a drop landing mid-blend is
   THE hard case — design it explicitly); mask/emergency precedence (they always
   win); fail-toward-today (signals unreadable ⇒ F3 inert, current behavior).
2. **Evidence appendix**: measured blend shapes from the recording (real numbers).
3. **Spec skeleton** (Part A–E per the repo spec skill) ready for Codex to implement
   after live-gating F2/F4 — implementation is NOT authorized now.
4. Registry row (next AWR id — re-check max first).

## Rules
- Design forks: pick safe defaults, flag veto-style, escalate only real forks to the
  executive (tmux superman3, send-keys). Operator taste calls: collect as a NAMED
  list for his desk, do not ask him mid-mix.
- Every claim about current behavior verified at HEAD with file:line.
- Sub-lanes allowed (Opus/Sonnet via tools/agents/) for recording analysis grinding.
- Completion: signal file per dispatch convention + printed sentinel.
