---
doc_status: current
truth_level: plan
last_verified_commit: 5f5b658
last_verified_date: 2026-07-08
validation_scope: AWR-147 phase-1 task file for the Opus 4.8 tmux delegate (claude4); authorizes offline corpus sweep + a read-only calibration report tool + findings doc only; NO calibration-constant changes, NO runtime behavior changes, NO live process or hardware action
---

# AWR-147 Phase 1 — Spectral Calibration Expansion: Corpus Refresh + Calibration Report (Opus delegate tasks)

**Target model:** Claude Opus 4.8 · **Effort:** `xhigh` (set a large max-output budget)
**You are the tmux session `claude4`, working in `/Users/bbui/rb_ss_bridge_v2` on `main`.**
**Manager:** the Fable session (`claude3`) executing `docs/prompts/active/spectral_calibration_expansion_fable_prompt.md`. Your output feeds its tuning decision; it will adversarially review your numbers.

## Mission (one line)

Refresh the whole-library v4 spectral cache, then build and run a permanent, re-runnable calibration report tool that recomputes every corpus-scale calibration claim on the expanded library — distributions plus named counterexamples, honestly, with no per-track special-casing anywhere.

## Verified context (all confirmed by the manager this session at `5f5b658` — trust these, re-verify only if something contradicts them)

- Extractor: `audio_spectral_features.py` (frozen v3 compat `_extract_v3_features` :163-239 + v4 single-STFT `_extract_v4_measurements` :274-435). Never modify it in this phase.
- Calibration constants: `SPECTRAL_V4_CALIBRATION`, `spectral_profile.py:21-58`. Derived views (pure functions) in the same file: `bass_duty`, `bottom_gone_flags`, `empty_floor_runs`, `roll_flags`, `stab_flags`, `growl_flags`, `sustained_synth_flags`, `lowmid_pulse_flags`, `section_map`, `drop_window_vector` (:502-556), `pre_drop_gap_beats` (:176-192 — AND-rule based; the F2 design uses a different sub-only tolerant scan, see below). Never modify this file in this phase; IMPORT it.
- Cache: `~/Library/Application Support/RBSS Bridge/spectral_cache/v4/*.json` — 704 entries / 206 MB at kickoff. `spectral_cache.get_cached_v4` is the loader; keys = SHA of (filepath, beatgrid fingerprint).
- Sweep tool: `tools/spectral_sweep.py` — enumerates on-disk active Rekordbox tracks via pyrekordbox (`master.db`, `unlock=True`), resolves beatgrids via `read_anlz_drops`, extracts v4, writes cache. Dry-run today: **731 on-disk active tracks**. Prior sweep (2026-07-05, design doc §7): 686 scope / 666 ok / 19 no_grid / 1 extract_failed.
- Prior corpus evidence to re-verify at the new scale: `docs/research/spectral_audio_analysis_redesign.md` §6.5 + §7 (priors listed per metric below); F2 rule-pack audit: `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md` §3.1 (family classifier), §3.2 (tier), §4.1 (darkness pack), §5.1 (bass-forward) — audited 2026-07-07 on 3,936 drops from the shipped cache.
- BY GENRE calibration rule (contract `spectral_analysis`, `docs/agents/change_contracts.yml:605-640`): **calibration statistics and validation claims use BY GENRE playlist tracks only** — the folder node ID 666898931 (25 children incl. ODDMOB, TECH HOUSE, ISOXO, …), RAP excluded; the other "BY GENRE" node (13 children, HIP HOP/POP BANG/ACAPELLAS) is never used. Dedupe by ContentID across playlists.

## Hard rules (carried from the operator's standing rules — violating any is a failed run)

1. **Offline only.** Before the sweep and before any heavy run: `pgrep -f 'rb_ss_bridge_v2$' | wc -l` must be 0. If it is not, STOP and report — Brandon may be mixing. Never launch or restart the bridge. No frames or commands to any lighting hardware or cloud. Never edit live gitignored configs.
2. **Lane isolation.** Never modify `govee_*`, `led_*` (including `led_identity_v2.py` — you may READ it), `state_manager.py`, `beat_sync_engine.py`, `tools/led_pad*`. Other sessions own those files today.
3. **Phase-1 write allowlist** (nothing else gets written in the repo):
   - `docs/agents/change_contracts.yml` — extend the `spectral_analysis` contract only (see Task 2; re-read the file FRESH immediately before editing — parallel lanes edit it today).
   - `tools/spectral_calibration_report.py` (new)
   - `tests/test_spectral_calibration_report.py` (new)
   - `docs/research/spectral_calibration_expansion_2026_07_08.md` (new findings doc)
   - `docs/architecture/doc_index.md` — only if the hard checks demand the new doc be indexed (re-read fresh first).
   - Scratch: `/tmp/awr147/` for raw JSON dumps and logs.
4. **Git:** commit ONLY by explicit file paths (`git add <path> <path>` — never `-a`, never `add -A`); an auto-sync hook also commits in this worktree. Message prefix `AWR-147`. Never branch, never stash, never `git clean`, never force-push, never rewrite history.
5. **No per-track special-casing** anywhere — no title/ID matching in any rule or metric. Named tracks appear only as reported evidence.
6. **No calibration changes.** Do not edit any threshold, constant, or shipped cache entry. Phase 1 measures; the manager decides tuning separately.
7. **Claim discipline.** In the findings doc, label every claim confirmed / assumed / unknown. Numbers you computed = confirmed (cite the command); anything inferred = assumed; anything you could not compute = unknown with the reason.

## Task 0 — Preflight (5 min)

1. `pgrep -f 'rb_ss_bridge_v2$' | wc -l` → must be 0.
2. `git log --oneline -1` → record HEAD in the findings doc.
3. Snapshot the pre-sweep v4 cache key set: `ls ~/Library/Application\ Support/RBSS\ Bridge/spectral_cache/v4/ > /tmp/awr147/pre_sweep_keys.txt`. This defines the **NEW-track split** later (a track is "new" if its post-sweep cache key is absent from this snapshot).

## Task 1 — Corpus sweep refresh (~10–30 min wall)

Run exactly:

```bash
mkdir -p /tmp/awr147
caffeinate -i python3 tools/spectral_sweep.py --jobs 2 2>&1 | tee /tmp/awr147/sweep.log
```

Only uncached tracks extract (~27+); already-cached return instantly. Record the final JSON block (counts: ok / cached / no_anlz / no_grid / extract_failed, elapsed, v4_entries, cache MB) verbatim in the findings doc. Every failure category gets reported honestly with its count; list the titles of `extract_failed` tracks individually (there should be ≈1, the known undecodable GRiZ flac — more means something changed worth flagging).

## Task 2 — Contract extension + the report tool

**Contract first:** re-read `docs/agents/change_contracts.yml` fresh, then extend `spectral_analysis`: add `tools/spectral_calibration_report.py` to `code_globs`, and add `docs/research/spectral_calibration_expansion_2026_07_08.md` to `inspect`. Commit this together with the tool (explicit paths) so `check_agent_contracts.py` never sees a contract pointing at a missing file.

**Then build `tools/spectral_calibration_report.py`** — one file, stdlib + pyrekordbox only (same DB access pattern as `tools/spectral_sweep.py:32-59`), read-only everywhere (never writes cache entries, never touches the DB/ANLZ/audio beyond reads). It imports `spectral_profile` / `spectral_cache` / `anlz_reader` rather than duplicating math, EXCEPT the F2 rules below, which are not in the codebase yet (design-only) and are implemented inside the report tool from these pinned formulas:

- **F2 pre-drop scan + darkness decision** (`LIGHTING_ENGINE_V2_DESIGN.md` §4.1, verbatim): floor notion is sub-only `gone[i] = sub_db[i] < 5.0`; tolerant scan finds newest gone beat `e` with `D−4 ≤ e ≤ D−1`, walks back to run start, `raw_gap = e − start + 1`; busy-build kill when run `bass_duty` (fraction of run beats with `bass_db ≥ 8.0`) `> 0.85`; blackout `gap = min(raw_gap, 16)`, floor-returned abort at 2nd consecutive floor-present beat in-window; relative dip `dip_score(b) = (med(full_db[b−16..b−1]) − full_db[b]) + 0.25·clip(med(sub[b−16..b−1]) − sub_db[b], 0, 8)` fires ≥ 4.0 with `sub_db[b] ≥ 5`, cap 4 beats; snap flick otherwise, upgraded to 1-beat when `growl_band_db[D−1] ≤ growl_band_db[D−2] − 5.0`.
- **F2 family classifier** (§3.1, verbatim — inputs `drop_window_vector(v4, D, width=16)` with `pre_gap` REPLACED by the tolerant sub-only `raw_gap` above, and `lift = full_db − loudness_ref_db`):
  `coverage < 8 → NEUTRAL`; `lift < −7 and attack_low_p90 < 5 → NEUTRAL`; `bpm ≥ 146 and air_db < 0 and sub_db ≥ 24 and onset_density_mh ≤ 3.2 → COMET`; `growl_flatness ≥ 0.27 and (high_db ≥ 4 or mid_db ≥ 8) → WALL`; `sub_db ≥ 26 and onset_density_mh ≤ 2.2 and pre_gap ≥ 1 → WALL`; `onset_density_mh ≥ 3.4 and high_db ≥ 5 → WALL`; `116 ≤ bpm ≤ 144 and low_swing_db ≥ 10.5 and attack_low_p90 ≥ 7 → HOUSE`; `116 ≤ bpm ≤ 144 and growl_flatness < 0.24 and sub_db ≥ 20 and low_swing_db < 10.5 and bass_db ≥ 14 → HOUSE`; else NEUTRAL. Rule order matters; first match wins.
- **F2 violence/tier** (§3.2, verbatim): `violence = 0.30·clip((full_db − 8)/10) + 0.20·clip((lift + 4)/5) + 0.25·clip(attack_low_p90/16) + 0.15·clip(onset_density_mh/4) + 0.10·clip(pre_gap/8)` (clip to [0,1]); tier 3 ≥ 0.698, tier 2 ≥ 0.616, else tier 1.
- **F2 bass-forward** (§5.1, verbatim): within the 16-beat window, `ceil = p90(growl_band_db[W])`; `bass_forward(b) = growl_band_db[b] ≥ ceil − 3.0 and growl_band_db[b] ≥ 18.0 and attack_low_db[b] < 9.0`; `kick_driving(b) = attack_low_db[b] ≥ 9.0`.

Drop markers come from `read_anlz_drops(anlz_abs).drop_beat_indices` — markers are ground truth; the tool never invents or times events.

**CLI:** `python3 tools/spectral_calibration_report.py --json /tmp/awr147/report.json --markdown /tmp/awr147/report.md [--limit N]`. It enumerates tracks like the sweep, loads each track's v4 entry once, computes all metrics in one pass, and emits: (a) the aggregate report, (b) a per-drop record array (track title, playlist(s), drop beat, window vector, family, violence, tier, darkness decision, bass-forward rate) in the JSON so the manager can spot-verify any number.

**Splits reported for every metric:** `library` (all on-disk tracks with v4 entries), `by_genre` (the calibration set — the only split used for calibration *claims*), `new` (tracks not in `/tmp/awr147/pre_sweep_keys.txt` — the held-out drift check).

**Metrics with their priors** (each row of the report shows: prior → new by_genre value → new-split value → drift verdict `holds / drifts / broken`):

| # | Metric | Prior (2026-07-05/07) |
|---|---|---|
| 1 | sub_db beats within 8 dB below / above the 5.0 threshold (+ 2-dB histogram −40..40 for valley shape) | 4.7% / 5.7% (genuine density valley) |
| 2 | full_db corpus p1 vs true-silence −30 | p1 = −26 (threshold below p1) |
| 3 | corpus percentile rank of growl_flatness 0.25 | ≈ p78 |
| 4 | onset_density_midhigh p90 vs roll threshold 3.0 | threshold > p90 (rolls rare) |
| 5 | loudness_ref_db p5–p95 spread | 15.3–19.3 dB |
| 6 | identity axes even/odd-beat Spearman (grit/punch/bass/drama), by_genre only | 0.929 / 0.935 / 0.967 / 0.928; gate = v3 band 0.902–0.957 |
| 7 | per-track bass_duty p5/p95 (observation only — `led_identity_v2.py:4` pins anchors 0.5856/0.9688; that file is another lane's, report drift, change nothing) | 0.5856 / 0.9688 |
| 8 | family distribution over all drops (+ per-playlist table) | HOUSE 41% / WALL 21% / COMET 11% / NEUTRAL 27% (n=3,936) |
| 9 | violence p55/p85 vs frozen tier cuts 0.616/0.698; tier counts | p55=0.616, p85=0.698; tiers 2159/1176/601 |
| 10 | darkness decisions: blackout/dip/snap/perc-flick/abort counts; dark-beats histogram; busy-build kills; runs with duty in [0.80,0.90] (the 0.85-cliff mass) | 1320 / 1145 / 1366 / 105 / 150; 219 at 16-cap; 48 zero-dark |
| 11 | bass-forward: % of drop windows with ≥1 B beat; per-window B-rate distribution; all-B and all-K degenerate window counts | no pinned prior — first corpus-wide measurement; CSN drop 128 anchor pattern `BKBBBKBBBKBBBKBB` must reproduce |
| 12 | lowmid_pulse per-track firing rate distribution + top-10 firing tracks | experimental grade; known: wobble + rolls + chugs + sirens all fire it |

**Counterexamples (named, with measured values — the manager needs concrete tracks, not vibes):** for each of these, list up to 10 tracks/drops: (i) NEUTRAL-classified drops with violence ≥ 0.698; (ii) tier-3 drops in DEEP HOUSE/GROOVE HOUSE/UKG; (iii) blackout runs with raw_gap ≥ 40 (cap distortion size); (iv) busy-kill near-misses (duty 0.80–0.90); (v) tracks with any identity axis at exact 0.0 or 1.0 (saturation); (vi) NEW tracks whose family/tier/darkness reads implausible on its face (your judgment, stated).

**Test (`tests/test_spectral_calibration_report.py`):** table-driven, synthetic series only, no cache/DB/audio dependency — hand-computed expectations for: the tolerant sub-only scan + busy-kill + abort + dip + perc-flick branches; the family classifier first-match ordering; violence/tier arithmetic; bass-forward flags. Follow the existing seam style in `tests/test_spectral_profile.py`. No fixtures from the real library.

## Task 3 — Run the report + write the findings doc

Run the tool over the full corpus (`--json` + `--markdown`), then write `docs/research/spectral_calibration_expansion_2026_07_08.md`: frontmatter header (doc_status current; truth_level measured; validation_scope "offline corpus analysis only, no behavior change"), the sweep results verbatim, the metric table with priors and drift verdicts, per-playlist family table, all counterexample lists, the NEW-split section, and a short honest "what this does NOT show" section (no listening validation; F2 rules are design-only; hardware unvalidated). Claim labels throughout.

## Task 4 — Verify + commit

1. `python3 -m unittest tests.test_spectral_calibration_report -v` then the focused spectral tests (`tests.test_spectral_profile`, `tests.test_spectral_cache`, `tests.test_audio_spectral_features`), then the full suite `python3 -m unittest discover tests` (known pre-existing environmental reds in untouched subsystems are acceptable — list them, verify they are the known five from the AWR-145 registry row, and flag anything new).
2. The three hard checks: `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`. All must pass.
3. Commits (explicit paths, `AWR-147` prefix): one for contract+tool+test, one for the findings doc (+ doc_index row only if the checks required it).
4. Final message in your session: paste the metric table with drift verdicts, the counterexample counts, sweep counts, test/check results, and the exact commit hashes. The manager reads your pane; end with the literal line `AWR147-PHASE1-DONE` (or `AWR147-PHASE1-BLOCKED: <reason>` if stopped).

## Success criteria (falsifiable)

- Sweep completed; coverage is a number; every failure category counted; extract-failure titles named.
- Report tool runs end-to-end on the real corpus in one command; per-drop records exported; re-runnable by anyone later.
- Every metric row has prior → new → verdict; every counterexample is a named track with values.
- No file outside the write allowlist modified (check `git status` before each commit); no calibration constant touched; suite green minus the known reds; three hard checks pass.
- Findings doc readable by the manager cold, claims labeled.
