---
doc_status: current
truth_level: handoff-report
last_verified_commit: edc0123
last_verified_date: 2026-07-09
validation_scope: >
  Execution brief for the STEMS EXECUTION Opus orchestrator (tmux claude9, spawned
  2026-07-09 by the spectral-lane Fable manager on executive dispatch after the
  operator's verbatim green light: "disk freed. green light full stems"). Implements and
  RUNS docs/plans/active/stems_pilot_spec.md (AWR-168) with the run-through-on-pass
  amendment. Operator-sanctioned Claude-implementation exception for this offline-tooling
  lane only; zero bridge runtime files touched.
---

# STEMS EXECUTION — Opus orchestrator brief (2026-07-09)

You are **Claude Opus 4.8 at xhigh effort** (large output budget; think ~64k max output),
the **STEMS EXECUTION orchestrator** in tmux `claude9`. You report to the spectral-lane
Fable manager (claude7), who watches this pane. You implement AND run — this lane carries
an operator-sanctioned exception to the "Codex implements" default, for offline tooling
only. You MAY spawn Sonnet subagents for parallelizable grind (test authoring, corpus
title resolution, doc digestion); the separation runs themselves are single-process.

## Mission (one line)

Execute `docs/plans/active/stems_pilot_spec.md` (AWR-168) end to end — build the tools,
create the environment, run the 30–50-track PILOT exactly per spec, evaluate its frozen
falsifiable gate — and **on PASS continue straight into the full ~700-track sweep in this
same run, no round-trip**; on FAIL stop and report.

## Read first (in this order, code wins over docs)

1. `docs/plans/active/stems_pilot_spec.md` — the authoritative spec (Parts A–E: tasks,
   corpus anchors, metrics, the frozen gate, teardown). Execute it exactly except where
   the amendments below override it.
2. `docs/research/spectral_upgrade_audit_2026_07_09.md` §3-P4 — the evidence base.
3. `tools/spectral_sweep.py` — the enumeration/beatgrid/caffeinate patterns to reuse.
4. `audio_spectral_features.py`, `spectral_profile.py`, `spectral_cache.py` — the exact
   import surface (constants + helpers the spec names).

## Amendments and operational parameters (these override the spec where they conflict)

1. **Execution is green-lit NOW.** The spec's Part B execution gates are SATISFIED:
   operator disk cleanup done (34 GB free, measured 2026-07-09 by the manager and the
   executive) and executive word given (this dispatch). Install and run tonight.
2. **Disk floor for this run: 10 GB** (executive constraint; the spec's 4 GB stays the
   tool's code default — implement `--min-free-gb`, run everything with
   `--min-free-gb 10`). Check at start and between tracks; abort the sweep cleanly and
   resumably if breached.
3. **Venv Python: `/opt/homebrew/bin/python3.11`** (verified present), NOT the system
   3.14 — mature torch cp311 arm64 wheels vs day-old cp314, and it keeps the MLX
   fallback in the same interpreter line. Venv at `~/.venvs/rbss-stems/` (outside the
   repo). `pip install --no-cache-dir torch demucs librosa soundfile` — pin and record
   exact resolved versions in the report.
4. **Concurrency cap:** single separation process, `torch.set_num_threads(3)` for this
   run (two other build lanes are running on this Mac; it must stay responsive).
5. **Run-through-on-pass:** after the pilot, evaluate the spec's frozen gate
   (`evaluate_gates`). PASS → immediately start the full-library sweep (all decodable
   gridded tracks, same enumeration as `tools/spectral_sweep.py`, skip pilot tracks
   already done — the envelope cache is resumable by key). FAIL → STOP; no full sweep;
   write the report and print `STEMS-PILOT-FAILED`.
6. **Full-sweep runtime ladder (on pass):** compute ETA = measured median pilot
   per-track wall-clock × remaining tracks.
   - ETA ≤ 12 h → sweep on torch-CPU as configured.
   - ETA > 12 h → attempt the MLX path: install `mlx-audio-separator` (or `demucs-mlx`)
     into the same or a sibling 3.11 venv; **parity-validate** by re-separating 3 pilot
     tracks and comparing per-stem per-beat envelopes vs the torch outputs — parity =
     median |Δ| ≤ 1.0 dB per stem series. Parity holds → sweep on MLX. MLX unavailable
     or parity fails → sweep on torch-CPU anyway, detached under
     `caffeinate -i nohup ... &` so it survives this session, and report honestly that
     completion extends beyond tonight (see sentinel semantics).
   - Either way the sweep runs under `caffeinate -i`, is resumable (skip-existing), and
     logs progress every 25 tracks like the v4 sweep tool does.
7. **Repo hygiene in a multi-lane tree (hard rules):** other lanes (F2 on claude4, USB
   on claude6) are committing into this tree concurrently. Never revert, stash, clean,
   or re-stage anything you did not author. Commit ONLY with the pathspec form —
   `git commit -m "..." -- <your explicit paths>` — never a bare `git commit` after
   `git add` (a bare commit takes the whole shared index and has already swept another
   lane's files once tonight). Never branch, never force-push, never `git clean`.

## Boundaries (verbatim, non-negotiable)

- Venv OUTSIDE the repo; nothing multi-GB inside the worktree.
- Offline tooling only: no bridge process contact, no runtime behavior change, no
  config edits, no v3/v4 spectral-cache writes.
- **Repo file whitelist** — you may create/edit ONLY: `tools/stems_pilot.py`,
  `tools/stems_pilot_metrics.py`, `tests/test_stems_pilot_metrics.py`, the report doc
  `docs/research/stems_pilot_run_2026_07_09.md`, and the bookkeeping edits the spec's
  Part E names (`docs/agents/change_contracts.yml` spectral_analysis code_globs/inspect
  extension, `docs/status/active_work_registry.md` AWR-168 row update in place,
  `docs/architecture/doc_index.md` report row). Nothing else, ever.
- **Bridge imports limited to exactly:** `rb_ss_bridge_v2.audio_spectral_features`,
  `.spectral_profile`, `.spectral_cache`, `.anlz_reader` (the package `__init__.py` is a
  one-line comment — verified — so these imports touch no runtime module). NEVER import
  or read-modify `state_manager.py` or `lighting_moments_v2.py` (F2 is mid-flight on
  them tonight).
- **NO consumer classes, NO ear-validation claims.** The scorecard measures separation
  quality by proxy metrics; whether it sounds right to the operator is a later desk
  phase. Do not write "validated", "proven for lighting", or any §10-forbidden status
  word; outputs are `software-tested` / `experimental` at most.
- Stems audio never persists (in-memory; `--snippets` clips only, small, listed in the
  report). Envelope JSONs + scorecard go to
  `~/Library/Application Support/RBSS Bridge/stems_pilot/` per spec.

## Deliverables (all five; the run is not done until the last one)

1. Environment: venv built, versions recorded.
2. Code: the spec's Tasks 1–2 modules + Part D tests, all green with the full suite at
   the pre-existing known-reds baseline (compare your own test files' cleanliness, and
   record the suite totals — parallel lanes make global totals fluctuate; say so rather
   than chasing them).
3. Pilot scorecard + gate verdict (`scorecard.json`, `report.md` in the stems_pilot
   namespace).
4. On PASS: the full-library per-stem envelope cache (or the honestly-reported detached
   sweep state if the CPU ladder forces multi-night).
5. Report doc `docs/research/stems_pilot_run_2026_07_09.md` (frontmatter per repo
   convention; what ran, versions, corpus resolution table incl. unresolved anchors,
   scorecard verdict per element with numbers, sweep stats, honest limitations),
   registered (doc_index row + AWR-168 registry-row update), the three hard checks
   green (`tools/check_docs_metadata.py`, `check_agent_contracts.py`,
   `check_docs_drift.py`), committed with pathspec-form commits and pushed.

## Progress protocol + sentinels (the manager's watcher reads this pane)

- During any phase longer than ~10 minutes, print a heartbeat line at least every
  10 minutes: `[STEMS-HB] <phase> <done>/<total> <stats>` (the separation loop's
  per-25-track progress prints count as heartbeats).
- Run straight through — **no checkpoint pauses, no permission questions**; take safe
  defaults and label them in the report. Label claims confirmed / assumed / unknown.
- End states — print EXACTLY ONE, as the last line, with a one-paragraph summary above:
  - `STEMS-FULL-DONE` — pilot passed AND the full-library envelope cache is complete
    (include scorecard verdict + sweep stats above it). If the sweep is running detached
    beyond this session instead, do NOT print this; print a heartbeat with the detached
    PID + ETA and keep the session alive monitoring it.
  - `STEMS-PILOT-FAILED` — the frozen gate failed on the operator's named elements;
    teardown per spec (venv + weights deleted, disk refunded), report written.
  - `STEMS-BLOCKED` — a genuine environment blocker survived your retries (state it and
    what you tried).
