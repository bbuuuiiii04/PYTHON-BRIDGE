---
doc_status: current
truth_level: prompt-handoff
last_verified_commit: 38e127a
last_verified_date: 2026-07-11
validation_scope: >
  Post-quota-reset triage kickstart (dispatch on/after 2026-07-15 09:00 reset)
  for three operator-reported Template Lab defects. Read-only triage first;
  fixes only via the normal spec path afterward.
---

# Template Lab triage — three operator symptoms (reported live 2026-07-11 ~17:5x)

Dispatch: tmux Claude lane, opus/high, READ-ONLY triage. The bridge may be
running — never touch it, no config/code edits, no pad/lab restarts.

OPERATOR SYMPTOMS (verbatim):
1. "half the drafts in template lab dont work"
2. "I can't tell which look is beatsynced and which look isnt"
3. "the BPM for temp lab does nothing"

Context the lane must know:
- Template Lab lives in the LED Pad web tool (:8766, `tools/led_pad_web.py`,
  `led_pad_controls.py`); the 25 wave-1 drafts (AWR-194) are gitignored under
  `config/led_lab/` and passed a 25/25 dry-render harness at the executive desk
  when they shipped (2026-07-10 ~01:1x) — so "don't work" is plausibly in the
  live preview/serving path, not the draft JSONs; verify, don't assume.
- The live LED config was restored 2026-07-11 (89 looks) and the pad Discarded
  its stale draft the same day; consider whether the lab preview path shares
  any state with that restore.
- AWR-193 overhauled the pad; AWR-202 fixed its config merge. Read those
  registry rows before blaming new code.

For each symptom: reproduce read-only (curl the lab endpoints / read the
render path), rank root causes with file:line evidence, and propose fix shapes
(not applied). Distinguish "broken" from "by design but undiscoverable" —
symptom 2 may be a missing UI affordance rather than a bug; if the preview
renderer ignores BPM by design, say exactly where and why.

Report to /tmp/rbss_lane_signals/<session>.TLAB.report.md + .done signal.
