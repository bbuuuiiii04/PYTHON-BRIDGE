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

EXECUTIVE PRE-TRIAGE (2026-07-11, verified at that desk — re-verify cites, then
build on this, don't redo it):
- Symptom 3 largely EXPLAINED: the BPM control is wired end-to-end into a real
  playback beat clock (`tools/led_pad_web.py:626-631` → `tools/led_pad_playback.py`
  set_bpm implementations, correct re-anchor math), and the playback loop passes
  `abs_beat_pos` into the render call (`tools/led_pad_playback.py:71`). But
  `govee_frame_renderer.py` contains ZERO bpm references — only beat-synced
  effects consume `abs_beat_pos`; time-based effects animate on wall seconds, so
  BPM visibly does nothing for them. Enumerate which effects are beat-driven vs
  time-driven; that inventory is the deliverable.
- Symptom 2 CONFIRMED missing affordance: `led_pad_controls.py` exposes no
  beat-sync metadata whatsoever — the UI cannot show it. Fix shape: surface a
  beat-synced badge per effect/look in the catalog payload + UI.
- Symptom 1 OPEN: hypothesis is the same beat/time split (beat-driven drafts
  sitting near-static in preview; note `beat_sync_engine.py:27`'s historic
  "beatsynced looks do not look beatsynced" re-anchor bug class). Reproduce
  per-draft read-only across all 25 wave-1 drafts; separate render-errors from
  static-but-rendering from working.
Then propose fix shapes (not applied): beat-sync badges, an honest BPM control
(greyed/limited to beat-synced effects, or preview-clock unification), and
per-draft repairs.

Report to /tmp/rbss_lane_signals/<session>.TLAB.report.md + .done signal.
