---
doc_status: current
truth_level: manager state brief (ledsim lane, AWR-196)
last_verified_commit: f01616b
last_verified_date: 2026-07-10
validation_scope: >
  Continuity brief for the ledsim manager seat (Fable/XHIGH). If this seat dies,
  the successor reads: charter docs/prompts/active/ledsim_charter_2026_07_10.md
  -> spec docs/plans/active/led_sim_build_spec_2026_07_10.md -> AWR-196 registry
  row -> this file, then verifies every lane FRESH against reality.
---

# ledsim manager state — AWR-196 (updated 2026-07-10 ~01:0x)

## Where we are
- Charter read in full; org doctrine + opus harness loaded; codex-spec skill read.
- Ground truth re-derived at HEAD 20329d7 (all in spec Part A): Frame=list[RGB],
  `GoveeFrameRenderer.render` at govee_frame_renderer.py:2372 is the only render
  path; `REALTIME_EFFECT_NAMES` :1232; fps 60 + segments 60 in
  config/led_look_director.example.json:600,610; recorder logs pre-tick inputs
  NOT frames (⇒ replay = frames-JSONL the sim defines; live capture tap = OUT of
  this round, executive decision later); pad fence per AWR-193 spec "Touch ONLY"
  list; port 8767 free.
- AWR-196 registry row written. Spec authored + committed `f01616b`
  (hard checks green at commit). Design rulings baked in: NO room photos —
  self-calibrating draggable corners/start/direction persisted as
  config/led_sim_profile.json (example committed); canvas 2D not WebGL;
  indirect-wash pass is the photometric centerpiece; all device unknowns =
  calibration knobs, never constants.
- Build lane `ledsimb` DISPATCHED tag A196 with the spec; boot verified (lane
  re-verifying spec cites at HEAD on first capture). ~01:0x executive relay of
  a standing operator order (FABLE XHIGH FOR EVERYTHING incl. build lanes):
  lane interrupted BEFORE Task 1 landed, re-pinned to **Fable/xhigh**, both
  acks verified on-screen, resumed with the quota park-with-state clause
  (limit mid-round → commit done tasks by explicit paths, report exact stop
  point, .blocked reason quota). Resume send initially sat UNSUBMITTED at the
  prompt (field bug; first watcher exited IDLE on it) — bare Enter fixed,
  processing confirmed, watcher re-armed (signal-file first, 5400 s, ONE
  watcher).
- Executive mailbox (superman4) notified of dispatch.

## Next step (for me or a successor)
1. Watcher returns: `.done` → adversarial review AT THIS DESK (re-run scoped
   tests + service smoke, diff-stat each commit vs spec file list, spot-check
   cites, full-suite reconcile BY NAME vs five-red baseline:
   test_drop_slot_color_smoke_and_snap / both test_export_pack_parity_self_heal
   / test_ddj_slots_8_16_17_24_exact_ch1_ch19 /
   test_autoloop_capture_rows_identify_passes_and_blockers). Visual pass: open
   http://127.0.0.1:8767 briefly at the desk (start server, look, kill it,
   bracketed pgrep to confirm nothing left).
2. `.blocked` → read one-line evidence, verify at desk, unblock or escalate to
   superman4 with severity + file:line + verdict.
3. IDLE/TIMEOUT → capture pane, judge (long build is expected; re-arm watcher
   if genuinely busy; paste-chip check if suspicious).
4. Round PASS → write /tmp/rbss_lane_signals/ledsim.SIM.report.md (operator
   plain-language summary first), touch /tmp/rbss_lane_signals/ledsim.SIM.done,
   mailbox one-liner, update AWR-196 registry row + this brief.

## Open questions / decisions banked
- Live-session frame capture (runtime tap for true replay) deliberately OUT of
  this round — needs an executive/operator call; frames-JSONL player + offline
  generator CLI ship now so the seam is exercised.
- Lab-draft rendering degrades gracefully while the pad lane rewrites
  led_pad_lab.py (guarded import contract in spec Task 2).
- Final gate is the OPERATOR'S EYES against his real room (charter); nothing in
  this round may claim beyond SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Fence reminders
- Pad lane (AWR-193, `padbuild`) owns tools/led_pad_web.py, tools/led_pad_lab.py,
  led_pad_controls.py, tools/led_pad_assets/** — ledsim touches NONE.
- Sim never contacts the device; loopback :8767 only; never port 8766.
- My completion signals: /tmp/rbss_lane_signals/ledsim.SIM.{report.md,done,blocked}.
