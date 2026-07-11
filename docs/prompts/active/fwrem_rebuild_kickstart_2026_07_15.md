---
doc_status: current
truth_level: prompt-handoff
last_verified_commit: 38e127a
last_verified_date: 2026-07-11
validation_scope: >
  Post-quota-reset implementation kickstart (dispatch on/after 2026-07-15):
  rebuild rt_post_drop_firework_remnants to the operator's stated design.
  Staged only; normal spec/contract path; operator auditions before re-bank.
---

# Firework remnants rebuild — operator design intent (verbatim, 2026-07-11)

> "firework remnants is supposed to be the first half of the rt drop chase cues
> sparkling effect (first 8 beats) and should not include the initial firework
> explosion. thats the problem. the firework explosion is supposed ot be a quick
> bright flash upon drop impact and the the firework remnants are the aggressive
> flickering strobing sparkle effects that follow after"

Dispatch: tmux Claude lane, opus/high. Read first: this file; the FWREM triage
report (/tmp/rbss_lane_signals/claude2.FWREM.report.md — what the current
implementation renders and why it fails: room-fill white background wash);
AGENTS.md §6/§7/§8.

Build (staged, contract `led_govee`):
1. In `govee_frame_renderer.py`, rebuild the `rt_post_drop_firework_remnants`
   effect: DELETE the full-strip background wash entirely; keep ONLY an
   aggressive flickering/strobing sparkle layer whose character matches the
   FIRST 8 BEATS of the rt_drop_chase cues' sparkle effect — read that
   implementation as the reference and reuse its sparkle mechanics where
   sensible rather than inventing new ones. rt_drop_firework_explosion (the
   quick bright flash at impact) is OUT OF SCOPE — do not touch it.
2. Peak simultaneous lit fraction must stay low (embers, never a room-fill) —
   pin it with a test. Duration: the post-drop tail window it already occupies.
3. Tests per the renderer's existing patterns + the dry-render harness; pin:
   zero whole-strip background contribution, flicker over time, lit-fraction
   ceiling, duration.
4. If the operator's stopgap (unbank + pairing repoint to
   rt_post_drop_remnant_nebula) landed, re-banking + repointing back is part of
   THIS round's config-example/docs work — but the LIVE config re-bank happens
   only after the operator auditions the rebuilt effect (Template Lab / ledsim
   / live), never automatically.
5. Registry row (new AWR id; re-check max), contract docs_update, 3 hard
   checks, scoped suites by name. STAGED; bridge restart activates it later.

Report + .done signal per dispatch convention.
