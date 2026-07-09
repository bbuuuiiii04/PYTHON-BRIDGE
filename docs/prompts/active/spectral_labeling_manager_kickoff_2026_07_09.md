---
doc_status: current
truth_level: handoff-report
last_verified_commit: ce235df
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff for the SPECTRAL LABELING manager (Fable/MAX effort, tmux `labels`,
  operator-attended, spawned final Fable evening 2026-07-09). The operator will list
  tracks + timestamps + plain-language descriptions to strengthen the spectral audio
  analysis; this lane converts every statement into verified, durable labeled data.
  Read-only on runtime; paper + measurement only.
---

# Spectral labeling session — manager kickoff (2026-07-09 evening)

You are the **spectral labeling manager** (Fable, MAX effort). Brandon attends and
drives: he lists tracks, timestamps, and describes what he hears and what the room
should do. Your job: turn every sentence of ear-truth into PERMANENT, verified,
machine-usable data before Fable access ends at 20:00. He is simultaneously running
the stems labeling round in the `stems` session — stay coordinated, never duplicate.

## The loop (per track he names)
1. Resolve the track in the Rekordbox DB (read-only; match his naming loosely, echo
   the exact title back once). Load the v4 cache + markers via the real seams:
   `read_anlz_drops(anlz_abs)` → grid + drops/buildups; `spectral_cache.get_cached_v4`;
   `led_identity_v2.identity_scores`/`assign_zone`; `lighting_moments_v2.build_track_plan`
   (the executive's derivation pattern from today — see
   `docs/prompts/active/led_spectral_tuning_kickoff_2026_07_09.md` context and the
   AWR-176 spec's named checks for examples).
2. For each timestamp he gives: convert mm:ss → beat via the beatgrid, then MEASURE
   what the analysis sees there (band series windows, perc/onset, growl amplitude,
   tier/family/darkness the plan assigns, zone/scores) and compare against his words.
3. Record ONE entry per statement in the corpus (format below): his words VERBATIM,
   the measured values, and a gap classification:
   `AGREES` (analysis sees it) / `PARTIAL` / `BLIND` (analysis cannot express it —
   name the missing dimension) / `MISREAD` (analysis contradicts his ear).
4. Tell him in one plain sentence what the system currently sees there — then next.
   Keep his flow: one track at a time, tiny asks, never re-ask what he already said.

## The corpus (the deliverable — durable, dual format)
- `docs/research/operator_track_labels_2026_07_09.md` — human-readable, grouped per
  track, doc header per repo rules, registered (registry row: take the NEXT free AWR
  id — re-check the current max immediately before writing, parallel lanes race).
- `local/labels/operator_track_labels_2026_07_09.jsonl` — one JSON object per entry:
  {track, title_exact, mmss, beat, his_words, measured: {...}, classification,
  systems: [f2|laser|led|stems|p1], notes}. Machine layer for future calibration.
- Commit explicit-path as you go (every few tracks, not one big batch at the end —
  the session may be cut off at 20:00).

## Routing rules (stay in your lane)
- BEHAVIOR verdicts he speaks ("lasers should…", "this blackout is wrong") → relay
  to the executive seat (tmux `superman3`; the seat may hand off to `superman4`
  mid-session — route to whichever exists, superman4 wins if both) and RECORD in the
  corpus. You never change configs, code, or the live bridge.
- STEMS-relevant labels (vocal-free windows, wobble moments, sidechain tracks) →
  tag `stems` in the corpus AND relay the entry to the `stems` session so his stems
  scorecard labels stay complete (that session owns the stems re-score).
- P1 context: `growl_centroid_frames` exists for FRESH extractions only — the
  library backfill runs after 20:00, so growl labels tonight are measured on
  amplitude and become the P1 acceptance set tomorrow. Say so plainly when relevant.

## Rules
- Read-only everywhere except your two corpus files + registry row. No bridge
  contact, no config edits, no full test suites (machine is under live load).
- Sub-agents (Opus/Sonnet) via tools/agents/ for measurement grinding if he lists
  faster than you measure — never block his flow on your tooling.
- Chat is the surface: plain English, mechanism kept, no jargon walls, no documents
  he has to open.
- At session end (or 19:45, whichever first): commit everything, print a one-line
  count (tracks/entries/classifications), signal file per convention (TAG LABELS).
