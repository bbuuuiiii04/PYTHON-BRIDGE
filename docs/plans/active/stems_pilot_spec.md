---
doc_status: current
truth_level: code-verified
last_verified_date: 2026-07-09
last_verified_commit: d2d684e
validation_scope: >
  Implementation spec for the STEMS PILOT (operator green-light 2026-07-09, verbatim: "i
  green light stems to be installed, as long as you believe this will massively improve
  lighting choreography"; executive accepted under the honest framing: the pilot proves
  separation quality on the operator's own masters first, full commitment only on pilot
  pass). Authored from the AWR-166 audit's P4 evaluation + its web research. Offline
  tooling only — zero bridge runtime change. Code tasks are implementable and testable
  WITHOUT any install; the install + pilot RUN are separately gated (operator disk
  cleanup + executive word). Nothing implemented yet.
---

# Codex Implementation Spec - STEMS PILOT: separation quality gate on the operator's masters (AWR-168)

The pilot answers ONE question before any full-library commitment: **does HTDemucs-class
4-stem separation hold up on this operator's brickwalled EDM masters well enough that
per-stem envelopes beat the existing v4 full-mix measures on the elements he named?** It
produces per-stem envelopes + a per-element separation-quality scorecard on 30–50 tracks
and evaluates a frozen pass/fail gate. It builds NO consumer classes — on PASS, consumer
work is specced later into the F4 texture layer (AWR-164, S-2 containment); on FAIL, the
lane closes and the disk is refunded.

## Part A - Context & Root Cause (verified; read, do not implement)

- **Why stems.** AWR-166 (`docs/research/spectral_upgrade_audit_2026_07_09.md` §1.2/§3-P4)
  [confirmed]: v4 has no vocal axis even in principle (`sustained_synth` counts vocals —
  AWR-147 semantic failure in both directions, calibration doc :229); HPSS `perc_full` is
  a transient/steady proxy, not a drums measure; `kick_prominence_flags` under-reads
  sidechain-pumped four-on-floor under walls (1/28 drop beats on Rock Ur World X Lights,
  redesign doc :1064-1069). Per-stem envelopes address all three directly.
- **Why a pilot, not a sweep.** Published separation quality (SDR) is measured on
  MUSDB-style mixes, not brickwalled EDM masters; no ground-truth stems exist for his
  library, so quality must be proven by proxy metrics + targeted operator moments on HIS
  tracks before ~716-track commitment [confirmed reasoning, AWR-166 P4].
- **Machine + runtime facts** [confirmed 2026-07-09 on this Mac]: Apple M2 base, 8 GB RAM,
  macOS 15, system Python 3.14.6, librosa 0.11/numpy 2.4/soundfile installed, **no
  torch**. Free disk **8.3 GB** (`df -h /`); operator hard floor: **4 GB free stands at
  all times**. torch 2.13.0 (2026-07-08) ships a cp314 macOS-arm64 wheel requiring
  macOS ≥ 14 — satisfied [confirmed via AWR-166 web research, pypi.org/project/torch].
  PyTorch MPS does not run Demucs reliably on Apple Silicon → **CPU-only** for the pilot;
  stock HTDemucs peaks ~7 GB RAM → **must run segmented** (`segment≈7.8 s`) on an 8 GB
  box [research-confirmed, github.com/facebookresearch/demucs/issues/498]. Extrapolated
  CPU throughput ~3–5 min per 4-min track → 50 tracks ≈ 2.5–4.5 h, overnight-safe
  [extrapolated — the pilot measures the real number; wall-clock is a planning input for
  the full sweep, NOT a pilot gate].
- **Model** [research-confirmed]: `htdemucs` single model (MIT code+weights, 4 stems
  drums/bass/vocals/other, ~80 MB weights). NOT `htdemucs_ft` (4× compute for no envelope
  benefit). Upstream `facebookresearch/demucs` is archived; the maintained line is the
  author's fork (`adefossez/demucs`); the PyPI `demucs` package is the install path
  [assumed: exact pinned version chosen at install time against the fork's latest release
  — record it in the pilot report].
- **Existing patterns to reuse** [confirmed at HEAD `d2d684e`]:
  `tools/spectral_sweep.py:32-59` (pyrekordbox track enumeration), `:76-80`
  (`read_anlz_drops` → beatgrid), `:69-71` (tools import bridge modules — this direction
  is allowed; the reverse is forbidden). `audio_spectral_features.BAND_RANGES`
  (`audio_spectral_features.py:39-55`), `_beat_spans` (`:438`), `_window_mean` (`:455`)
  — the beat-span math per-stem envelopes must match. v4 extraction lazy-imports heavy
  deps and returns None on absence (`:124-136`) — the stems tool mirrors this shape.
- **What the bridge consumes today** [confirmed, AWR-166 §1.1]: nothing stems-related.
  The pilot writes to its own namespace only; the v4 cache and all runtime behavior are
  untouched.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules

- **Out of scope / must not touch:** `audio_spectral_features.py`, `spectral_profile.py`,
  `spectral_cache.py`, `state_manager.py`, all runtime modules, all configs, the v4/v3
  cache directories, the live bridge, the F2/F4 implementation lanes' files. No consumer
  classes anywhere. No changes to `SPECTRAL_V4_CALIBRATION`.
- **No install, no download, no network in these tasks.** All code must import cleanly
  and pass its tests on the CURRENT machine (no torch). torch/demucs imports are lazy and
  only reached by the gated run path.
- **EXECUTION GATES (the run, not the code):** `pip install` into the venv, model-weight
  download, and any separation run happen ONLY after BOTH: (1) the operator's disk
  cleanup is done (8.3 GB free today is NOT cleared for a multi-GB install; the 4 GB hard
  floor stands), and (2) explicit executive word. The tool also self-enforces: refuse to
  start and abort between tracks if free disk < 4 GB (`shutil.disk_usage`), fail closed.
- **Venv lives OUTSIDE the repo:** `~/.venvs/rbss-stems/` — never inside the worktree
  (the auto-sync hook commits anything dirty; a venv in-repo is a repo hazard). No
  `.gitignore` change needed or wanted.
- **Error handling:** per-track failures (decode, separation, RAM) are logged with the
  track id + reason and SKIPPED (pilot continues, resumable); environment failures (disk
  floor, missing venv deps) ABORT the run with a clear message. No broad try/except
  around whole phases, no success-shaped fallbacks, no silent empty outputs.
- **Dirty worktree:** other overnight lanes commit into this tree concurrently. Never
  revert, stash, or clean anything you did not author; commit your own files by explicit
  path only; never use destructive git.

### Task 1 - `tools/stems_pilot_metrics.py`: pure measurement + gate module (no torch, no I/O)

Pure functions over arrays/dicts only (importable and testable with numpy alone):

1. `stem_beat_envelopes(power_frames, frame_times_ms, beatgrid_times_ms) -> dict`
   — per-beat and per-quarter-beat dB series for one stem's band-power frames, using
   beat-span semantics identical to v4 (arithmetic mean of linear power per span, then
   `10*log10(max(p, 1e-10))`, 0.1 dB rounding; reuse/replicate `_beat_spans` +
   `_window_mean` semantics — import them from `rb_ss_bridge_v2.audio_spectral_features`
   rather than re-implementing).
   Bands per stem (from `BAND_RANGES`): every stem: full; drums: `attack_low` (20–200)
   and `high` (2000–6000); bass: `sub` (20–60) and `bass` (60–150); vocals and other:
   `mid` (500–2000) and full only. Nothing more.
2. `reconstruction_delta_db(mix_full_frames, summed_stems_full_frames, ...) -> per-beat
   |delta| series` — sanity: stems must approximately sum to the mix.
3. `pump_visibility(bass_sub_quarters, drums_low_quarters) -> float` — sidechain metric:
   median within-beat dip depth (dB) of the bass-stem sub at drums-stem kick instants
   (slot-0-led beats only).
4. `ghost_margin_db(vocal_full_beats, instrumental_windows) -> float` — vocal-stem level
   inside operator-known instrumental windows relative to the track's vocal p95
   (more negative = cleaner).
5. `modulation_strength(stem_frames, frame_hop_s, beatgrid_times_ms, window) -> (rate_cpb,
   concentration)` — reuse the exact Goertzel grid semantics of
   `spectral_profile.lowmid_pulse_measure` (import `_goertzel_power` +
   `PULSE_RATE_GRID_CPB` from `rb_ss_bridge_v2.spectral_profile`) applied to a stem
   envelope, full 0.5–8.0 cyc/beat range, NO 2.5 gate.
6. `evaluate_gates(scorecard: dict, thresholds: dict) -> dict` — deterministic PASS /
   PARTIAL / FAIL per element + the overall pilot verdict per Part B Task 4's gate
   arithmetic. Pure dict-in/dict-out so the gate is unit-testable.

### Task 2 - `tools/stems_pilot.py`: the gated pilot runner (lazy heavy imports)

CLI: `--dry-run` (resolve corpus + print scope, no deps needed), `--limit N`,
`--snippets` (write 8-bar A/B stem wavs for flagged windows), `--report` (recompute
scorecard + gates from existing envelope JSONs, no separation).

1. **Corpus resolution.** Enumerate the library exactly like `tools/spectral_sweep.py`
   `_enumerate_tracks()`; resolve the pinned anchor list (below) by case-insensitive
   title substring match. Unresolved or ambiguous titles: log and list in the report —
   never guess. Fill to 30–50 total so every element has ≥3 tracks, extra picks selected
   from the BY GENRE playlists and recorded (title + element tag) in the report.
   **Pinned anchors (element → tracks, all operator-validated moments from the authority
   docs):**
   - *wobble bass:* capochino (1:01.7 formant wows), Girl$ (1:16.1, 2:25.6), You & Me
     (YDG FLIP — slow wub, `lowmid_pulse` 0/32), LUNCH (Billie Eilish — the labeled fast
     amplitude-wobble positive)
   - *sidechained tech-house sub under walls:* Rock Ur World X Lights (Knock2 vs Dabin —
     the 1/28 anchor) + ≥2 tech-house picks
   - *rolls:* Girl$ (0:46.3 snare buildup), Satisfaction ("hard rolling relentless")
   - *808s:* ONE CHANCE (2:36 trap monster), kidstopbreathing + ≥1 trap pick
   - *screeches:* DROP EM (Ray Volpe), STFU (Crankdat), GNARLY EMBERCORE
   - *distorted kicks / industrial claps-snares:* Pitch Mad Attak, Tremor, Age Of Love
     + hard-techno picks
   - *offbeat hats:* WHICH ONE (UKG intro), Bangarang (BRLLNT Edit — the syncopation
     signature) + tech-house picks
   - *vocal axis (from AWR-166 P4, the stems core promise):* the AWR-147 semantic pair —
     the 0.93 pad-wall track ("not really synth heavy") vs gritty-synth tracks he called
     synth-heavy — plus Can't Say Nah (chorus softness), I Kissed Girl (vocal over
     silence), Adventure of a Lifetime, Temperature
   Beatgrids via `read_anlz_drops` (same call sites as the sweep tool). Tracks without a
   usable grid: skip + log.
2. **Separation (gated path).** Lazy-import torch + demucs inside the run function only.
   Decode with the PROVEN corpus path: librosa/soundfile → stereo float32 @ 44.1 kHz
   (the v4 sweeps decoded 100% of gridded tracks with this stack; do NOT introduce
   ffmpeg/torchaudio decode). Feed the tensor to the demucs Python API
   (`demucs.pretrained.get_model("htdemucs")` + `demucs.apply.apply_model(...,
   split=True, segment≈7.8, overlap default)`) [assumed: exact API names re-verified
   against the installed demucs version at implementation — record the resolved call in
   the report]. `torch.set_num_threads(4)`. Stems stay IN MEMORY — never written to disk
   except `--snippets` clips. Log per-track wall-clock and peak RSS
   (`resource.getrusage(...).ru_maxrss` — stdlib, no psutil).
3. **Envelopes + metrics.** Compute band-power frames per stem (single STFT per stem,
   v4's `_SR`-equivalent settings at 44.1 kHz documented in-code), then call the Task 1
   pure functions. Write one JSON per track to
   `~/Library/Application Support/RBSS Bridge/stems_pilot/envelopes/<v4-style-key>.json`
   (reuse the v4 cache-key material: realpath+mtime+size+beatgrid fingerprint, imported
   from `rb_ss_bridge_v2.spectral_cache`). Resumable: skip tracks whose envelope JSON
   already exists.
4. **Scorecard + gate.** Aggregate per-element evidence into
   `.../stems_pilot/scorecard.json` + a human-readable `.../stems_pilot/report.md`
   (per element: PASS/PARTIAL/FAIL, numeric evidence, bleed notes; plus the operational
   stats: error rate, peak RSS, per-track minutes, disk used). Evaluate
   `evaluate_gates(...)` and print the verdict.

### Task 3 - environment doc block (inside `tools/stems_pilot.py` module docstring)

The exact gated install procedure, so the run needs no improvisation:
`python3 -m venv ~/.venvs/rbss-stems && ~/.venvs/rbss-stems/bin/pip install
--no-cache-dir torch demucs librosa soundfile` (torch 2.13+ cp314 arm64; pin versions at
install and record them). Disk budget to state in the docstring: torch+deps ≈ 1.5–2.5 GB
installed + htdemucs weights ~80 MB (downloaded to the demucs cache on first run)
[research-estimated — measure and record actuals]. Pre-flight: the tool refuses to run
below the 4 GB floor. Teardown on call-off: `rm -rf ~/.venvs/rbss-stems` + the demucs
weight cache — refund the disk.

### Task 4 - the frozen pass/fail gate (encode in `evaluate_gates`, document in the spec report)

Threshold discipline: all numeric thresholds below are **provisional through the first 5
pilot tracks** (tuning allowed, every change logged), then **FROZEN** and the full corpus
evaluated against the frozen values — no post-hoc tuning of the gate on the data it
judges.

**PROCEED to full-library sweep + F4-consumer speccing only if ALL of:**
1. **Operational:** ≥90% of resolved pilot tracks separate without error; peak RSS stays
   under 6.5 GB at segment 7.8 (halving the segment once is the only permitted retry).
2. **Reconstruction sanity:** median per-beat |sum-of-stems − mix| ≤ 1.5 dB on ≥90% of
   tracks (separation that can't re-sum is garbage on these masters).
3. **Sidechain:** pump visibly measured (`pump_visibility` ≥ 3 dB) on ≥2 of the ≥3
   sidechain anchors — the windows where v4 read 1/28.
4. **Vocal axis:** vocals-stem presence separates the AWR-147 semantic pair in the
   operator's stated direction, AND `ghost_margin_db` ≤ −12 dB on known-instrumental
   drop windows (bounded ghosting).
5. **Wobble:** `modulation_strength` reads a dominant rate at ≥2 of the 4 labeled wobble
   moments from the bass/other stems (no 2.5 cyc/beat gate).
6. **Named-element floor:** ≥6 of the 9 scored elements PASS, and NO operator-named
   element FAILs on all of its anchors (an element failing everywhere means the proxy
   does not survive brickwalled masters).

**CALL OFF (any one):** repeated RAM failure after the segment halving; reconstruction
sanity broken; vocal ghosting unbounded; fewer than 2 elements show a measurable
advantage over the existing v4 full-mix measures. On call-off: run Task 3 teardown, keep
the report + scorecard as the record, close the lane. Wall-clock is explicitly NOT a
gate; the measured per-track minutes × 716 becomes the full-sweep plan input (torch-CPU
nights vs the MLX port per AWR-166's research).

## Part C - Invariants That MUST Still Hold (live safety)

- Zero runtime behavior change: no bridge module imports any stems file (tools→bridge
  imports only, never the reverse); the 200 Hz push loop, ANLZ thread, and at-load v4
  extraction path are untouched.
- The v3/v4 spectral caches are never written, evicted, or re-keyed by this lane; the
  stems namespace is `.../RBSS Bridge/stems_pilot/` only.
- `SPECTRAL_V4_CALIBRATION`, identity axes, and every ear-validated constant unchanged —
  the 41 AWR-147 verdicts cannot be touched by a pilot that only reads audio and writes
  its own JSONs.
- The 4 GB disk hard floor is enforced by the tool itself, not just by procedure.
- No secrets, device IDs, or live config involved anywhere in this lane.

## Part D - Tests (`tests/test_stems_pilot_metrics.py`; no torch, no network, no audio files)

- `stem_beat_envelopes`: synthetic frames vs hand-computed per-beat/quarter-beat dB
  (including the empty-span nearest-frame fallback, matching v4 semantics).
- `reconstruction_delta_db`: identical arrays → 0; a 3 dB offset → 3.0.
- `pump_visibility`: constructed pumped-sub + kick-train arrays → expected dip; flat
  sustain → ~0.
- `ghost_margin_db`: constructed vocal envelope with quiet instrumental windows →
  expected negative margin.
- `modulation_strength`: synthetic 1.0 cyc/beat and 5.0 cyc/beat modulations → correct
  dominant rate on the un-gated grid (proves the slow range is readable).
- `evaluate_gates`: fixture scorecards for clean-PASS, each single-criterion FAIL, and
  the call-off combinations → exact expected verdicts.
- Disk-floor guard: `shutil.disk_usage` monkeypatched below/above the floor → refuse/run.
- Resumability: existing envelope JSON → track skipped (temp dir fixture).

## Part E - Acceptance (definition of done)

- [ ] Contract-first: extend `docs/agents/change_contracts.yml` `spectral_analysis`
      `code_globs` with `tools/stems_pilot.py` + `tools/stems_pilot_metrics.py` (and its
      `inspect` list with this spec) BEFORE code lands; then update every `docs_update`
      doc that contract names.
- [ ] Tasks 1–4 implemented exactly; all Part D tests green; full suite
      (`python3 -m unittest discover tests`) at the known-reds baseline (verify the
      baseline against the quiescent tree first — parallel lanes are committing).
- [ ] `--dry-run` works on THIS machine today (no torch): corpus resolves, unresolved
      anchors listed, scope printed. NO install performed, NO weights downloaded, NO
      separation attempted — the execution gates in Part B stand.
- [ ] Three hard checks green (`check_docs_metadata.py`, `check_agent_contracts.py`,
      `check_docs_drift.py`); registry row updated (this AWR), doc_index untouched (this
      spec is registered via the registry; add a doc_index row only if the doc_index
      convention for active specs requires it — mirror AWR-163's handling).
- [ ] Commits by explicit path only; never `git clean`; never revert parallel-lane files.

## When You Finish

Report: changed files, tests/checks run + results, the unresolved-anchor list from
`--dry-run`, and confirmation that no install/download/separation ran.

Plain-language operator summary (include verbatim): "The stems pilot code is built and
tested, but nothing is installed yet — that waits for your disk cleanup and the
executive's go. When it runs, it will split 30–50 of your own tracks into
drums/bass/vocals/other overnight, measure how cleanly each of the sounds you named
(sidechained subs, offbeat hats, claps, screeches, wobbles, 808s, rolls, distorted
kicks) comes out on your actual masters, and produce a scorecard with a hard pass/fail
verdict. Pass means we commit to the full library and the lights' texture layer gets
stem-level senses; fail means we delete it all, get the disk back, and keep what we
have. It cannot touch the live bridge, your existing analysis cache, or any of the
listening calibration you've already signed off — worst case is some lost overnight
compute. Honest expectation-setting: this pilot proves whether the separation is CLEAN
enough to build on; the 'massively improve the choreography' part comes only after the
F4 texture layer consumes these signals and you judge it in the room."

## Adversarial self-review (pre-handoff checklist item 9)

Attacked failure modes and how the spec prevents them: (a) *venv committed by auto-sync*
→ venv lives outside the repo by absolute rule; (b) *8 GB RAM swap-death mid-run* →
segmented inference pinned, single process, thread cap, peak-RSS logging, one permitted
segment-halving retry then operational FAIL — a gate criterion, not a crash loop;
(c) *disk exhaustion* → tool-enforced 4 GB floor checked at start and between tracks,
stems never hit disk; (d) *gate p-hacking* → thresholds frozen after the first 5 tracks,
tuning logged; (e) *title resolution guessing the wrong track* → unresolved anchors are
listed and skipped, never fuzzy-guessed silently; (f) *torch/demucs API drift vs the
research* → all heavy imports lazy, exact call re-verified at implementation and
recorded, code tests never touch them; (g) *decode failures on odd masters* → the decode
stack is the one already proven at 100% on this exact corpus by the v4 sweeps, and
per-track failures skip-and-log, they don't abort the pilot.
