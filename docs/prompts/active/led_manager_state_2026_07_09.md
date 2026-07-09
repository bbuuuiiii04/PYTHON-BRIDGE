---
doc_status: current
truth_level: manager-state snapshot
last_verified_date: 2026-07-09
last_verified_commit: HEAD-2026-07-09-overnight
validation_scope: LED-lane Fable manager state brief (session f33cb16b) written at ~97% context before compaction; the registry rows carry the program of record — this file is ONLY the delta (pre-authorizations verbatim, unrecorded verdicts, lane mechanics, in-head nuance); if post-compaction anything reads lost, re-read THIS FIRST, then the registry AWR-152..164 rows, before acting
---

# LED-lane manager state brief — overnight 2026-07-09 (delta only)

**Who I am in this org:** Fable manager for the LED quality-pass program.
Executive = tmux `superman` (Fable) — ALL reports/reviews/ship notices go
there via `tmux send-keys` (paste-safe: send text with `-l`, wait ~3s, send
Enter AGAIN — first Enter is often eaten by bracketed paste). Doctrine
(operator, restated 3×): superman Fable / Fable managers (parallel, one per
task) / OPUS tmux orchestrators / SONNET grind subagents — NEVER Fable below
manager. New dispatches pin the model explicitly and VERIFY on-screen
("Set model to Opus 4.8" + banner) BEFORE task text.

## Immediate state at write time

- **AWR-161-FIX micro-round IN FLIGHT on claude5 (Opus-pinned, verified).**
  Scope: 3 RENDER_GROUPS names (`led_pad_controls.py:194` import-crash fix —
  would crash the pad server on restart, hence NO PAD RESTARTS tonight; fix
  must be at HEAD before the operator's morning pad session); 5 legacy
  strobe tests re-pinned to the Hz contract (MUST still prove dark frames
  across a full 1/6 s cycle at hz 6.0/duty 0.3 — no deletion/weakening);
  one-line `post_drop_center_comet_blue_cyan` → `REALTIME_STROBE_EFFECTS`
  + membership test (my authorized call: IN). Sentinel `AWR161FIX-DONE`
  with numbers. Watcher `b1lqwb70q` running.
- **Acceptance for the micro-round: 3599 collected / EXACTLY the six-red
  baseline / three hard checks.** Six-red baseline BY NAME:
  `test_drop_slot_color_smoke_and_snap` (error), both
  `test_export_pack_parity_self_heal` fails,
  `test_ddj_slots_8_16_17_24_exact_ch1_ch19`,
  `test_loader_ships_calibrated_fixed_band_and_menu_ch9` (parent-dir cwd
  form only — passes from repo root), parity-oracle
  `test_autoloop_capture_rows_identify_passes_and_blockers`.
- After the sentinel: MY verification → superman re-runs the suite at their
  desk → if clean, SUPERMAN sends the combined rounds 1.5+2+3 ship notice
  (not me) and the F2 dispatch proceeds.

## Standing pre-authorizations (verbatim substance — do not re-ask)

1. **F2+AWR-162 implementation dispatch to claude4, NO round-trip needed,**
   once ALL of: (a) the three executive spec edits committed — DONE
   (`6c70fc7`); (b) AWR-159 + AWR-161 sentinels landed — DONE; (c) the
   quiescent suite reproduces the known-six-red baseline — PENDING the
   micro-round + superman's desk re-run. Dispatch = presence-check, /clear,
   `/model opus`, VERIFY on-screen, then the task; spec
   `docs/plans/active/lighting_engine_v2_f2_spec.md` (AWR-163, RELEASED,
   edits applied); AWR-162 implements inside it as Task 4.
2. **F4 dispatch same structure** once F2 lands + gates clean (spec
   `docs/plans/active/lighting_engine_v2_f4_spec.md`, AWR-164, RELEASED,
   seam re-cited at HEAD; strict F2-first).
3. **Mirror (R5) authorized** after rounds 2+3 ship + review: timestamped
   gitignored backup FIRST, merge example→live preserving live-only values
   (IPs, keys, device ids), verify via the tracked-and-live config test,
   bridge stays DOWN, apply is operator/executive-gated.
4. **Notify superman per ship**; superman's rate-throttle calls; reviews
   queue at my desk.

## Review verdicts NOT fully in registry rows

- **AWR-159 review: substantially verified, not formally closed.** Seam
  checks passed (one-tick cancel flag set :2928 / consumed :2750-2754 /
  cleared on teardowns :2588/:2864; refused-flash + gate-reason logging;
  files scoped to drop_presentation/state_manager/led_palette_control).
  Its registry row is thorough and honest. REMAINING: nothing blocking —
  fold formal PASS into the post-micro-round report.
- **AWR-161 review: conditional PASS → conditions being fixed by the
  micro-round.** Ember contrast INDEPENDENTLY re-derived at exactly 101/255
  (my own modal-background method); zero beat-tied gates remain; buildup
  sine ramps untouched; 20 hz-dialable names = 18 new + 2 from AWR-156, all
  in-scope, no buildups.
- **Misattribution flag (reported to superman):** both lanes mislabeled the
  8 extra reds (159 said "pre-existing", 161 said "159 mid-flight") — they
  were 161's own consequences. Watch for this pattern in lane self-reports.
- **AWR-160**: PASS pending the quiescent suite (the fold-in verified:
  ANLZ catch-up only fires when already_loaded; FEIN case tested).

## Lane map at write time

- `claude4` = PARKED (Sonnet; did 152-round1/154/155/157/160) — next use:
  F2 dispatch, REPIN TO OPUS first.
- `claude` (Track B) = idle post-AWR-159 (Sonnet, finished as dispatched).
- `claude5` (Track C) = Opus, running the micro-round.
- `claude6` = ANOTHER MANAGER'S seat (USB workstream, paper-only, reports
  to superman) — HANDS OFF; its docs-only surface may contend on registry/
  doc_index; sequencing at superman's desk.
- `claude7` = THIRD MANAGER'S seat (Fable xhigh, spectral-analysis audit,
  read-only report + registry/doc_index rows, reports to superman) — HANDS
  OFF. Contention throttle order if it appears: claude6 pauses first, then
  claude7; MY lane and any in-flight micro-round never pause.
- `superman` = executive.

## In-head nuance (the expensive lessons)

- **Watchers must detect IDLE, not just sentinels** (executive save #2:
  claude4 idled 17 min at an orchestrator checkpoint awaiting ack —
  sentinel-only watchers are blind to it). Pattern: hash consecutive pane
  captures; 3 identical = idle-suspect = investigate. Dispatches must
  PRE-AUTHORIZE checkpoint continuation ("do not pause for acknowledgment
  between tasks").
- **Sentinel watchers false-positive on echoed dispatch text.** Guards that
  work: exact-line regex `^[^A-Za-z0-9]*TAG-DONE[[:space:]]*$` + skip while
  "print exactly" visible in pane + git-side commit-count gates. My own
  amendment texts have ALSO tripped them ("When X-DONE prints…") — never
  put a bare sentinel in mid-run messages.
- **tmux ghost-vs-typed test:** `capture-pane -e`, dim SGR `\033[2m` wraps
  autosuggest ghosts; real typed input has no dim wrap. Presence-check
  before /clear on ANY lane; typed input = abort and tell superman.
- **Model identification:** transcripts under
  `~/.claude/projects/-Users-bbui-rb-ss-bridge-v2/*.jsonl` — match a lane
  by its TASK-OUTPUT content, not topic keywords (I once misidentified the
  executive's own session as a lane and killed a compliant Sonnet
  workflow); `"model":"..."` on the last assistant entries.
- **Auto-sync hook** sweeps ANY dirty tree at my turn ends into
  `auto-sync:` commits — it has swept delegates' mid-task work, my staged
  docs, and once put my laser-config diff inside a delegate's named commit.
  Content lands; attribution gets messy; NEVER rewrite. Commits under
  contention: patient retry loop; `index.lock` with fresh mtime = LIVE
  contention (delegates retry in loops), never delete it.
- **cwd sensitivity:** suite from parent dir vs repo root flips
  `test_loader_ships_calibrated_fixed_band_and_menu_ch9` (relative path in
  test). My canonical run: parent dir → expect the six-red form.
- **Live config** (`config/led_look_director.json`) still UN-MIRRORED:
  every round was built so absent keys = today's behavior; the two
  code-level changes that apply anyway are the AWR-156 strobe-gate rebuild
  + knob-#4 mapping (operator's explicit locked verdicts).
- **DIY workstream:** deferred, OPUS-ONLY by operator directive — one
  admin line max, see memory `project_diy_recreation_opus_only`; Fable
  never touches its content.
- **Flagged one-line operator vetoes outstanding:** strobe_red_white side B
  (=white), groove comet width 2.5, F2's NEUTRAL→small + damped-thin→small
  laser silences (~27% of drops), AWR-162 burn-down OFF pending haze
  session; pre-drop tease = parked morning item (never spec it).
- Remaining program after F2/F4: mirror (R5) → morning summary for Brandon
  (superman sends ship notices; my reports feed them).
