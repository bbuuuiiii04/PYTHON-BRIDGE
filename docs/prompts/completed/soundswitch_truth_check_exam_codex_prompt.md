---
doc_status: active-prompt
truth_level: current-commit-and-command-output-grounded
last_verified_commit: 5bb3a5b
last_verified_date: 2026-07-02
validation_scope: Codex operational prompt to orchestrate the Art-Net U0/U1 truth-check capture
  exam (SoundSwitch as ground truth, bridge pack shadow on U1). No implementation authority; a
  defect found during the exam is evidence to report, never something to patch mid-exam.
---

# Codex Prompt — SoundSwitch Truth-Check Final Exam (U0/U1 capture)

**One-line:** orchestrate the live side-by-side exam that measures whether the bridge lighting
pack's DMX decisions are identical to SoundSwitch's real output in the time domain — timing,
autoloop cycling, rewinds, BPM changes, transitions — the only dimensions the byte-proven render
model (commit `5bb3a5b`, 261/261 + A5 16/16) does not already cover.

**Roles.** Codex pre-flights, arms the environment, runs the comparator, analyzes, reports, and
disarms. **The operator performs every live action** (bridge start via menubar, opening
SoundSwitch, all DJing). Codex never starts/stops the bridge, never clicks SoundSwitch, never
opens Enttec/serial, never sends MIDI/DMX, and **never edits code during the exam** — a defect
found live is captured and reported for a separate fix cycle.

## Grounded facts (verified at 5bb3a5b — do not re-derive)

- Truth-check env (read in `artnet_truth.py:25-30`): `RBSS_ARTNET_TRUTH_CHECK=1` +
  `RBSS_ARTNET_UNIVERSE=1` enable the U1 shadow path; sidecar default
  `/tmp/rbss_artnet_truth_frames.jsonl` (override: `RBSS_ARTNET_TRUTH_SIDECAR`). While
  SoundSwitch/OS2L is connected the production pack lane submits software ZERO and the same
  render decision is enqueued to U1 with sidecar metadata — SS drives the real output on U0.
- Comparator: `python3 tools/artnet_compare.py` (repo root). Defaults: `--ss-universe 0
  --bridge-universe 1 --bridge-status /tmp/rb_ss_bridge_v2_status.json --tolerance-ms 5.0
  --timeout-s 120`. `--self-check` passes at HEAD (39 synthetic traces). It observes both streams
  LIVE, requires fresh matching `truth_check.run_id` from bridge status and the sidecar header,
  ordered nearest-neighbor U0/U1 byte matches within tolerance, strict sidecar agreement for
  every captured U1 packet, and coverage only from matched rows. Read the module docstring before
  choosing `--timeout-s` for a full session run.
- Bridge launch: menubar only → `/Users/bbui/ss_bridge_watcher.sh` (`RBSS_BRIDGE_MANUAL=1`).
  Env additions go in the hard-coded block near line 85 of that script. After any start:
  `pgrep -f rb_ss_bridge_v2 | wc -l` must be exactly `1`.
- Canonical pack: `local/soundswitch/rbss_canonical_pack` (gitignored). Current fresh-export
  active lanes: `{algorithm_generalized: 67, oracle_proven: 16, unverified_parity: 0}`.
- Known-in-advance, expected differences (report, do not hide, do not fail silently):
  1. Track-change handoff: the pack zeroes for ~1-2 driver ticks at a deck/track switch; SS holds
     the outgoing show's last frame ~50-240 ms. Frames in that window may mismatch by design.
  2. `9947c65e` carries one genuine `stale_source_edit` (its file differs from what SS plays at
     one boundary). If it is exercised, that boundary may mismatch — a known, named residual.

## Part 1 — Pre-flight (Codex, offline)

1. Repo at/after `5bb3a5b`; `python3 tools/artnet_compare.py --self-check` → PASS.
2. Operator saves + quits SoundSwitch (standing rule), then Codex re-publishes the canonical pack
   (`python3 tools/export_soundswitch_pack.py --publish-canonical --result-json
   /tmp/rbss_publish.json`) and confirms `ok: true` and zero active `unverified_parity`.
3. Arm the env: add `RBSS_ARTNET_TRUTH_CHECK=1` and `RBSS_ARTNET_UNIVERSE=1` to the
   `ss_bridge_watcher.sh` env block. Record the exact edit for later removal.
4. Print the operator run-sheet (Part 2 checklist) in chat and wait for the operator.

## Part 2 — Live run (OPERATOR actions; Codex monitors)

Start order: bridge via menubar → verify one process → open SoundSwitch (confirm OS2L
connected) → Codex starts the comparator with `--pack-path local/soundswitch/rbss_canonical_pack
--sidecar /tmp/rbss_artnet_truth_frames.jsonl --report-out /tmp/rbss_truth_exam_report.json` and
a `--timeout-s` sized for the whole session. Keep `--tolerance-ms` at the 5.0 default — never
loosen it to pass.

Scenario checklist (covers every dimension of the operator's greenlight statement):

- [ ] **Scripted tracks (≥3), MUST include:** "New Sky (Odd Mob Remix)" through both strobe
      sections (0:38-1:00 and 2:40-3:01) and "TITANIUM (TWINSICK REMIX)" through 1:30-2:40 —
      the exact former divergence sites — plus one more scripted track played deep (5+ min
      elapsed) for timeline drift.
- [ ] **Playback edges:** pause mid-scripted, hold ≥3 s, resume; stop and restart; load a track
      and play from mid-track.
- [ ] **Rewind/seek:** seek backwards ≥30 s mid-scripted; seek forward past a cue boundary.
- [ ] **BPM adjustments:** pitch fader moves (both directions) during a scripted track AND while
      an autoloop is held.
- [ ] **Autoloops:** fire drop looks across the bank (ch1 notes 96-111, including the new
      52-55 loops); hold ≥2 loops through at least one full 32-beat cycle (wrap coverage);
      trigger groove/breakdown/buildup (notes 32/1/64 — the dark loops).
- [ ] **Static looks:** hold + release Stream Deck static looks over scripted AND over an
      autoloop; overlapping holds; blackout (note 0) via smart-drop pre-drop and via breakdown;
      manual blackout press/toggle from the controller.
- [ ] **Transitions / active deck:** ≥3 deck-to-deck transitions (scripted→scripted and
      scripted→autoloop-track) with real crossfades and active-deck switches.

## Part 3 — Analysis + report (Codex)

1. Comparator verdict + the full coverage ledger (scripted timeline events/rapid pairs, autoloop
   visible/authored-dark phase buckets per loop cycle, static/blackout overlay-release
   combinations, active-deck/mode transition directions). Coverage gaps = the exam is NOT passed;
   name what's missing and which scenario re-run would close it.
2. Every settled-frame mismatch reported verbatim: elapsed/mono, universes, expected vs observed
   bytes, channel diffs, and whether it falls in a known-expected window (handoff blip, 9947
   stale edit) or is a NEW divergence. New divergences are blockers: capture evidence, stop, and
   report — do not patch.
3. Final statement mapping: for each dimension in the operator's greenlight statement
   (autoloops, scripted, statics, cues, output values, timeline, timing, cycling, rewinds,
   playback, BPM, transitions, active deck, MIDI), state MEASURED-PASS / MEASURED-FAIL /
   NOT-COVERED with the evidence line.
4. Disarm: remove the two env lines from `ss_bridge_watcher.sh`, operator restarts the bridge
   clean (verify one process), delete nothing from the capture/sidecar/report — they are the
   exam evidence. Update `docs/plans/active/soundswitch_exporter_remaining_work.md`'s exam
   checklist item with the dated outcome and run the three hard docs checks before committing.

**Pass = comparator PASS + full coverage + zero unexplained mismatches.** Only then does the
operator's greenlight statement become assertable (software/wire level; physical fixture
validation remains a separate, operator-visual step).
